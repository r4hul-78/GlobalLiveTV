"""
Stream Health-Checking Engine
Safely probes external HLS streams, validates manifest structures, enforces SSRF defenses,
and records health metrics without downloading continuous broadcasts.
"""
import time
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, List, Tuple, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

from app import db
from app.models import Channel, StreamCheck
from app.services.security import safe_http_get, resolve_relative_url

logger = logging.getLogger(__name__)

# Valid standardized health outcomes
OUTCOME_HEALTHY = "healthy"
OUTCOME_DEGRADED = "degraded"
OUTCOME_UNAVAILABLE = "unavailable"
OUTCOME_UNSUPPORTED = "unsupported"
OUTCOME_UNKNOWN = "unknown"

# Latency threshold for degraded status (ms)
LATENCY_DEGRADED_THRESHOLD_MS = 2500.0


@dataclass
class StreamHealthResult:
    """Diagnostic outcome of an individual stream health probe."""
    channel_id: int
    outcome: str
    http_status: Optional[int]
    response_time_ms: Optional[float]
    diagnostic_reason: str
    is_live_manifest: bool = False
    checked_at: Optional[datetime] = None

    def to_dict(self):
        return {
            "channel_id": self.channel_id,
            "outcome": self.outcome,
            "http_status": self.http_status,
            "response_time_ms": self.response_time_ms,
            "diagnostic_reason": self.diagnostic_reason,
            "is_live_manifest": self.is_live_manifest,
            "checked_at": self.checked_at.isoformat() if self.checked_at else None
        }


