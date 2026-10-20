"""
Process Concurrency and Non-Overlapping Job Lock Service
Prevents concurrent background execution of catalog ingestion, health checks,
and refresh tasks using robust PID and timestamp verification.
"""
import os
import sys
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)


def is_process_running(pid: int) -> bool:
    """
    Check if a process with the given PID is currently active on the host OS.
    Works across Windows and POSIX systems.
    """
    if pid <= 0:
        return False

    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            kernel32 = ctypes.windll.kernel32
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259

            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return False
            try:
                exit_code = wintypes.DWORD()
                if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return exit_code.value == STILL_ACTIVE
                return False
            finally:
                kernel32.CloseHandle(handle)
        except Exception as exc:
            logger.warning("Error checking process liveness for PID %d on Windows: %s", pid, exc)
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


class LockAcquisitionError(Exception):
    """Raised when a job lock cannot be acquired because another worker is running."""
    pass


class JobLock:
    """
    File-based process lock to prevent concurrent runs of background tasks.
    Safely recovers from stale or orphaned locks left by killed processes.
    """

    def __init__(
        self,
        name: str,
        lock_dir: Optional[str] = None,
        timeout_seconds: int = 3600
    ):
        self.name = name
        self.timeout_seconds = timeout_seconds

        if lock_dir:
            self.lock_dir = Path(lock_dir)
        else:
            # Default to instance/locks relative to project root
            base_dir = Path(__file__).resolve().parent.parent.parent
            self.lock_dir = base_dir / "instance" / "locks"

        self.lock_dir.mkdir(parents=True, exist_ok=True)
        self.lock_file = self.lock_dir / f"{self.name}.lock"
        self._is_acquired = False

    def acquire(self) -> bool:
        """
        Attempt to acquire the lock.
        Raises LockAcquisitionError if an active process already holds it.
        """
        if self._is_acquired:
            return True

        now = datetime.now(timezone.utc)

        if self.lock_file.exists():
            stale, holder_info = self._check_if_stale()
            if not stale:
                pid = holder_info.get("pid", "unknown")
                started = holder_info.get("started_at", "unknown")
                msg = (
                    f"Job '{self.name}' is already running under PID {pid} "
                    f"(started at {started}). Aborting to prevent overlapping execution."
                )
                logger.warning(msg)
                raise LockAcquisitionError(msg)
            else:
                logger.warning(
                    "Reclaiming stale lock file for '%s' (previous PID %s)",
                    self.name,
                    holder_info.get("pid")
                )
                try:
                    self.lock_file.unlink(missing_ok=True)
                except Exception as exc:
                    logger.warning("Could not remove stale lock file: %s", exc)

        # Write lock payload
        payload = {
            "name": self.name,
            "pid": os.getpid(),
            "started_at": now.isoformat()
        }

        try:
            temp_path = self.lock_file.with_suffix(".tmp")
            temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            temp_path.replace(self.lock_file)
            self._is_acquired = True
            logger.debug("Acquired lock '%s' (PID %d)", self.name, os.getpid())
            return True
        except Exception as exc:
            msg = f"Failed to write lock file for '{self.name}': {exc}"
            logger.error(msg)
            raise LockAcquisitionError(msg) from exc

    def release(self) -> bool:
        """
        Release the lock file if owned by the current process.
        """
        if not self.lock_file.exists():
            self._is_acquired = False
            return True

        try:
            data = json.loads(self.lock_file.read_text(encoding="utf-8"))
            if data.get("pid") == os.getpid():
                self.lock_file.unlink(missing_ok=True)
                self._is_acquired = False
                logger.debug("Released lock '%s' (PID %d)", self.name, os.getpid())
                return True
            else:
                logger.warning(
                    "Did not release lock '%s': owned by PID %s, current PID is %d",
                    self.name,
                    data.get("pid"),
                    os.getpid()
                )
                return False
        except Exception as exc:
            logger.warning("Error releasing lock '%s': %s", self.name, exc)
            self.lock_file.unlink(missing_ok=True)
            self._is_acquired = False
            return True

    def _check_if_stale(self) -> Tuple[bool, Dict[str, Any]]:
        """
        Evaluate whether the existing lock file is stale.
        Returns (is_stale: bool, lock_info: dict)
        """
        try:
            content = self.lock_file.read_text(encoding="utf-8")
            data = json.loads(content)
        except Exception:
            # Corrupted or empty lock file is treated as stale
            return True, {}

        pid = data.get("pid")
        started_str = data.get("started_at")

        if not pid or not isinstance(pid, int):
            return True, data

        # Check process liveness
        if not is_process_running(pid):
            return True, data

        # Check timeout expiration
        if started_str:
            try:
                started_dt = datetime.fromisoformat(started_str)
                age_seconds = (datetime.now(timezone.utc) - started_dt).total_seconds()
                if age_seconds > self.timeout_seconds:
                    logger.warning(
                        "Lock '%s' held by PID %d has exceeded timeout (%.1fs > %ds)",
                        self.name,
                        pid,
                        age_seconds,
                        self.timeout_seconds
                    )
                    return True, data
            except Exception:
                pass

        return False, data

    @classmethod
    def get_lock_status(cls, name: str, lock_dir: Optional[str] = None) -> Dict[str, Any]:
        """Inspect the current lock status without acquiring it."""
        lock = cls(name, lock_dir=lock_dir)
        if not lock.lock_file.exists():
            return {"locked": False}
        stale, data = lock._check_if_stale()
        return {
            "locked": not stale,
            "stale": stale,
            "info": data
        }

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
