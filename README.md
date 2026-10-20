# Global Live TV Platform

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0%2B-green.svg)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-101%20Passed-brightgreen.svg)]()
[![Code%20Style](https://img.shields.io/badge/Code%20Style-Black%20%2F%20Flake8-black.svg)]()

A modern, high-performance web application designed to discover, search, filter, and stream publicly available, legal television broadcasts directly in the browser with **zero server-side media proxying**. 

The platform aggregates channel metadata from the community-maintained [iptv-org/iptv](https://github.com/iptv-org/iptv) project, normalizes it into a relational database, performs asynchronous health inspections, exposes a RESTful API, and renders an accessible, responsive web interface powered by pinned HLS.js.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture and Data Flow](#2-architecture-and-data-flow)
3. [Prerequisites](#3-prerequisites)
4. [Installation and Virtual-Environment Setup](#4-installation-and-virtual-environment-setup)
5. [Environment Configuration](#5-environment-configuration)
6. [Database Initialization](#6-database-initialization)
7. [Starting the Flask Application](#7-starting-the-flask-application)
8. [Running Ingestion](#8-running-ingestion)
9. [Running Health Checks](#9-running-health-checks)
10. [Scheduling Refresh Jobs](#10-scheduling-refresh-jobs)
11. [Running Automated Tests](#11-running-automated-tests)
12. [Production Deployment Instructions](#12-production-deployment-instructions)
13. [Known Limitations](#13-known-limitations)
14. [Source Attribution and Usage Considerations](#14-source-attribution-and-usage-considerations)
15. [Channel-Reporting Procedures](#15-channel-reporting-procedures)
16. [Supplementary Documentation](#16-supplementary-documentation)

---

## 1. Project Overview

The **Global Live TV Platform** provides a structured, reliable, and privacy-conscious gateway to free-to-air and publicly broadcast television channels worldwide.

### Key Objectives & Philosophy
- **Zero Media Proxying**: The Flask backend serves purely as an index and metadata API. Media segments (.ts / .m4s / fMP4) and HLS manifests (.m3u8) are delivered directly from authorized broadcaster CDN edges to the user's browser.
- **SSRF & Network Hardening**: Outbound playlist importers and stream health probers actively validate URLs, reject private/internal IP address ranges (RFC 1918, RFC 3927, loopback, multicast), and enforce strict hop-by-hop redirect verification.
- **Honest Health Reporting**: Streams are periodically inspected using bounded HTTP range requests that validate M3U8 headers (`#EXTM3U`, `#EXT-X-VERSION`, `#EXTINF`), target duration, and sequence progression. Streams are categorized into explicit statuses: `healthy`, `degraded`, `unavailable`, and `unsupported`.
- **Lightweight, Framework-Free Frontend**: Built entirely with Vanilla HTML5, CSS3, and JavaScript—no bloated client runtimes, tracking scripts, or ad networks.
- **Decoupled Asynchronous Processing**: Ingestion and health verification execute in independent CLI/batch processes guarded by atomic file locks (`JobLock`) to ensure web workers remain responsive.

---

## 2. Architecture and Data Flow

### System Architecture Diagram

```
+----------------------------------------------------------------------------------------------------+
|                                      EXTERNAL SOURCES & CDNs                                       |
|  +-------------------------------------+          +---------------------------------------------+  |
|  |     iptv-org / GitHub Playlists     |          |       Official Broadcaster CDN Edges        |  |
|  |  (index.m3u, countries, categories) |          |        (Direct Live HLS / M3U8 Streams)     |  |
|  +-------------------------------------+          +---------------------------------------------+  |
+-------------------------------------------------------------------|--------------------------------+
                  | (Periodic CLI Sync)                             |
                  v                                                 | (Direct Client Playback:
+--------------------------------------------------+                |  Zero Server Media Proxying)
|      INGESTION & HEALTH-CHECKING PIPELINE        |                |
|  - scripts/ingest.py (Playlist Parser & Upsert)  |                |
|  - scripts/check_health.py (M3U8 Syntax Probes)  |                |
|  - scripts/refresh.py (Scheduled Job Runner)     |                |
|  - JobLock (Atomic Concurrency Mutex)            |                |
|  - SSRF Guard (Private IP & DNS Rebind Filter)   |                |
+--------------------------------------------------+                |
                  |                                                 |
                  v                                                 |
+--------------------------------------------------+                |
|              RELATIONAL DATABASE LAYER           |                |
|  SQLite (Local) / PostgreSQL (Production)        |                |
|  - channels (Indexed by country, genre, health)  |                |
|  - countries, genres, languages (Taxonomies)     |                |
|  - stream_checks (Historical Probe Logs)         |                |
|  - channel_reports (User-Submitted Issues)       |                |
|  - job_runs (Job Run Auditing & Durations)       |                |
+--------------------------------------------------+                |
                  ^                                                 |
                  | Query Data                                      |
+--------------------------------------------------+                |
|            FLASK WEB APPLICATION LAYER           |                |
|  - Application Factory (app/__init__.py)         |                |
|  - Blueprints: Web (main.py) & REST API (api.py) |                |
|  - TTL Memory Cache (Filters Aggregation)        |                |
|  - Content Security Policy & Strict Headers      |                |
+--------------------------------------------------+                |
                  ^                                                 |
                  | HTTP / JSON REST APIs                           |
                  v                                                 v
+----------------------------------------------------------------------------------------------------+
|                                    CLIENT BROWSER (HTML5 + CSS + JS)                               |
|  - Channel Discovery UI (Search, Multiselect Filters, Dynamic Pagination, History State)          |
|  - Pinned HLS.js Player Engine (v1.5.17) with Native Safari Fallback                               |
|  - Anonymous Issue Reporting Dialog (POST /api/channels/<id>/report)                               |
|  - Responsive Dark-Glass Design & Accessible Keyboard Focus (ARIA-Live Announcements)              |
+----------------------------------------------------------------------------------------------------+
```

### End-to-End Data Flow

1. **Ingestion Flow**:
   - `scripts/ingest.py` downloads M3U playlists from `iptv-org` via `safe_http_get`.
   - The parser extracts EXTINF metadata (`tvg-id`, `tvg-name`, `tvg-logo`, `group-title`, stream URL).
   - Channels and taxonomies are normalized and upserted into the database idempotently.
2. **Health Inspection Flow**:
   - `scripts/check_health.py` prioritizes uninspected or degraded channels.
   - A concurrent worker pool sends bounded HTTP GET requests to inspect manifest headers (`#EXTM3U`, `#EXT-X-TARGETDURATION`).
   - Results are saved to `stream_checks`, and the channel's `health_status` is updated.
3. **API & Discovery Flow**:
   - Users browse `http://127.0.0.1:5000/`. The frontend queries `GET /api/filters` (cached in memory) and `GET /api/channels` with debounced search terms and taxonomy filters.
   - Channel cards are dynamically rendered with lazy-loaded logos and initials fallbacks.
4. **Playback Flow**:
   - The user clicks a channel card. The HLS player modal opens.
   - Pinned HLS.js connects directly to the broadcaster's stream URL. If the browser natively supports HLS (e.g., Safari), it falls back to native video tag handling.
   - The media stream is rendered directly on screen without passing through Flask.

---

## 3. Prerequisites

Before installing the application, ensure your environment meets the following requirements:

| Component | Requirement | Notes |
|---|---|---|
| **Python** | Version **3.10** or higher | Developed and verified on Python 3.10, 3.11, 3.12, and 3.13. |
| **Operating System** | Linux, macOS, or Windows | Fully cross-platform with platform-native scripts. |
| **Git** | Modern Git release | For repository cloning and version tracking. |
| **Web Browser** | Chrome, Firefox, Edge, or Safari | Requires Media Source Extensions (MSE) or Native HLS support. |
| **Database** | SQLite 3 (included) or PostgreSQL 14+ | SQLite is used by default; PostgreSQL is supported via `DATABASE_URL`. |

---

## 4. Installation and Virtual-Environment Setup

### Step 1: Clone or Open the Repository
```powershell
# Open terminal or PowerShell in your development directory
cd d:/Development/IPTV
```

### Step 2: Create a Virtual Environment
Isolate Python dependencies from your global system environment:

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Linux / macOS (Bash):**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Step 3: Upgrade pip and Install Dependencies
Install all required packages pinned in `requirements.txt`:
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 5. Environment Configuration

The application uses `python-dotenv` to load environment variables from a `.env` file in the project root.

### Create `.env` File
Copy the provided template:
```powershell
# Windows PowerShell
Copy-Item .env.example .env

# Linux / macOS
cp .env.example .env
```

### Environment Variable Reference

| Variable Name | Default Value | Description |
|---|---|---|
| `FLASK_ENV` | `development` | Environment mode (`development`, `testing`, `production`). |
| `FLASK_APP` | `run.py` | Flask application entry point. |
| `SECRET_KEY` | *(Random 32-char key)* | Secret key for session signing and CSRF tokens. |
| `DATABASE_URL` | `sqlite:///instance/iptv.db` | SQLAlchemy connection string (SQLite or PostgreSQL). |
| `CORS_ORIGINS` | `*` | Allowed origins for cross-origin API requests. |
| `LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `LOG_FILE` | *(empty)* | Optional file path for rotating log output (e.g., `logs/iptv.log`). |
| `INGEST_PLAYLIST_URLS` | *(iptv-org URLs)* | Comma-separated list of remote M3U playlist URLs. |
| `INGEST_MAX_RECORDS` | `500` | Maximum number of records to ingest per run (`0` for unlimited). |
| `INGEST_TIMEOUT` | `15` | Network timeout in seconds for downloading remote playlists. |
| `HEALTH_CHECK_INTERVAL_HOURS` | `6` | Hours before an active channel is re-checked by the health checker. |
| `HEALTH_CHECK_TIMEOUT` | `8` | Network timeout in seconds per stream health probe. |
| `HEALTH_CHECK_MAX_WORKERS` | `5` | Maximum concurrent worker threads for health checking. |
| `HEALTH_CHECK_BATCH_SIZE` | `50` | Maximum number of channels to check per batch. |
| `REFRESH_INTERVAL_HOURS` | `12` | Frequency in hours for scheduled catalogue refreshes. |
| `JOB_LOCK_TIMEOUT_SECONDS` | `1800` | Process lock timeout in seconds (30 mins) before auto-reclaiming stale locks. |
| `FILTER_CACHE_TTL_SECONDS` | `300` | In-memory cache duration in seconds (5 mins) for taxonomy filter lists. |

---

## 6. Database Initialization

Before starting the web server, initialize the database schema and tables.

### Initialize Tables
Run the database initialization script to create tables (`channels`, `countries`, `genres`, `languages`, `stream_checks`, `channel_reports`, `job_runs`):
```powershell
python scripts/init_db.py
```

### Optional: Seed with Verified Sample Channels
To populate the database with a curated selection of verified, legal public streams for immediate testing:
```powershell
python scripts/init_db.py --seed
```

---

## 7. Starting the Flask Application

### Local Development Server
Start the development server with auto-reloading and debug diagnostics:
```powershell
python run.py
```
By default, the server listens at `http://127.0.0.1:5000`.

### Verify Application Health
In a separate terminal, test the JSON health endpoint:
```powershell
curl http://127.0.0.1:5000/api/health
```
**Expected Response:**
```json
{
  "status": "healthy",
  "database": "connected",
  "version": "1.0.0",
  "channel_count": 25
}
```

### Accessing the Web UI
Open your browser and navigate to:
- **Live Channel Discovery & Player**: [http://127.0.0.1:5000/](http://127.0.0.1:5000/)
- **Ethics, Sources & About**: [http://127.0.0.1:5000/about](http://127.0.0.1:5000/about)

---

## 8. Running Ingestion

The ingestion engine parses standard M3U/M3U8 playlists from `iptv-org` or custom URLs, sanitizes URLs against SSRF vulnerabilities, normalizes channel metadata, and performs idempotent upserts into the database.

### Ingestion Commands

```powershell
# 1. Standard ingestion using default configured playlist URLs
python scripts/ingest.py

# 2. Ingest with a record limit (e.g. 50 channels for quick testing)
python scripts/ingest.py --limit 50

# 3. Dry-run mode: parse and validate without committing changes to the database
python scripts/ingest.py --dry-run

# 4. Ingest from custom playlist URLs
python scripts/ingest.py --urls https://iptv-org.github.io/iptv/countries/us.m3u https://iptv-org.github.io/iptv/countries/gb.m3u
```

### Ingestion Features
- **Idempotent Upserting**: Channels are matched by direct stream URL. Repeated imports update metadata (logo, name, category) without creating duplicate records.
- **SSRF Rejection**: Any stream URL resolving to private, loopback, multicast, or non-HTTP/HTTPS destinations is discarded before reaching the database.
- **Resilience**: If an external playlist download fails, existing catalog records are preserved intact.

---

## 9. Running Health Checks

The health checker probes channel stream URLs to verify availability and manifest validity. It runs independently of Flask web workers.

### Health Check Commands

```powershell
# 1. Inspect a standard batch of up to 50 channels
python scripts/check_health.py

# 2. Inspect a specific batch size with concurrent workers
python scripts/check_health.py --batch-size 100 --workers 10

# 3. Force check all channels regardless of last check timestamp
python scripts/check_health.py --force

# 4. Dry-run mode: probe streams without saving records
python scripts/check_health.py --dry-run
```

### Health Status Definitions
- `healthy`: Stream URL returned HTTP 200/206 with a valid `#EXTM3U` manifest and reachable media segments.
- `degraded`: The stream failed 1 or 2 consecutive probes, or had high response latency (> 5000ms).
- `unavailable`: The stream failed 3 or more consecutive probes, returned HTTP 404/410/5xx, or timed out.
- `unsupported`: Stream format is not HLS (e.g. RTSP, RTMP, or unparsable binary).
- `unknown`: Newly ingested channel awaiting its initial health inspection probe.

---

## 10. Scheduling Refresh Jobs

The platform provides a unified scheduler CLI (`scripts/refresh.py`) protected by an atomic process lock (`JobLock`) to prevent overlapping workers.

### Unified Refresh Script
```powershell
# Run both ingestion and health checks in sequence
python scripts/refresh.py --mode all

# Run ingestion only
python scripts/refresh.py --mode ingest

# Run health checks only
python scripts/refresh.py --mode health
```

### 1. Windows Task Scheduler
Schedule periodic refreshes via PowerShell / `schtasks`:

```powershell
# Schedule an automated refresh every 6 hours
schtasks /create /tn "IPTV_Refresh_Job" /tr "d:\Development\IPTV\.venv\Scripts\python.exe d:\Development\IPTV\scripts\refresh.py --mode all" /sc hourly /mo 6 /f
```

### 2. Linux / macOS Cron
Open crontab:
```bash
crontab -e
```
Add the following lines:
```cron
# Run stream health checking every 2 hours
0 */2 * * * cd /opt/iptv && .venv/bin/python scripts/refresh.py --mode health >> logs/refresh.log 2>&1

# Run playlist catalog ingestion once every 24 hours at 03:00 UTC
0 3 * * * cd /opt/iptv && .venv/bin/python scripts/refresh.py --mode ingest >> logs/refresh.log 2>&1
```

### 3. Linux systemd Service & Timer
For enterprise Linux deployments, use systemd unit files:

`/etc/systemd/system/iptv-refresh.service`:
```ini
[Unit]
Description=Global Live TV Platform Refresh Job
After=network.target

[Service]
Type=oneshot
User=www-data
WorkingDirectory=/opt/iptv
ExecStart=/opt/iptv/.venv/bin/python scripts/refresh.py --mode all
StandardOutput=append:/var/log/iptv-refresh.log
StandardError=append:/var/log/iptv-refresh.error.log
```

`/etc/systemd/system/iptv-refresh.timer`:
```ini
[Unit]
Description=Run IPTV Refresh Job Every 6 Hours

[Timer]
OnBootSec=10min
OnUnitActiveSec=6h
Persistent=true

[Install]
WantedBy=timers.target
```
Enable and start the timer:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now iptv-refresh.timer
```

---

## 11. Running Automated Tests

The platform includes a comprehensive, 101-test automated test suite covering all functional layers.

### Run All Tests
```powershell
python -m pytest -v
```

### Run with Code Coverage
```powershell
python -m pytest -v --cov=app --cov-report=term-missing
```

### Test Suite Structure
| Test File | Tests | Coverage Focus |
|---|---|---|
| [`tests/test_app.py`](file:///d:/Development/IPTV/tests/test_app.py) | 19 | Factory configs, error handlers, static asset serving, templates, and UI components. |
| [`tests/test_models.py`](file:///d:/Development/IPTV/tests/test_models.py) | 4 | ORM models, relationships, cascades, serialization, and constraints. |
| [`tests/test_parser.py`](file:///d:/Development/IPTV/tests/test_parser.py) | 8 | M3U/EXTINF parsing, quoted attribute parsing, commas in names, and SSRF rejection. |
| [`tests/test_health_checker.py`](file:///d:/Development/IPTV/tests/test_health_checker.py) | 9 | HLS manifest validation, SSRF redirect defense, failure transitions, and batch execution. |
| [`tests/test_ingestion.py`](file:///d:/Development/IPTV/tests/test_ingestion.py) | 6 | Idempotent upserts, multi-playlist enrichment, dry-run mode, and error recovery. |
| [`tests/test_api.py`](file:///d:/Development/IPTV/tests/test_api.py) | 21 | Search queries, taxonomy filters, pagination bounds, issue reporting, and CORS headers. |
| [`tests/test_refresh.py`](file:///d:/Development/IPTV/tests/test_refresh.py) | 11 | JobLock concurrency, stale lock reclamation, in-memory TTL caching, and job auditing. |
| [`tests/test_audit_e2e.py`](file:///d:/Development/IPTV/tests/test_audit_e2e.py) | 17 | End-to-end user journeys, comprehensive SSRF IP suite, cascade deletions, and boundary checks. |
| **Total** | **101** | **100% Passing** |

---

## 12. Production Deployment Instructions

### 1. WSGI Server Configuration

Never run `python run.py` (Flask development server) in production. Use a production WSGI server.

#### Linux: Gunicorn
Install Gunicorn inside your virtual environment:
```bash
pip install gunicorn
```
Run with 4 worker processes:
```bash
gunicorn -w 4 -b 127.0.0.1:5000 --access-logfile - --error-logfile - "app:create_app('production')"
```

#### Windows: Waitress
Install Waitress inside your virtual environment:
```powershell
pip install waitress
```
Run with Waitress:
```powershell
waitress-serve --listen=127.0.0.1:5000 --call "app:create_app:production"
```

### 2. Nginx Reverse Proxy Configuration
Deploy Nginx in front of Gunicorn/Waitress for SSL termination, security headers, and high-performance static asset caching.

`/etc/nginx/sites-available/iptv`:
```nginx
server {
    listen 80;
    server_name live.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name live.yourdomain.com;

    # SSL Certificates
    ssl_certificate /etc/letsencrypt/live/live.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/live.yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Security Headers
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; media-src 'self' blob: *; img-src 'self' data: https: *; connect-src 'self' blob: *;" always;

    # Static Assets Caching (Served directly by Nginx)
    location /static/ {
        alias /opt/iptv/app/static/;
        expires 30d;
        add_header Cache-Control "public, no-transform";
        gzip_static on;
    }

    # Proxy API & Web Requests to Flask WSGI
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 10s;
        proxy_read_timeout 30s;
    }
}
```

### 3. PostgreSQL Migration
To use PostgreSQL in production:
1. Install PostgreSQL and `psycopg2-binary`:
   ```bash
   pip install psycopg2-binary
   ```
2. Create database and user:
   ```sql
   CREATE DATABASE iptv;
   CREATE USER iptv_user WITH ENCRYPTED PASSWORD 'your_secure_password';
   GRANT ALL PRIVILEGES ON DATABASE iptv TO iptv_user;
   ```
3. Update `.env`:
   ```ini
   DATABASE_URL=postgresql+psycopg2://iptv_user:your_secure_password@localhost:5432/iptv
   ```
4. Run table initialization:
   ```bash
   python scripts/init_db.py
   python scripts/ingest.py
   ```

---

## 13. Known Limitations

1. **Browser CORS Restrictions**: Some broadcasters configure their CDN access policies to only allow requests originating from their own official web domain (`Access-Control-Allow-Origin: broadcaster.com`). When a user's browser attempts to stream such channels directly from this platform, the browser will block the manifest request. The platform surfaces clear diagnostic messaging for CORS blocks.
2. **Mixed-Content Blocking**: If the platform is hosted over HTTPS (`https://`), modern web browsers will block insecure HTTP (`http://`) stream URLs. Broadcasters using unencrypted HTTP streams cannot be played on HTTPS deployments without direct client-side overrides.
3. **Geographic Restrictions (Geo-blocking)**: Certain national public broadcasters enforce geo-fencing at the CDN edge. Users located outside the broadcaster's home country may experience 403 Forbidden errors.
4. **Codec Compatibility**: HLS.js relies on browser Media Source Extensions (MSE) decoding capabilities. While standard H.264 video and AAC audio play universally, streams encoded in HEVC/H.265 or AC3 audio may require specific client hardware or OS decoder support.
5. **Dynamic / Ephemeral Tokens**: Some public streams utilize expiring session tokens (e.g. Akamai HD / Cloudflare tokenized URLs). These stream URLs may expire after several hours, requiring fresh ingestion runs to obtain updated links.

---

## 14. Source Attribution and Usage Considerations

### Upstream Data Source
- Channel metadata and initial stream discovery URLs are derived from the community-driven [iptv-org/iptv](https://github.com/iptv-org/iptv) project under the Unlicense / public domain.
- We gratefully acknowledge the extensive volunteer effort of the global open-source IPTV community.

### Ethical & Legal Guardrails
- **No Copyright Ownership**: This platform does not claim ownership, affiliation, or copyright over any broadcasted television channels, names, logos, or streams listed in the catalog. All trademarks belong to their respective rights holders.
- **No DRM Circumvention**: The application strictly prohibits and contains zero mechanisms for circumventing Digital Rights Management (Widevine, PlayReady, FairPlay), breaking encryption, or bypassing paywalls and subscription controls.
- **Search & Directory Index**: The application functions solely as an informational index and directory of publicly accessible, unencrypted streams.
- **Takedown Policy**: Rights holders may request immediate channel delisting by submitting an issue report via the web UI or contacting the system administrator. Delisting requests are handled promptly.

---

## 15. Channel-Reporting Procedures

To maintain high directory quality and respect broadcaster rights, the platform provides an anonymous, friction-free issue reporting workflow.

### How Users Report Issues
1. In the channel directory or inside the video player modal, click the **"Report Issue"** button.
2. Select the issue category from the dropdown:
   - `stream_offline`: Stream does not load or returns an error.
   - `wrong_channel`: Stream content does not match the channel name.
   - `poor_quality`: Frequent buffering, desynced audio, or poor bitrate.
   - `inappropriate_content`: Content violates broadcast standards or contains illegal material.
   - `copyright_infringement`: Stream owner requests delisting or removal.
   - `other`: General feedback or notes.
3. (Optional) Provide additional details or diagnostic notes.
4. Submit the report.

### Privacy Guarantees
- Submitting an issue report requires **no account registration**, login, or tracking cookies.
- User IP addresses are **never stored** in the `channel_reports` database table.

### Administrative Triage Workflow
- Submitted reports are saved to the `channel_reports` table with status `pending`.
- Administrators can inspect reports using SQL or administrative scripts:
  ```sql
  SELECT c.name, r.reason, r.details, r.created_at 
  FROM channel_reports r 
  JOIN channels c ON r.channel_id = c.id 
  WHERE r.status = 'pending' 
  ORDER BY r.created_at DESC;
  ```
- If a channel is reported for copyright infringement or confirmed offline across multiple sources, set `is_active = 0` in the database to instantly hide it from public catalog listings.

---

## 16. Supplementary Documentation

For developers, contributors, and AI agents, comprehensive architecture documentation, developer playbooks, and development prompt specifications are organized in the [`docs/`](docs/) directory:

| Document | Description |
|---|---|
| [**Architecture & System Design**](docs/ARCHITECTURE.md) | Component architecture, data flow, SSRF safeguards, caching, and database schemas. |
| [**Development Guide**](docs/DEVELOPMENT.md) | Local environment setup, dependency management, code conventions, and manual test workflows. |
| [**Testing & Quality Assurance**](docs/TESTING.md) | Test suite organization, mock strategies, edge cases, and CI automation details. |
| [**Debugging & Diagnostics**](docs/DEBUG.md) | Playbook for diagnosing stream playback failures, ingestion locks, and database integrity. |
| [**Project Context & Roadmap**](docs/PROJECT_CONTEXT.md) | High-level roadmap, core principles, technology decisions, and milestone audits. |
| [**Agent Operational Protocols**](docs/AGENT.md) | Guidelines, operating principles, and reporting standards for AI coding agents. |
| [**Master Prompt Specification**](docs/global_live_tv_master_prompt.md) | Complete 9-step functional and technical requirements specification. |

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
Stream metadata is provided through [iptv-org](https://github.com/iptv-org/iptv).
