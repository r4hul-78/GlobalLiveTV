from flask import Blueprint, render_template, current_app

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    """Render the main channel discovery and player landing page."""
    current_app.logger.debug("Serving index landing page")
    return render_template(
        "index.html",
        title="Global Live TV Platform",
        app_name="Global Live TV",
        version="1.0.0"
    )


@main_bp.route("/about")
def about():
    """Render the about and project ethics page."""
    return render_template(
        "about.html",
        title="About - Global Live TV Platform",
        app_name="Global Live TV"
    )
