"""
REST API Blueprint
Exposes public catalog endpoints, channel detail, search, dynamic filters, and operational health.
"""
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, current_app
from sqlalchemy import text
from app import db
from app.models import Channel, ChannelReport
from app.services.channel_service import ChannelService, DEFAULT_PER_PAGE, MAX_PER_PAGE


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

