"""Password hashing, token, CSRF, and throttle primitives. No database. Synthetic values only."""

import hashlib
import threading
import time

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


def test_limiter_global_cap_blocks_every_client() -> None:
    limiter = auth.FailedLoginLimiter(max_failures=3, max_global_failures=5, window_seconds=60)
    for i in range(5):  # five clients, one failure each: none reaches its own limit
        assert not limiter.blocked(f"proxy:198.51.100.{i}", now=float(i))
        limiter.record_failure(f"proxy:198.51.100.{i}", now=float(i))

    assert limiter.blocked("proxy:203.0.113.9", now=10.0)  # a fresh client too
    assert limiter.blocked("direct", now=10.0)
    assert not limiter.blocked("proxy:203.0.113.9", now=60.5)  # the first failure expired


def test_limiter_window_expiry_unblocks_the_client() -> None:
    limiter = auth.FailedLoginLimiter(max_failures=2, window_seconds=900)
    limiter.record_failure("direct", now=0.0)
    limiter.record_failure("direct", now=1.0)

    assert limiter.blocked("direct", now=899.9)
    assert not limiter.blocked("direct", now=901.0)


def test_limiter_default_policy() -> None:
    limiter = auth.FailedLoginLimiter()

    assert (limiter.max_failures, limiter.max_global_failures) == (10, 50)
    assert limiter.window_seconds == 15 * 60


def test_limiter_sweeps_stale_keys() -> None:
    limiter = auth.FailedLoginLimiter(max_failures=10, max_global_failures=2, window_seconds=10)
    for i in range(5):
        limiter.record_failure(f"k{i}", now=0.0)
    limiter.record_failure("fresh", now=100.0)

    assert set(limiter._failures) == {"fresh"}  # pyright: ignore[reportPrivateUsage]


def test_argon2_work_is_capped_per_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """Many concurrent logins never run more than ARGON2_CONCURRENCY hashes at once."""
    active = 0
    peak = 0
    lock = threading.Lock()

    def slow_verify(password: str, password_hash: str) -> bool:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return False

    monkeypatch.setattr(auth._password_hash, "verify", slow_verify)  # pyright: ignore[reportPrivateUsage]
    threads = [
        threading.Thread(target=auth.verify_password, args=(PASSWORD, "hash")) for _ in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert peak == auth.ARGON2_CONCURRENCY == 2


def test_argon2_guard_is_released_after_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(password: str, password_hash: str) -> bool:
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(auth._password_hash, "verify", broken)  # pyright: ignore[reportPrivateUsage]
    for _ in range(auth.ARGON2_CONCURRENCY + 1):
        with pytest.raises(RuntimeError):
            auth.verify_password(PASSWORD, "hash")
    monkeypatch.undo()

    assert auth.verify_password(PASSWORD, auth.hash_password(PASSWORD))  # slots still free
