# TESTING STRATEGY & GUIDE

## 1. Overview
The Global Live TV Platform enforces strict automated testing across all nine development phases to guarantee system stability, SSRF protection, playlist parsing resilience, database integrity, and REST API correctness.

All automated tests are written with `pytest` and utilize Flask's native test client and temporary in-memory SQLite fixtures (`sqlite:///:memory:`).

---

## 2. Test Suite Architecture

```
tests/
|-- __init__.py
|-- conftest.py             # Global test fixtures (app, client, isolated db_session)
|-- test_app.py             # Step 1, 5, 6, 7: App factory, configs, error handlers, static & UI templates (19 tests)
|-- test_models.py          # Step 2: Channel, Country, Genre, Language, StreamCheck ORM & cascades (4 tests)
|-- test_parser.py          # Step 2: M3U/EXTINF playlist parser, quotes, commas, SSRF URL rejection (8 tests)
|-- test_health_checker.py  # Step 3: Stream health checking, HLS manifest validation & redirect SSRF (9 tests)
|-- test_ingestion.py       # Step 2 & 8: Multi-playlist import, enrichment, idempotence, dry-run (6 tests)
|-- test_api.py             # Step 4 & 7: REST API search, taxonomy filters, pagination, reporting, CORS (21 tests)
|-- test_refresh.py         # Step 8: JobLock concurrency, stale lock reclamation, TTL cache, audit log (11 tests)
`-- test_audit_e2e.py       # Step 9: End-to-end user journeys, comprehensive SSRF IP suite, cascades (17 tests)
```

**Total Tests**: **101 Tests** | **Status**: **100% Passing**

---

## 3. Running the Test Suite

### Run All Tests
```powershell
# Windows (PowerShell)
.\.venv\Scripts\pytest -v

# Linux / macOS
./.venv/bin/pytest -v
```

### Run with Coverage Reporting
```powershell
.\.venv\Scripts\pytest -v --cov=app --cov-report=term-missing
```

### Run a Specific Module
```powershell
.\.venv\Scripts\pytest -v tests/test_audit_e2e.py
```

---

## 4. Test Breakdown by Development Step

### Step 1: Project Foundation & Static Delivery (`tests/test_app.py`)
- Application factory creation across `development`, `testing`, and `production` configurations.
- Health check endpoint (`GET /api/health`) returns 200 OK.
- Landing page (`GET /`) and About page (`GET /about`) render correctly.
- Static assets (`/static/css/style.css`, `/static/js/main.js`, `/static/js/vendor/hls.min.js`) are served with correct MIME types.
- Dual-mode error handlers: HTML for web browser navigation, JSON for `/api/*` endpoints.

### Step 2: Database Layer & Ingestion (`tests/test_models.py`, `tests/test_parser.py`, `tests/test_ingestion.py`)
- Database schema constraints, foreign keys, and relationships.
- Cascading delete verification (deleting a channel deletes its stream checks).
- Robust EXTINF line parser handling quoted attributes, commas inside titles, missing attributes, and inconsistent line endings (`\r\n` vs `\n`).
- Security validation: Discarding unsafe schemes (`ftp://`, `file://`, `javascript:`) and loopback/private IP addresses during parsing.
- Idempotent upserts: Repeated imports do not create duplicate records.
- Graceful error recovery: Catalog is preserved if remote playlist download fails.

### Step 3: Stream Health-Checking Engine (`tests/test_health_checker.py`)
- HTTP manifest syntax validation (`#EXTM3U`, `#EXT-X-VERSION`, `#EXT-X-TARGETDURATION`).
- Rejection of non-manifest responses (HTML login pages, 404s, empty responses).
- Strict SSRF blocking during stream checks and across HTTP redirect hops.
- Consecutive failure progression: `healthy` -> `degraded` -> `unavailable`.

### Step 4 & 7: REST API & Integration (`tests/test_api.py`)
- Catalog search (`?q=...`) across channel names and categories.
- Combined taxonomy filtering (`?country=...&genre=...&language=...&status=...`).
- Deterministic pagination with boundary protection (`page < 1`, `per_page > 100`).
- Dynamic taxonomy filter aggregation (`GET /api/filters`).
- Anonymous issue reporting (`POST /api/channels/<id>/report`) with reason validation.
- Cross-Origin Resource Sharing (CORS) headers applied to all API endpoints.

### Step 8: Automated Refresh & Concurrency (`tests/test_refresh.py`)
- Cross-platform process mutex (`JobLock`) acquiring and releasing locks cleanly.
- Overlapping worker prevention: Secondary workers immediately abort if a job is in progress.
- Stale process lock reclamation when a worker dies unexpectedly.
- Job timeout expiry reclamation for long-stalled operations.
- In-memory taxonomy filter TTL caching with cache hit/miss and force-refresh behaviors.
- Incremental channel prioritization for health checks.
- Audit recording in `job_runs` table with start time, completion time, duration, and metrics.

### Step 9: Final Release Audit & E2E Validation (`tests/test_audit_e2e.py`)
- Complete end-to-end user journey: Catalog discovery -> taxonomy filtering -> channel detail lookup -> stream verification -> issue report submission.
- Exhaustive SSRF defense test matrix against private IP ranges (`127.0.0.1`, `localhost`, `10.0.0.1`, `192.168.1.100`, `172.16.0.5`, `169.254.169.254`, `[::1]`) and prohibited URL schemes (`ftp://`, `file://`, `javascript:`, `gopher://`).
- Inactive channel masking: Ensures channels marked `is_active = 0` are completely excluded from public discovery queries, details lookups, and reporting.
- API boundary and invalid parameter resilience.
