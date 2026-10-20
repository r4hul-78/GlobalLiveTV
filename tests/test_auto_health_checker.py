"""
Automated Health Check System Tests
Tests configuration, background scheduler lifecycle, REST API endpoints,
on-demand channel stream probing, lock handling, and CLI runner.
"""
import os
import json
import time
import threading
from datetime import datetime, timezone
import pytest

from app import db, create_app
from app.config import Config, TestingConfig
from app.models import Channel, StreamCheck, JobRun
from app.services.scheduler_service import (
    HealthCheckScheduler,
    get_health_scheduler,
    start_health_check_scheduler,
    stop_health_check_scheduler
)
from app.services.health_checker import StreamHealthChecker, StreamHealthResult, OUTCOME_HEALTHY, OUTCOME_UNAVAILABLE
from app.services.lock_service import JobLock


def test_config_auto_health_check_defaults():
    """Verify default configurations for automated health check."""
    assert hasattr(Config, "AUTO_HEALTH_CHECK_ENABLED")
    assert hasattr(Config, "AUTO_HEALTH_CHECK_INTERVAL_SECONDS")
    assert hasattr(Config, "AUTO_HEALTH_CHECK_BATCH_SIZE")
    assert Config.AUTO_HEALTH_CHECK_INTERVAL_SECONDS == 3600
    assert Config.AUTO_HEALTH_CHECK_BATCH_SIZE == 50
    assert TestingConfig.AUTO_HEALTH_CHECK_ENABLED is False


def test_health_scheduler_lifecycle(app):
    """Verify scheduler can be initialized, started, and stopped cleanly."""
    scheduler = HealthCheckScheduler(app)
    scheduler.interval_seconds = 1000
    assert not scheduler.is_running

    started = scheduler.start(run_immediately=False)
    assert started is True
    assert scheduler.is_running is True

    # Starting again should return False
    assert scheduler.start() is False

    # Stopping should cleanly terminate the thread
    stopped = scheduler.stop(timeout=2.0)
    assert stopped is True
    assert scheduler.is_running is False


def test_health_scheduler_execute_check(app, monkeypatch):
    """Verify scheduler execute_check executes health checks within app context."""
    with app.app_context():
        ch = Channel(name="Sched Test Channel", stream_url="https://example.com/sched.m3u8", is_active=True)
        db.session.add(ch)
        db.session.commit()

        monkeypatch.setattr(
            StreamHealthChecker,
            "probe_stream_network",
            lambda self, channel_id, stream_url: StreamHealthResult(
                channel_id=channel_id,
                outcome=OUTCOME_HEALTHY,
                http_status=200,
                response_time_ms=45.0,
                diagnostic_reason="Valid manifest",
                is_live_manifest=True
            )
        )

        scheduler = HealthCheckScheduler(app)
        scheduler.batch_size = 10
        scheduler.concurrency = 2

        summary = scheduler.execute_check(use_lock=False)
        assert summary["total_checked"] >= 1
        assert summary["healthy"] >= 1
        assert scheduler.total_runs_completed == 1
        assert scheduler.last_run_started_at is not None
        assert scheduler.last_run_completed_at is not None
        assert scheduler.last_summary == summary


def test_health_scheduler_trigger_now(app):
    """Verify trigger_now signals the scheduler worker event."""
    scheduler = HealthCheckScheduler(app)
    scheduler.interval_seconds = 3600

    # Not running should return False
    assert scheduler.trigger_now() is False

    scheduler.start(run_immediately=False)
    assert scheduler.is_running is True

    triggered = scheduler.trigger_now()
    assert triggered is True
    assert scheduler._trigger_event.is_set()

    scheduler.stop(timeout=2.0)


def test_api_health_check_status_endpoint(client, app):
    """Verify GET /api/health-check/status returns scheduler status and catalog summary."""
    with app.app_context():
        ch = Channel(name="Status Test Ch", stream_url="https://example.com/test.m3u8", health_status="healthy", is_active=True)
        db.session.add(ch)
        db.session.commit()

    response = client.get("/api/health-check/status")
    assert response.status_code == 200
    assert response.is_json
    data = response.get_json()

    assert "scheduler" in data
    assert "catalog_summary" in data
    assert "timestamp" in data
    assert data["catalog_summary"]["total_active_channels"] >= 1
    assert data["catalog_summary"]["healthy"] >= 1


