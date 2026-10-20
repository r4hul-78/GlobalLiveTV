import json
from app import create_app
from app.config import DevelopmentConfig, TestingConfig, ProductionConfig


def test_app_factory_configurations():
    """Verify application factory initializes correctly under different configurations."""
    dev_app = create_app("development")
    assert dev_app.config["DEBUG"] is True
    assert dev_app.config["TESTING"] is False

    test_app = create_app("testing")
    assert test_app.config["TESTING"] is True
    assert test_app.config["SQLALCHEMY_DATABASE_URI"] == "sqlite:///:memory:"

    prod_app = create_app("production")
    assert prod_app.config["DEBUG"] is False
    assert prod_app.config["TESTING"] is False


def test_landing_page_loads(client):
    """Verify landing page renders successfully with proper branding."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"Global Live TV" in response.data
    assert b"Step 1" in response.data


def test_about_page_loads(client):
    """Verify the ethics and about page renders successfully."""
    response = client.get("/about")
    assert response.status_code == 200
    assert b"Source Attribution" in response.data


def test_health_check_endpoint(client):
    """Verify /api/health returns valid JSON with healthy status."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.is_json
    data = response.get_json()
    assert data["status"] == "healthy"
    assert data["service"] == "Global Live TV Platform"
    assert data["database"] == "connected"
    assert "timestamp" in data


def test_static_css_served(client):
    """Verify that CSS static assets are served with correct MIME type."""
    response = client.get("/static/css/style.css")
    assert response.status_code == 200
    assert "text/css" in response.content_type
    assert b"Global Live TV Platform" in response.data


def test_static_js_served(client):
    """Verify that JavaScript static assets are served with correct MIME type."""
    response = client.get("/static/js/main.js")
    assert response.status_code == 200
    assert "javascript" in response.content_type or "text/plain" in response.content_type
    assert b"initHealthMonitoring" in response.data


def test_404_error_handler_html(client):
    """Verify 404 handler returns customized HTML for web routes."""
    response = client.get("/non-existent-web-page")
    assert response.status_code == 404
    assert b"Page Not Found" in response.data


def test_404_error_handler_api(client):
    """Verify 404 handler returns structured JSON for API routes."""
    response = client.get("/api/non-existent-endpoint")
    assert response.status_code == 404
    assert response.is_json
    data = response.get_json()
    assert data["error"] == "Not Found"
    assert data["status"] == 404


def test_discovery_ui_components_rendered(client):
    """Verify landing page renders all required Step 5 Channel Discovery UI elements."""
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    required_ids = [
        "channelSearchInput",
        "btnClearSearch",
        "filterCountry",
        "filterGenre",
        "filterLanguage",
        "filterStatus",
        "btnClearFilters",
        "resultsSummary",
        "activeFilterChips",
        "skeletonGrid",
        "channelGrid",
        "emptyState",
        "errorState",
        "paginationNav",
        "btnPrevPage",
        "btnNextPage",
        "pageIndicators",
        "channelDetailsModal",
        "btnModalClose",
        "modalChannelTitle",
        "modalStreamUrl"
    ]
    for element_id in required_ids:
        assert f'id="{element_id}"' in html, f"Missing required discovery element ID: {element_id}"


def test_discovery_css_rules_present(client):
    """Verify style.css serves all Step 5 discovery classes."""
    response = client.get("/static/css/style.css")
    assert response.status_code == 200
    css = response.get_data(as_text=True)

    required_selectors = [
        ".search-wrapper",
        ".search-input",
        ".discovery-toolbar",
        ".channel-grid",
        ".channel-card",
        ".channel-logo-container",
        ".status-badge",
        ".skeleton-shimmer",
        ".pagination-nav",
        ".modal-backdrop",
        ".modal-dialog"
    ]
    for selector in required_selectors:
        assert selector in css, f"Missing required CSS selector: {selector}"


def test_discovery_js_controller_present(client):
    """Verify main.js includes Step 5 catalog fetching, rendering, and modal controllers."""
    response = client.get("/static/js/main.js")
    assert response.status_code == 200
    js = response.get_data(as_text=True)

    required_identifiers = [
        "initChannelDiscovery",
        "loadFilterMetadata",
        "fetchChannels",
        "renderChannelCards",
        "renderChannelLogo",
        "renderInitialsFallback",
        "formatHealthStatus",
        "getCountryFlag",
        "openChannelModal"
    ]
    for identifier in required_identifiers:
        assert identifier in js, f"Missing required JS identifier: {identifier}"


