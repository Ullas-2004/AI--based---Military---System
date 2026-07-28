"""Shared pytest fixtures.

The suite runs without a real MongoDB: ``mongomock`` provides an in-memory
replacement so persistence paths are genuinely exercised in CI.
"""
import os
import sys

import mongomock
import pytest

API_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, API_DIR)

# Deterministic, safe configuration before any application import.
os.environ.update({
    "FLASK_ENV": "development",
    "FLASK_DEBUG": "0",
    "JWT_SECRET_KEY": "test-secret-key-that-is-long-enough-for-hs256-abcdef",
    "BCRYPT_ROUNDS": "4",          # keep hashing fast in tests
    "TOKEN_EXPIRY_HOURS": "1",
    "GROQ_API_KEY": "",            # force offline assistant mode
    "MAX_UPLOAD_MB": "2",
})


@pytest.fixture()
def mock_db(monkeypatch):
    """An in-memory MongoDB wired into every module that calls get_db()."""
    client = mongomock.MongoClient()
    db = client["aegis_test"]
    db.users.create_index("username_lower", unique=True)

    import database.mongodb as mongodb
    monkeypatch.setattr(mongodb, "get_db", lambda: db)
    for module in (
        "middleware.auth", "routes.auth_routes", "routes.threat_routes",
        "routes.predictive_routes", "routes.assistant_routes",
        "routes.data_routes", "services.report_service",
    ):
        __import__(module)
        monkeypatch.setattr(sys.modules[module], "get_db", lambda: db, raising=False)
    return db


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """Counters are process-global; clear them so tests stay independent."""
    from middleware import rate_limit
    rate_limit.reset()
    yield
    rate_limit.reset()


@pytest.fixture()
def app():
    from app import create_app
    application = create_app()
    application.config.update(TESTING=True)
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def auth_headers():
    """Valid analyst credentials as an Authorization header."""
    from middleware.auth import generate_token
    return {"Authorization": f"Bearer {generate_token('user-1', 'analyst')}"}


@pytest.fixture()
def admin_headers():
    from middleware.auth import generate_token
    return {"Authorization": f"Bearer {generate_token('admin-1', 'admin')}"}
