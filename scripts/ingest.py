"""
CLI Ingestion Script
Runs IPTV playlist ingestion outside of Flask web workers.
Guarded by process-level lock to prevent concurrent runs.
"""
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app import create_app, db
from app.models.job_run import JobRun
from app.services.ingestion_service import IngestionService
from app.services.channel_service import ChannelService
from app.services.lock_service import JobLock, LockAcquisitionError
from app.jobs.ingest_job import run_ingest_job


def main():
    parser = argparse.ArgumentParser(description="Ingest IPTV channels into the database.")
    parser.add_argument("--dry-run", action="store_true", help="Simulate ingestion without committing to database.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of channels to import.")
    parser.add_argument("--file", type=str, default=None, help="Import from a local M3U file instead of downloading.")
    parser.add_argument("--url", type=str, default=None, help="Custom primary M3U playlist URL.")
    parser.add_argument("--no-lock", action="store_true", help="Bypass worker lock check (not recommended).")

    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        # Ensure database tables exist
        db.create_all()

        print(f"=== Starting IPTV Ingestion (Dry-run: {args.dry_run}, Limit: {args.limit}) ===")
        print(f"Started at: {datetime.now(timezone.utc).isoformat()}")

        use_lock = not args.no_lock

        if args.file:
            file_path = Path(args.file)
            if not file_path.exists():
                print(f"Error: Local file not found: {args.file}", file=sys.stderr)
                sys.exit(1)

            lock = JobLock("ingest") if use_lock else None
            if lock:
                try:
                    lock.acquire()
                except LockAcquisitionError as err:
                    print(f"Lock Error: {err}", file=sys.stderr)
                    sys.exit(1)

            try:
                print(f"Reading local playlist file: {file_path}")
                content = file_path.read_text(encoding="utf-8", errors="replace")
                service = IngestionService()
                result = service.ingest_from_content(content, dry_run=args.dry_run, limit=args.limit)

                if not args.dry_run:
                    ChannelService.invalidate_filter_cache()
                    # Audit job run
                    try:
                        job_run = JobRun(
                            job_type="ingest_local",
                            status="completed",
                            started_at=datetime.now(timezone.utc),
                            completed_at=datetime.now(timezone.utc),
                            duration_seconds=result.duration_seconds,
                            records_processed=result.total_parsed,
                            records_imported=result.imported,
                            records_updated=result.updated,
                            records_skipped=result.skipped,
                            records_failed=len(result.errors),
                            summary=f"Imported from {args.file}: {result.imported} new, {result.updated} updated"
                        )
                        db.session.add(job_run)
                        db.session.commit()
                    except Exception as exc:
                        print(f"Warning: Could not save JobRun record: {exc}", file=sys.stderr)
            finally:
                if lock:
                    lock.release()
        else:
            result = run_ingest_job(
                dry_run=args.dry_run,
                limit=args.limit,
                main_url=args.url,
                use_lock=use_lock
            )

        print("\n=== Ingestion Summary ===")
        print(f"Total Parsed:     {result.total_parsed}")
        print(f"New Imported:     {result.imported}")
        print(f"Updated Records:  {result.updated}")
        print(f"Skipped Entries:  {result.skipped}")
        print(f"Errors:           {len(result.errors)}")
        print(f"Duration:         {result.duration_seconds:.2f}s")
        print(f"Dry Run:          {result.dry_run}")
        print(f"Completed at:     {datetime.now(timezone.utc).isoformat()}")

        if result.errors:
            print("\nSample Errors:")
            for err in result.errors[:5]:
                print(f" - {err}")


if __name__ == "__main__":
    main()
