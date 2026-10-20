"""
Channel Catalog Service
Handles database queries, searching, combined filtering, and pagination for channels and taxonomies.
"""
import math
import time
import threading
from typing import Optional, List, Tuple, Dict, Any
from flask import current_app
from sqlalchemy import func, asc
from app import db
from app.models import Channel, Country, Genre, Language, channel_genres, channel_languages


VALID_HEALTH_STATUSES = {"healthy", "degraded", "unavailable", "unsupported", "unknown"}
MAX_PER_PAGE = 100
DEFAULT_PER_PAGE = 20


class ChannelService:
    """Service providing catalog search, filtering, and taxonomy metadata."""

    _filter_cache: Optional[Dict[str, Any]] = None
    _filter_cache_expires_at: float = 0.0
    _filter_cache_lock = threading.Lock()

    @classmethod
    def invalidate_filter_cache(cls) -> None:
        """Clear cached filter taxonomy to force recalculation on next query."""
        with cls._filter_cache_lock:
            cls._filter_cache = None
            cls._filter_cache_expires_at = 0.0

    @staticmethod
    def search_channels(
        q: Optional[str] = None,
        country: Optional[str] = None,
        genre: Optional[str] = None,
        language: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        per_page: int = DEFAULT_PER_PAGE
    ) -> Tuple[List[Channel], int, int]:
        """
        Query channels with combined filtering and deterministic pagination.

        Args:
            q: Search term matched case-insensitively against channel name and tvg-id.
            country: Country code filter (e.g., 'US', 'FR').
            genre: Genre slug or display name (e.g., 'news', 'News').
            language: Language code filter (e.g., 'eng', 'fra').
            status: Stream health filter ('healthy', 'degraded', 'unavailable', 'unsupported', 'unknown').
            page: 1-indexed page number.
            per_page: Number of items per page (bounded between 1 and 100).

        Returns:
            (items: List[Channel], total_items: int, total_pages: int)
        """
        # Validate and bound pagination
        if page < 1:
            raise ValueError("Parameter 'page' must be a positive integer >= 1")
        if per_page < 1 or per_page > MAX_PER_PAGE:
            raise ValueError(f"Parameter 'per_page' must be an integer between 1 and {MAX_PER_PAGE}")

        query = Channel.query.filter(Channel.is_active.is_(True))

        # Channel name or external ID search
        if q and q.strip():
            search_term = f"%{q.strip()}%"
            query = query.filter(
                Channel.name.ilike(search_term) | Channel.external_id.ilike(search_term)
            )

        # Country filter
        if country and country.strip():
            c_code = country.strip().upper()
            query = query.filter(Channel.country_code == c_code)

        # Genre filter (by slug or name)
        if genre and genre.strip():
            g_term = genre.strip().lower()
            query = query.join(Channel.genres).filter(
                (Genre.slug == g_term) | (func.lower(Genre.name) == g_term)
            )

        # Language filter (by code or name)
        if language and language.strip():
            l_term = language.strip().lower()
            query = query.join(Channel.languages).filter(
                (Language.code == l_term) | (func.lower(Language.name) == l_term)
            )

        # Stream health status filter
        if status and status.strip():
            normalized_status = status.strip().lower()
            if normalized_status not in VALID_HEALTH_STATUSES:
                valid_list = ", ".join(sorted(VALID_HEALTH_STATUSES))
                raise ValueError(f"Invalid health status '{status}'. Allowed values: {valid_list}")
            query = query.filter(Channel.health_status == normalized_status)

        # Total count before pagination
        total_items = query.with_entities(func.count(func.distinct(Channel.id))).scalar() or 0
        total_pages = max(1, math.ceil(total_items / per_page)) if total_items > 0 else 0

        # Deterministic ordering by case-insensitive name then internal ID
        query = query.distinct().order_by(func.lower(Channel.name).asc(), asc(Channel.id))

        # Apply offset and limit
        offset = (page - 1) * per_page
        items = query.offset(offset).limit(per_page).all()

        return items, total_items, total_pages

    @staticmethod
    def get_channel_by_id(channel_id: int) -> Optional[Channel]:
        """Retrieve a single active channel by internal database ID."""
        if not isinstance(channel_id, int) or channel_id < 1:
            return None
        return Channel.query.filter_by(id=channel_id, is_active=True).first()

    @classmethod
    def get_available_filters(cls, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Return dynamically aggregated countries, genres, and languages based on actual active channels.
        Avoids stale or orphaned taxonomy items, and caches results for a bounded TTL to minimize database load.
        """
        ttl = 300
        try:
            if current_app:
                ttl = current_app.config.get("FILTER_CACHE_TTL_SECONDS", 300)
        except RuntimeError:
            ttl = 300

        now = time.time()
        if not force_refresh and ttl > 0:
            with cls._filter_cache_lock:
                if cls._filter_cache is not None and now < cls._filter_cache_expires_at:
                    return cls._filter_cache

        # Active countries
        countries = (
            db.session.query(Country.code, Country.name)
            .join(Channel, Channel.country_code == Country.code)
            .filter(Channel.is_active.is_(True))
            .distinct()
            .order_by(asc(Country.name))
            .all()
        )

        # Active genres
        genres = (
            db.session.query(Genre.slug, Genre.name)
            .join(channel_genres, Genre.id == channel_genres.c.genre_id)
            .join(Channel, Channel.id == channel_genres.c.channel_id)
            .filter(Channel.is_active.is_(True))
            .distinct()
            .order_by(asc(Genre.name))
            .all()
        )

        # Active languages
        languages = (
            db.session.query(Language.code, Language.name)
            .join(channel_languages, Language.code == channel_languages.c.language_code)
            .join(Channel, Channel.id == channel_languages.c.channel_id)
            .filter(Channel.is_active.is_(True))
            .distinct()
            .order_by(asc(Language.name))
            .all()
        )

        # Active status counts
        status_counts = (
            db.session.query(Channel.health_status, func.count(Channel.id))
            .filter(Channel.is_active.is_(True))
            .group_by(Channel.health_status)
            .all()
        )

        result = {
            "countries": [{"code": c[0], "name": c[1]} for c in countries],
            "genres": [{"slug": g[0], "name": g[1]} for g in genres],
            "languages": [{"code": l[0], "name": l[1]} for l in languages],
            "statuses": {s[0]: s[1] for s in status_counts}
        }

        if ttl > 0:
            with cls._filter_cache_lock:
                cls._filter_cache = result
                cls._filter_cache_expires_at = now + ttl

        return result

