"""
Decoupled Stream Health Check Job
Executes batch stream validation independently of web requests.
Supports concurrency locking, incremental prioritization, and job run auditing.
"""
import time
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from flask import current_app
from sqlalchemy import nullsfirst, asc

from app import db
from app.models import Channel
from app.models.job_run import JobRun
from app.services.health_checker import (
    StreamHealthChecker,
    OUTCOME_HEALTHY,
    OUTCOME_DEGRADED,
    OUTCOME_UNAVAILABLE,
    OUTCOME_UNSUPPORTED
)
from app.services.channel_service import ChannelService
from app.services.lock_service import JobLock, LockAcquisitionError

logger = logging.getLogger(__name__)


def run_health_job(
    limit: Optional[int] = 50,
    status_filter: Optional[str] = None,
    concurrency: Optional[int] = None,
    channel_id: Optional[int] = None,
    use_lock: bool = True
) -> Dict[str, Any]:
    """
    Execute background batch stream health checks on catalog channels.
    Guarded by JobLock to prevent overlapping health inspection runs.
    Records audit entry in JobRun table.
    """
    config = current_app.config
    timeout = config.get("HEALTH_CHECK_TIMEOUT_SECONDS", 5)
    concurrency = concurrency or config.get("HEALTH_CHECK_CONCURRENCY", 5)
    max_failures = config.get("HEALTH_CHECK_MAX_FAILURES", 3)

    lock = JobLock("health_check", timeout_seconds=config.get("REFRESH_LOCK_TIMEOUT_SECONDS", 3600)) if use_lock else None

    if lock:
        try:
            lock.acquire()
        except LockAcquisitionError as err:
            logger.warning("Health check job aborted: %s", err)
            return {
                "total_checked": 0,
                "healthy": 0,
                "degraded": 0,
                "unavailable": 0,
                "unsupported": 0,
                "results": [],
                "error": str(err)
            }

    started_at = datetime.now(timezone.utc)
    t0 = time.time()
    job_run = None

    try:
        job_run = JobRun(
            job_type="health_check",
            status="running",
            started_at=started_at
        )
        db.session.add(job_run)
        db.session.commit()
    except Exception as exc:
        logger.warning("Could not create initial JobRun audit record for health job: %s", exc)
        db.session.rollback()

    try:
        checker = StreamHealthChecker(timeout=timeout, max_failures=max_failures)

        query = Channel.query.filter_by(is_active=True)

        if channel_id:
            query = query.filter_by(id=channel_id)
        elif status_filter:
            query = query.filter_by(health_status=status_filter.lower())

        # Prioritize channels that have never been checked or have the oldest check timestamp
        query = query.order_by(nullsfirst(asc(Channel.last_health_check)))

        if limit and limit > 0:
            query = query.limit(limit)

        channels = query.all()
        total_to_check = len(channels)

        logger.info("Starting health check job for %d channels (concurrency=%d)", total_to_check, concurrency)

        if total_to_check == 0:
            summary = {
                "total_checked": 0,
                "healthy": 0,
                "degraded": 0,
                "unavailable": 0,
                "unsupported": 0,
                "results": []
            }
            if job_run:
                job_run.status = "completed"
                job_run.completed_at = datetime.now(timezone.utc)
                job_run.duration_seconds = time.time() - t0
                job_run.summary = "No channels matched criteria to check."
                db.session.commit()
            return summary

        results = checker.check_batch(channels, concurrency=concurrency, save=True)

        healthy_count = sum(1 for r in results if r.outcome == OUTCOME_HEALTHY)
        degraded_count = sum(1 for r in results if r.outcome == OUTCOME_DEGRADED)
        unavailable_count = sum(1 for r in results if r.outcome == OUTCOME_UNAVAILABLE)
        unsupported_count = sum(1 for r in results if r.outcome == OUTCOME_UNSUPPORTED)

        summary = {
            "total_checked": len(results),
            "healthy": healthy_count,
            "degraded": degraded_count,
            "unavailable": unavailable_count,
            "unsupported": unsupported_count,
            "results": [r.to_dict() for r in results]
        }

        # Invalidate filter cache so status count aggregation reflects latest health checks
        ChannelService.invalidate_filter_cache()

        duration = time.time() - t0
        if job_run:
            job_run.status = "completed"
            job_run.completed_at = datetime.now(timezone.utc)
            job_run.duration_seconds = duration
            job_run.records_processed = len(results)
            job_run.records_imported = healthy_count
            job_run.records_updated = degraded_count
            job_run.records_failed = unavailable_count + unsupported_count
            job_run.summary = (
                f"Checked: {len(results)}, Healthy: {healthy_count}, "
                f"Degraded: {degraded_count}, Unavailable: {unavailable_count}, "
                f"Unsupported: {unsupported_count}"
            )
            db.session.commit()

        logger.info(
            "Health check job completed in %.2fs: %d total, %d healthy, %d degraded, %d unavailable, %d unsupported",
            duration,
            summary["total_checked"],
            summary["healthy"],
            summary["degraded"],
            summary["unavailable"],
            summary["unsupported"]
        )
        return summary

    except Exception as exc:
        logger.error("Unhandled exception during health check job: %s", exc, exc_info=True)
        if job_run:
            try:
                job_run.status = "failed"
                job_run.completed_at = datetime.now(timezone.utc)
                job_run.duration_seconds = time.time() - t0
                job_run.error_message = str(exc)
                db.session.commit()
            except Exception:
                db.session.rollback()
        raise
    finally:
        if lock:
            lock.release()
