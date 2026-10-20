"""
REST API Endpoint Tests
Covers /api/channels, /api/channels/<id>, /api/filters, /api/health,
parameter validation, pagination, filtering, deterministic sorting, and error handling.
"""
import pytest
from app import db
from app.models import Channel, Country, Genre, Language, StreamCheck
from datetime import datetime, timezone


@pytest.fixture
def sample_catalog(app):
    """Seed test database with diverse channels, countries, genres, and languages."""
    with app.app_context():
        # Countries
        us = Country(code="US", name="United States")
        gb = Country(code="GB", name="United Kingdom")
        fr = Country(code="FR", name="France")
        db.session.add_all([us, gb, fr])

        # Genres
        news = Genre(slug="news", name="News")
        sports = Genre(slug="sports", name="Sports")
        music = Genre(slug="music", name="Music")
        db.session.add_all([news, sports, music])

        # Languages
        eng = Language(code="eng", name="English")
        fra = Language(code="fra", name="French")
        db.session.add_all([eng, fra])
        db.session.flush()

        # Channels
        c1 = Channel(
            external_id="CNN.us",
            name="CNN International",
            logo_url="https://example.com/cnn.png",
            stream_url="https://streams.example.com/cnn/live.m3u8",
            country=us,
            genres=[news],
            languages=[eng],
            health_status="healthy",
            is_active=True
        )
        c2 = Channel(
            external_id="BBCNews.uk",
            name="BBC News",
            logo_url="https://example.com/bbc.png",
            stream_url="https://streams.example.com/bbc/live.m3u8",
            country=gb,
            genres=[news],
            languages=[eng],
            health_status="healthy",
            is_active=True
        )
        c3 = Channel(
            external_id="France24.fr",
            name="France 24",
            logo_url="https://example.com/france24.png",
            stream_url="https://streams.example.com/france24/live.m3u8",
            country=fr,
            genres=[news],
            languages=[fra, eng],
            health_status="degraded",
            is_active=True
        )
        c4 = Channel(
            external_id="ESPN.us",
            name="ESPN Live",
            logo_url="https://example.com/espn.png",
            stream_url="https://streams.example.com/espn/live.m3u8",
            country=us,
            genres=[sports],
            languages=[eng],
            health_status="unavailable",
            is_active=True
        )
        c5 = Channel(
            external_id="SkySports.uk",
            name="Sky Sports Premier",
            logo_url="https://example.com/sky.png",
            stream_url="https://streams.example.com/sky/live.m3u8",
            country=gb,
            genres=[sports, news],
            languages=[eng],
            health_status="healthy",
            is_active=True
        )
        c6 = Channel(
            external_id="ClassicMusic.uk",
            name="Classic Music TV",
            logo_url="https://example.com/classic.png",
            stream_url="https://streams.example.com/classic/live.m3u8",
            country=gb,
            genres=[music],
            languages=[eng],
            health_status="unknown",
            is_active=True
        )
        # Inactive channel (should never appear in public catalog)
        c7 = Channel(
            external_id="Inactive.us",
            name="Defunct Channel",
            logo_url="https://example.com/defunct.png",
            stream_url="https://streams.example.com/defunct/live.m3u8",
            country=us,
            genres=[news],
            languages=[eng],
            health_status="unavailable",
            is_active=False
        )
        db.session.add_all([c1, c2, c3, c4, c5, c6, c7])
        db.session.flush()

        # Add recent health checks for c1
        check1 = StreamCheck(
            channel_id=c1.id,
            outcome="healthy",
            http_status=200,
            response_time_ms=185.4,
            diagnostic_reason="Valid HLS playlist",
            checked_at=datetime.now(timezone.utc)
        )
        db.session.add(check1)
        c1_id = c1.id
        c7_id = c7.id
        db.session.commit()

        return {
            "c1_id": c1_id,
            "c7_id": c7_id
        }


