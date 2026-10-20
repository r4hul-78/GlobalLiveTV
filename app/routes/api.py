"""
REST API Blueprint
Exposes public catalog endpoints, channel detail, search, dynamic filters, and operational health.
"""
from datetime import datetime, timezone
import threading
from flask import Blueprint, jsonify, request, current_app
from sqlalchemy import text, func
from app import db
from app.models import Channel, ChannelReport, JobRun
from app.services.channel_service import ChannelService, DEFAULT_PER_PAGE, MAX_PER_PAGE
from app.jobs.health_job import run_health_job
from app.services.scheduler_service import get_health_scheduler
from app.services.health_checker import StreamHealthChecker


api_bp = Blueprint("api", __name__)


@api_bp.after_request
def add_cors_headers(response):
    """Enable CORS headers for cross-origin browser access and previews."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Accept,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response



@api_bp.route("/health", methods=["GET"])
def health_check():
    """
    Return minimal application health status and catalog summary.
    Avoids exposing internal server paths, credentials, or sensitive infrastructure.
    """
    db_status = "connected"
    channel_count = 0
    http_code = 200

    try:
        db.session.execute(text("SELECT 1"))
        channel_count = Channel.query.filter_by(is_active=True).count()
    except Exception as exc:
        current_app.logger.warning("Database connectivity check failed: %s", str(exc))
        db_status = "unavailable"
        http_code = 503

    return jsonify({
        "status": "healthy" if db_status == "connected" else "degraded",
        "service": "Global Live TV Platform",
        "database": db_status,
        "total_active_channels": channel_count,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }), http_code


@api_bp.route("/channels", methods=["GET"])
def get_channels():
    """
    Search and filter catalog channels with pagination and deterministic sorting.
    Query parameters:
      - q: channel name or external ID search
      - country: country code (e.g., 'US', 'FR')
      - genre: category slug or name (e.g., 'news', 'sports')
      - language: language code (e.g., 'eng', 'spa')
      - status: health status ('healthy', 'degraded', 'unavailable', 'unsupported', 'unknown')
      - page: page number (>= 1, default: 1)
      - per_page: page size (1..100, default: 20)
    """
    # Parse pagination parameters
    try:
        page = int(request.args.get("page", 1))
    except (ValueError, TypeError):
        return jsonify({
            "error": "Bad Request",
            "message": "Query parameter 'page' must be a valid positive integer.",
            "status": 400
        }), 400

    try:
        per_page = int(request.args.get("per_page", DEFAULT_PER_PAGE))
    except (ValueError, TypeError):
        return jsonify({
            "error": "Bad Request",
            "message": f"Query parameter 'per_page' must be a valid integer between 1 and {MAX_PER_PAGE}.",
            "status": 400
        }), 400

    # Extract filter parameters
    q = request.args.get("q", "").strip() or None
    country = request.args.get("country", "").strip() or None
    genre = request.args.get("genre", "").strip() or None
    language = request.args.get("language", "").strip() or None
    status = request.args.get("status", "").strip() or None

    try:
        channels, total_items, total_pages = ChannelService.search_channels(
            q=q,
            country=country,
            genre=genre,
            language=language,
            status=status,
            page=page,
            per_page=per_page
        )
    except ValueError as val_err:
        return jsonify({
            "error": "Bad Request",
            "message": str(val_err),
            "status": 400
        }), 400
    except Exception as exc:
        current_app.logger.error("Failed to query channel catalog: %s", str(exc), exc_info=True)
        return jsonify({
            "error": "Internal Server Error",
            "message": "A database error occurred while querying channels.",
            "status": 500
        }), 500

    has_prev = page > 1 and page <= total_pages
    has_next = page < total_pages

    return jsonify({
        "data": [c.to_dict() for c in channels],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total_items": total_items,
            "total_pages": total_pages,
            "has_prev": has_prev,
            "has_next": has_next
        },
        "filters": {
            "q": q,
            "country": country,
            "genre": genre,
            "language": language,
            "status": status
        }
    }), 200


@api_bp.route("/channels/<int:channel_id>", methods=["GET"])
def get_channel_detail(channel_id: int):
    """
    Retrieve single channel metadata and recent health check audit records.
    """
    channel = ChannelService.get_channel_by_id(channel_id)
    if not channel:
        return jsonify({
            "error": "Not Found",
            "message": f"Channel with ID {channel_id} was not found.",
            "status": 404
        }), 404

    return jsonify({
        "data": channel.to_dict(include_checks=True)
    }), 200


@api_bp.route("/filters", methods=["GET"])
def get_filters():
    """
    Return available countries, genres, and languages associated with active channels.
    """
    try:
        filter_metadata = ChannelService.get_available_filters()
        return jsonify(filter_metadata), 200
    except Exception as exc:
        current_app.logger.error("Failed to load filter metadata: %s", str(exc), exc_info=True)
        return jsonify({
            "error": "Internal Server Error",
            "message": "Failed to retrieve filter options.",
            "status": 500
        }), 500


VALID_REPORT_ISSUES = {
    "offline": "Stream Offline / Blank Screen",
    "playback_error": "Playback Error / Format Unsupported",
    "audio_issue": "Audio Missing or Out of Sync",
    "wrong_channel": "Wrong Channel / Mismatched Broadcast",
    "geo_blocked": "Geo-Blocked / CORS Restricted",
    "buffering": "Severe Buffering / Freezing",
    "other": "Other Technical Issue"
}


@api_bp.route("/channels/<int:channel_id>/report", methods=["POST"])
def report_channel_issue(channel_id: int):
    """
    Submit an anonymous channel issue report.
    Guarantees privacy: No IP address, email, or user tracking cookies collected.
    """
    channel = ChannelService.get_channel_by_id(channel_id)
    if not channel:
        return jsonify({
            "error": "Not Found",
            "message": f"Channel with ID {channel_id} was not found.",
            "status": 404
        }), 404

    payload = request.get_json(silent=True) or {}
    issue_type = str(payload.get("issue_type", "")).strip().lower()
    description = str(payload.get("description", "")).strip()

    if not issue_type or issue_type not in VALID_REPORT_ISSUES:
        return jsonify({
            "error": "Bad Request",
            "message": f"Field 'issue_type' is required and must be one of: {list(VALID_REPORT_ISSUES.keys())}",
            "status": 400
        }), 400

    if len(description) > 500:
        description = description[:500]

    report = ChannelReport(
        channel_id=channel.id,
        issue_type=issue_type,
        description=description or None
    )

    try:
        db.session.add(report)
        db.session.commit()
        current_app.logger.info(
            "Channel issue report submitted for #%d '%s': issue=%s",
            channel.id, channel.name, issue_type
        )
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error("Failed to save channel report: %s", str(exc), exc_info=True)
        return jsonify({
            "error": "Internal Server Error",
            "message": "Failed to record issue report.",
            "status": 500
        }), 500

    return jsonify({
        "status": "success",
        "message": "Thank you! Your issue report has been recorded anonymously.",
        "report": {
            "id": report.id,
            "channel_id": channel.id,
            "channel_name": channel.name,
            "issue_type": report.issue_type,
            "reported_at": report.reported_at.isoformat()
        }
    }), 201


@api_bp.route("/health-check/status", methods=["GET"])
def get_health_check_status():
    """
    Retrieve current status of automated health check scheduler and channel health breakdown.
    """
    scheduler = get_health_scheduler()
    scheduler_status = scheduler.get_status()

    # Query breakdown of channel health states
    try:
        counts = dict(
            db.session.query(Channel.health_status, func.count(Channel.id))
            .filter(Channel.is_active == True)
            .group_by(Channel.health_status)
            .all()
        )
    except Exception as exc:
        current_app.logger.warning("Failed to aggregate channel health status: %s", exc)
        counts = {}

    total_active = sum(counts.values())

    # Retrieve latest JobRun for health_check if any
    try:
        latest_job = JobRun.query.filter_by(job_type="health_check").order_by(JobRun.id.desc()).first()
        latest_run_info = latest_job.to_dict() if latest_job else None
    except Exception as exc:
        current_app.logger.warning("Failed to query latest health check job run: %s", exc)
        latest_run_info = None

    return jsonify({
        "scheduler": scheduler_status,
        "latest_run": latest_run_info,
        "catalog_summary": {
            "total_active_channels": total_active,
            "healthy": counts.get("healthy", 0),
            "degraded": counts.get("degraded", 0),
            "unavailable": counts.get("unavailable", 0),
            "unsupported": counts.get("unsupported", 0),
            "unknown": counts.get("unknown", 0)
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }), 200


@api_bp.route("/health-check/run", methods=["POST"])
def trigger_health_check_run():
    """
    Trigger a batch stream health check run.
    Accepts JSON or query parameters:
      - limit: int (1..500, default: 50)
      - status: str (optional health status filter)
      - concurrency: int (1..20, default: 10)
      - async: bool (default: False)
    """
    payload = request.get_json(silent=True) or {}

    try:
        limit = int(request.args.get("limit", payload.get("limit", 50)))
        if limit < 1 or limit > 500:
            limit = 50
    except (ValueError, TypeError):
        limit = 50

    try:
        concurrency = int(request.args.get("concurrency", payload.get("concurrency", 10)))
        if concurrency < 1 or concurrency > 20:
            concurrency = 10
    except (ValueError, TypeError):
        concurrency = 10

    status_filter = request.args.get("status", payload.get("status", "")).strip().lower() or None
    is_async = str(request.args.get("async", payload.get("async", "false"))).lower() in ("true", "1", "yes")

    if is_async:
        app_obj = current_app._get_current_object()
        def _async_runner():
            with app_obj.app_context():
                try:
                    run_health_job(
                        limit=limit,
                        status_filter=status_filter,
                        concurrency=concurrency,
                        use_lock=True
                    )
                except Exception as exc:
                    app_obj.logger.error("Async health check failed: %s", exc)

        t = threading.Thread(target=_async_runner, daemon=True)
        t.start()

        return jsonify({
            "status": "started",
            "message": f"Background stream health check dispatched (limit={limit}, concurrency={concurrency}).",
            "parameters": {
                "limit": limit,
                "status_filter": status_filter,
                "concurrency": concurrency,
                "async": True
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }), 202

    try:
        summary = run_health_job(
            limit=limit,
            status_filter=status_filter,
            concurrency=concurrency,
            use_lock=True
        )

        if summary.get("error"):
            return jsonify({
                "error": "Conflict",
                "message": summary["error"],
                "status": 409
            }), 409

        return jsonify({
            "status": "completed",
            "summary": summary,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }), 200

    except Exception as exc:
        current_app.logger.error("Health check execution failed: %s", exc, exc_info=True)
        return jsonify({
            "error": "Internal Server Error",
            "message": "Health check execution failed.",
            "status": 500
        }), 500


@api_bp.route("/channels/<int:channel_id>/check", methods=["POST"])
def check_single_channel(channel_id: int):
    """
    Trigger an immediate on-demand health probe for a single channel.
    Updates the channel's health_status and records an audit StreamCheck.
    """
    channel = Channel.query.get(channel_id)
    if not channel:
        return jsonify({
            "error": "Not Found",
            "message": f"Channel with ID {channel_id} was not found.",
            "status": 404
        }), 404

    if not channel.is_active:
        return jsonify({
            "error": "Bad Request",
            "message": f"Channel with ID {channel_id} is inactive.",
            "status": 400
        }), 400

    try:
        config = current_app.config
        timeout = config.get("HEALTH_CHECK_TIMEOUT_SECONDS", 5)
        max_failures = config.get("HEALTH_CHECK_MAX_FAILURES", 3)
        checker = StreamHealthChecker(timeout=timeout, max_failures=max_failures)

        result = checker.check_stream(channel, save=True)
        ChannelService.invalidate_filter_cache()

        current_app.logger.info(
            "On-demand health check for channel #%d '%s': %s (response_time=%.1fms)",
            channel.id, channel.name, result.outcome, result.response_time_ms or 0.0
        )

        return jsonify({
            "status": "success",
            "channel": channel.to_dict(include_checks=True),
            "result": result.to_dict(),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }), 200

    except Exception as exc:
        db.session.rollback()
        current_app.logger.error("Failed to check stream for channel #%d: %s", channel_id, exc, exc_info=True)
        return jsonify({
            "error": "Internal Server Error",
            "message": f"Failed to check channel stream: {str(exc)}",
            "status": 500
        }), 500

