"""Tests to verify the backend project setup is correct."""

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_endpoint():
    """The health check endpoint returns OK status."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_cors_middleware_configured():
    """CORS middleware allows requests from the configured origin."""
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" in response.headers


def test_app_title():
    """The application has the correct title."""
    assert app.title == "Daily Money Tracker"


def test_database_module_imports():
    """Database engine and session factory are properly configured."""
    from app.database import Base, SessionLocal, engine

    assert engine is not None
    assert SessionLocal is not None
    assert Base is not None


def test_scheduler_module_imports():
    """APScheduler is properly configured."""
    from app.scheduler import scheduler

    assert scheduler is not None


def test_config_defaults():
    """Application config has expected defaults."""
    from app.config import settings

    assert settings.app_name == "Daily Money Tracker"
    assert "mysql+pymysql" in settings.database_url
