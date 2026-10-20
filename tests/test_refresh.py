"""
Step 8 Automated Refresh and Performance Tests
Verifies concurrency locks, stale lock recovery, job run auditing,
idempotent reruns, filter query caching, and independent execution.
"""
import os
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest

from app import db
from app.models import Channel, Country, Genre, Language, StreamCheck, JobRun
from app.services.lock_service import JobLock, LockAcquisitionError, is_process_running
from app.services.channel_service import ChannelService
from app.jobs.ingest_job import run_ingest_job
from app.jobs.health_job import run_health_job


SAMPLE_M3U_PLAYLIST = """#EXTM3U
#EXTINF:-1 tvg-id="Test.News.US" tvg-name="Test News US" tvg-logo="https://example.com/logo1.png" group-title="News",Test News US
https://example.com/live/test1.m3u8
#EXTINF:-1 tvg-id="Test.Sports.UK" tvg-name="Test Sports UK" tvg-logo="https://example.com/logo2.png" group-title="Sports",Test Sports UK
https://example.com/live/test2.m3u8
"""


# -----------------------------------------------------------------------------
# 1. Concurrency and Process Lock Tests
# -----------------------------------------------------------------------------

def test_job_lock_acquire_and_release(tmp_path):
    """Test standard acquisition and release lifecycle of JobLock."""
    lock_dir = tmp_path / "locks"
    lock = JobLock("test_job", lock_dir=str(lock_dir))

    assert not lock.lock_file.exists()
    assert lock.acquire() is True
    assert lock.lock_file.exists()

    # Verify written lock payload
    payload = json.loads(lock.lock_file.read_text(encoding="utf-8"))
    assert payload["name"] == "test_job"
    assert payload["pid"] == os.getpid()

    assert lock.release() is True
    assert not lock.lock_file.exists()


def test_job_lock_context_manager(tmp_path):
    """Test context manager auto-releases lock upon exit."""
    lock_dir = tmp_path / "locks"
    lock = JobLock("test_cm", lock_dir=str(lock_dir))

    with lock:
        assert lock.lock_file.exists()

    assert not lock.lock_file.exists()


def test_job_lock_prevents_overlapping_workers(tmp_path):
    """Test that attempting to acquire a lock held by an active process raises LockAcquisitionError."""
    lock_dir = tmp_path / "locks"
    lock1 = JobLock("worker_job", lock_dir=str(lock_dir))
    lock1.acquire()

    # Second worker trying to acquire the same lock while lock1 is held
    lock2 = JobLock("worker_job", lock_dir=str(lock_dir))
    with pytest.raises(LockAcquisitionError) as exc_info:
        lock2.acquire()

    assert "already running under PID" in str(exc_info.value)
    lock1.release()


def test_job_lock_reclaims_stale_dead_process(tmp_path):
    """Test that a lock file from a non-existent PID is automatically reclaimed."""
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    fake_lock_file = lock_dir / "stale_job.lock"

    # Simulate an orphaned lock file from a dead process
    dead_pid = 99999999
    assert not is_process_running(dead_pid)

    fake_lock_file.write_text(json.dumps({
        "name": "stale_job",
        "pid": dead_pid,
        "started_at": datetime.now(timezone.utc).isoformat()
    }), encoding="utf-8")

    # New worker should detect dead PID and acquire successfully
    new_lock = JobLock("stale_job", lock_dir=str(lock_dir))
    assert new_lock.acquire() is True
    assert new_lock.lock_file.exists()

    payload = json.loads(new_lock.lock_file.read_text(encoding="utf-8"))
    assert payload["pid"] == os.getpid()
    new_lock.release()


def test_job_lock_reclaims_expired_timeout(tmp_path):
    """Test that a lock file older than timeout_seconds is reclaimed even if active."""
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    timeout_lock_file = lock_dir / "timeout_job.lock"

    # Simulate a lock acquired 2 hours ago
    old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    timeout_lock_file.write_text(json.dumps({
        "name": "timeout_job",
        "pid": os.getpid(),
        "started_at": old_time
    }), encoding="utf-8")

    # Lock with 60 second timeout should reclaim the old lock
    new_lock = JobLock("timeout_job", lock_dir=str(lock_dir), timeout_seconds=60)
    assert new_lock.acquire() is True
    new_lock.release()


