import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from app.models import Channel, StreamCheck
from app.services.health_checker import (
    StreamHealthChecker,
    OUTCOME_HEALTHY,
    OUTCOME_DEGRADED,
    OUTCOME_UNAVAILABLE,
    OUTCOME_UNSUPPORTED
)
from app.services.security import is_safe_url, safe_http_get, resolve_relative_url


SAMPLE_VALID_MEDIA_PLAYLIST = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:10
#EXT-X-MEDIA-SEQUENCE:100
#EXTINF:10.0,
segment100.ts
#EXTINF:10.0,
segment101.ts
#EXTINF:10.0,
segment102.ts
"""

SAMPLE_VALID_MASTER_PLAYLIST = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-STREAM-INF:BANDWIDTH=1280000,RESOLUTION=1280x720
chunklist_720p.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=2560000,RESOLUTION=1920x1080
chunklist_1080p.m3u8
"""

SAMPLE_HTML_ERROR_PAGE = """<!DOCTYPE html>
<html>
<head><title>404 Not Found - Captive Portal</title></head>
<body><h1>Stream Unavailable</h1></body>
</html>
"""


def test_inspect_valid_media_playlist():
    """Verify inspector marks valid media playlist with active segments as healthy."""
    checker = StreamHealthChecker()
    outcome, reason, is_live = checker.inspect_manifest_content(
        SAMPLE_VALID_MEDIA_PLAYLIST,
        base_url="https://example.com/live/stream.m3u8"
    )
    assert outcome == OUTCOME_HEALTHY
    assert is_live is True
    assert "active segments" in reason


def test_inspect_rejects_html_content():
    """Verify inspector rejects HTML web pages returning HTTP 200 as unsupported."""
    checker = StreamHealthChecker()
    outcome, reason, is_live = checker.inspect_manifest_content(
        SAMPLE_HTML_ERROR_PAGE,
        base_url="https://example.com/stream.m3u8"
    )
    assert outcome == OUTCOME_UNSUPPORTED
    assert is_live is False
    assert "HTML document" in reason


def test_inspect_rejects_missing_extm3u_header():
    """Verify inspector rejects plain text or malformed files missing #EXTM3U."""
    checker = StreamHealthChecker()
    outcome, reason, is_live = checker.inspect_manifest_content(
        "Some random non-HLS text content",
        base_url="https://example.com/stream"
    )
    assert outcome == OUTCOME_UNSUPPORTED
    assert is_live is False
    assert "Missing #EXTM3U" in reason


def test_inspect_empty_content():
    """Verify inspector handles empty content gracefully."""
    checker = StreamHealthChecker()
    outcome, reason, is_live = checker.inspect_manifest_content("", base_url="https://example.com")
    assert outcome == OUTCOME_UNAVAILABLE
    assert is_live is False


def test_stream_check_ssrf_rejection(app):
    """Verify stream health check immediately rejects prohibited IP ranges without network call."""
    with app.app_context():
        from app import db
        channel = Channel(
            name="Loopback Attack Stream",
            stream_url="http://127.0.0.1:8080/live/malicious.m3u8"
        )
        db.session.add(channel)
        db.session.commit()

        checker = StreamHealthChecker()
        result = checker.check_stream(channel)

        assert result.outcome == OUTCOME_UNSUPPORTED
        assert "Blocked unsafe destination" in result.diagnostic_reason
        assert channel.health_status == OUTCOME_UNSUPPORTED

        # Verify audit record created
        audit = StreamCheck.query.filter_by(channel_id=channel.id).first()
        assert audit is not None
        assert audit.outcome == OUTCOME_UNSUPPORTED


@patch("app.services.health_checker.safe_http_get")
def test_stream_check_success_flow(mock_get, app):
    """Verify successful manifest probe marks channel healthy and records latency."""
    mock_get.return_value = (
        200,
        {"Content-Type": "application/vnd.apple.mpegurl"},
        SAMPLE_VALID_MEDIA_PLAYLIST.encode("utf-8"),
        145.2,
        ""
    )

    with app.app_context():
        from app import db
        channel = Channel(
            name="Healthy Stream",
            stream_url="https://example.com/live/playlist.m3u8"
        )
        db.session.add(channel)
        db.session.commit()

        checker = StreamHealthChecker()
        result = checker.check_stream(channel)

        assert result.outcome == OUTCOME_HEALTHY
        assert result.response_time_ms == 145.2
        assert channel.health_status == OUTCOME_HEALTHY
        assert channel.consecutive_failures == 0
        assert channel.last_successful_check is not None


