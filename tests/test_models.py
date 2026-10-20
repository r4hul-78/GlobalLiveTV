import pytest
from datetime import datetime, timezone
from app.models import Channel, Country, Genre, Language, StreamCheck


def test_channel_creation_and_attributes(app):
    """Test creating a channel with core attributes and default values."""
    with app.app_context():
        from app import db
        channel = Channel(
            external_id="BBCNews.uk",
            name="BBC News",
            logo_url="https://example.com/bbc.png",
            stream_url="https://example.com/bbc.m3u8"
        )
        db.session.add(channel)
        db.session.commit()

        assert channel.id is not None
        assert channel.name == "BBC News"
        assert channel.external_id == "BBCNews.uk"
        assert channel.is_active is True
        assert channel.health_status == "unknown"
        assert channel.first_seen_at is not None
        assert channel.last_updated_at is not None


def test_taxonomy_relationships(app):
    """Test relationships between Channel and Country, Genre, and Language."""
    with app.app_context():
        from app import db
        # Create taxonomies
        country = Country(code="US", name="United States")
        genre1 = Genre(slug="news", name="News")
        genre2 = Genre(slug="entertainment", name="Entertainment")
        lang = Language(code="eng", name="English")

        db.session.add_all([country, genre1, genre2, lang])
        db.session.commit()

        # Create channel and link taxonomies
        channel = Channel(
            external_id="CNN.us",
            name="CNN",
            stream_url="https://example.com/cnn.m3u8",
            country=country,
            genres=[genre1, genre2],
            languages=[lang]
        )
        db.session.add(channel)
        db.session.commit()

        # Query back and verify
        saved_channel = db.session.get(Channel, channel.id)
        assert saved_channel.country.code == "US"
        assert saved_channel.country.name == "United States"
        assert len(saved_channel.genres) == 2
        genre_slugs = [g.slug for g in saved_channel.genres]
        assert "news" in genre_slugs
        assert "entertainment" in genre_slugs
        assert len(saved_channel.languages) == 1
        assert saved_channel.languages[0].code == "eng"


def test_stream_check_relationship_and_cascade(app):
    """Test StreamCheck creation, relationship to Channel, and cascade deletion."""
    with app.app_context():
        from app import db
        channel = Channel(
            name="Test Stream",
            stream_url="https://example.com/test.m3u8"
        )
        db.session.add(channel)
        db.session.commit()

        check1 = StreamCheck(
            channel_id=channel.id,
            outcome="healthy",
            http_status=200,
            response_time_ms=120.5,
            diagnostic_reason="Valid HLS manifest with live media segments"
        )
        check2 = StreamCheck(
            channel_id=channel.id,
            outcome="degraded",
            http_status=200,
            response_time_ms=850.0,
            diagnostic_reason="Slow manifest response"
        )
        db.session.add_all([check1, check2])
        db.session.commit()

        assert channel.stream_checks.count() == 2
        assert channel.stream_checks.first().outcome in ("healthy", "degraded")

        # Verify cascade delete
        channel_id = channel.id
        db.session.delete(channel)
        db.session.commit()

        orphaned_checks = db.session.query(StreamCheck).filter_by(channel_id=channel_id).all()
        assert len(orphaned_checks) == 0


def test_channel_to_dict_serialization(app):
    """Test serialization of Channel model to dictionary."""
    with app.app_context():
        from app import db
        country = Country(code="FR", name="France")
        genre = Genre(slug="music", name="Music")
        channel = Channel(
            external_id="Mezzo.fr",
            name="Mezzo TV",
            logo_url="https://example.com/mezzo.png",
            stream_url="https://example.com/mezzo.m3u8",
            country=country,
            genres=[genre]
        )
        db.session.add_all([country, genre, channel])
        db.session.commit()

        payload = channel.to_dict()
        assert payload["id"] == channel.id
        assert payload["external_id"] == "Mezzo.fr"
        assert payload["name"] == "Mezzo TV"
        assert payload["country"]["code"] == "FR"
        assert payload["genres"][0]["slug"] == "music"
        assert payload["health_status"] == "unknown"
