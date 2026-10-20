"""
M3U and EXTINF Playlist Parser
Parses IPTV playlists with robust handling of malformed records, attributes, and URLs.
"""
import re
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from app.services.security import validate_stream_url

logger = logging.getLogger(__name__)

# Regex for key="value" or key='value' or key=value attributes in #EXTINF
ATTR_REGEX = re.compile(r'([a-zA-Z0-9_\-]+)=(?:"([^"]*)"|\'([^\']*)\'|([^\s,]+))')


@dataclass
class M3UChannelRecord:
    """Normalized parsed representation of an M3U channel entry."""
    name: str
    stream_url: str
    external_id: Optional[str] = None
    logo_url: Optional[str] = None
    group_title: Optional[str] = None
    country_code: Optional[str] = None
    country_name: Optional[str] = None
    language_code: Optional[str] = None
    genres: List[str] = field(default_factory=list)
    raw_attributes: Dict[str, str] = field(default_factory=dict)


def _split_extinf_line(line: str) -> Tuple[str, str]:
    """
    Split an #EXTINF line into (attributes_part, title_part).
    Correctly accounts for commas inside quoted attributes.
    """
    # Remove '#EXTINF:' prefix
    content = line[8:].strip()

    in_quotes = False
    quote_char = None
    comma_idx = -1

    for idx, ch in enumerate(content):
        if ch in ('"', "'"):
            if not in_quotes:
                in_quotes = True
                quote_char = ch
            elif quote_char == ch:
                in_quotes = False
                quote_char = None
        elif ch == ',' and not in_quotes:
            comma_idx = idx
            break

    if comma_idx == -1:
        # No unquoted comma found; entire content is attributes or title
        return content, ""

    attrs_part = content[:comma_idx].strip()
    title_part = content[comma_idx + 1:].strip()
    return attrs_part, title_part


def _parse_attributes(attrs_str: str) -> Dict[str, str]:
    """Extract key-value pairs from the attributes portion of an EXTINF line."""
    attributes = {}
    for match in ATTR_REGEX.finditer(attrs_str):
        key = match.group(1).lower()
        # Group 2 (double quotes), Group 3 (single quotes), Group 4 (unquoted)
        val = match.group(2) if match.group(2) is not None else (
            match.group(3) if match.group(3) is not None else match.group(4)
        )
        if val is not None:
            attributes[key] = val.strip()
    return attributes


def parse_m3u_content(content: str, source_type: str = "general") -> List[M3UChannelRecord]:
    """
    Parse M3U / EXTINF text into a list of validated M3UChannelRecord objects.

    Args:
        content: Raw text content of the M3U playlist.
        source_type: One of 'general', 'country', 'category', 'language'.

    Returns:
        List of parsed, validated M3UChannelRecord instances.
    """
    if not content or not isinstance(content, str):
        return []

    # Normalize line endings
    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    
    records: List[M3UChannelRecord] = []
    current_extinf: Optional[Dict[str, any]] = None
    current_extgrp: Optional[str] = None

    for line_num, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("#EXTM3U"):
            continue

        if line.startswith("#EXTINF:"):
            attrs_part, title_part = _split_extinf_line(line)
            attributes = _parse_attributes(attrs_part)

            # Determine best name: title_part > tvg-name > None
            channel_name = title_part or attributes.get("tvg-name") or ""

            current_extinf = {
                "name": channel_name,
                "attributes": attributes,
                "line_num": line_num
            }
            current_extgrp = None
            continue

        if line.startswith("#EXTGRP:"):
            # Optional group tag
            current_extgrp = line[8:].strip()
            continue

        if line.startswith("#"):
            # Other directive or comment, ignore
            continue

        # If we reach here, line is a candidate stream URL
        if current_extinf is not None:
            stream_url = line
            is_safe, reason = validate_stream_url(stream_url)

            if not is_safe:
                logger.warning(
                    "Skipping channel at line %d with unsafe/unsupported stream URL '%s': %s",
                    current_extinf["line_num"],
                    stream_url,
                    reason
                )
                current_extinf = None
                continue

            attrs = current_extinf["attributes"]
            name = current_extinf["name"]

            # If name is still empty, fallback to tvg-id or hostname
            if not name:
                name = attrs.get("tvg-id") or attrs.get("tvg-name") or "Unnamed Channel"

            external_id = attrs.get("tvg-id")
            if external_id and not external_id.strip():
                external_id = None

            logo_url = attrs.get("tvg-logo")
            group_title = current_extgrp or attrs.get("group-title")

            country_code = attrs.get("tvg-country")
            if not country_code and external_id:
                c_m = re.search(r'\.([a-z]{2})(?:@[a-zA-Z0-9]+)?$', external_id)
                if c_m:
                    extracted = c_m.group(1).upper()
                    country_code = "GB" if extracted == "UK" else extracted

            country_name = None
            language_code = attrs.get("tvg-language")
            genres = []

            # Enrich based on source_type or attributes
            if group_title:
                if source_type == "country":
                    country_name = group_title
                elif source_type == "category":
                    genres.append(group_title)
                elif source_type == "language":
                    language_code = language_code or group_title
                else:
                    # General playlist: group-title is usually a category/genre
                    genres.append(group_title)

            record = M3UChannelRecord(
                name=name,
                stream_url=stream_url,
                external_id=external_id,
                logo_url=logo_url,
                group_title=group_title,
                country_code=country_code.upper() if country_code else None,
                country_name=country_name,
                language_code=language_code.lower() if language_code else None,
                genres=genres,
                raw_attributes=attrs
            )
            records.append(record)
            current_extinf = None

    return records