@patch("app.services.health_checker.safe_http_get")
def test_consecutive_failures_progression(mock_get, app):
    """Verify temporary failure degrades status; only reaches unavailable after max_failures."""
    with app.app_context():
        from app import db
        channel = Channel(
            name="Flaky Stream",
            stream_url="https://example.com/flaky.m3u8"
        )
        db.session.add(channel)
        db.session.commit()

        checker = StreamHealthChecker(max_failures=3)

        # 1st Failure: Timeout
        mock_get.return_value = (0, {}, b"", 3000.0, "Request timed out after 3s")
        res1 = checker.check_stream(channel)
        assert res1.outcome == OUTCOME_DEGRADED
        assert channel.consecutive_failures == 1
        assert channel.health_status == OUTCOME_DEGRADED

        # 2nd Failure: HTTP 500
        mock_get.return_value = (500, {}, b"", 120.0, "HTTP request failed: Server Error")
        res2 = checker.check_stream(channel)
        assert res2.outcome == OUTCOME_DEGRADED
        assert channel.consecutive_failures == 2
        assert channel.health_status == OUTCOME_DEGRADED

        # 3rd Failure: Reaches max_failures threshold
        mock_get.return_value = (503, {}, b"", 80.0, "HTTP request failed: Service Unavailable")
        res3 = checker.check_stream(channel)
        assert res3.outcome == OUTCOME_UNAVAILABLE
        assert channel.consecutive_failures == 3
        assert channel.health_status == OUTCOME_UNAVAILABLE

        # Recovery: returns valid manifest
        mock_get.return_value = (200, {}, SAMPLE_VALID_MEDIA_PLAYLIST.encode("utf-8"), 110.0, "")
        res4 = checker.check_stream(channel)
        assert res4.outcome == OUTCOME_HEALTHY
        assert channel.consecutive_failures == 0
        assert channel.health_status == OUTCOME_HEALTHY


@patch("requests.get")
def test_safe_http_get_blocks_redirect_ssrf(mock_requests_get):
    """Verify that a 302 redirect leading to a private internal network IP is blocked."""
    # Step 1: Public URL responds with 302 redirect pointing to private IP
    mock_resp_redirect = MagicMock()
    mock_resp_redirect.status_code = 302
    mock_resp_redirect.headers = {"Location": "http://192.168.1.1/admin/stream.m3u8"}
    mock_requests_get.return_value = mock_resp_redirect

    status, headers, content, elapsed, err = safe_http_get("https://example.com/redirect-attack")
    assert status == 0
    assert "Redirect to unsafe destination blocked" in err


@patch("app.services.health_checker.safe_http_get")
def test_batch_health_checker_execution(mock_get, app):
    """Verify batch health check executes across multiple channels and commits audit entries."""
    mock_get.return_value = (200, {}, SAMPLE_VALID_MEDIA_PLAYLIST.encode("utf-8"), 95.0, "")

    with app.app_context():
        from app import db
        ch1 = Channel(name="Ch 1", stream_url="https://example.com/ch1.m3u8")
        ch2 = Channel(name="Ch 2", stream_url="https://example.com/ch2.m3u8")
        ch3 = Channel(name="Ch 3", stream_url="https://example.com/ch3.m3u8")
        db.session.add_all([ch1, ch2, ch3])
        db.session.commit()

        checker = StreamHealthChecker()
        results = checker.check_batch([ch1, ch2, ch3], concurrency=3, save=True)

        assert len(results) == 3
        assert all(r.outcome == OUTCOME_HEALTHY for r in results)

        # Verify audit records in DB
        checks_count = StreamCheck.query.filter(StreamCheck.channel_id.in_([ch1.id, ch2.id, ch3.id])).count()
        assert checks_count == 3
