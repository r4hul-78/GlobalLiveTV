"""
Application Entry Point
Runs the Flask application server.
"""
import os
from app import create_app

app = create_app()

if __name__ == "__main__":
    host = os.getenv("FLASK_RUN_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_RUN_PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "1").lower() in ("true", "1", "yes")

    print(f"Starting Global Live TV Platform on http://{host}:{port} (Debug: {debug})")
    app.run(host=host, port=port, debug=debug)
