"""
Free-To-Air (FTA) Stream Discovery & Verification Tool
Searches iptv-org and public broadcasting indexes for legal, free-to-air HLS channels
across multiple genres (News, Documentary, Science, Music, Classic/Movies, Sports,
Animation, Kids, Weather, Culture).
Validates SSRF security and probes live stream health before saving to a curated playlist.
"""
import os
import re
import sys
import time
import logging
import argparse
import urllib.request
from typing import Dict, List, Tuple, Any
from pathlib import Path

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app import create_app, db
from app.services.security import is_safe_url
from app.services.health_checker import StreamHealthChecker, OUTCOME_HEALTHY
from app.services.ingestion_service import IngestionService

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("discover_fta")

# Target categories to search for balanced genre diversity
TARGET_CATEGORIES = [
    ("news", "News"),
    ("documentary", "Documentary"),
    ("science", "Science"),
    ("music", "Music"),
    ("classic", "Classic"),
    ("movies", "Movies"),
    ("sports", "Sports"),
    ("animation", "Animation"),
    ("kids", "Kids"),
    ("weather", "Weather"),
    ("culture", "Culture"),
    ("education", "Education"),
    ("auto", "Auto"),
    ("comedy", "Comedy"),
]


def fetch_category_playlist(category_slug: str) -> List[Tuple[Dict[str, str], str]]:
    """Download category playlist from iptv-org and parse candidate channels."""
    url = f"https://iptv-org.github.io/iptv/categories/{category_slug}.m3u"
    logger.info("Fetching playlist for category '%s': %s", category_slug, url)

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GlobalLiveTV/1.0"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        logger.warning("Could not download %s: %s", url, exc)
        return []

    channels = []
    lines = content.splitlines()
    current_attrs = None

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF:"):
            # Parse attributes
            attrs = {}
            id_m = re.search(r'tvg-id="([^"]*)"', line)
            name_m = re.search(r'tvg-name="([^"]*)"', line)
            logo_m = re.search(r'tvg-logo="([^"]*)"', line)
            country_m = re.search(r'tvg-country="([^"]*)"', line)
            lang_m = re.search(r'tvg-language="([^"]*)"', line)
            group_m = re.search(r'group-title="([^"]*)"', line)

            # Extract channel display title after last comma
            comma_idx = line.rfind(",")
            title = line[comma_idx + 1:].strip() if comma_idx != -1 else ""

            attrs["id"] = id_m.group(1).strip() if id_m else ""
            attrs["name"] = title or (name_m.group(1).strip() if name_m else "Channel")
            attrs["logo"] = logo_m.group(1).strip() if logo_m else ""
            attrs["country"] = country_m.group(1).strip() if country_m else ""
            attrs["language"] = lang_m.group(1).strip() if lang_m else ""
            attrs["group"] = group_m.group(1).strip() if group_m else category_slug.capitalize()

            current_attrs = attrs
        elif not line.startswith("#") and current_attrs:
            stream_url = line.strip()
            # Basic sanity checks: http/https, no geo-block tag in name
            is_geo = "[Geo-blocked]" in current_attrs["name"]
            if not is_geo and (stream_url.startswith("http://") or stream_url.startswith("https://")):
                channels.append((current_attrs, stream_url))
            current_attrs = None

    logger.info("Found %d candidate streams in '%s'", len(channels), category_slug)
    return channels