def test_player_ui_components_rendered(client):
    """Verify landing page renders all required Step 6 HLS Video Player UI elements."""
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    required_player_elements = [
        "playerModal",
        "playerChannelName",
        "btnTestStream",
        "btnClosePlayer",
        "videoContainer",
        "hlsVideoPlayer",
        "playerLoadingOverlay",
        "playerLoadingText",
        "playerAutoplayOverlay",
        "btnUnmuteAutoplay",
        "playerErrorOverlay",
        "playerErrorTitle",
        "playerErrorDescription",
        "playerErrorReason",
        "btnRetryPlayer",
        "btnOpenStreamExternal",
        "btnCloseFromError",
        "playerHealthTag",
        "playerStreamUrlDisplay",
        "btnCopyPlayerUrl"
    ]
    for element_id in required_player_elements:
        assert f'id="{element_id}"' in html, f"Missing required player element ID: {element_id}"


def test_player_css_rules_present(client):
    """Verify style.css serves all Step 6 video player classes and overlay styles."""
    response = client.get("/static/css/style.css")
    assert response.status_code == 200
    css = response.get_data(as_text=True)

    required_selectors = [
        ".player-modal-backdrop",
        ".player-modal-dialog",
        ".player-header",
        ".video-container",
        ".video-element",
        ".video-overlay",
        ".spinner-ring",
        ".autoplay-icon",
        ".error-reason-pill",
        ".player-footer"
    ]
    for selector in required_selectors:
        assert selector in css, f"Missing required player CSS selector: {selector}"


def test_player_vendor_asset_served(client):
    """Verify pinned HLS.js vendor script is served with HTTP 200 and valid JS content."""
    response = client.get("/static/js/vendor/hls.min.js")
    assert response.status_code == 200
    assert "javascript" in response.content_type or "text/plain" in response.content_type
    assert len(response.data) > 100000  # Pinned bundle is ~413 KB
    assert b"Hls" in response.data


def test_player_js_controller_logic(client):
    """Verify main.js includes Step 6 HLS player lifecycle, recovery, and fallback logic."""
    response = client.get("/static/js/main.js")
    assert response.status_code == 200
    js = response.get_data(as_text=True)

    required_symbols = [
        "initHlsPlayer",
        "destroyPlayer",
        "attemptPlaySafely",
        "playChannel",
        "showPlayerError",
        "test-streams.mux.dev",
        "Hls.isSupported",
        "canPlayType"
    ]
    for sym in required_symbols:
        assert sym in js, f"Missing required HLS player JS symbol/pattern: {sym}"


def test_step7_integration_components_rendered(client):
    """Verify landing page renders all Step 7 integration elements (reporting, a11y announcer)."""
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    required_integration_ids = [
        "a11yAnnouncer",
        "reportModal",
        "reportModalTitle",
        "reportTargetChannelName",
        "reportIssueForm",
        "reportChannelId",
        "reportIssueType",
        "reportDescription",
        "reportFeedbackMessage",
        "btnCancelReport",
        "btnSubmitReport",
        "btnReportClose",
        "btnReportPlayer",
        "btnReportFromDetails"
    ]
    for element_id in required_integration_ids:
        assert f'id="{element_id}"' in html, f"Missing required integration element ID: {element_id}"


def test_step7_css_integration_rules_present(client):
    """Verify style.css includes accessibility utilities and issue reporting modal styles."""
    response = client.get("/static/css/style.css")
    assert response.status_code == 200
    css = response.get_data(as_text=True)

    required_selectors = [
        ".sr-only",
        ".report-dialog",
        ".report-form",
        ".form-group",
        ".form-label",
        ".report-feedback"
    ]
    for selector in required_selectors:
        assert selector in css, f"Missing required CSS selector: {selector}"


def test_step7_js_integration_utilities(client):
    """Verify main.js includes Step 7 centralized API client, a11y announcer, and URL sync."""
    response = client.get("/static/js/main.js")
    assert response.status_code == 200
    js = response.get_data(as_text=True)

    required_identifiers = [
        "apiClient",
        "announceToScreenReader",
        "syncUrlState",
        "initIssueReporting",
        "openReportModal",
        "popstate"
    ]
    for ident in required_identifiers:
        assert ident in js, f"Missing required integration JS identifier: {ident}"


def test_step7_html_disclaimers_and_ethics(client):
    """Verify landing page includes clear direct-playback architecture and attribution notes."""
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert "Zero Proxy Architecture" in html
    assert "Direct Playback Architecture" in html
    assert "external broadcaster servers" in html


