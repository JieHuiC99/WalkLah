import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_endpoint():
    """Test that /health returns 200 with status ok."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_response_schema():
    """Test that /health response matches HealthResponse schema."""
    from app.schemas import HealthResponse

    response = client.get("/health")
    data = response.json()

    # Validate against schema
    health_response = HealthResponse(**data)
    assert health_response.status == "ok"
