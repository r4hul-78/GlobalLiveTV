"""
Automated Stream Health Check Scheduler Service
Manages recurring background health inspection for active catalog channels.
Cycles through channels incrementally using last_health_check priority,
guaranteeing complete catalog health coverage without blocking web workers.
"""
import atexit
import logging
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from app.jobs.health_job import run_health_job

logger = logging.getLogger(__name__)


class HealthCheckScheduler:
    """
    Background daemon thread scheduler that periodically runs stream health checks
    on active channels.
    """

    def __init__(self, app=None):
        self.app = app
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._trigger_event = threading.Event()
        self._state_lock = threading.Lock()

        # Operational metrics and status
        self.interval_seconds: int = 3600
        self.batch_size: int = 50
        self.concurrency: int = 5
        self.last_run_started_at: Optional[datetime] = None
        self.last_run_completed_at: Optional[datetime] = None
        self.next_run_estimated_at: Optional[datetime] = None
        self.total_runs_completed: int = 0
        self.last_summary: Optional[Dict[str, Any]] = None
        self.last_error: Optional[str] = None
        self._is_running: bool = False

    @property
    def is_running(self) -> bool:
        return self._is_running and self._thread is not None and self._thread.is_alive()

    def configure(self, app):
        """Configure scheduler settings from Flask application configuration."""
        self.app = app
        config = app.config
        self.interval_seconds = int(config.get("AUTO_HEALTH_CHECK_INTERVAL_SECONDS", 3600))
        self.batch_size = int(config.get("AUTO_HEALTH_CHECK_BATCH_SIZE", 50))
        self.concurrency = int(config.get("HEALTH_CHECK_CONCURRENCY", 5))

    def start(self, app=None, run_immediately: bool = False) -> bool:
        """
        Start the background scheduler thread if not already running.
        """
        with self._state_lock:
            if self.is_running:
                logger.info("HealthCheckScheduler is already running.")
                return False

            if app:
                self.configure(app)
            elif not self.app:
                raise ValueError("Flask app instance must be provided to start HealthCheckScheduler.")

            self._stop_event.clear()
            self._trigger_event.clear()
            if run_immediately:
                self._trigger_event.set()

            self._is_running = True
            self.next_run_estimated_at = datetime.now(timezone.utc) if run_immediately else (
                datetime.now(timezone.utc) + timedelta(seconds=self.interval_seconds)
            )

            self._thread = threading.Thread(
                target=self._worker_loop,
                name="HealthCheckSchedulerThread",
                daemon=True
            )
            self._thread.start()
            logger.info(
                "HealthCheckScheduler started (interval=%ds, batch_size=%d, concurrency=%d)",
                self.interval_seconds, self.batch_size, self.concurrency
            )
            return True

    def stop(self, timeout: float = 5.0) -> bool:
        """
        Gracefully signal the scheduler thread to stop and wait for it to join.
        """
        with self._state_lock:
            if not self._is_running:
                return True

            logger.info("Stopping HealthCheckScheduler...")
            self._stop_event.set()
            self._trigger_event.set()
            self._is_running = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

        logger.info("HealthCheckScheduler stopped.")
        return True

    def trigger_now(self) -> bool:
        """
        Signal the worker thread to initiate a health check immediately without waiting
        for the current interval sleep to expire.
        """
        if not self.is_running:
            return False
        self._trigger_event.set()
        return True

    def execute_check(
        self,
        limit: Optional[int] = None,
        status_filter: Optional[str] = None,
        concurrency: Optional[int] = None,
        use_lock: bool = True
    ) -> Dict[str, Any]:
        """
        Execute a single health check batch synchronously within the application context.
        """
        if not self.app:
            raise RuntimeError("Cannot execute check without an initialized Flask app.")

        limit = limit or self.batch_size
        concurrency = concurrency or self.concurrency

        with self.app.app_context():
            started_at = datetime.now(timezone.utc)
            self.last_run_started_at = started_at
            try:
                summary = run_health_job(
                    limit=limit,
                    status_filter=status_filter,
                    concurrency=concurrency,
                    use_lock=use_lock
                )
                completed_at = datetime.now(timezone.utc)
                self.last_run_completed_at = completed_at
                self.last_summary = summary
                self.last_error = summary.get("error")
                if not summary.get("error"):
                    self.total_runs_completed += 1
                return summary
            except Exception as exc:
                self.last_error = str(exc)
                logger.error("Error executing automated health check: %s", exc, exc_info=True)
                raise

    def get_status(self) -> Dict[str, Any]:
        """Return operational status and metadata for diagnostics and API exposure."""
        return {
            "is_running": self.is_running,
            "interval_seconds": self.interval_seconds,
            "batch_size": self.batch_size,
            "concurrency": self.concurrency,
            "last_run_started_at": self.last_run_started_at.isoformat() if self.last_run_started_at else None,
            "last_run_completed_at": self.last_run_completed_at.isoformat() if self.last_run_completed_at else None,
            "next_run_estimated_at": self.next_run_estimated_at.isoformat() if self.next_run_estimated_at else None,
            "total_runs_completed": self.total_runs_completed,
            "last_summary": self.last_summary,
            "last_error": self.last_error
        }

    def _worker_loop(self):
        """Internal daemon worker thread loop."""
        logger.debug("HealthCheckScheduler worker thread active.")

        while not self._stop_event.is_set():
            # Wait for either manual trigger or interval timeout
            triggered = self._trigger_event.wait(timeout=float(self.interval_seconds))
            if self._stop_event.is_set():
                break

            if triggered:
                self._trigger_event.clear()

            # Execute batch check
            try:
                logger.info("Executing scheduled stream health check iteration...")
                self.execute_check(
                    limit=self.batch_size,
                    concurrency=self.concurrency,
                    use_lock=True
                )
            except Exception as exc:
                logger.warning("Scheduled health check cycle encountered error: %s", exc)

            # Schedule next run estimate
            self.next_run_estimated_at = datetime.now(timezone.utc) + timedelta(seconds=self.interval_seconds)

        self._is_running = False
        logger.debug("HealthCheckScheduler worker thread terminated.")


# Module-level singleton
_scheduler_instance: Optional[HealthCheckScheduler] = None
_scheduler_lock = threading.Lock()


def get_health_scheduler() -> HealthCheckScheduler:
    """Retrieve or create the global HealthCheckScheduler singleton instance."""
    global _scheduler_instance
    with _scheduler_lock:
        if _scheduler_instance is None:
            _scheduler_instance = HealthCheckScheduler()
        return _scheduler_instance


def start_health_check_scheduler(app, run_immediately: bool = False) -> bool:
    """Convenience helper to initialize and launch the health scheduler."""
    scheduler = get_health_scheduler()
    return scheduler.start(app, run_immediately=run_immediately)


def stop_health_check_scheduler() -> bool:
    """Convenience helper to halt the global health scheduler."""
    global _scheduler_instance
    if _scheduler_instance:
        return _scheduler_instance.stop()
    return True


# Register clean shutdown on interpreter termination
atexit.register(stop_health_check_scheduler)
