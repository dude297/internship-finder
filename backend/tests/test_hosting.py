"""Hosted-deployment safeguards that need no database (ADR-009). Synthetic values only."""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.api.auth import DIRECT_CLIENT, PROXY_SECRET_HEADER, login_client_key
from app.core.config import get_settings
from app.main import create_app

SECRET = "synthetic-proxy-secret-0123456789abcdef"


@pytest.fixture
def proxy_secret(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("PROXY_SHARED_SECRET", SECRET)
    get_settings.cache_clear()
    yield


def request_with(**headers: str) -> Request:
    raw = [(k.replace("_", "-").lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "method": "POST", "path": "/", "headers": raw})


def hosted_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setenv("HOSTED", "true")
    get_settings.cache_clear()
    return create_app()


# --- Login throttle client identity (ADR-009 §6) ----------------------------------------------


@pytest.mark.usefixtures("proxy_secret")
def test_proxied_request_is_keyed_by_the_forwarded_client() -> None:
    request = request_with(
        x_if_proxy_secret=SECRET, x_forwarded_for="198.51.100.7, 203.0.113.1, 10.0.0.2"
    )

    assert login_client_key(request) == "proxy:198.51.100.7"


@pytest.mark.usefixtures("proxy_secret")
@pytest.mark.parametrize(
    "headers",
    [
        {"x_forwarded_for": "198.51.100.7"},  # direct caller forging the address
        {"x_if_proxy_secret": "wrong-" + SECRET, "x_forwarded_for": "198.51.100.7"},
        {"x_if_proxy_secret": "", "x_forwarded_for": "198.51.100.7"},
        {"x_real_ip": "198.51.100.7", "x_vercel_forwarded_for": "198.51.100.7"},
        {},
    ],
)
def test_untrusted_requests_share_the_direct_key(headers: dict[str, str]) -> None:
    assert login_client_key(request_with(**headers)) == DIRECT_CLIENT


def test_forwarded_headers_are_ignored_without_a_configured_secret() -> None:
    request = request_with(x_if_proxy_secret=SECRET, x_forwarded_for="198.51.100.7")

    assert login_client_key(request) == DIRECT_CLIENT


@pytest.mark.usefixtures("proxy_secret")
def test_proxied_request_without_forwarded_for_still_has_a_key() -> None:
    assert login_client_key(request_with(x_if_proxy_secret=SECRET)) == "proxy:unknown"


def test_proxy_secret_header_name() -> None:
    assert PROXY_SECRET_HEADER == "X-IF-Proxy-Secret"


# --- API docs surface, caching, redirects -----------------------------------------------------


def test_local_mode_keeps_interactive_docs() -> None:
    client = TestClient(create_app())

    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200


def test_hosted_mode_hides_docs_but_keeps_the_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    app = hosted_app(monkeypatch)
    client = TestClient(app)

    for path in ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"):
        assert client.get(path).status_code == 404, path
    assert "/api/auth/login" in app.openapi()["paths"]
    assert client.get("/api/health").status_code == 200


def test_api_responses_are_not_cacheable() -> None:
    client = TestClient(create_app())

    for path in ("/api/health", "/api/does-not-exist"):
        assert client.get(path).headers["cache-control"] == "no-store", path


def test_unknown_api_paths_are_json_404s() -> None:
    response = TestClient(create_app()).get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


@pytest.mark.parametrize("path", ["/api/health/", "/api/auth/session/", "/api/opportunities/"])
def test_no_automatic_slash_redirects(path: str) -> None:
    """A redirect from Render would name the Render host instead of the Vercel origin."""
    response = TestClient(create_app()).get(path, follow_redirects=False)

    assert response.status_code == 404
    assert "location" not in response.headers
