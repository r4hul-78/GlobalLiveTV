# DEVELOPMENT GUIDE & WORKFLOW

## 1. Prerequisites
- **Python**: 3.10+ (tested on Python 3.13)
- **Git**: Installed and available in PATH
- **Web Browser**: Modern browser supporting HTML5 Video & Media Source Extensions (MSE)

---

## 2. Initial Setup
1. **Clone/Open Repository**:
   Navigate to the project root directory.

2. **Create Virtual Environment**:
   ```powershell
   python -m venv .venv
   ```

3. **Install Dependencies**:
   ```powershell
   .\.venv\Scripts\pip install -r requirements.txt
   ```

4. **Configure Environment**:
   Copy `.env.example` to `.env`:
   ```powershell
   Copy-Item .env.example .env
   ```

5. **Initialize Database**:
   ```powershell
   .\.venv\Scripts\python scripts/init_db.py
   ```

---

## 3. Running the Application Locally
To launch the Flask development server:
```powershell
.\.venv\Scripts\python run.py
```
Open your browser at `http://127.0.0.1:5000`.

---

## 4. Running Tests
Run the automated test suite using pytest:
```powershell
.\.venv\Scripts\pytest -v
```

---

## 5. Code Style & Conventions
- Modular Flask architecture using Application Factory pattern.
- Configuration isolated in `app/config.py`.
- Clear separation between Routes, Services, Models, and Jobs.
- Direct external streaming only (zero server media proxying).
- Full SSRF prevention on any outbound network request.

---

## 6. Automated Refresh, Concurrency & Operating System Scheduling

### A. Standalone CLI Commands
All refresh commands run outside the Flask web workers and use `JobLock` to prevent overlapping or concurrent duplicate runs:

1. **Unified Catalog Refresh**:
   ```powershell
   # Full cycle (Ingest playlists, then inspect 50 stale/new streams)
   .\.venv\Scripts\python scripts/refresh_catalog.py --mode full --health-limit 50 --concurrency 5

   # Playlist ingestion only (with optional record limit)
   .\.venv\Scripts\python scripts/refresh_catalog.py --mode ingest-only --ingest-limit 100

   # Stream health inspection only
   .\.venv\Scripts\python scripts/refresh_catalog.py --mode health-only --health-limit 50
   ```

2. **Dedicated Ingestion**:
   ```powershell
   .\.venv\Scripts\python scripts/ingest.py --limit 100
   ```

3. **Dedicated Health Checking**:
   ```powershell
   .\.venv\Scripts\python scripts/check_health.py --limit 50 --concurrency 5
   ```

### B. Scheduling Deployment Configuration

> [!IMPORTANT]
> **Operational Note**: Running background scheduling requires registering the task with your host operating system or container orchestrator. The CLI tools and lock safeguards are fully operational, but are **NOT** active in the background until scheduled.

#### 1. Windows Task Scheduler (`schtasks.exe`)
To run catalog refresh daily at 03:00 AM:
```cmd
schtasks /Create /SC DAILY /TN "GlobalLiveTV_CatalogRefresh" /TR "D:\Development\IPTV\.venv\Scripts\python.exe D:\Development\IPTV\scripts\refresh_catalog.py --mode full" /ST 03:00 /RU SYSTEM
```
To run stream health validation every 4 hours:
```cmd
schtasks /Create /SC HOURLY /MO 4 /TN "GlobalLiveTV_HealthCheck" /TR "D:\Development\IPTV\.venv\Scripts\python.exe D:\Development\IPTV\scripts\check_health.py --limit 50" /ST 00:00 /RU SYSTEM
```

#### 2. Linux / macOS Cron (`crontab -e`)
```cron
# Ingest catalog daily at 3:00 AM UTC
0 3 * * * cd /opt/iptv && .venv/bin/python scripts/refresh_catalog.py --mode ingest-only >> logs/cron_ingest.log 2>&1

# Health-check streams every 4 hours
0 */4 * * * cd /opt/iptv && .venv/bin/python scripts/check_health.py --limit 50 --concurrency 5 >> logs/cron_health.log 2>&1
```

#### 3. Linux Systemd Timer (`/etc/systemd/system/iptv-refresh.timer`)
```ini
[Unit]
Description=Run Global Live TV Catalog Refresh Daily

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

### C. Performance & Caching Features
- **Database Composite Indexes**:
  - `idx_channel_active_health`: Accelerates health-filtered catalog queries.
  - `idx_channel_country_active`: Speeds up country taxonomy browsing.
  - `idx_channel_active_name`: Enhances alphabetical sorting of active channels.
  - `idx_channel_active_last_check`: Optimizes incremental health checking queries (`nullsfirst(asc(last_health_check))`).
  - `idx_streamcheck_channel_checked`: Fast channel audit history lookups.
  - `channel_genres.genre_id` & `channel_languages.language_code`: Reverse taxonomy joins.
- **In-Memory Filter TTL Caching**:
  - `ChannelService.get_available_filters()` caches distinct countries, genres, and languages for 300 seconds (configurable via `FILTER_CACHE_TTL_SECONDS`).
  - Cache is invalidated automatically upon completed playlist ingestion or status updates.