# -----------------------------------------------------------------------------
# 2. Filter Caching and Invalidation Tests
# -----------------------------------------------------------------------------

def test_filter_cache_serves_cached_results(app):
    """Test that get_available_filters caches query results within TTL."""
    with app.app_context():
        # Clear any existing cache
        ChannelService.invalidate_filter_cache()

        # Seed sample channel
        country = Country(code="US", name="United States")
        genre = Genre(slug="news", name="News")
        channel = Channel(
            external_id="Cache.Test.US",
            name="Cache Test Channel",
            stream_url="https://example.com/test.m3u8",
            country=country,
            is_active=True,
            health_status="healthy"
        )
        channel.genres.append(genre)
        db.session.add_all([country, genre, channel])
        db.session.commit()

        # First call computes from database
        filters1 = ChannelService.get_available_filters()
        assert any(c["code"] == "US" for c in filters1["countries"])
        assert any(g["slug"] == "news" for g in filters1["genres"])

        # Add another country directly to database
        country_fr = Country(code="FR", name="France")
        channel_fr = Channel(
            external_id="FR.Channel",
            name="France Channel",
            stream_url="https://example.com/fr.m3u8",
            country=country_fr,
            is_active=True,
            health_status="healthy"
        )
        db.session.add_all([country_fr, channel_fr])
        db.session.commit()

        # Second call without invalidation returns cached result (FR not yet visible)
        filters2 = ChannelService.get_available_filters()
        assert not any(c["code"] == "FR" for c in filters2["countries"])

        # Explicit invalidation flushes cache
        ChannelService.invalidate_filter_cache()
        filters3 = ChannelService.get_available_filters()
        assert any(c["code"] == "FR" for c in filters3["countries"])


def test_filter_cache_force_refresh_bypasses_cache(app):
    """Test force_refresh parameter immediately queries fresh database state."""
    with app.app_context():
        ChannelService.invalidate_filter_cache()

        country_de = Country(code="DE", name="Germany")
        channel_de = Channel(
            external_id="DE.Channel",
            name="German TV",
            stream_url="https://example.com/de.m3u8",
            country=country_de,
            is_active=True,
            health_status="healthy"
        )
        db.session.add_all([country_de, channel_de])
        db.session.commit()

        # Warm cache
        ChannelService.get_available_filters()

        # Add new genre
        new_genre = Genre(slug="science", name="Science")
        channel_de.genres.append(new_genre)
        db.session.add(new_genre)
        db.session.commit()

        # force_refresh=True returns fresh state
        fresh_filters = ChannelService.get_available_filters(force_refresh=True)
        assert any(g["slug"] == "science" for g in fresh_filters["genres"])


# -----------------------------------------------------------------------------
# 3. Idempotent Reruns and Incremental Processing Tests
# -----------------------------------------------------------------------------

def test_repeated_ingestion_is_idempotent(app, monkeypatch):
    """Test that repeatedly running ingestion does not create duplicate channels or records."""
    with app.app_context():
        ChannelService.invalidate_filter_cache()

        # Mock download_playlist to return sample M3U
        from app.services.ingestion_service import IngestionService
        monkeypatch.setattr(
            IngestionService,
            "download_playlist",
            lambda self, url: SAMPLE_M3U_PLAYLIST if url else None
        )

        # Run 1
        res1 = run_ingest_job(dry_run=False, use_lock=False)
        assert res1.imported == 2
        initial_count = Channel.query.count()
        assert initial_count == 2

        # Run 2 (re-run of exact same playlist)
        res2 = run_ingest_job(dry_run=False, use_lock=False)
        assert res2.imported == 0
        assert res2.updated == 2
        assert Channel.query.count() == initial_count


