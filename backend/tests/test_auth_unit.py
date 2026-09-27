"""Password hashing, token, CSRF, and throttle primitives. No database. Synthetic values only."""

import hashlib

import pytest

from app.services import auth

PASSWORD = "synthetic-test-password"


def test_password_hash_is_argon2id_and_not_the_password() -> None:
    hashed = auth.hash_password(PASSWORD)

    assert hashed != PASSWORD
    assert PASSWORD not in hashed
    assert hashed.startswith("$argon2id$")
    assert auth.verify_password(PASSWORD, hashed)
    assert not auth.verify_password(PASSWORD + "x", hashed)


def test_password_hashes_are_salted() -> None:
    assert auth.hash_password(PASSWORD) != auth.hash_password(PASSWORD)


def test_token_hash_is_sha256_hex() -> None:
    assert auth.hash_token("abc") == hashlib.sha256(b"abc").hexdigest()


def test_csrf_token_is_bound_to_the_session_token() -> None:
    token = "synthetic-session-token"
    csrf = auth.csrf_token_for(token)

    assert csrf != token and token not in csrf
    assert auth.csrf_token_for(token) == csrf  # stable across reloads
    assert auth.csrf_matches(token, csrf)
    assert not auth.csrf_matches(token, None)
    assert not auth.csrf_matches(token, "")
    assert not auth.csrf_matches(token, auth.csrf_token_for("another-session-token"))


@pytest.mark.parametrize("password", ["", "short", "x" * (auth.MIN_PASSWORD_LENGTH - 1)])
def test_new_passwords_must_be_long_enough(password: str) -> None:
    with pytest.raises(auth.OwnerError):
        auth.check_new_password(password)


def test_limiter_blocks_after_max_failures_within_the_window() -> None:
    limiter = auth.FailedLoginLimiter(max_failures=3, window_seconds=60)
    for t in (0.0, 1.0, 2.0):
        assert not limiter.blocked("1.2.3.4", now=t)
        limiter.record_failure("1.2.3.4", now=t)

    assert limiter.blocked("1.2.3.4", now=3.0)
    assert not limiter.blocked("5.6.7.8", now=3.0)  # per client
    assert limiter.blocked("1.2.3.4", now=59.9)
    assert not limiter.blocked("1.2.3.4", now=60.5)  # the oldest failure slid out


def test_limiter_forgets_old_failures() -> None:
    limiter = auth.FailedLoginLimiter(max_failures=2, window_seconds=10)
    limiter.record_failure("k", now=0.0)
    limiter.record_failure("k", now=20.0)

    assert not limiter.blocked("k", now=21.0)
