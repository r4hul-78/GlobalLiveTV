"""
Step 9 Final Audit: End-to-End User Journey, Security SSRF Defense, and Database Integrity Tests
Validates the complete application lifecycle, boundary conditions, privacy, and release readiness.
"""
import json
import pytest
from datetime import datetime, timezone

from app import db
from app.models import Channel, Country, Genre, Language, StreamCheck, ChannelReport, JobRun
from app.services.security import is_safe_url
from app.services.health_checker import (
    safe_http_get,
    StreamHealthChecker,
    StreamHealthResult,
    OUTCOME_HEALTHY
)
from app.services.channel_service import ChannelService
from app.services.ingestion_service import IngestionService
from app.jobs.health_job import run_health_job


SAMPLE_AUDIT_M3U = """#EXTM3U
#EXTINF:-1 tvg-id="Audit.News.US" tvg-name="Audit News USA" tvg-logo="https://example.com/logo_us.png" group-title="News",Audit News USA
https://example.com/live/us_stream.m3u8
#EXTINF:-1 tvg-id="Audit.Sports.FR" tvg-name="Audit Sports France" tvg-logo="https://example.com/logo_fr.png" group-title="Sports",Audit Sports France
https://example.com/live/fr_stream.m3u8
"""


# -----------------------------------------------------------------------------
# 1. End-to-End User Journey Audit
# -----------------------------------------------------------------------------

def test_audit_e2e_complete_user_journey(client, app, monkeypatch):
    """
    Simulates a full end-to-end user journey:
    1. Empty catalog check
    2. Playlist ingestion & enrichment
    3. Multi-taxonomy filtering and search
    4. Channel details inspection
    5. Anonymous stream issue reporting
    6. Background health probe and status aggregation
    """
    with app.app_context():
        # Step 1: Empty catalog check
        res = client.get("/api/channels")
        assert res.status_code == 200
        data = res.get_json()
        assert data["pagination"]["total_items"] == 0
        assert data["data"] == []

        # Step 2: Ingest catalog records
        service = IngestionService()
        country_m3u = """#EXTM3U
#EXTINF:-1 tvg-id="Audit.News.US" tvg-country="US" group-title="United States",Audit News USA
https://example.com/live/us_stream.m3u8
#EXTINF:-1 tvg-id="Audit.Sports.FR" tvg-country="FR" group-title="France",Audit Sports France
https://example.com/live/fr_stream.m3u8
"""
        category_m3u = """#EXTM3U
#EXTINF:-1 tvg-id="Audit.News.US" group-title="News",Audit News USA
https://example.com/live/us_stream.m3u8
#EXTINF:-1 tvg-id="Audit.Sports.FR" group-title="Sports",Audit Sports France
https://example.com/live/fr_stream.m3u8
"""

        ingest_res = service.ingest_from_content(
            main_content=SAMPLE_AUDIT_M3U,
            country_content=country_m3u,
            category_content=category_m3u,
            dry_run=False
        )
        assert ingest_res.imported == 2
        ChannelService.invalidate_filter_cache()

        # Step 3: Search and Filter channels
        # Search by name
        s_res = client.get("/api/channels?q=Sports")
        assert s_res.status_code == 200
        s_data = s_res.get_json()
        assert s_data["pagination"]["total_items"] == 1
        assert s_data["data"][0]["name"] == "Audit Sports France"

        # Combined country + genre filter
        c_res = client.get("/api/channels?country=US&genre=news")
        assert c_res.status_code == 200
        c_data = c_res.get_json()
        assert c_data["pagination"]["total_items"] == 1
        assert c_data["data"][0]["external_id"] == "Audit.News.US"

        # Step 4: Channel detail view
        channel_id = c_data["data"][0]["id"]
        d_res = client.get(f"/api/channels/{channel_id}")
        assert d_res.status_code == 200
        channel_detail = d_res.get_json()["data"]
        assert channel_detail["id"] == channel_id

        assert channel_detail["stream_url"] == "https://example.com/live/us_stream.m3u8"
        assert channel_detail["country"]["code"] == "US"
        assert any(g["slug"] == "news" for g in channel_detail["genres"])

        # Step 5: Anonymous issue reporting
        report_payload = {
            "issue_type": "offline",
            "description": "Stream is returning 404 manifest."
        }
        r_res = client.post(
            f"/api/channels/{channel_id}/report",
            json=report_payload,
            content_type="application/json"
        )
        assert r_res.status_code == 201
        report_data = r_res.get_json()
        assert report_data["status"] == "success"

        # Verify report in database
        saved_report = ChannelReport.query.filter_by(channel_id=channel_id).first()
        assert saved_report is not None
        assert saved_report.issue_type == "offline"
        assert saved_report.description == "Stream is returning 404 manifest."


        # Step 6: Health checking audit
        monkeypatch.setattr(
            StreamHealthChecker,
            "probe_stream_network",
            lambda self, cid, url: StreamHealthResult(
                channel_id=cid,
                outcome=OUTCOME_HEALTHY,
                http_status=200,
                response_time_ms=62.0,
                diagnostic_reason="Valid test manifest",
                is_live_manifest=True
            )
        )

        health_summary = run_health_job(limit=10, use_lock=False)
        assert health_summary["total_checked"] == 2
        assert health_summary["healthy"] == 2

        # Verify filters reflect updated health status
        f_res = client.get("/api/filters")
        assert f_res.status_code == 200
        f_data = f_res.get_json()
        assert f_data["statuses"].get("healthy", 0) == 2


