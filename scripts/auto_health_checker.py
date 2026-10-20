"""
Standalone Continuous Automated Health Check Daemon
Runs continuous background health checks on catalog channels.
Cycles through channels in priority order (oldest/never checked first),
preventing lock collisions and handling graceful termination.
"""
import sys
import time
import signal
import logging
import argparse
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app import create_app, db
from app.jobs.health_job import run_health_job

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [auto_health_checker] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("auto_health_checker")

# Graceful termination handling
shutdown_requested = False


def signal_handler(signum, frame):
    global shutdown_requested
    sig_name = signal.Signals(signum).name
    logger.info("Received termination signal %s. Initiating graceful shutdown...", sig_name)
    shutdown_requested = True


def run_daemon(
    interval: int = 300,
    batch_size: int = 50,
    concurrency: int = 5,
    status_filter: str = None,
    run_once: bool = False
):
    """
    Main execution loop for continuous health checking.
    """
    signal.signal(signal.SIGINT, signal_handler)
    try:
        signal.signal(signal.SIGTERM, signal_handler)
    except (AttributeError, ValueError):
        # SIGTERM might not be available or catchable on all Windows configurations
        pass

    app = create_app()

    cycle_count = 0
    total_probed = 0
    total_healthy = 0
    total_degraded = 0
    total_unavailable = 0
    total_unsupported = 0

    logger.info("=================================================================")
    logger.info("  Global Live TV - Continuous Stream Health Daemon")
    logger.info("  Interval: %ds | Batch Size: %d | Concurrency: %d", interval, batch_size, concurrency)
    logger.info("  Mode: %s", "Single Run" if run_once else "Continuous Daemon")
    logger.info("=================================================================")

    with app.app_context():
        # Ensure database tables exist
        db.create_all()

        while not shutdown_requested:
            cycle_count += 1
            cycle_start = time.time()
            logger.info("--- Starting Health Check Cycle #%d at %s ---", cycle_count, datetime.now(timezone.utc).isoformat())

            try:
                summary = run_health_job(
                    limit=batch_size,
                    status_filter=status_filter,
                    concurrency=concurrency,
                    use_lock=True
                )

                if summary.get("error"):
                    logger.warning("Cycle #%d skipped or deferred: %s", cycle_count, summary["error"])
                else:
                    probed = summary.get("total_checked", 0)
                    h = summary.get("healthy", 0)
                    d = summary.get("degraded", 0)
                    u = summary.get("unavailable", 0)
                    uns = summary.get("unsupported", 0)

                    total_probed += probed
                    total_healthy += h
                    total_degraded += d
                    total_unavailable += u
                    total_unsupported += uns

                    elapsed = time.time() - cycle_start
                    logger.info(
                        "Cycle #%d completed in %.2fs. Probed: %d (Healthy: %d, Degraded: %d, Unavailable: %d, Unsupported: %d)",
                        cycle_count, elapsed, probed, h, d, u, uns
                    )

            except Exception as exc:
                logger.error("Unhandled exception in cycle #%d: %s", cycle_count, exc, exc_info=True)

            if run_once:
                break

            # Sleep in 1-second ticks so we can respond immediately to shutdown signals
            sleep_remaining = interval
            logger.info("Next health check cycle scheduled in %d seconds. Waiting...", interval)
            while sleep_remaining > 0 and not shutdown_requested:
                time.sleep(1)
                sleep_remaining -= 1

    logger.info("=================================================================")
    logger.info("  Health Daemon Terminated.")
    logger.info("  Total Cycles: %d | Total Probed: %d", cycle_count, total_probed)
    logger.info("  Healthy: %d | Degraded: %d | Unavailable: %d | Unsupported: %d",
                total_healthy, total_degraded, total_unavailable, total_unsupported)
    logger.info("=================================================================")


def main():
    parser = argparse.ArgumentParser(description="Continuous stream health checking daemon.")
    parser.add_argument("--interval", type=int, default=300, help="Seconds to wait between cycles (default: 300).")
    parser.add_argument("--batch-size", type=int, default=50, help="Number of channels to check per cycle (default: 50).")
    parser.add_argument("--concurrency", type=int, default=5, help="Concurrent probe threads (default: 5).")
    parser.add_argument("--status", type=str, default=None, help="Optional health status filter.")
    parser.add_argument("--run-once", action="store_true", help="Execute single cycle and exit.")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    run_daemon(
        interval=args.interval,
        batch_size=args.batch_size,
        concurrency=args.concurrency,
        status_filter=args.status,
        run_once=args.run_once
    )


if __name__ == "__main__":
    main()
