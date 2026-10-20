"""
Unified Catalog Refresh Script
Orchestrates automated IPTV playlist ingestion and stream health validation outside Flask web workers.
Guarded by process locks to prevent concurrent runs and duplicate workers.
"""
import sys
import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app import create_app, db
from app.models.job_run import JobRun
from app.jobs.ingest_job import run_ingest_job
from app.jobs.health_job import run_health_job
from app.services.lock_service import JobLock, LockAcquisitionError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("refresh_catalog")


def main():
    parser = argparse.ArgumentParser(
        description="Unified catalog refresh: orchestrates IPTV playlist ingestion and stream health checks."
    )
    parser.add_argument(
        "--mode",
        choices=["full", "ingest-only", "health-only"],
        default="full",
        help="Refresh operation mode (default: full)."
    )
    parser.add_argument(
        "--ingest-limit",
        type=int,
        default=None,
        help="Maximum channels to ingest (None for all)."
    )
    parser.add_argument(
        "--health-limit",
        type=int,
        default=50,
        help="Maximum channels to health-check (default: 50)."
    )
    parser.add_argument(
        "--health-status",
        type=str,
        default=None,
        help="Filter channels to health-check by status (e.g. unknown, degraded)."
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Concurrency for health checking worker threads (default: 5)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate ingestion without database writes."
    )
    parser.add_argument(
        "--no-lock",
        action="store_true",
        help="Bypass master process lock (not recommended)."
    )

    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        # Ensure database tables exist
        db.create_all()

        start_time = datetime.now(timezone.utc)
        print("=" * 65)
        print("GLOBAL LIVE TV PLATFORM — AUTOMATED REFRESH RUNNER")
        print("=" * 65)
        print(f"Mode:          {args.mode}")
        print(f"Dry Run:       {args.dry_run}")
        print(f"Started At:    {start_time.isoformat()}")
        print("-" * 65)

        master_lock = JobLock("refresh_catalog") if not args.no_lock else None
        if master_lock:
            try:
                master_lock.acquire()
            except LockAcquisitionError as err:
                print(f"Aborted: {err}", file=sys.stderr)
                sys.exit(1)

        job_run = None
        if not args.dry_run:
            try:
                job_run = JobRun(
                    job_type=f"refresh_{args.mode}",
                    status="running",
                    started_at=start_time
                )
                db.session.add(job_run)
                db.session.commit()
            except Exception as exc:
                logger.warning("Could not create JobRun record: %s", exc)

        ingest_summary = None
        health_summary = None
        has_error = False

        try:
            # Phase 1: Ingestion
            if args.mode in ("full", "ingest-only"):
                print("\n[Phase 1/2] Ingesting IPTV Playlists...")
                ingest_res = run_ingest_job(
                    dry_run=args.dry_run,
                    limit=args.ingest_limit,
                    use_lock=False  # Master lock covers execution
                )
                ingest_summary = {
                    "total_parsed": ingest_res.total_parsed,
                    "imported": ingest_res.imported,
                    "updated": ingest_res.updated,
                    "skipped": ingest_res.skipped,
                    "errors": len(ingest_res.errors),
                    "duration_seconds": ingest_res.duration_seconds
                }
                print(f"  -> Ingestion completed in {ingest_res.duration_seconds:.2f}s")
                print(f"     Imported: {ingest_res.imported}, Updated: {ingest_res.updated}, Errors: {len(ingest_res.errors)}")

            # Phase 2: Stream Health Inspection
            if args.mode in ("full", "health-only"):
                print(f"\n[Phase 2/2] Inspecting Stream Health (Limit: {args.health_limit}, Concurrency: {args.concurrency})...")
                health_res = run_health_job(
                    limit=args.health_limit,
                    status_filter=args.health_status,
                    concurrency=args.concurrency,
                    use_lock=False  # Master lock covers execution
                )
                health_summary = health_res
                print(f"  -> Health check completed: {health_res['total_checked']} checked")
                print(f"     Healthy: {health_res['healthy']}, Degraded: {health_res['degraded']}, "
                      f"Unavailable: {health_res['unavailable']}, Unsupported: {health_res['unsupported']}")

        except Exception as exc:
            has_error = True
            logger.error("Error occurred during refresh job: %s", exc, exc_info=True)
            if job_run:
                try:
                    job_run.status = "failed"
                    job_run.completed_at = datetime.now(timezone.utc)
                    job_run.duration_seconds = (job_run.completed_at - start_time).total_seconds()
                    job_run.error_message = str(exc)
                    db.session.commit()
                except Exception:
                    pass
            print(f"\nRefresh Runner Error: {exc}", file=sys.stderr)
            sys.exit(1)

        finally:
            if master_lock:
                master_lock.release()

        end_time = datetime.now(timezone.utc)
        total_duration = (end_time - start_time).total_seconds()

        if job_run and not has_error:
            try:
                job_run.status = "completed"
                job_run.completed_at = end_time
                job_run.duration_seconds = total_duration

                summary_parts = []
                if ingest_summary:
                    job_run.records_imported = ingest_summary["imported"]
                    job_run.records_updated = ingest_summary["updated"]
                    job_run.records_skipped = ingest_summary["skipped"]
                    job_run.records_failed = ingest_summary["errors"]
                    summary_parts.append(
                        f"Ingested: {ingest_summary['imported']} new, {ingest_summary['updated']} upd"
                    )
                if health_summary:
                    job_run.records_processed = health_summary["total_checked"]
                    summary_parts.append(
                        f"Checked: {health_summary['total_checked']} ({health_summary['healthy']} healthy, {health_summary['unavailable']} unavail)"
                    )
                job_run.summary = "; ".join(summary_parts)
                db.session.commit()
            except Exception as exc:
                logger.warning("Could not finalize JobRun record: %s", exc)

        print("\n" + "=" * 65)
        print("REFRESH RUN COMPLETED SUCCESSFULLY")
        print("=" * 65)
        print(f"Completed At:   {end_time.isoformat()}")
        print(f"Total Duration: {total_duration:.2f}s")
        if ingest_summary:
            print(f"Ingest Stats:   {ingest_summary['imported']} imported, {ingest_summary['updated']} updated, {ingest_summary['errors']} errors")
        if health_summary:
            print(f"Health Stats:   {health_summary['healthy']} healthy, {health_summary['degraded']} degraded, {health_summary['unavailable']} unavailable")
        print("=" * 65)


if __name__ == "__main__":
    main()
