# ARCHITECTURE DOCUMENTATION

## 1. System Overview
The Global Live TV Platform follows a modular layered architecture designed for separation of concerns, testability, and security.

```
                      +---------------------------------------+
                      |          Browser Client               |
                      |  - Vanilla HTML5 / CSS3 / ES6 JS     |
                      |  - Pinned HLS.js Video Player         |
                      +-------------------+-------------------+
                                          |
                        +-----------------+-----------------+
                        | (Metadata & UI)                   | (Direct HLS Stream)
                        v                                   v
             +-----------------------+           +-----------------------+
             |   Flask Web Server    |           |  External TV Stream   |
             |   (App Factory)       |           |  CDNs & Broadcasters  |
             +-----------+-----------+           +-----------------------+
                         |
           +-------------+-------------+
           |                           |
           v                           v
  +-----------------+         +-----------------+
  | Blueprints:     |         | SQLAlchemy ORM  |
  | - main (HTML)   |         | Database Engine |
  | - api (JSON)    |         +--------+--------+
  +-----------------+                  |
                                       v
                              +-----------------+
                              | SQLite / Postgre|
                              |   Relational DB |
                              +-----------------+

  ================ Background Tasks (Decoupled CLI / Jobs) ================
  +-------------------------+                 +-------------------------+
  | Ingestion Engine        |                 | Stream Health Checker   |
  | - iptv-org M3U Parser   |                 | - Safe Probing Engine   |
  | - Idempotent Upserts    |                 | - SSRF / DNS Protection |
  +-------------------------+                 +-------------------------+
```

---

## 2. Directory Structure
```
d:/Development/IPTV/
|-- app/
|   |-- __init__.py           # Application factory (create_app), extension setup
|   |-- config.py             # Config classes (Development, Testing, Production)
|   |-- models/               # SQLAlchemy models
|   |   |-- __init__.py
|   |   |-- channel.py        # Channel entity with composite performance indexes
|   |   |-- country.py        # Country taxonomy entity
|   |   |-- genre.py          # Genre taxonomy entity & channel_genres table
|   |   |-- language.py       # Language taxonomy entity & channel_languages table
|   |   |-- stream_check.py   # Health check audit records
|   |   |-- channel_report.py # Anonymous viewer issue reports
|   |   `-- job_run.py        # Background execution audit records
|   |-- routes/               # Modular Flask Blueprints
|   |   |-- __init__.py
|   |   |-- main.py           # Web UI landing page and views
|   |   `-- api.py            # REST JSON endpoints (/api/channels, /api/filters, etc.)
|   |-- services/             # Core business logic
|   |   |-- __init__.py
|   |   |-- m3u_parser.py     # M3U/EXTINF streaming parser with SSRF defense
|   |   |-- health_checker.py # Stream probing engine with safe manifest inspection
|   |   |-- channel_service.py# Filter, search, and in-memory TTL caching
|   |   |-- ingestion_service.py # Idempotent multi-playlist upsert service
|   |   `-- lock_service.py   # Cross-platform concurrency lock (PID & timeout recovery)
|   |-- jobs/                 # Decoupled batch tasks & CLI integration
|   |   |-- __init__.py
|   |   |-- ingest_job.py     # Channel playlist ingestion job
|   |   `-- health_job.py     # Batch stream health validation job
|   |-- templates/            # Jinja2 HTML templates
|   |   |-- base.html         # Base template with semantic HTML & accessible layout
|   |   |-- index.html        # Discovery UI and player wrapper
|   |   `-- errors/           # Custom error pages (404, 500)
|   |       |-- 404.html
|   |       `-- 500.html
|   `-- static/               # Static assets
|       |-- css/
|       |   `-- style.css     # Clean modern design system, responsive styles
|       `-- js/
|           |-- main.js       # Search, filter, UI controller & client API
|           |-- player.js     # HLS.js player lifecycle management
|           `-- vendor/
|               `-- hls.min.js# Pinned HLS.js v1.5.17 library
|-- scripts/                  # Management scripts & CLI helpers
|   |-- init_db.py            # Database table creation script
|   |-- ingest.py             # Standalone playlist ingestion script
|   |-- check_health.py       # Standalone stream health check script
|   `-- refresh_catalog.py    # Unified non-overlapping refresh runner
|-- tests/                    # Automated pytest test suite
|   |-- __init__.py
|   |-- conftest.py           # Test fixtures & temporary in-memory database
|   |-- test_app.py           # App factory, health, and static asset tests
|   |-- test_models.py        # Entity & relationship integrity tests
|   |-- test_parser.py        # M3U parser & SSRF protection tests
|   |-- test_ingestion.py     # Multi-playlist enrichment & idempotence tests
|   |-- test_health_checker.py# Manifest inspector & redirect protection tests
|   |-- test_api.py           # REST endpoints, search, filtering, and report tests
|   `-- test_refresh.py       # Lock concurrency, caching, and JobRun tests
|-- .env.example              # Template environment variables
|-- .gitignore                # Git ignore rules for Python, SQLite, logs, venv
|-- requirements.txt          # Python project dependencies
|-- run.py                    # Entry point for local development
`-- README.md                 # Complete documentation
```

---

## 3. Component Details

### A. Application Factory Pattern (`app/__init__.py`)
- Standardized `create_app(config_name=None)` initializes Flask.
- Binds SQLAlchemy extension `db`.
- Sets up centralized logging (console + rotating file when configured).
- Registers Blueprints (`main_bp`, `api_bp`).
- Configures custom JSON error handlers for API routes and HTML error pages for browser routes.

### B. Configuration System (`app/config.py`)
- Reads values from environment variables via `python-dotenv`.
- Base configuration with defaults:
  - `SECRET_KEY`: Secure fallback for session protection.
  - `SQLALCHEMY_DATABASE_URI`: Default to `sqlite:///iptv.db`, configurable for Postgres (`postgresql://...`).
  - `SQLALCHEMY_TRACK_MODIFICATIONS`: Disabled for performance.
  - `LOG_LEVEL`: Configurable (INFO, DEBUG, WARNING, ERROR).
- Environments: `DevelopmentConfig`, `TestingConfig`, `ProductionConfig`.

### C. Security Architecture
1. **SSRF Guardrail**:
   - URL validation rejects `127.0.0.1`, `localhost`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `169.254.0.0/16`, IPv6 loopback (`::1`), link-local, and multicast addresses.
   - Hostname resolution validates resolved IPs before network requests.
   - Redirection chains re-validate each target IP before following.
2. **No Media Proxying**:
   - The server only returns stream URLs to authenticated/authorized client requests.
   - Stream content is pulled client-side by HLS.js directly.
3. **Information Disclosure Shielding**:
   - Internal stack traces, raw file paths, and database details are suppressed in non-debug mode.
   - Public health endpoints expose only high-level status (`status: "ok"`, `timestamp: ...`).