def test_health_check_incremental_prioritization(app, monkeypatch):
    """Test that health checks prioritize channels with oldest or null check timestamps."""
    with app.app_context():
        # Create 3 channels with different check timestamps
        now = datetime.now(timezone.utc)
        ch_never = Channel(name="Never Checked", stream_url="https://example.com/never.m3u8", is_active=True)
        ch_old = Channel(
            name="Old Check",
            stream_url="https://example.com/old.m3u8",
            is_active=True,
            last_health_check=now - timedelta(days=5)
        )
        ch_recent = Channel(
            name="Recent Check",
            stream_url="https://example.com/recent.m3u8",
            is_active=True,
            last_health_check=now - timedelta(hours=1)
        )
        db.session.add_all([ch_never, ch_old, ch_recent])
        db.session.commit()

        # Mock health checker probe
        from app.services.health_checker import StreamHealthChecker, StreamHealthResult, OUTCOME_HEALTHY
        monkeypatch.setattr(
            StreamHealthChecker,
            "check_stream",
            lambda self, url, ch_id=None: StreamHealthResult(
                channel_id=ch_id,
                outcome=OUTCOME_HEALTHY,
                http_status=200,
                response_time_ms=45.0,
                diagnostic_reason="Mocked healthy test stream",
                is_live_manifest=True
            )
        )

        # Run health job with limit 2
        summary = run_health_job(limit=2, use_lock=False)
        assert summary["total_checked"] == 2

        # The checked channels must be ch_never and ch_old, leaving ch_recent untouched
        checked_ids = [r["channel_id"] for r in summary["results"]]
        assert ch_never.id in checked_ids
        assert ch_old.id in checked_ids
        assert ch_recent.id not in checked_ids


# -----------------------------------------------------------------------------
# 4. JobRun Audit Tracking Tests
# -----------------------------------------------------------------------------

def test_job_run_recorded_for_health_job(app, monkeypatch):
    """Test that running health_job records a JobRun audit log in the database."""
    with app.app_context():
        ch = Channel(name="Audit Test Channel", stream_url="https://example.com/audit.m3u8", is_active=True)
        db.session.add(ch)
        db.session.commit()

        from app.services.health_checker import StreamHealthChecker, StreamHealthResult, OUTCOME_HEALTHY
        monkeypatch.setattr(
            StreamHealthChecker,
            "check_stream",
            lambda self, url, ch_id=None: StreamHealthResult(
                channel_id=ch_id,
                outcome=OUTCOME_HEALTHY,
                http_status=200,
                response_time_ms=50.0,
                diagnostic_reason="Valid manifest",
                is_live_manifest=True
            )
        )

        summary = run_health_job(limit=5, use_lock=False)
        assert summary["total_checked"] >= 1

        # Query latest JobRun
        latest_run = JobRun.query.filter_by(job_type="health_check").order_by(JobRun.id.desc()).first()
        assert latest_run is not None
        assert latest_run.status == "completed"
        assert latest_run.records_processed >= 1
        assert latest_run.completed_at is not None
        assert latest_run.duration_seconds is not None
        assert "Checked:" in latest_run.summary


def test_job_run_recorded_for_ingest_job(app, monkeypatch):
    """Test that running ingest_job records a JobRun audit log in the database."""
    with app.app_context():
        from app.services.ingestion_service import IngestionService
        monkeypatch.setattr(
            IngestionService,
            "download_playlist",
            lambda self, url: SAMPLE_M3U_PLAYLIST if url else None
        )

        res = run_ingest_job(dry_run=False, use_lock=False)
        assert res.imported > 0

        latest_run = JobRun.query.filter_by(job_type="ingest").order_by(JobRun.id.desc()).first()
        assert latest_run is not None
        assert latest_run.status == "completed"
        assert latest_run.records_imported == res.imported
        assert latest_run.completed_at is not None
        assert latest_run.duration_seconds is not None
        assert "Parsed:" in latest_run.summary
