import pytest
from app import create_app, db


@pytest.fixture
def app():
    """Create and configure a clean Flask application instance for testing."""
    test_app = create_app("testing")
    
    with test_app.app_context():
        db.create_all()
        yield test_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """Provide a test client for simulating HTTP requests."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Provide a CLI test runner for testing Flask CLI commands."""
    return app.test_cli_runner()
