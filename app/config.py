import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file if present
load_dotenv(BASE_DIR / ".env")


def _get_database_uri():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        instance_dir = BASE_DIR / "instance"
        instance_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{instance_dir / 'iptv.db'}"
    
    # If using sqlite relative path, ensure parent directory exists
    if db_url.startswith("sqlite:///"):
        rel_path = db_url.replace("sqlite:///", "")
        if not os.path.isabs(rel_path):
            full_path = (BASE_DIR / rel_path).resolve()
            full_path.parent.mkdir(parents=True, exist_ok=True)
            return f"sqlite:///{full_path}"
        else:
            Path(rel_path).parent.mkdir(parents=True, exist_ok=True)
    return db_url


class Config:
    """Base application configuration."""
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure-secret-key-change-in-production")
    
    # Database configuration
    SQLALCHEMY_DATABASE_URI = _get_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Logging configuration
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_TO_FILE = os.getenv("LOG_TO_FILE", "false").lower() in ("true", "1", "yes")
    LOG_FILE_PATH = os.getenv("LOG_FILE_PATH", str(BASE_DIR / "logs" / "app.log"))
    
    # Ingestion URLs
    PLAYLIST_INDEX_URL = os.getenv(
        "PLAYLIST_INDEX_URL", 
        "https://iptv-org.github.io/iptv/index.m3u"
    )
    PLAYLIST_COUNTRY_URL = os.getenv(
        "PLAYLIST_COUNTRY_URL", 
        "https://iptv-org.github.io/iptv/index.country.m3u"
    )
    PLAYLIST_CATEGORY_URL = os.getenv(
        "PLAYLIST_CATEGORY_URL", 
        "https://iptv-org.github.io/iptv/index.category.m3u"
    )
    PLAYLIST_LANGUAGE_URL = os.getenv(
        "PLAYLIST_LANGUAGE_URL", 
        "https://iptv-org.github.io/iptv/index.language.m3u"
    )
    
    # Stream Health Checking
    HEALTH_CHECK_TIMEOUT_SECONDS = int(os.getenv("HEALTH_CHECK_TIMEOUT_SECONDS", "5"))
    HEALTH_CHECK_CONCURRENCY = int(os.getenv("HEALTH_CHECK_CONCURRENCY", "5"))
    HEALTH_CHECK_MAX_FAILURES = int(os.getenv("HEALTH_CHECK_MAX_FAILURES", "3"))

    # Performance, Caching & Concurrency Locks
    FILTER_CACHE_TTL_SECONDS = int(os.getenv("FILTER_CACHE_TTL_SECONDS", "300"))
    REFRESH_LOCK_TIMEOUT_SECONDS = int(os.getenv("REFRESH_LOCK_TIMEOUT_SECONDS", "3600"))
    REFRESH_BATCH_SIZE = int(os.getenv("REFRESH_BATCH_SIZE", "50"))


class DevelopmentConfig(Config):
    """Development environment configuration."""
    DEBUG = True
    TESTING = False
    TEMPLATES_AUTO_RELOAD = True
    SEND_FILE_MAX_AGE_DEFAULT = 0


class TestingConfig(Config):
    """Testing environment configuration."""
    DEBUG = False
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    LOG_LEVEL = "WARNING"


class ProductionConfig(Config):
    """Production environment configuration."""
    DEBUG = False
    TESTING = False


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}


def get_config(config_name=None):
    """Retrieve config class by name or FLASK_ENV environment variable."""
    if config_name is None:
        config_name = os.getenv("FLASK_ENV", "development").lower()
    return config_by_name.get(config_name, DevelopmentConfig)