def test_get_channels_empty_catalog(client):
    """Verify /api/channels returns an empty structure when no channels exist."""
    response = client.get("/api/channels")
    assert response.status_code == 200
    assert response.is_json
    data = response.get_json()
    assert data["data"] == []
    assert data["pagination"]["total_items"] == 0
    assert data["pagination"]["total_pages"] == 0
    assert data["pagination"]["page"] == 1
    assert data["pagination"]["has_prev"] is False
    assert data["pagination"]["has_next"] is False


def test_get_channels_default_pagination(client, sample_catalog):
    """Verify default pagination returns active channels in deterministic order."""
    response = client.get("/api/channels")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["pagination"]["total_items"] == 6  # Excludes c7 (inactive)
    assert payload["pagination"]["page"] == 1
    assert payload["pagination"]["per_page"] == 20
    assert len(payload["data"]) == 6

    # Verify deterministic ordering: alphabetical by name (case-insensitive)
    names = [c["name"] for c in payload["data"]]
    assert names == sorted(names, key=lambda s: s.lower())
    assert names[0] == "BBC News"
    assert names[1] == "Classic Music TV"


def test_get_channels_search_by_name(client, sample_catalog):
    """Verify ?q searches channel name case-insensitively."""
    response = client.get("/api/channels?q=sports")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["pagination"]["total_items"] == 1
    assert payload["data"][0]["name"] == "Sky Sports Premier"


def test_get_channels_search_by_external_id(client, sample_catalog):
    """Verify ?q matches tvg-id external identifier."""
    response = client.get("/api/channels?q=France24.fr")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["pagination"]["total_items"] == 1
    assert payload["data"][0]["name"] == "France 24"


def test_get_channels_filter_by_country(client, sample_catalog):
    """Verify ?country filters channels by country code case-insensitively."""
    response = client.get("/api/channels?country=gb")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["pagination"]["total_items"] == 3
    for channel in payload["data"]:
        assert channel["country"]["code"] == "GB"


def test_get_channels_filter_by_genre(client, sample_catalog):
    """Verify ?genre filters channels by genre slug or name."""
    # Filter by slug
    response = client.get("/api/channels?genre=sports")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["pagination"]["total_items"] == 2
    names = {c["name"] for c in payload["data"]}
    assert names == {"ESPN Live", "Sky Sports Premier"}

    # Filter by display name
    response_name = client.get("/api/channels?genre=News")
    assert response_name.status_code == 200
    assert response_name.get_json()["pagination"]["total_items"] == 4


def test_get_channels_filter_by_language(client, sample_catalog):
    """Verify ?language filters channels by language code or name."""
    response = client.get("/api/channels?language=fra")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["pagination"]["total_items"] == 1
    assert payload["data"][0]["name"] == "France 24"


def test_get_channels_filter_by_status(client, sample_catalog):
    """Verify ?status filters channels by stream health."""
    response = client.get("/api/channels?status=healthy")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["pagination"]["total_items"] == 3
    for c in payload["data"]:
        assert c["health_status"] == "healthy"


def test_get_channels_combined_filters(client, sample_catalog):
    """Verify combined multi-parameter filtering works properly."""
    # UK + News + Healthy
    response = client.get("/api/channels?country=GB&genre=news&status=healthy")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["pagination"]["total_items"] == 2
    names = {c["name"] for c in payload["data"]}
    assert names == {"BBC News", "Sky Sports Premier"}


def test_get_channels_empty_search_results(client, sample_catalog):
    """Verify empty result set when no channels match the criteria."""
    response = client.get("/api/channels?q=NonExistentChannelNameXYZ")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["data"] == []
    assert payload["pagination"]["total_items"] == 0
    assert payload["pagination"]["total_pages"] == 0


