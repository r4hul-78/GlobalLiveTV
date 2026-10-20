import sys
import argparse
from pathlib import Path

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app import create_app, db
import app.models  # Register all models with SQLAlchemy metadata


def init_database(reset=False):
    """Create database tables within application context."""
    flask_app = create_app()
    with flask_app.app_context():
        if reset:
            print("Dropping all existing database tables...")
            db.drop_all()
        print(f"Creating database tables using URI: {flask_app.config['SQLALCHEMY_DATABASE_URI']}")
        db.create_all()
        print("Database tables initialized successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize database schema.")
    parser.add_argument("--reset", action="store_true", help="Drop existing tables before recreating.")
    args = parser.parse_args()
    init_database(reset=args.reset)