class StreamHealthChecker:
    """
    Engine for lightweight, non-invasive validation of live TV streams.
    
    IMPORTANT DISCLAIMER:
    A successful manifest and segment probe confirms accessibility and syntax validity
    at the time of the check, but CANNOT guarantee uninterrupted playback in every user's
    browser due to potential client-side CORS headers, browser codec limitations, or
    geographic/ISP access controls.
    """

    def __init__(self, timeout: int = 3, max_failures: int = 3):
        self.timeout = timeout
        self.max_failures = max_failures

    def inspect_manifest_content(
        self,
        content_text: str,
        base_url: str,
        check_variant: bool = True
    ) -> Tuple[str, str, bool]:
        """
        Inspect text content to determine if it is a recognizable, valid HLS manifest.

        Returns:
            (outcome: str, reason: str, is_live_manifest: bool)
        """
        if not content_text or not content_text.strip():
            return OUTCOME_UNAVAILABLE, "Empty response body from stream endpoint", False

        stripped = content_text.strip()

        # Reject HTML pages / captive portals / soft 404s returning 200
        lower_prefix = stripped[:150].lower()
        if "<!doctype html" in lower_prefix or "<html" in lower_prefix or "<body" in lower_prefix:
            return OUTCOME_UNSUPPORTED, "Stream endpoint returned HTML document instead of HLS manifest", False

        # Check for standard HLS header
        if not stripped.startswith("#EXTM3U"):
            return OUTCOME_UNSUPPORTED, "Missing #EXTM3U header in stream playlist", False

        lines = [line.strip() for line in stripped.splitlines() if line.strip()]

        # Check if Master Playlist containing variant streams
        is_master_playlist = any(line.startswith("#EXT-X-STREAM-INF:") for line in lines)

        if is_master_playlist:
            variant_uri = None
            for idx, line in enumerate(lines):
                if line.startswith("#EXT-X-STREAM-INF:") and idx + 1 < len(lines):
                    candidate_line = lines[idx + 1]
                    if not candidate_line.startswith("#"):
                        variant_uri = candidate_line
                        break

            if not variant_uri:
                return OUTCOME_DEGRADED, "Master playlist detected but no variant stream URI found", False

            if check_variant:
                # Safely resolve and probe a tiny snippet of the referenced variant
                ok, resolved_variant_url, reason = resolve_relative_url(base_url, variant_uri)
                if not ok:
                    return OUTCOME_UNAVAILABLE, f"Variant stream destination rejected: {reason}", False

                # Bounded probe of variant playlist (up to 32KB)
                v_code, _, v_bytes, _, v_err = safe_http_get(
                    resolved_variant_url,
                    timeout=min(self.timeout, 2),
                    max_bytes=32 * 1024
                )
                if v_code != 200:
                    return OUTCOME_DEGRADED, f"Master playlist valid, but variant returned HTTP {v_code}: {v_err or 'Failed'}", False

                v_text = v_bytes.decode("utf-8", errors="replace")
                if not v_text.startswith("#EXTM3U"):
                    return OUTCOME_DEGRADED, "Referenced variant playlist lacks #EXTM3U header", False

            return OUTCOME_HEALTHY, "Valid HLS master playlist with accessible variant stream", True

        # Check if Media Playlist
        has_extinf = any(line.startswith("#EXTINF:") for line in lines)
        has_target_duration = any(line.startswith("#EXT-X-TARGETDURATION:") for line in lines)
        has_media_segments = any(
            line.endswith((".ts", ".m4s", ".aac", ".mp4")) or ".ts?" in line or ".m4s?" in line
            for line in lines if not line.startswith("#")
        )

        if has_extinf or has_target_duration or has_media_segments:
            return OUTCOME_HEALTHY, "Valid HLS media playlist with active segments", True

        return OUTCOME_DEGRADED, "HLS header present but no media segments or variants detected", False

    def probe_stream_network(self, channel_id: int, stream_url: str) -> StreamHealthResult:
        """
        Pure network probe and manifest inspection for a stream URL.
        Does not touch the database session, allowing safe concurrent multi-threading.
        """
        now = datetime.now(timezone.utc)
        status_code, headers, content_bytes, response_time_ms, err_msg = safe_http_get(
            stream_url,
            timeout=self.timeout,
            max_bytes=64 * 1024
        )

        if err_msg or status_code == 0:
            is_ssrf = "Blocked unsafe destination" in err_msg or "private" in err_msg
            outcome = OUTCOME_UNSUPPORTED if is_ssrf else OUTCOME_UNAVAILABLE
            reason = err_msg or "Connection failure"
            return StreamHealthResult(
                channel_id=channel_id,
                outcome=outcome,
                http_status=status_code or None,
                response_time_ms=response_time_ms,
                diagnostic_reason=reason,
                is_live_manifest=False,
                checked_at=now
            )

        if status_code in (404, 410):
            reason = f"Stream endpoint returned HTTP {status_code} (Not Found)"
            return StreamHealthResult(
                channel_id=channel_id,
                outcome=OUTCOME_UNAVAILABLE,
                http_status=status_code,
                response_time_ms=response_time_ms,
                diagnostic_reason=reason,
                is_live_manifest=False,
                checked_at=now
            )

        if status_code >= 400:
            reason = f"Stream endpoint returned HTTP {status_code}"
            return StreamHealthResult(
                channel_id=channel_id,
                outcome=OUTCOME_DEGRADED,
                http_status=status_code,
                response_time_ms=response_time_ms,
                diagnostic_reason=reason,
                is_live_manifest=False,
                checked_at=now
            )

        # HTTP 20x response: parse and inspect manifest body
        content_text = content_bytes.decode("utf-8", errors="replace")
        outcome, reason, is_live = self.inspect_manifest_content(content_text, base_url=stream_url)

        if outcome == OUTCOME_HEALTHY and response_time_ms and response_time_ms > LATENCY_DEGRADED_THRESHOLD_MS:
            outcome = OUTCOME_DEGRADED
            reason = f"{reason} (High latency: {response_time_ms:.0f}ms)"

        return StreamHealthResult(
            channel_id=channel_id,
            outcome=outcome,
            http_status=status_code,
            response_time_ms=response_time_ms,
            diagnostic_reason=reason,
            is_live_manifest=is_live,
            checked_at=now
        )

    def apply_health_result(self, channel: Channel, result: StreamHealthResult, save: bool = True) -> StreamHealthResult:
        """
        Apply the probe result to the Channel entity, manage failure counts, and create audit log.
        """
        now = result.checked_at or datetime.now(timezone.utc)

        if result.outcome == OUTCOME_HEALTHY:
            channel.consecutive_failures = 0
            channel.last_successful_check = now
            final_outcome = OUTCOME_HEALTHY
        elif result.outcome == OUTCOME_UNSUPPORTED:
            channel.consecutive_failures += 1
            final_outcome = OUTCOME_UNSUPPORTED
        else:
            channel.consecutive_failures += 1
            if channel.consecutive_failures >= self.max_failures:
                final_outcome = OUTCOME_UNAVAILABLE
            else:
                final_outcome = OUTCOME_DEGRADED

        result.outcome = final_outcome
        channel.health_status = final_outcome
        channel.last_health_check = now
        channel.response_time_ms = result.response_time_ms
        channel.diagnostic_reason = result.diagnostic_reason

        audit_entry = StreamCheck(
            channel_id=channel.id,
            checked_at=now,
            outcome=final_outcome,
            http_status=result.http_status,
            response_time_ms=result.response_time_ms,
            diagnostic_reason=result.diagnostic_reason
        )
        db.session.add(audit_entry)

        if save:
            try:
                db.session.commit()
            except Exception as exc:
                db.session.rollback()
                logger.error("Failed to commit stream check for channel %d: %s", channel.id, str(exc))

        return result

    def check_stream(self, channel: Channel, save: bool = True) -> StreamHealthResult:
        """
        Probe and update health for a single channel record.
        """
        probe_res = self.probe_stream_network(channel.id, channel.stream_url)
        return self.apply_health_result(channel, probe_res, save=save)

    def check_batch(
        self,
        channels: List[Channel],
        concurrency: int = 5,
        save: bool = True
    ) -> List[StreamHealthResult]:
        """
        Probe a batch of channels concurrently using a bounded thread pool.
        Network I/O is parallelized; database persistence is transactionally applied.
        """
        results: List[StreamHealthResult] = []
        if not channels:
            return results

        concurrency = max(1, min(concurrency, 20))  # Bound between 1 and 20 workers
        channel_map = {ch.id: ch for ch in channels}
        probe_tasks = [(ch.id, ch.stream_url) for ch in channels]

        # Parallel network probes
        probe_results: Dict[int, StreamHealthResult] = {}
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            future_to_id = {
                executor.submit(self.probe_stream_network, cid, url): cid
                for cid, url in probe_tasks
            }
            for future in as_completed(future_to_id):
                cid = future_to_id[future]
                try:
                    probe_results[cid] = future.result()
                except Exception as exc:
                    logger.error("Error probing channel %d: %s", cid, str(exc))

        # Synchronous, safe database application in caller thread session
        for ch in channels:
            res = probe_results.get(ch.id)
            if res:
                applied = self.apply_health_result(ch, res, save=False)
                results.append(applied)

        if save:
            try:
                db.session.commit()
            except Exception as exc:
                db.session.rollback()
                logger.error("Failed to commit batch stream checks: %s", str(exc))

        return results
