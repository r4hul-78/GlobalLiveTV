"""
IPTV Ingestion Service
Manages automated downloading, metadata enrichment, and idempotent upserts of playlists.
"""
import time
import logging
import requests
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict
from sqlalchemy.orm import Session

from app import db
from app.models import Channel, Country, Genre, Language
from app.services.m3u_parser import parse_m3u_content, M3UChannelRecord
from app.services.security import is_safe_url

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    """Summary of an ingestion run."""
    total_parsed: int = 0
    imported: int = 0
    updated: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    dry_run: bool = False

    def to_dict(self):
        return {
            "total_parsed": self.total_parsed,
            "imported": self.imported,
            "updated": self.updated,
            "skipped": self.skipped,
            "error_count": len(self.errors),
            "errors": self.errors[:10],  # Return top 10 errors for brevity
            "duration_seconds": round(self.duration_seconds, 2),
            "dry_run": self.dry_run
        }


class IngestionService:
    """Service responsible for downloading, parsing, and upserting IPTV channel catalogs."""

    def __init__(self, session: Optional[Session] = None):
        self.session = session or db.session

    def download_playlist(self, url: str, timeout: int = 20) -> Optional[str]:
        """
        Download an M3U playlist from an external URL with SSRF protection and bounded timeouts.
        """
        is_safe, reason = is_safe_url(url)
        if not is_safe:
            logger.error("Blocked unsafe playlist URL '%s': %s", url, reason)
            return None

        try:
            headers = {"User-Agent": "GlobalLiveTV/1.0 (+https://github.com/iptv-org/iptv)"}
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as exc:
            logger.warning("Failed to download playlist from '%s': %s", url, str(exc))
            return None

    def _get_or_create_country(self, code: Optional[str], name: Optional[str]) -> Optional[Country]:
        """Get or create Country entity."""
        if not code:
            return None
        code = code.strip().upper()
        country = self.session.query(Country).filter_by(code=code).first()
        if not country:
            country = Country(code=code, name=name or code)
            self.session.add(country)
            self.session.flush()
        elif name and country.name == country.code and name != code:
            # Upgrade placeholder country name with real name if available
            country.name = name
        return country

    def _get_or_create_genre(self, genre_name: str) -> Optional[Genre]:
        """Get or create Genre entity with normalized slug."""
        if not genre_name or not genre_name.strip():
            return None
        cleaned_name = genre_name.strip()
        slug = cleaned_name.lower().replace(" ", "-").replace("&", "and")
        # Sanitize slug
        slug = "".join(c for c in slug if c.isalnum() or c == "-")
        if not slug:
            return None

        genre = self.session.query(Genre).filter_by(slug=slug).first()
        if not genre:
            genre = Genre(slug=slug, name=cleaned_name.title())
            self.session.add(genre)
            self.session.flush()
        return genre

    def _get_or_create_language(self, lang_code: str, display_name: Optional[str] = None) -> Optional[Language]:
        """Get or create Language entity."""
        if not lang_code or not lang_code.strip():
            return None
        code = lang_code.strip().lower()
        language = self.session.query(Language).filter_by(code=code).first()
        if not language:
            language = Language(code=code, name=display_name or code.capitalize())
            self.session.add(language)
            self.session.flush()
        return language

    def upsert_records(
        self,
        records: List[M3UChannelRecord],
        dry_run: bool = False,
        limit: Optional[int] = None
    ) -> IngestionResult:
        """
        Idempotently upsert parsed channel records into the database.
        """
        start_time = time.time()
        result = IngestionResult(dry_run=dry_run)
        result.total_parsed = len(records)

        records_to_process = records[:limit] if limit and limit > 0 else records

        # Cache known channels to minimize query overhead during batch
        for record in records_to_process:
            try:
                if not record.name or not record.stream_url:
                    result.skipped += 1
                    continue

                # Match existing channel: prefer external_id (tvg-id), fallback to stream_url
                channel = None
                if record.external_id:
                    channel = self.session.query(Channel).filter_by(external_id=record.external_id).first()

                if channel is None:
                    channel = self.session.query(Channel).filter_by(stream_url=record.stream_url).first()

                # Upsert Country
                country_obj = None
                if record.country_code or record.country_name:
                    country_obj = self._get_or_create_country(record.country_code, record.country_name)

                # Upsert Genres
                genre_objs = []
                for g_name in record.genres:
                    g_obj = self._get_or_create_genre(g_name)
                    if g_obj and g_obj not in genre_objs:
                        genre_objs.append(g_obj)

                # Upsert Language
                language_objs = []
                if record.language_code:
                    l_obj = self._get_or_create_language(record.language_code)
                    if l_obj and l_obj not in language_objs:
                        language_objs.append(l_obj)

                if channel:
                    # Update existing record
                    channel.name = record.name
                    if record.external_id and not channel.external_id:
                        channel.external_id = record.external_id
                    if record.logo_url:
                        channel.logo_url = record.logo_url
                    channel.stream_url = record.stream_url
                    if country_obj:
                        channel.country = country_obj

                    for g in genre_objs:
                        if g not in channel.genres:
                            channel.genres.append(g)

                    for l in language_objs:
                        if l not in channel.languages:
                            channel.languages.append(l)

                    channel.last_updated_at = datetime.now(timezone.utc)
                    channel.is_active = True
                    result.updated += 1
                else:
                    # Insert new record
                    new_channel = Channel(
                        external_id=record.external_id,
                        name=record.name,
                        logo_url=record.logo_url,
                        stream_url=record.stream_url,
                        country=country_obj,
                        genres=genre_objs,
                        languages=language_objs,
                        is_active=True,
                        health_status="unknown"
                    )
                    self.session.add(new_channel)
                    result.imported += 1

            except Exception as exc:
                error_msg = f"Failed to upsert channel '{record.name}': {str(exc)}"
                logger.error(error_msg, exc_info=True)
                result.errors.append(error_msg)
                result.skipped += 1

        if dry_run:
            logger.info("Dry-run mode enabled; rolling back database transaction.")
            self.session.rollback()
        else:
            try:
                self.session.commit()
                logger.info(
                    "Ingestion committed: %d imported, %d updated, %d skipped.",
                    result.imported,
                    result.updated,
                    result.skipped
                )
            except Exception as exc:
                self.session.rollback()
                err = f"Failed to commit ingestion transaction: {str(exc)}"
                logger.critical(err, exc_info=True)
                result.errors.append(err)

        result.duration_seconds = time.time() - start_time
        return result

    def ingest_from_content(
        self,
        main_content: str,
        country_content: Optional[str] = None,
        category_content: Optional[str] = None,
        language_content: Optional[str] = None,
        dry_run: bool = False,
        limit: Optional[int] = None
    ) -> IngestionResult:
        """
        Parse and merge multiple playlist contents, then upsert records into the database.
        """
        # Parse main playlist
        records = parse_m3u_content(main_content, source_type="general")
        records_by_key: Dict[str, M3UChannelRecord] = {}

        for rec in records:
            key = rec.external_id or rec.stream_url
            records_by_key[key] = rec

        # Enrich country data if provided
        if country_content:
            country_records = parse_m3u_content(country_content, source_type="country")
            for c_rec in country_records:
                key = c_rec.external_id or c_rec.stream_url
                if key in records_by_key:
                    target = records_by_key[key]
                    if c_rec.country_code and not target.country_code:
                        target.country_code = c_rec.country_code
                    if c_rec.country_name and not target.country_name:
                        target.country_name = c_rec.country_name

        # Enrich category/genre data if provided
        if category_content:
            cat_records = parse_m3u_content(category_content, source_type="category")
            for cat_rec in cat_records:
                key = cat_rec.external_id or cat_rec.stream_url
                if key in records_by_key:
                    target = records_by_key[key]
                    for g in cat_rec.genres:
                        if g not in target.genres:
                            target.genres.append(g)

        # Enrich language data if provided
        if language_content:
            lang_records = parse_m3u_content(language_content, source_type="language")
            for l_rec in lang_records:
                key = l_rec.external_id or l_rec.stream_url
                if key in records_by_key:
                    target = records_by_key[key]
                    if l_rec.language_code and not target.language_code:
                        target.language_code = l_rec.language_code

        merged_records = list(records_by_key.values())
        return self.upsert_records(merged_records, dry_run=dry_run, limit=limit)
