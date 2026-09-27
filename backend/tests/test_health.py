import pytest
from fastapi.testclient import TestClient

from app.api.health import HealthResponse
from app.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    HealthResponse.model_validate(response.json())


def test_health_does_not_need_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert client.get("/api/health").status_code == 200


def test_no_cross_origin_access_is_granted() -> None:
    """Same-origin API (ADR-007 §6): browsers must refuse cross-origin reads."""
    response = client.get("/api/health", headers={"Origin": "https://evil.example"})
    preflight = client.options(
        "/api/auth/login",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )

    assert "access-control-allow-origin" not in response.headers
    assert "access-control-allow-origin" not in preflight.headers
