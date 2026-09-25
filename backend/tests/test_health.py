import pytest
from fastapi.testclient import TestClient

from app.api.health import HealthResponse
from app.main import app, create_app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    HealthResponse.model_validate(response.json())


def test_health_does_not_need_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert client.get("/api/health").status_code == 200


def test_cors_allows_only_configured_origin() -> None:
    allowed = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    other = client.get("/api/health", headers={"Origin": "https://evil.example"})

    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in other.headers


def test_cors_uses_frontend_origin_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://app.example")
    configured = TestClient(create_app())

    allowed = configured.get("/api/health", headers={"Origin": "https://app.example"})
    default = configured.get("/api/health", headers={"Origin": "http://localhost:5173"})

    assert allowed.headers.get("access-control-allow-origin") == "https://app.example"
    assert "access-control-allow-origin" not in default.headers
