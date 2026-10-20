import pytest
from app.models import Channel, Country, Genre, Language
from app.services.ingestion_service import IngestionService, IngestionResult


SAMPLE_MAIN_M3U = """#EXTM3U
#EXTINF:-1 tvg-id="France24.fr" tvg-name="France 24" tvg-logo="https://example.com/f24.png" group-title="News",France 24 English
https://example.com/f24/live.m3u8
#EXTINF:-1 tvg-id="DW.de" tvg-name="DW" tvg-logo="https://example.com/dw.png" group-title="News",DW English
https://example.com/dw/live.m3u8
#EXTINF:-1 tvg-id="NHK.jp" tvg-name="NHK World" tvg-logo="https://example.com/nhk.png" group-title="General",NHK World Japan
https://example.com/nhk/live.m3u8
"""

SAMPLE_COUNTRY_M3U = """#EXTM3U
#EXTINF:-1 tvg-id="France24.fr" tvg-country="FR" group-title="France",France 24 English
https://example.com/f24/live.m3u8
#EXTINF:-1 tvg-id="DW.de" tvg-country="DE" group-title="Germany",DW English
https://example.com/dw/live.m3u8
#EXTINF:-1 tvg-id="NHK.jp" tvg-country="JP" group-title="Japan",NHK World Japan
https://example.com/nhk/live.m3u8
"""

SAMPLE_CATEGORY_M3U = """#EXTM3U
#EXTINF:-1 tvg-id="France24.fr" group-title="International News",France 24 English
https://example.com/f24/live.m3u8
#EXTINF:-1 tvg-id="DW.de" group-title="Documentary",DW English
https://example.com/dw/live.m3u8
"""

SAMPLE_LANGUAGE_M3U = """#EXTM3U
#EXTINF:-1 tvg-id="France24.fr" tvg-language="eng",France 24 English
https://example.com/f24/live.m3u8
#EXTINF:-1 tvg-id="DW.de" tvg-language="eng",DW English
https://example.com/dw/live.m3u8
#EXTINF:-1 tvg-id="NHK.jp" tvg-language="jpn",NHK World Japan
https://example.com/nhk/live.m3u8
"""


def test_ingestion_idempotence(app):
    """Verify repeated imports do not produce duplicate channel records."""
    with app.app_context():
        from app import db
        service = IngestionService()

        # First ingestion
        res1 = service.ingest_from_content(SAMPLE_MAIN_M3U)
        assert res1.imported == 3
        assert res1.updated == 0
        assert db.session.query(Channel).count() == 3

        # Second identical ingestion
        res2 = service.ingest_from_content(SAMPLE_MAIN_M3U)
        assert res2.imported == 0
        assert res2.updated == 3
        # Total channels must still be 3 (no duplicates)
        assert db.session.query(Channel).count() == 3


def test_ingestion_metadata_updates(app):
    """Verify existing records are updated when playlist metadata changes."""
    with app.app_context():
        from app import db
        service = IngestionService()

        initial_m3u = """#EXTM3U
#EXTINF:-1 tvg-id="Test.1" tvg-logo="https://example.com/old_logo.png",Original Title
https://example.com/stream1.m3u8
"""
        updated_m3u = """#EXTM3U
#EXTINF:-1 tvg-id="Test.1" tvg-logo="https://example.com/new_logo.png",Updated Title
https://example.com/stream1.m3u8
"""
        service.ingest_from_content(initial_m3u)
        ch = db.session.query(Channel).filter_by(external_id="Test.1").first()
        assert ch.name == "Original Title"
        assert ch.logo_url == "https://example.com/old_logo.png"

        # Update
        service.ingest_from_content(updated_m3u)
        db.session.expire_all()
        ch_updated = db.session.query(Channel).filter_by(external_id="Test.1").first()
        assert ch_updated.name == "Updated Title"
        assert ch_updated.logo_url == "https://example.com/new_logo.png"


def test_ingestion_dry_run(app):
    """Verify dry-run mode does not commit changes to the database."""
    with app.app_context():
        from app import db
        service = IngestionService()

        res = service.ingest_from_content(SAMPLE_MAIN_M3U, dry_run=True)
        assert res.dry_run is True
        assert res.imported == 3
        # DB should remain completely empty
        assert db.session.query(Channel).count() == 0


def test_ingestion_record_limit(app):
    """Verify optional limit parameter bounds the processed channels."""
    with app.app_context():
        from app import db
        service = IngestionService()

        res = service.ingest_from_content(SAMPLE_MAIN_M3U, limit=2)
        assert res.imported == 2
        assert db.session.query(Channel).count() == 2


def test_ingestion_multi_playlist_enrichment(app):
    """Verify metadata is properly enriched across country, category, and language playlists."""
    with app.app_context():
        from app import db
        service = IngestionService()

        res = service.ingest_from_content(
            main_content=SAMPLE_MAIN_M3U,
            country_content=SAMPLE_COUNTRY_M3U,
            category_content=SAMPLE_CATEGORY_M3U,
            language_content=SAMPLE_LANGUAGE_M3U
        )
        assert res.imported == 3

        f24 = db.session.query(Channel).filter_by(external_id="France24.fr").first()
        assert f24 is not None
        assert f24.country.code == "FR"
        assert f24.country.name == "France"

        f24_genres = [g.name for g in f24.genres]
        assert "News" in f24_genres
        assert "International News" in f24_genres

        f24_langs = [l.code for l in f24.languages]
        assert "eng" in f24_langs


def test_failed_download_preserves_catalog(app):
    """Verify that an ingestion failure or empty source does not corrupt existing catalog."""
    with app.app_context():
        from app import db
        service = IngestionService()

        # Seed catalog
        service.ingest_from_content(SAMPLE_MAIN_M3U)
        assert db.session.query(Channel).count() == 3

        # Simulate failed/empty source
        empty_res = service.ingest_from_content("")
        assert empty_res.imported == 0
        assert empty_res.total_parsed == 0

        # Existing catalog must remain intact
        assert db.session.query(Channel).count() == 3