def test_get_channels_pagination_multiple_pages(client, sample_catalog):
    """Verify pagination navigation with custom page and per_page sizes."""
    # 6 items total; per_page=2 -> 3 pages
    # Page 1
    r1 = client.get("/api/channels?per_page=2&page=1")
    assert r1.status_code == 200
    p1 = r1.get_json()
    assert len(p1["data"]) == 2
    assert p1["pagination"]["total_pages"] == 3
    assert p1["pagination"]["has_prev"] is False
    assert p1["pagination"]["has_next"] is True

    # Page 2
    r2 = client.get("/api/channels?per_page=2&page=2")
    assert r2.status_code == 200
    p2 = r2.get_json()
    assert len(p2["data"]) == 2
    assert p2["pagination"]["has_prev"] is True
    assert p2["pagination"]["has_next"] is True

    # Page 3
    r3 = client.get("/api/channels?per_page=2&page=3")
    assert r3.status_code == 200
    p3 = r3.get_json()
    assert len(p3["data"]) == 2
    assert p3["pagination"]["has_prev"] is True
    assert p3["pagination"]["has_next"] is False


def test_get_channels_invalid_page_number(client):
    """Verify invalid page numbers return 400 Bad Request."""
    for bad_page in ["0", "-1", "abc"]:
        response = client.get(f"/api/channels?page={bad_page}")
        assert response.status_code == 400
        payload = response.get_json()
        assert payload["error"] == "Bad Request"


def test_get_channels_invalid_per_page(client):
    """Verify invalid per_page parameters return 400 Bad Request."""
    for bad_per_page in ["0", "-5", "not_an_int"]:
        response = client.get(f"/api/channels?per_page={bad_per_page}")
        assert response.status_code == 400
        payload = response.get_json()
        assert payload["error"] == "Bad Request"


def test_get_channels_exceeds_max_per_page(client):
    """Verify per_page exceeding MAX_PER_PAGE (100) returns 400."""
    response = client.get("/api/channels?per_page=101")
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"] == "Bad Request"
    assert "between 1 and 100" in payload["message"]


def test_get_channels_invalid_health_status(client):
    """Verify invalid status value returns 400 Bad Request."""
    response = client.get("/api/channels?status=invalid_status_xyz")
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"] == "Bad Request"
    assert "Invalid health status" in payload["message"]


def test_get_channel_detail_success(client, sample_catalog):
    """Verify /api/channels/<id> returns single channel details with check history."""
    c1_id = sample_catalog["c1_id"]
    response = client.get(f"/api/channels/{c1_id}")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["data"]["id"] == c1_id
    assert payload["data"]["name"] == "CNN International"
    assert payload["data"]["country"]["code"] == "US"
    assert "recent_checks" in payload["data"]
    assert len(payload["data"]["recent_checks"]) == 1
    assert payload["data"]["recent_checks"][0]["outcome"] == "healthy"


def test_get_channel_detail_not_found(client):
    """Verify /api/channels/<id> returns 404 for non-existent channel."""
    response = client.get("/api/channels/999999")
    assert response.status_code == 404
    payload = response.get_json()
    assert payload["error"] == "Not Found"
    assert payload["status"] == 404


def test_get_channel_detail_inactive_channel_404(client, sample_catalog):
    """Verify /api/channels/<id> returns 404 for inactive channels."""
    c7_id = sample_catalog["c7_id"]
    response = client.get(f"/api/channels/{c7_id}")
    assert response.status_code == 404
    payload = response.get_json()
    assert payload["error"] == "Not Found"


def test_get_filters_dynamic_aggregation(client, sample_catalog):
    """Verify /api/filters aggregates distinct options from active channels."""
    response = client.get("/api/filters")
    assert response.status_code == 200
    payload = response.get_json()

    # Active countries: US, GB, FR
    country_codes = [c["code"] for c in payload["countries"]]
    assert set(country_codes) == {"US", "GB", "FR"}

    # Active genres: news, sports, music
    genre_slugs = [g["slug"] for g in payload["genres"]]
    assert set(genre_slugs) == {"news", "sports", "music"}

    # Active languages: eng, fra
    lang_codes = [l["code"] for l in payload["languages"]]
    assert set(lang_codes) == {"eng", "fra"}

    # Status breakdown
    assert payload["statuses"]["healthy"] == 3
    assert payload["statuses"]["degraded"] == 1
    assert payload["statuses"]["unavailable"] == 1
    assert payload["statuses"]["unknown"] == 1


