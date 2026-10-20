# DEBUGGING & TROUBLESHOOTING GUIDE

## 1. Local Environment & Virtualenv Issues

### PowerShell Execution Policy Error
If running Python scripts or activation script produces an execution policy error:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```
Alternatively, directly call the virtual environment executables without activation:
```powershell
.\.venv\Scripts\python.exe run.py
.\.venv\Scripts\pytest
```

---

## 2. Database & SQLite Issues

### SQLite Database Locked
- Cause: Multiple processes attempting to write simultaneously.
- Fix: Ensure background ingestion and health-check jobs use short transaction boundaries and avoid holding open write connections while performing network requests.

### Schema Migration or Reset
- To recreate the local database during development:
```powershell
.\.venv\Scripts\python.exe scripts/init_db.py --reset
```

---

## 3. Stream & Network Troubleshooting

### CORS Errors in Browser Video Playback
- **Symptom**: Browser console shows `Access-Control-Allow-Origin` missing on stream URL or segments.
- **Explanation**: The stream provider does not allow browser-based cross-origin fetching. The application does not proxy streams through Flask (by architectural principle).
- **Resolution**: Mark the channel status as `degraded` or `unsupported` in health check, and display an honest message to the user explaining external host CORS restrictions.

### SSRF Protection Rejections
- **Symptom**: Health check marks a URL as `unsupported` or `unsafe`.
- **Explanation**: The host resolved to a private or loopback IP range (e.g., `127.0.0.1`, `192.168.x.x`, `169.254.x.x`).
- **Resolution**: This is expected behavior. Check logs to ensure the rejection is intentional.

---

## 4. Application Logs
- By default, logs are written to stdout/stderr in development.
- When `LOG_TO_FILE=true` is set in `.env`, logs are written to `logs/app.log` with automatic rotation.
- To increase verbosity, set `LOG_LEVEL=DEBUG` in `.env`.