def discover_and_verify_channels(
    per_category: int = 4,
    max_candidates_to_test: int = 25
) -> List[Tuple[Dict[str, str], str]]:
    """
    Search across target categories, test stream health, and select verified healthy streams.
    """
    app = create_app()
    checker = StreamHealthChecker(timeout=4, max_failures=2)
    selected_channels = []
    seen_urls = set()
    seen_names = set()

    with app.app_context():
        for cat_slug, cat_display in TARGET_CATEGORIES:
            candidates = fetch_category_playlist(cat_slug)
            if not candidates:
                continue

            verified_for_cat = 0
            logger.info("Probing streams for category '%s' (seeking %d healthy)...", cat_display, per_category)

            # Test a subset of candidates to find healthy ones
            for attrs, stream_url in candidates[:max_candidates_to_test]:
                if verified_for_cat >= per_category:
                    break

                if stream_url in seen_urls:
                    continue

                clean_name = re.sub(r"\s*\(\d+p\)", "", attrs["name"]).strip()
                if clean_name.lower() in seen_names:
                    continue

                # 1. SSRF Safety Check
                safe, reason = is_safe_url(stream_url)
                if not safe:
                    logger.debug("Skipping unsafe URL: %s (%s)", stream_url, reason)
                    continue

                # 2. Live Stream Health Probe
                try:
                    probe = checker.probe_stream_network(channel_id=0, stream_url=stream_url)
                    if probe.outcome == OUTCOME_HEALTHY:
                        verified_for_cat += 1
                        seen_urls.add(stream_url)
                        seen_names.add(clean_name.lower())
                        attrs["name"] = clean_name
                        attrs["group"] = cat_display
                        selected_channels.append((attrs, stream_url))
                        logger.info(
                            "  [HEALTHY] %s (%s, %s) - %.0fms - %s",
                            clean_name, cat_display, attrs.get("country", ""),
                            probe.response_time_ms or 0.0, stream_url
                        )
                    else:
                        logger.debug("  [FAIL] %s: %s", clean_name, probe.diagnostic_reason)
                except Exception as exc:
                    logger.debug("  [EXC] %s: %s", clean_name, exc)

            logger.info("Category '%s' finished: %d healthy channels added.", cat_display, verified_for_cat)

    return selected_channels


def generate_m3u_content(channels: List[Tuple[Dict[str, str], str]]) -> str:
    """Format selected channels into standard extended M3U format."""
    lines = ["#EXTM3U"]
    for attrs, url in channels:
        tvg_id = attrs.get("id", "")
        name = attrs.get("name", "Channel")
        logo = attrs.get("logo", "")
        country = attrs.get("country", "")
        lang = attrs.get("language", "")
        group = attrs.get("group", "General")

        tag_parts = ['#EXTINF:-1']
        if tvg_id:
            tag_parts.append(f'tvg-id="{tvg_id}"')
        tag_parts.append(f'tvg-name="{name}"')
        if logo:
            tag_parts.append(f'tvg-logo="{logo}"')
        if country:
            tag_parts.append(f'tvg-country="{country}"')
        if lang:
            tag_parts.append(f'tvg-language="{lang}"')
        if group:
            tag_parts.append(f'group-title="{group}"')

        extinf_line = " ".join(tag_parts) + f",{name}"
        lines.append(extinf_line)
        lines.append(url)

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Discover and verify free-to-air live channels across genres.")
    parser.add_argument("--per-category", type=int, default=3, help="Number of verified channels to collect per genre (default: 3).")
    parser.add_argument("--test-limit", type=int, default=20, help="Max channels to probe per category (default: 20).")
    parser.add_argument("--output", type=str, default="data/curated_fta_channels.m3u", help="Output M3U file path.")
    parser.add_argument("--ingest", action="store_true", help="Directly ingest verified channels into database.")

    args = parser.parse_args()

    out_path = Path(args.output)
    if not out_path.is_absolute():
        out_path = BASE_DIR / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Starting FTA Channel Discovery across %d genres...", len(TARGET_CATEGORIES))
    selected = discover_and_verify_channels(
        per_category=args.per_category,
        max_candidates_to_test=args.test_limit
    )

    logger.info("Discovery complete! Total verified healthy channels: %d", len(selected))

    m3u_text = generate_m3u_content(selected)
    out_path.write_text(m3u_text, encoding="utf-8")
    logger.info("Saved curated M3U playlist to: %s", out_path)

    if args.ingest:
        logger.info("Ingesting curated channels into database...")
        app = create_app()
        with app.app_context():
            db.create_all()
            service = IngestionService()
            stats = service.ingest_from_content(m3u_text)
            logger.info("Ingestion completed: %d parsed, %d imported, %d updated",
                        stats.total_parsed, stats.imported, stats.updated)


if __name__ == "__main__":
    main()
