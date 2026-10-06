"""The only HTTP client used for ingestion (ADR-008 §10). A security boundary.

Only HTTPS GETs to hard-coded provider hosts. Adapters build URLs from those hosts and a
validated identifier; nothing user-supplied is ever requested.
"""

import ipaddress
import json
import logging
import re
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx2

from app.core.config import get_settings

logger = logging.getLogger(__name__)

ALLOWED_HOSTS = frozenset(
    {
        "zshah101.github.io",
        "boards-api.greenhouse.io",
        "api.lever.co",
        "api.eu.lever.co",
        "api.ashbyhq.com",
        "api.smartrecruiters.com",
        # Workable's documented widget API answers on www and redirects to apply (ADR-015 §7).
        "www.workable.com",
        "apply.workable.com",
    }
)
# Providers that serve each customer's public board from its own subdomain of a fixed provider
# domain (ADR-015 §7). The label is validated by the adapter; this is the network boundary.
ALLOWED_HOST_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.pinpointhq\.com\Z")
USER_AGENT = (
    "PersonalInternshipFinder/0.1 (single-user; +https://github.com/dude297/internship-finder)"
)
TIMEOUT = httpx2.Timeout(connect=5.0, read=20.0, write=10.0, pool=5.0)
MAX_BYTES = 20 * 1024 * 1024
MAX_REDIRECTS = 3
MAX_ATTEMPTS = 3
MAX_RETRY_AFTER_SECONDS = 30.0
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