def test_api_health_check_run_sync(client, app, monkeypatch):
    """Verify POST /api/health-check/run executes a synchronous batch health check."""
    with app.app_context():
        ch = Channel(name="Run Sync Ch", stream_url="https://example.com/sync.m3u8", is_active=True)
        db.session.add(ch)
        db.session.commit()

        monkeypatch.setattr(
            StreamHealthChecker,
            "probe_stream_network",
            lambda self, channel_id, stream_url: StreamHealthResult(
                channel_id=channel_id,
                outcome=OUTCOME_HEALTHY,
                http_status=200,
                response_time_ms=60.0,
                diagnostic_reason="Valid test stream",
                is_live_manifest=True
            )
        )

    response = client.post("/api/health-check/run", json={"limit": 5, "concurrency": 2})
    assert response.status_code == 200
    assert response.is_json
    data = response.get_json()

    assert data["status"] == "completed"
    assert "summary" in data
    assert data["summary"]["total_checked"] >= 1
    assert data["summary"]["healthy"] >= 1


def test_api_health_check_run_async(client, monkeypatch):
    """Verify POST /api/health-check/run with async=true returns 202 Accepted without orphaned threads."""
    monkeypatch.setattr("threading.Thread.start", lambda self: None)
    response = client.post("/api/health-check/run?async=true", json={"limit": 2})
    assert response.status_code == 202
    assert response.is_json
    data = response.get_json()

    assert data["status"] == "started"
    assert "Background stream health check dispatched" in data["message"]


def test_api_health_check_run_lock_conflict(client, app):
    """Verify POST /api/health-check/run returns 409 Conflict if JobLock is held."""
    with app.app_context():
        config = app.config
        lock = JobLock("health_check", timeout_seconds=config.get("REFRESH_LOCK_TIMEOUT_SECONDS", 3600))
        lock.acquire()

        try:
            response = client.post("/api/health-check/run", json={"limit": 5})
            assert response.status_code == 409
            data = response.get_json()
            assert data["error"] == "Conflict"
            assert "already running" in data["message"]
        finally:
            lock.release()


def test_api_channel_single_check_success(client, app, monkeypatch):
    """Verify POST /api/channels/<id>/check triggers an immediate on-demand probe."""
    with app.app_context():
        ch = Channel(
            name="Single Check Ch",
            stream_url="https://example.com/single.m3u8",
            health_status="unknown",
            is_active=True
        )
        db.session.add(ch)
        db.session.commit()
        channel_id = ch.id

        monkeypatch.setattr(
            StreamHealthChecker,
            "probe_stream_network",
            lambda self, cid, url: StreamHealthResult(
                channel_id=cid,
                outcome=OUTCOME_HEALTHY,
                http_status=200,
                response_time_ms=42.0,
                diagnostic_reason="Single check OK",
                is_live_manifest=True
            )
        )

        response = client.post(f"/api/channels/{channel_id}/check")
        assert response.status_code == 200
        data = response.get_json()

        assert data["status"] == "success"
        assert data["channel"]["id"] == channel_id
        assert data["channel"]["health_status"] == "healthy"
        assert data["result"]["outcome"] == "healthy"
        assert data["result"]["response_time_ms"] == 42.0

        # Verify StreamCheck record saved in DB
        checks = StreamCheck.query.filter_by(channel_id=channel_id).all()
        assert len(checks) >= 1
        assert checks[0].outcome == "healthy"


def test_api_channel_single_check_not_found(client):
    """Verify POST /api/channels/<id>/check returns 404 for non-existent channel."""
    response = client.post("/api/channels/999999/check")
    assert response.status_code == 404
    data = response.get_json()
    assert data["error"] == "Not Found"


def test_api_channel_single_check_inactive(client, app):
    """Verify POST /api/channels/<id>/check returns 400 for inactive channel."""
    with app.app_context():
        ch = Channel(name="Inactive Ch", stream_url="https://example.com/inact.m3u8", is_active=False)
        db.session.add(ch)
        db.session.commit()
        channel_id = ch.id

    response = client.post(f"/api/channels/{channel_id}/check")
    assert response.status_code == 400
    data = response.get_json()
    assert data["error"] == "Bad Request"
    assert "inactive" in data["message"]


def test_auto_health_checker_daemon_run_once(app, monkeypatch):
    """Verify scripts.auto_health_checker.run_daemon runs in run_once mode without errors."""
    with app.app_context():
        ch = Channel(name="Daemon Test Ch", stream_url="https://example.com/daemon.m3u8", is_active=True)
        db.session.add(ch)
        db.session.commit()

        monkeypatch.setattr(
            StreamHealthChecker,
            "probe_stream_network",
            lambda self, cid, url: StreamHealthResult(
                channel_id=cid,
                outcome=OUTCOME_HEALTHY,
                http_status=200,
                response_time_ms=30.0,
                diagnostic_reason="Daemon OK",
                is_live_manifest=True
            )
        )

        from scripts.auto_health_checker import run_daemon
        # Run 1 cycle with batch_size 1
        run_daemon(interval=1, batch_size=1, concurrency=1, run_once=True)
