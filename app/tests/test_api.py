import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from app.main import app
from app.core.config import settings
from app.db.session import get_db_session

client = TestClient(app)


def test_healthz():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "aivar-backend"}


def test_api_key_protection():
    # If settings is not in dev mode, it should block requests without header
    original_env = settings.APP_ENV
    settings.APP_ENV = "production"
    try:
        response = client.get("/api/v1/assets")
        assert response.status_code == 401
    finally:
        settings.APP_ENV = original_env


def test_validation_rejection():
    # Attempting to post invalid data to discovery endpoint
    response = client.post(
        "/api/v1/assets/discovery",
        json={"invalid_field": "error"},
        headers={"X-API-Key": settings.API_KEY}
    )
    # FastAPI returns 422 Unprocessable Entity for invalid schema inputs
    assert response.status_code == 422