# -----------------------------------------------------------------------------
# 2. Comprehensive Security and SSRF Defense Audit
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("prohibited_url", [
    "http://127.0.0.1/live/test.m3u8",
    "http://localhost:5000/api/health",
    "http://10.0.0.1/stream.m3u8",
    "http://192.168.1.100:8080/live.m3u8",
    "http://172.16.0.5/stream.m3u8",
    "http://169.254.169.254/latest/meta-data/",
    "http://[::1]/stream.m3u8",
    "ftp://example.com/stream.m3u8",
    "file:///etc/passwd",
    "javascript:alert(1)",
    "gopher://example.com/",
])
def test_audit_ssrf_prohibited_destinations(prohibited_url):
    """Exhaustive SSRF defense verification for prohibited network addresses."""
    is_safe, reason = is_safe_url(prohibited_url, resolve_dns=False)
    assert is_safe is False
    assert ("prohibited" in reason.lower() or "only http and https" in reason.lower())


def test_audit_safe_http_get_rejects_ssrf_immediately():
    """Verify safe_http_get will never send a request to a prohibited destination."""
    code, _, _, _, err = safe_http_get("http://169.254.169.254/latest/meta-data/")
    assert code == 0
    assert "Blocked unsafe destination" in err


# -----------------------------------------------------------------------------
# 3. Database Integrity and Constraint Audit
# -----------------------------------------------------------------------------

def test_audit_channel_cascade_deletes_stream_checks(app):
    """Ensure deleting a channel cleanly cascade-deletes associated stream checks."""
    with app.app_context():
        channel = Channel(name="Cascade Test", stream_url="https://example.com/casc.m3u8")
        db.session.add(channel)
        db.session.commit()

        check = StreamCheck(
            channel_id=channel.id,
            outcome="healthy",
            http_status=200,
            response_time_ms=50.0
        )
        db.session.add(check)
        db.session.commit()

        check_id = check.id
        assert StreamCheck.query.get(check_id) is not None

        # Delete channel
        db.session.delete(channel)
        db.session.commit()

        # StreamCheck must be deleted automatically
        assert StreamCheck.query.get(check_id) is None


def test_audit_inactive_channels_hidden_from_public_catalog(client, app):
    """Verify channels marked is_active=False do not leak into search, details, or filters."""
    with app.app_context():
        ChannelService.invalidate_filter_cache()
        inactive_ch = Channel(
            name="Deactivated Channel",
            stream_url="https://example.com/inactive.m3u8",
            is_active=False
        )
        db.session.add(inactive_ch)
        db.session.commit()

        ch_id = inactive_ch.id

        # Search must not return it
        res = client.get("/api/channels?q=Deactivated")
        assert res.get_json()["pagination"]["total_items"] == 0

        # Direct ID lookup must return 404
        d_res = client.get(f"/api/channels/{ch_id}")
        assert d_res.status_code == 404

        # Issue reporting on inactive channel must return 404
        r_res = client.post(f"/api/channels/{ch_id}/report", json={"reason": "offline"})
        assert r_res.status_code == 404


# -----------------------------------------------------------------------------
# 4. API Boundary and Error Handling Audit
# -----------------------------------------------------------------------------

def test_audit_api_boundary_validation(client, app):
    """Test boundary and negative cases for API parameter validation."""
    # Negative page
    r1 = client.get("/api/channels?page=-1")
    assert r1.status_code == 400
    assert "error" in r1.get_json()

    # Non-integer page
    r2 = client.get("/api/channels?page=abc")
    assert r2.status_code == 400

    # per_page exceeds max allowed
    r3 = client.get("/api/channels?per_page=999")
    assert r3.status_code == 400

    # Invalid stream health status
    r4 = client.get("/api/channels?status=non_existent_status")
    assert r4.status_code == 400

    # Non-existent channel ID
    r5 = client.get("/api/channels/999999")
    assert r5.status_code == 404

    with app.app_context():
        ch = Channel(name="Boundary Test", stream_url="https://example.com/b.m3u8", is_active=True)
        db.session.add(ch)
        db.session.commit()
        ch_id = ch.id

    # Invalid report reason enum on existing channel
    r6 = client.post(f"/api/channels/{ch_id}/report", json={"issue_type": "arbitrary_unauthorized_reason"})
    assert r6.status_code == 400


    # Empty payload to report endpoint
    r7 = client.post(f"/api/channels/{ch_id}/report", json={})
    assert r7.status_code == 400


def test_audit_error_handlers_content_type(client):
    """Verify HTML requests receive HTML 404 and API requests receive JSON 404."""
    # HTML request
    html_res = client.get("/non-existent-page", headers={"Accept": "text/html"})
    assert html_res.status_code == 404
    assert b"404" in html_res.data

    # API JSON request
    json_res = client.get("/api/non-existent-endpoint", headers={"Accept": "application/json"})
    assert json_res.status_code == 404
    assert json_res.is_json
    assert "error" in json_res.get_json()
