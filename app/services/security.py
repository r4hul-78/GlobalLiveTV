"""
Security and SSRF Protection Service
Validates external URLs to prevent SSRF and prohibited network access.
"""
import ipaddress
import socket
import urllib.parse
from typing import Tuple


PROHIBITED_HOST_PATTERNS = {
    "localhost",
    "127.0.0.1",
    "::1",
    "0.0.0.0",
    "metadata.google.internal",
    "169.254.169.254",  # Cloud metadata service
}


def is_safe_url(url: str, resolve_dns: bool = True) -> Tuple[bool, str]:
    """
    Validate external URL against SSRF, internal network access, and unsafe schemes.
    
    Args:
        url: The candidate URL string.
        resolve_dns: Whether to perform DNS resolution to inspect resolved IP addresses.

    Returns:
        (is_safe: bool, reason: str)
    """
    if not url or not isinstance(url, str):
        return False, "URL is empty or not a string"

    url = url.strip()
    if len(url) > 2048:
        return False, "URL exceeds maximum allowed length of 2048 characters"

    try:
        parsed = urllib.parse.urlparse(url)
    except Exception as exc:
        return False, f"Malformed URL syntax: {str(exc)}"

    # Scheme validation: Only http and https allowed
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        return False, f"Unsupported URL scheme '{scheme}'. Only HTTP and HTTPS are permitted."

    hostname = parsed.hostname
    if not hostname:
        return False, "URL is missing a valid hostname"

    hostname_lower = hostname.lower()

    # Block explicit prohibited hostnames
    if hostname_lower in PROHIBITED_HOST_PATTERNS or hostname_lower.endswith((".local", ".internal", ".lan")):
        return False, f"Host '{hostname}' is a prohibited local/internal destination"

    # Check if hostname itself is directly a numeric IP
    try:
        ip = ipaddress.ip_address(hostname_lower)
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False, f"Direct IP '{ip}' is in a prohibited or private range"
    except ValueError:
        # Not a raw IP literal, it is a domain name
        pass

    if resolve_dns:
        try:
            # Resolve DNS records for hostname (port 80 fallback)
            addr_info = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
            if not addr_info:
                return False, f"DNS resolution yielded no addresses for '{hostname}'"

            for entry in addr_info:
                sockaddr = entry[4]
                ip_str = sockaddr[0]
                resolved_ip = ipaddress.ip_address(ip_str)

                if (
                    resolved_ip.is_loopback
                    or resolved_ip.is_private
                    or resolved_ip.is_link_local
                    or resolved_ip.is_multicast
                    or resolved_ip.is_reserved
                    or resolved_ip.is_unspecified
                ):
                    return False, f"Resolved IP '{resolved_ip}' for host '{hostname}' is in a prohibited private/local range"
        except socket.gaierror as err:
            return False, f"DNS resolution failed for '{hostname}': {str(err)}"
        except Exception as exc:
            return False, f"Network security validation error for '{hostname}': {str(exc)}"

    return True, "Safe"


def validate_stream_url(url: str) -> Tuple[bool, str]:
    """
    Syntactic validation of stream URL for parsing and catalog indexing.
    Does not require immediate DNS resolution to avoid blocking large batch imports.
    """
    return is_safe_url(url, resolve_dns=False)


def resolve_relative_url(base_url: str, relative_path: str) -> Tuple[bool, str, str]:
    """
    Safely resolve a relative resource URL against a base URL and validate the destination.

    Returns:
        (is_safe: bool, resolved_url_or_error: str, reason: str)
    """
    try:
        resolved = urllib.parse.urljoin(base_url, relative_path)
    except Exception as exc:
        return False, "", f"Failed to join URL '{relative_path}' with base '{base_url}': {str(exc)}"

    is_safe, reason = is_safe_url(resolved, resolve_dns=True)
    if not is_safe:
        return False, resolved, reason

    return True, resolved, "Safe"


def safe_http_get(
    url: str,
    timeout: int = 5,
    max_bytes: int = 128 * 1024,
    max_redirects: int = 3
) -> Tuple[int, dict, bytes, float, str]:
    """
    Execute a safe, bounded HTTP GET request with SSRF validation on every redirect hop.

    Args:
        url: Target destination URL.
        timeout: Total connection/read timeout in seconds.
        max_bytes: Maximum payload bytes to read into memory (prevents unbounded media streams).
        max_redirects: Maximum redirect hops allowed before aborting.

    Returns:
        (status_code: int, headers: dict, content_bytes: bytes, response_time_ms: float, error_message: str)
    """
    import time
    import requests

    current_url = url
    redirect_count = 0
    total_elapsed_ms = 0.0

    while redirect_count <= max_redirects:
        # Validate candidate URL before making network request
        is_safe, reason = is_safe_url(current_url, resolve_dns=True)
        if not is_safe:
            return 0, {}, b"", total_elapsed_ms, f"Blocked unsafe destination: {reason}"

        req_headers = {
            "User-Agent": "GlobalLiveTV-HealthCheck/1.0 (+https://github.com/iptv-org/iptv)",
            "Accept": "*/*"
        }

        start_time = time.time()
        try:
            resp = requests.get(
                current_url,
                headers=req_headers,
                timeout=timeout,
                stream=True,
                allow_redirects=False
            )
            step_elapsed = (time.time() - start_time) * 1000.0
            total_elapsed_ms += step_elapsed

            # Inspect redirect responses
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("Location")
                resp.close()
                if not location:
                    return resp.status_code, dict(resp.headers), b"", total_elapsed_ms, "Redirect response missing Location header"

                # Safely join relative redirect location
                ok, target_url, reason = resolve_relative_url(current_url, location)
                if not ok:
                    return 0, {}, b"", total_elapsed_ms, f"Redirect to unsafe destination blocked: {reason}"

                redirect_count += 1
                if redirect_count > max_redirects:
                    return resp.status_code, dict(resp.headers), b"", total_elapsed_ms, f"Exceeded maximum allowed redirects ({max_redirects})"

                current_url = target_url
                continue

            # Read response up to bounded max_bytes
            buffer = bytearray()
            try:
                for chunk in resp.iter_content(chunk_size=4096):
                    if chunk:
                        buffer.extend(chunk)
                        if len(buffer) >= max_bytes:
                            break
            finally:
                resp.close()

            return resp.status_code, dict(resp.headers), bytes(buffer), round(total_elapsed_ms, 2), ""

        except requests.exceptions.Timeout:
            elapsed = (time.time() - start_time) * 1000.0
            return 0, {}, b"", round(total_elapsed_ms + elapsed, 2), f"Request timed out after {timeout}s"
        except requests.exceptions.ConnectionError as err:
            elapsed = (time.time() - start_time) * 1000.0
            return 0, {}, b"", round(total_elapsed_ms + elapsed, 2), f"Connection failed: {str(err)}"
        except Exception as exc:
            elapsed = (time.time() - start_time) * 1000.0
            return 0, {}, b"", round(total_elapsed_ms + elapsed, 2), f"HTTP request failed: {str(exc)}"

    return 0, {}, b"", total_elapsed_ms, "Redirect loop or exceeded limit"