class FetchError(Exception):
    """A safe, user-presentable fetch failure. `code` is a short machine-readable category."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Fetched:
    """`data` is None when the server answered 304 Not Modified."""

    data: Any
    etag: str | None
    last_modified: str | None
    size: int = 0  # decoded body bytes (0 for 304); lets a multi-request adapter keep a budget

    @property
    def not_modified(self) -> bool:
        return self.data is None


Resolver = Callable[[str], list[str]]


def _resolve(host: str) -> list[str]:
    return [str(info[4][0]) for info in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)]


def check_url(url: str, resolve: Resolver | None = _resolve) -> None:
    """Refuse anything but HTTPS to an allowlisted host on the default port without userinfo,
    and (when `resolve` is given) any host that resolves to a non-public address."""
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise FetchError("blocked_url", "Only HTTPS source URLs are allowed.")
    if parts.username or parts.password or parts.port not in (None, 443):
        raise FetchError("blocked_url", "Source URLs can't carry credentials or custom ports.")
    host = (parts.hostname or "").lower()
    if host not in ALLOWED_HOSTS and not ALLOWED_HOST_PATTERN.fullmatch(host):
        raise FetchError("blocked_url", "The source host isn't on the allowlist.")
    if resolve is None:
        return
    try:
        addresses = resolve(host)
    except OSError as error:
        raise FetchError("network_error", f"Couldn't resolve {host}.") from error
    # Defense in depth: the hosts are fixed public providers, but never connect inward.
    if not addresses or not all(ipaddress.ip_address(a).is_global for a in addresses):
        raise FetchError("blocked_url", f"{host} resolved to a non-public address.")


def _retry_delay(response: httpx2.Response | None, attempt: int) -> float:
    header = response.headers.get("Retry-After") if response is not None else None
    if header:
        try:
            delay = float(header)
        except ValueError:
            try:
                delay = parsedate_to_datetime(header).timestamp() - time.time()
            except (TypeError, ValueError):
                delay = 0.0
        return max(delay, 0.0)
    return float(2**attempt)  # 1 s, then 2 s


def _read_body(response: httpx2.Response, max_bytes: int = MAX_BYTES) -> bytes:
    # iter_bytes() yields *decoded* chunks, so the cap also bounds a compression bomb.
    declared = response.headers.get("Content-Length")
    if declared and declared.isdigit() and int(declared) > max_bytes:
        raise FetchError("response_too_large", "The source response is too large.")
    body = bytearray()
    for chunk in response.iter_bytes():
        body.extend(chunk)
        if len(body) > max_bytes:
            raise FetchError("response_too_large", "The source response is too large.")
    return bytes(body)


def _parse_json(response: httpx2.Response, body: bytes) -> Any:
    content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
    if content_type != "application/json" and not content_type.endswith("+json"):
        raise FetchError("unexpected_content_type", "The source didn't return JSON.")
    try:
        parsed = json.loads(body)
    except ValueError as error:
        raise FetchError("invalid_json", "The source returned malformed JSON.") from error
    if parsed is None:  # JSON null is not a snapshot (and None would read as 304 Not Modified)
        raise FetchError("invalid_json", "The source returned an empty document.")
    return parsed


def fetch_json(
    url: str,
    *,
    etag: str | None = None,
    last_modified: str | None = None,
    transport: httpx2.BaseTransport | None = None,
    sleep: Callable[[float], None] = time.sleep,
    max_bytes: int = MAX_BYTES,
    deadline: float | None = None,
) -> Fetched:
    """GET a JSON document with conditional headers, bounded redirects/retries/size.
    `max_bytes` may only tighten the global MAX_BYTES cap (e.g. small per-job detail bodies).
    `deadline` (a time.monotonic() value) is checked before every attempt, and a retry sleep that
    would pass it is refused (FetchError "timeout"). It is not a hard wall: a server dripping
    bytes can hold one attempt open while each read stays inside the 20 s read timeout.

    `transport` replaces the network (tests and the E2E fixture); DNS checks are skipped then,
    since nothing is resolved."""
    max_bytes = min(max_bytes, MAX_BYTES)
    resolve = None if transport is not None else _resolve
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    with httpx2.Client(
        timeout=TIMEOUT,
        follow_redirects=False,
        trust_env=False,  # never pick up proxy settings or .netrc credentials
        transport=transport,
        headers=headers,
    ) as client:
        for attempt in range(MAX_ATTEMPTS):
            if deadline is not None and time.monotonic() >= deadline:
                raise FetchError("timeout", "The time budget for this source ran out.")
            last = attempt == MAX_ATTEMPTS - 1
            response: httpx2.Response | None = None
            try:
                target = url
                for _ in range(MAX_REDIRECTS + 1):
                    check_url(target, resolve)
                    with client.stream("GET", target) as response:
                        location = response.headers.get("Location")
                        if response.status_code in REDIRECT_STATUSES and location:
                            origin = (urlsplit(target).hostname or "").lower()
                            target = urljoin(target, location)
                            # A redirect may only reach another fixed provider host or stay on
                            # the same host: never hop to another tenant's subdomain.
                            hop = (urlsplit(target).hostname or "").lower()
                            if hop != origin and hop not in ALLOWED_HOSTS:
                                raise FetchError("blocked_url", "The source redirected elsewhere.")
                            continue
                        if response.status_code in RETRY_STATUSES and not last:
                            break  # retried below
                        if response.status_code == 304:
                            return Fetched(None, etag, last_modified)
                        if response.status_code == 429:
                            raise FetchError("rate_limited", "The source is rate limiting us.")
                        if response.status_code == 404:
                            raise FetchError("not_found", "The source board wasn't found.")
                        if response.status_code >= 400:
                            raise FetchError(
                                "http_error", f"The source answered HTTP {response.status_code}."
                            )
                        body = _read_body(response, max_bytes)
                        return Fetched(
                            _parse_json(response, body),
                            response.headers.get("ETag"),
                            response.headers.get("Last-Modified"),
                            len(body),
                        )
                else:
                    raise FetchError("too_many_redirects", "The source redirected too many times.")
            except httpx2.TimeoutException as error:
                if last:
                    raise FetchError("timeout", "The source timed out.") from error
            except httpx2.TransportError as error:
                if last:
                    raise FetchError("network_error", "Couldn't connect to the source.") from error
            except httpx2.HTTPError as error:  # e.g. an undecodable body: not worth retrying
                raise FetchError(
                    "network_error", "The source response couldn't be read."
                ) from error
            delay = _retry_delay(response, attempt)
            if delay > MAX_RETRY_AFTER_SECONDS:
                raise FetchError("rate_limited", "The source asked us to wait too long; try later.")
            if deadline is not None and time.monotonic() + delay >= deadline:
                raise FetchError("timeout", "The time budget for this source ran out.")
            sleep(delay)
    raise AssertionError("unreachable")  # every attempt returns or raises


def fixture_transport(path: str) -> httpx2.MockTransport:
    """Test-only transport: answers from a JSON file mapping full URLs to bodies (re-read on every
    request, so a test can change the snapshot between syncs). Unknown URLs get 404. It can only
    reduce network access: nothing is fetched while it's configured."""

    def handle(request: httpx2.Request) -> httpx2.Response:
        responses: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
        body = responses.get(str(request.url))
        return httpx2.Response(404) if body is None else httpx2.Response(200, json=body)

    return httpx2.MockTransport(handle)


def configured_transport() -> httpx2.BaseTransport | None:
    """The transport sync uses: the network (None) unless the test-only fixture file is set."""
    path = get_settings().ingestion_fixture_file
    if not path:
        return None
    logger.warning("Ingestion is using the test fixture file instead of the network.")
    return fixture_transport(path)
