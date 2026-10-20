import os
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from flask import Flask, jsonify, render_template, request
from flask_sqlalchemy import SQLAlchemy
from app.config import get_config

# Initialize extensions
db = SQLAlchemy()


def setup_logging(app):
    """Configure structured logging for the application."""
    log_level = getattr(logging, app.config.get("LOG_LEVEL", "INFO"), logging.INFO)
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s in %(module)s (%(process)d): %(message)s"
    )

    # Clean existing handlers to prevent duplicates
    app.logger.handlers.clear()
    app.logger.setLevel(log_level)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    app.logger.addHandler(console_handler)

    # File handler if enabled
    if app.config.get("LOG_TO_FILE"):
        log_file_path = Path(app.config.get("LOG_FILE_PATH", "logs/app.log"))
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            str(log_file_path),
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(log_level)
        app.logger.addHandler(file_handler)

    app.logger.info("Logging configured with level: %s", app.config.get("LOG_LEVEL", "INFO"))


def register_error_handlers(app):
    """Register centralized error handlers for both API and UI routes."""

    @app.errorhandler(404)
    def handle_not_found(error):
        if request.path.startswith("/api/"):
            return jsonify({
                "error": "Not Found",
                "message": "The requested API resource does not exist.",
                "status": 404
            }), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def handle_internal_server_error(error):
        app.logger.error("Internal Server Error: %s", str(error), exc_info=True)
        if request.path.startswith("/api/"):
            return jsonify({
                "error": "Internal Server Error",
                "message": "An unexpected error occurred. Please try again later.",
                "status": 500
            }), 500
        return render_template("errors/500.html"), 500

    @app.errorhandler(400)
    def handle_bad_request(error):
        if request.path.startswith("/api/"):
            return jsonify({
                "error": "Bad Request",
                "message": str(error.description) if hasattr(error, "description") else "Malformed request.",
                "status": 400
            }), 400
        return render_template("errors/400.html", error=error), 400


def create_app(config_name=None):
    """Application factory for the Global Live TV Platform."""
    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder="templates",
        static_folder="static"
    )

    # Load configuration
    config_class = get_config(config_name)
    app.config.from_object(config_class)

    # Ensure the instance directory exists for SQLite
    os.makedirs(app.instance_path, exist_ok=True)

    # Configure logging
    setup_logging(app)

    # Initialize extensions
    db.init_app(app)

    # Register blueprints
    from app.routes.main import main_bp
    from app.routes.api import api_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    # Register error handlers
    register_error_handlers(app)

    app.logger.info("Application initialized successfully in %s mode", config_class.__name__)
    return app
