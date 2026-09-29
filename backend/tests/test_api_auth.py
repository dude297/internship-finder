"""Authentication, sessions, CSRF, and the private-API boundary (ADR-007). Synthetic data only."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.main import PUBLIC_PATHS, create_app
from app.models import AuthSession, AuthUser
from app.services import auth as auth_service
from app.services.auth import FailedLoginLimiter, hash_token
from tests.conftest import OWNER_PASSWORD, OWNER_USERNAME

pytestmark = pytest.mark.postgres

GENERIC_FAILURE = {"detail": "Invalid username or password."}


def login(client: TestClient, username: str = OWNER_USERNAME, password: str = OWNER_PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def set_cookie_header(response_headers: list[tuple[str, str]]) -> str:
    [cookie] = [v for k, v in response_headers if k.lower() == "set-cookie"]
    return cookie


def test_login_sets_a_hardened_session_cookie(anon_client: TestClient, owner: AuthUser) -> None:
    response = login(anon_client)

    assert response.status_code == 200
    body = response.json()
    assert body["authenticated"] is True
    assert body["username"] == OWNER_USERNAME
    assert body["csrf_token"]
    assert set(body) == {"authenticated", "username", "csrf_token"}
    cookie = set_cookie_header(response.headers.multi_items()).lower()
    assert cookie.startswith("if_session=")
    for attribute in ("httponly", "secure", "samesite=lax", "path=/", "max-age=86400"):
        assert attribute in cookie


def test_cookie_secure_flag_follows_configuration(
    anon_client: TestClient, owner: AuthUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    get_settings.cache_clear()  # the app factory already read settings

    cookie = set_cookie_header(login(anon_client).headers.multi_items()).lower()

    assert "secure" not in cookie
    assert "httponly" in cookie


def test_only_hashes_are_stored(anon_client: TestClient, owner: AuthUser, db: Session) -> None:
    response = login(anon_client)
    token = response.cookies["if_session"]

    [session] = db.scalars(select(AuthSession)).all()
    user = db.get(AuthUser, owner.id)
    assert user is not None
    assert session.token_hash == hash_token(token)
    assert token not in session.token_hash
    assert len(token) >= 43  # 32 random bytes, base64url
    assert user.password_hash != OWNER_PASSWORD
    assert user.password_hash.startswith("$argon2id$")
    assert response.json()["csrf_token"] != token


@pytest.mark.parametrize(
    ("username", "password"),
    [
        (OWNER_USERNAME, "wrong-synthetic-password"),
        ("unknown-synthetic-user", OWNER_PASSWORD),
        (OWNER_USERNAME.upper(), OWNER_PASSWORD),
    ],
)
def test_login_failures_are_generic(
    anon_client: TestClient, owner: AuthUser, username: str, password: str
) -> None:
    response = login(anon_client, username, password)

    assert response.status_code == 401
    assert response.json() == GENERIC_FAILURE
    assert "set-cookie" not in response.headers


def test_disabled_user_cannot_log_in_and_loses_sessions(
    client: TestClient, owner: AuthUser, db: Session
) -> None:
    db.execute(update(AuthUser).values(is_active=False))
    db.commit()

    assert client.get("/api/opportunities").status_code == 401
    assert client.get("/api/auth/session").json() == {
        "authenticated": False,
        "username": None,
        "csrf_token": None,
    }
    response = login(client)
    assert response.status_code == 401
    assert response.json() == GENERIC_FAILURE


def test_session_endpoint_reports_state_and_returns_the_same_csrf(
    anon_client: TestClient, owner: AuthUser
) -> None:
    assert anon_client.get("/api/auth/session").json()["authenticated"] is False

    csrf = login(anon_client).json()["csrf_token"]
    status = anon_client.get("/api/auth/session").json()

    assert status == {"authenticated": True, "username": OWNER_USERNAME, "csrf_token": csrf}


def test_expired_session_is_rejected(client: TestClient, db: Session) -> None:
    db.execute(update(AuthSession).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    db.commit()

    assert client.get("/api/opportunities").status_code == 401
    assert client.get("/api/auth/session").json()["authenticated"] is False


def test_logout_revokes_the_session(client: TestClient, db: Session) -> None:
    token = client.cookies["if_session"]

    response = client.post("/api/auth/logout")

    assert response.status_code == 204
    assert (
        'if_session=""' in response.headers["set-cookie"]
        or "Max-Age=0" in (response.headers["set-cookie"])
    )
    assert db.scalars(select(AuthSession)).all() == []
    client.cookies.set("if_session", token)  # replaying the old cookie doesn't help
    assert client.get("/api/opportunities").status_code == 401


def test_login_again_replaces_this_browsers_session(client: TestClient, db: Session) -> None:
    old = client.cookies["if_session"]

    login(client)

    [session] = db.scalars(select(AuthSession)).all()
    assert session.token_hash != hash_token(old)


@pytest.mark.parametrize("cookie", [None, "", "not-a-real-session-token"])
def test_missing_or_invalid_cookie_is_401(
    anon_client: TestClient, owner: AuthUser, cookie: str | None
) -> None:
    if cookie is not None:
        anon_client.cookies.set("if_session", cookie)

    assert anon_client.get("/api/profile").status_code == 401
    assert anon_client.put("/api/profile", json={}).status_code == 401


@pytest.mark.parametrize("csrf", [None, "", "wrong-token"])
def test_mutations_require_a_valid_csrf_token(client: TestClient, csrf: str | None) -> None:
    del client.headers["X-CSRF-Token"]
    headers = {} if csrf is None else {"X-CSRF-Token": csrf}

    for response in (
        client.put("/api/profile", json={}, headers=headers),
        client.post("/api/auth/logout", headers=headers),
        client.post("/api/sources/sync", headers=headers),
        client.post("/api/sources", json={}, headers=headers),
    ):
        assert response.status_code == 403
        assert response.json() == {"detail": "Missing or invalid CSRF token."}
    assert client.get("/api/opportunities").status_code == 200  # reads don't need it
    assert client.get("/api/sources").status_code == 200


def test_valid_csrf_token_allows_mutation(client: TestClient) -> None:
    assert client.put("/api/profile", json={}).status_code == 200


def test_csrf_token_from_another_session_is_rejected(
    anon_client: TestClient, owner: AuthUser
) -> None:
    other_csrf = login(anon_client).json()["csrf_token"]
    login(anon_client)  # new session in this browser; the old one is replaced

    response = anon_client.put("/api/profile", json={}, headers={"X-CSRF-Token": other_csrf})

    assert response.status_code == 403


def test_every_non_public_route_requires_authentication(
    anon_client: TestClient, owner: AuthUser
) -> None:
    # Every API operation the app registers, from its OpenAPI schema.
    paths: dict[str, dict[str, object]] = create_app().openapi()["paths"]
    operations = [(m.upper(), p) for p, ops in paths.items() for m in ops]
    private = [(m, p) for m, p in operations if p not in PUBLIC_PATHS]
    assert {p for _, p in operations} >= PUBLIC_PATHS
    assert len(private) >= 17

    for method, template in private:
        path = template.replace("{opportunity_id}", "00000000-0000-0000-0000-000000000000")
        path = path.replace("{source_id}", "00000000-0000-0000-0000-000000000000")
        response = anon_client.request(method, path, json={})
        assert response.status_code == 401, (method, template)


def test_there_is_no_registration_endpoint(anon_client: TestClient) -> None:
    for path in ("/api/auth/register", "/api/auth/signup", "/api/users"):
        assert anon_client.post(path, json={}).status_code in {404, 405}


def test_validation_errors_do_not_echo_the_password(anon_client: TestClient) -> None:
    secret = "synthetic-secret-value"
    response = anon_client.post("/api/auth/login", json={"username": "", "password": secret})

    assert response.status_code == 422
    assert secret not in response.text
    assert all(set(e) <= {"loc", "msg", "type"} for e in response.json()["detail"])


def test_repeated_failures_are_throttled(anon_client: TestClient, owner: AuthUser) -> None:
    for _ in range(10):
        assert login(anon_client, password="wrong-synthetic-password").status_code == 401

    blocked = login(anon_client)  # even the right password, until the window passes

    assert blocked.status_code == 429
    assert "set-cookie" not in blocked.headers


# --- Hosted login throttle (ADR-009 §6) -------------------------------------------------------

PROXY_SECRET = "synthetic-proxy-secret-0123456789abcdef"


@pytest.fixture
def proxied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROXY_SHARED_SECRET", PROXY_SECRET)
    get_settings.cache_clear()


def via_proxy(client: TestClient, address: str, password: str = OWNER_PASSWORD):
    return client.post(
        "/api/auth/login",
        json={"username": OWNER_USERNAME, "password": password},
        headers={"X-IF-Proxy-Secret": PROXY_SECRET, "X-Forwarded-For": address},
    )


@pytest.mark.usefixtures("proxied")
def test_forged_addresses_through_the_proxy_share_one_bucket(
    anon_client: TestClient, owner: AuthUser
) -> None:
    for i in range(10):
        assert via_proxy(anon_client, f"198.51.100.{i}", "wrong-synthetic").status_code == 401

    assert via_proxy(anon_client, "198.51.100.200").status_code == 429
    assert login(anon_client).status_code == 200  # the direct bucket is separate


@pytest.mark.usefixtures("proxied")
def test_direct_callers_cannot_spoof_new_buckets(anon_client: TestClient, owner: AuthUser) -> None:
    for i in range(10):
        response = anon_client.post(
            "/api/auth/login",
            json={"username": OWNER_USERNAME, "password": "wrong-synthetic"},
            headers={"X-Forwarded-For": f"203.0.113.{i}", "X-IF-Proxy-Secret": "forged"},
        )
        assert response.status_code == 401

    spoofed = anon_client.post(
        "/api/auth/login",
        json={"username": OWNER_USERNAME, "password": OWNER_PASSWORD},
        headers={"X-Forwarded-For": "203.0.113.200"},
    )
    assert spoofed.status_code == 429
    assert via_proxy(anon_client, "198.51.100.3").status_code == 200  # browsers unaffected


@pytest.mark.usefixtures("proxied")
def test_global_limit_blocks_every_client(anon_client: TestClient, owner: AuthUser) -> None:
    anon_client.app.state.login_limiter = FailedLoginLimiter(  # type: ignore[attr-defined]
        max_failures=10, max_global_failures=3
    )
    for i in range(3):
        assert via_proxy(anon_client, f"198.51.100.{i}", "wrong-synthetic").status_code == 401

    assert via_proxy(anon_client, "198.51.100.99").status_code == 429
    assert login(anon_client).status_code == 429


def test_throttle_window_expires(
    anon_client: TestClient, owner: AuthUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [1000.0]
    monkeypatch.setattr(auth_service.time, "monotonic", lambda: clock[0])
    for _ in range(10):
        assert login(anon_client, password="wrong-synthetic").status_code == 401
    assert login(anon_client).status_code == 429

    clock[0] += 15 * 60 + 1

    assert login(anon_client).status_code == 200


def test_successful_login_is_not_counted_and_does_not_reset(
    anon_client: TestClient, owner: AuthUser
) -> None:
    for _ in range(9):
        assert login(anon_client, password="wrong-synthetic").status_code == 401
    for _ in range(3):
        assert login(anon_client).status_code == 200  # successes don't count

    assert login(anon_client, password="wrong-synthetic").status_code == 401  # 10th failure
    assert login(anon_client).status_code == 429  # and the earlier nine still did


# --- Private responses are never cacheable (ADR-009 §8) ---------------------------------------


@pytest.mark.parametrize(
    "path", ["/api/auth/session", "/api/profile", "/api/opportunities", "/api/sources"]
)
def test_private_responses_are_no_store(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert response.status_code in {200, 404}  # the profile is 404 until created
    assert response.headers["cache-control"] == "no-store"


def test_rejected_requests_are_no_store(anon_client: TestClient) -> None:
    assert anon_client.get("/api/profile").headers["cache-control"] == "no-store"


def test_login_response_is_no_store(anon_client: TestClient, owner: AuthUser) -> None:
    assert login(anon_client).headers["cache-control"] == "no-store"


def test_collection_paths_are_exact(client: TestClient) -> None:
    assert client.get("/api/opportunities").status_code == 200
    response = client.get("/api/opportunities/", follow_redirects=False)
    assert response.status_code == 404  # no redirect toward the backend host
    assert client.post("/api/sources/", json={}, follow_redirects=False).status_code in {404, 405}