def test_get_filters_excludes_empty_taxonomies(client, app):
    """Verify /api/filters does not return orphaned countries or genres with 0 active channels."""
    with app.app_context():
        # Add an unused country and genre
        unused_country = Country(code="ZZ", name="Unused Land")
        unused_genre = Genre(slug="unused", name="Unused Category")
        db.session.add_all([unused_country, unused_genre])
        db.session.commit()

    response = client.get("/api/filters")
    assert response.status_code == 200
    payload = response.get_json()
    assert "ZZ" not in [c["code"] for c in payload["countries"]]
    assert "unused" not in [g["slug"] for g in payload["genres"]]


def test_api_health_endpoint(client, sample_catalog):
    """Verify /api/health accurately reports total active channels without sensitive info."""
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "healthy"
    assert payload["database"] == "connected"
    assert payload["total_active_channels"] == 6  # Excludes inactive c7
    assert "password" not in response.get_data(as_text=True)
    assert "traceback" not in response.get_data(as_text=True)


def test_api_cors_headers_applied(client):
    """Verify CORS headers are present on API responses for browser compatibility."""
    response = client.get("/api/channels")
    assert response.headers.get("Access-Control-Allow-Origin") == "*"
    assert "GET" in response.headers.get("Access-Control-Allow-Methods", "")


def test_api_database_error_handling(client, monkeypatch):
    """Verify database failures are caught and returned as clean 500 JSON errors."""
    from app.services.channel_service import ChannelService

    def mock_search_channels(*args, **kwargs):
        raise RuntimeError("Simulated database failure")

    monkeypatch.setattr(ChannelService, "search_channels", mock_search_channels)

    response = client.get("/api/channels")
    assert response.status_code == 500
    payload = response.get_json()
    assert payload["error"] == "Internal Server Error"
    assert "traceback" not in response.get_data(as_text=True)


def test_report_channel_issue_success(client, sample_catalog):
    """Verify successful anonymous issue report submission returns 201 Created."""
    c1_id = sample_catalog["c1_id"]
    payload = {
        "issue_type": "offline",
        "description": "Stream stopped working around 10am."
    }
    response = client.post(
        f"/api/channels/{c1_id}/report",
        json=payload,
        content_type="application/json"
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["status"] == "success"
    assert "recorded anonymously" in data["message"]
    assert data["report"]["channel_id"] == c1_id
    assert data["report"]["issue_type"] == "offline"


def test_report_channel_issue_invalid_reason(client, sample_catalog):
    """Verify invalid issue_type returns 400 Bad Request."""
    c1_id = sample_catalog["c1_id"]
    response = client.post(
        f"/api/channels/{c1_id}/report",
        json={"issue_type": "invalid_issue_xyz"},
        content_type="application/json"
    )
    assert response.status_code == 400
    data = response.get_json()
    assert data["error"] == "Bad Request"


def test_report_channel_issue_channel_not_found(client, sample_catalog):
    """Verify reporting issue for non-existent channel returns 404 Not Found."""
    response = client.post(
        "/api/channels/99999/report",
        json={"issue_type": "offline"},
        content_type="application/json"
    )
    assert response.status_code == 404
    data = response.get_json()
    assert data["error"] == "Not Found"


def test_report_channel_issue_inactive_channel(client, sample_catalog):
    """Verify reporting issue on inactive channel returns 404 Not Found."""
    c7_id = sample_catalog["c7_id"]  # Inactive channel in sample_catalog
    response = client.post(
        f"/api/channels/{c7_id}/report",
        json={"issue_type": "playback_error"},
        content_type="application/json"
    )
    assert response.status_code == 404


