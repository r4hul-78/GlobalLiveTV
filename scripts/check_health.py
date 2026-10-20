"""
CLI Stream Health-Check Script
Probes stream availability outside of Flask web workers.
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
from app.jobs.health_job import run_health_job


def main():
    parser = argparse.ArgumentParser(description="Run stream health checks on catalog channels.")
    parser.add_argument("--limit", type=int, default=50, help="Maximum number of channels to inspect (default: 50).")
    parser.add_argument("--channel-id", type=int, default=None, help="Check a specific channel by ID.")
    parser.add_argument("--status", type=str, default=None, help="Filter by current health status (e.g., unknown, degraded).")
    parser.add_argument("--concurrency", type=int, default=5, help="Number of concurrent worker threads (default: 5).")
    parser.add_argument("--no-lock", action="store_true", help="Bypass worker lock check (not recommended).")

    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        # Ensure database tables exist
        db.create_all()

        print(f"=== Starting Stream Health Check (Limit: {args.limit}, Concurrency: {args.concurrency}) ===")
        print(f"Started at: {datetime.now(timezone.utc).isoformat()}")

        use_lock = not args.no_lock
        summary = run_health_job(
            limit=args.limit,
            status_filter=args.status,
            concurrency=args.concurrency,
            channel_id=args.channel_id,
            use_lock=use_lock
        )

        if summary.get("error"):
            print(f"\nExecution Aborted: {summary['error']}", file=sys.stderr)
            sys.exit(1)

        print("\n=== Stream Health Audit Summary ===")
        print(f"Total Inspected: {summary['total_checked']}")
        print(f"Healthy:         {summary['healthy']}")
        print(f"Degraded:        {summary['degraded']}")
        print(f"Unavailable:     {summary['unavailable']}")
        print(f"Unsupported:     {summary['unsupported']}")
        print(f"Completed at:    {datetime.now(timezone.utc).isoformat()}")

        if summary["results"]:
            print("\nChannel Outcomes (First 10):")
            for item in summary["results"][:10]:
                rt = f"{item['response_time_ms']:.0f}ms" if item.get('response_time_ms') is not None else "N/A"
                print(f" - [Channel #{item['channel_id']}] Status: {item['outcome'].upper()} ({rt}) - {item['diagnostic_reason']}")


if __name__ == "__main__":
    main()
