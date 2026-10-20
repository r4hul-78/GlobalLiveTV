"""
Decoupled Ingestion Job
Executes IPTV catalog ingestion independently of web requests.
Supports concurrency locking, incremental limits, and job run auditing.
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from flask import current_app

from app import db
from app.models.job_run import JobRun
from app.services.ingestion_service import IngestionService, IngestionResult
from app.services.channel_service import ChannelService
from app.services.lock_service import JobLock, LockAcquisitionError

logger = logging.getLogger(__name__)


def run_ingest_job(
    dry_run: bool = False,
    limit: Optional[int] = None,
    main_url: Optional[str] = None,
    country_url: Optional[str] = None,
    category_url: Optional[str] = None,
    language_url: Optional[str] = None,
    use_lock: bool = True
) -> IngestionResult:
    """
    Run an end-to-end IPTV ingestion job using configured or custom URLs.
    Guarded by JobLock to prevent overlapping executions.
    Records audit entry in JobRun table.
    """
    config = current_app.config
    main_url = main_url or config.get("PLAYLIST_INDEX_URL")
    country_url = country_url or config.get("PLAYLIST_COUNTRY_URL")
    category_url = category_url or config.get("PLAYLIST_CATEGORY_URL")
    language_url = language_url or config.get("PLAYLIST_LANGUAGE_URL")

    lock = JobLock("ingest", timeout_seconds=config.get("REFRESH_LOCK_TIMEOUT_SECONDS", 3600)) if use_lock else None

    if lock:
        try:
            lock.acquire()
        except LockAcquisitionError as err:
            logger.warning("Ingest job aborted: %s", err)
            result = IngestionResult(dry_run=dry_run)
            result.errors.append(str(err))
            return result

    started_at = datetime.now(timezone.utc)
    job_run = None
    if not dry_run:
        try:
            job_run = JobRun(
                job_type="ingest",
                status="running",
                started_at=started_at
            )
            db.session.add(job_run)
            db.session.commit()
        except Exception as exc:
            logger.warning("Could not create initial JobRun audit record: %s", exc)
            db.session.rollback()

    try:
        logger.info("Starting ingestion job (dry_run=%s, limit=%s)", dry_run, limit)
        service = IngestionService()

        logger.info("Downloading primary playlist: %s", main_url)
        main_content = service.download_playlist(main_url)

        if not main_content:
            logger.error("Primary playlist download failed. Preserving existing catalog.")
            result = IngestionResult(dry_run=dry_run)
            result.errors.append(f"Failed to fetch primary playlist from {main_url}")

            if job_run:
                job_run.status = "failed"
                job_run.completed_at = datetime.now(timezone.utc)
                job_run.duration_seconds = (job_run.completed_at - started_at).total_seconds()
                job_run.error_message = f"Failed to download primary playlist from {main_url}"
                db.session.commit()

            return result

        logger.info("Downloading supplementary playlists (country, category, language)...")
        country_content = service.download_playlist(country_url) if country_url else None
        category_content = service.download_playlist(category_url) if category_url else None
        language_content = service.download_playlist(language_url) if language_url else None

        result = service.ingest_from_content(
            main_content=main_content,
            country_content=country_content,
            category_content=category_content,
            language_content=language_content,
            dry_run=dry_run,
            limit=limit
        )

        # Invalidate filter cache on successful import/update
        if not dry_run and (result.imported > 0 or result.updated > 0):
            ChannelService.invalidate_filter_cache()

        logger.info(
            "Ingestion job complete in %.2fs: %d imported, %d updated, %d skipped, %d errors",
            result.duration_seconds,
            result.imported,
            result.updated,
            result.skipped,
            len(result.errors)
        )

        if job_run:
            job_run.status = "completed"
            job_run.completed_at = datetime.now(timezone.utc)
            job_run.duration_seconds = result.duration_seconds
            job_run.records_processed = result.total_parsed
            job_run.records_imported = result.imported
            job_run.records_updated = result.updated
            job_run.records_skipped = result.skipped
            job_run.records_failed = len(result.errors)
            job_run.summary = (
                f"Parsed: {result.total_parsed}, Imported: {result.imported}, "
                f"Updated: {result.updated}, Skipped: {result.skipped}, Errors: {len(result.errors)}"
            )
            db.session.commit()

        return result

    except Exception as exc:
        logger.error("Unhandled exception during ingestion job: %s", exc, exc_info=True)
        if job_run:
            try:
                job_run.status = "failed"
                job_run.completed_at = datetime.now(timezone.utc)
                job_run.duration_seconds = (job_run.completed_at - started_at).total_seconds()
                job_run.error_message = str(exc)
                db.session.commit()
            except Exception:
                db.session.rollback()
        raise
    finally:
        if lock:
            lock.release()
