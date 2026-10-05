"""Adversarial review of the Workable and Pinpoint adapters (ADR-014 §2, ADR-015 §7): host
validation and SSRF, redirects, request bounds, false closures, wrong-company data, identity
spoofing and text injection against a hostile provider. Synthetic data only; never real network.

Unit tests need no database; pipeline tests are marked postgres individually."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import httpx2
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import IngestionRunStatus, IngestionSourceKind, OpportunityType, SourceScope
from app.ingestion.adapters import SourceConfig, pinpoint, workable
from app.ingestion.http import MAX_BYTES, FetchError, check_url, fetch_json
from app.ingestion.normalize import ItemError, NormalizedOpportunity, SnapshotError
from app.ingestion.pipeline import sync_source
from app.models import (
    IngestionSource,
    Opportunity,
    OpportunityIdentifier,
    OpportunitySourceRecord,
)
from app.services.sources import parse_reference
from tests.ingestion_fixtures import FakeSource

SLUG_OUT = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}\Z")
LABEL_OUT = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")

WK = SourceConfig(IngestionSourceKind.WORKABLE, "acme", None, "Acme")
PP = SourceConfig(IngestionSourceKind.PINPOINT, "acme", None, "Acme")
CODE = "AB12CD34EF"
OTHER = "FF00FF00FF"


def no_sleep(_seconds: float) -> None:
    return None


def wk_job(code: str = CODE, **changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "title": "Synthetic Intern",
        "shortcode": code,
        "url": f"https://apply.workable.com/acme/j/{code}/",
        "published_on": "2040-09-05",
    }
    return base | changes


def pp_posting(pid: str = "1", **changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": pid,
        "title": "Synthetic Intern",
        "url": f"https://acme.pinpointhq.com/en/postings/{pid}",
    }
    return base | changes


def wk_items(*jobs: Any, source: SourceConfig = WK) -> list[NormalizedOpportunity | ItemError]:
    return workable.parse({"jobs": list(jobs)}, source).items


def pp_items(*rows: Any, source: SourceConfig = PP) -> list[NormalizedOpportunity | ItemError]:
    return pinpoint.parse({"data": list(rows)}, source).items


def only(items: list[NormalizedOpportunity | ItemError]) -> NormalizedOpportunity:
    (item,) = items
    assert isinstance(item, NormalizedOpportunity)
    return item


# --- host validation / SSRF ----------------------------------------------------------------------

HOSTILE_URLS = [
    "https://x.pinpointhq.com./postings.json",  # trailing-dot host
    "https://x.pinpointhq.com.evil.example/postings.json",
    "https://evilpinpointhq.com/postings.json",
    "https://pinpointhq.com/postings.json",
    "https://a.b.pinpointhq.com/postings.json",
    "https://-x.pinpointhq.com/postings.json",
    "https://x-.pinpointhq.com/postings.json",
    f"https://{'a' * 64}.pinpointhq.com/postings.json",  # overlong label
    "https://exämple.pinpointhq.com/postings.json",
    "https://ｅxample.pinpointhq.com/postings.json",  # fullwidth e
    "https://x。pinpointhq.com/postings.json",  # ideographic full stop
    "https://x.pinpointhq.com@evil.example/postings.json",
    "https://evil.example\\@x.pinpointhq.com/postings.json",
    "https://x.pinpointhq.com:8443/postings.json",
    "http://x.pinpointhq.com/postings.json",
    "https://x_y.pinpointhq.com/postings.json",
    "https://127.0.0.1/postings.json",
    "https://apply.workable.com.evil.example/x",
    "https://workable.com/api/accounts/x",
    "https://evil.workable.com/api/accounts/x",
]


@pytest.mark.parametrize("url", HOSTILE_URLS)
def test_check_url_blocks_hostile_hosts(url: str) -> None:
    with pytest.raises(FetchError) as caught:
        check_url(url, None)
    assert caught.value.code == "blocked_url"


@pytest.mark.parametrize(
    "url",
    [
        "https://acme.pinpointhq.com/postings.json",
        "https://ACME.PinpointHQ.com/postings.json",  # hosts are case-insensitive
        f"https://{'a' * 63}.pinpointhq.com/postings.json",
        "https://www.workable.com/api/accounts/acme?details=true",
        "https://apply.workable.com/api/v1/widget/accounts/acme",
    ],
)
def test_check_url_allows_the_documented_hosts(url: str) -> None:
    check_url(url, None)


def test_check_url_refuses_private_resolution_for_a_tenant_host() -> None:
    url = "https://acme.pinpointhq.com/postings.json"
    with pytest.raises(FetchError) as caught:
        check_url(url, lambda _h: ["10.0.0.5"])
    assert caught.value.code == "blocked_url"
    with pytest.raises(FetchError):
        check_url(url, lambda _h: ["8.8.8.8", "169.254.1.1"])


HOSTILE_REFERENCES = [
    "acme%2f..",
    "acme%2e%2e",
    "..",
    "acme/..",
    "acme@evil.example",
    "acme#frag",
    "acme?x=1",
    "acme.",
    "acme\x00",
    "acmeK",  # Kelvin sign lowercases to ASCII k: no non-ASCII may get through
    "ａｃｍｅ",
    "https://acme.pinpointhq.com.",
    "https://acme.pinpointhq.com./x",
    "https://acme.workable.com.",
    "https://acme.workable.com@evil.example/",
    "https://evil.example\\@acme.pinpointhq.com/",
    "https://evil.example\\@apply.workable.com/acme",
    "https://acme.pinpointhq.com%2eevil.example/",
    "https://%61cme.evil.example/",
    "https://apply.workable.com.evil.example/acme",
    "https://xn--acme-.pinpointhq.com/",
    "javascript://acme.pinpointhq.com/%0aalert(1)",
]


@pytest.mark.parametrize("kind", [IngestionSourceKind.WORKABLE, IngestionSourceKind.PINPOINT])
@pytest.mark.parametrize("value", HOSTILE_REFERENCES)
def test_references_never_yield_an_unsafe_identifier(kind: IngestionSourceKind, value: str) -> None:
    """Whatever parse_reference accepts is a strict ASCII label; the rest raises ValueError."""
    try:
        identifier, region = parse_reference(kind, value, None)
    except ValueError:
        return
    assert region is None
    assert identifier.isascii()
    assert (SLUG_OUT if kind is IngestionSourceKind.WORKABLE else LABEL_OUT).match(identifier)
    if kind is IngestionSourceKind.PINPOINT:
        assert "." not in identifier


def test_adapter_urls_cannot_leave_the_provider_host() -> None:
    for identifier in ("acme", "a.b", "x/../../y", "a?b=c#d", "%2e%2e", "a b"):
        source = SourceConfig(IngestionSourceKind.WORKABLE, identifier, None, "X")
        url = workable.ADAPTER.url(source)
        assert url.startswith("https://www.workable.com/api/accounts/")
        assert "/../" not in url and "#" not in url and url.count("?") == 1
        check_url(url, None)
    for identifier in ("evil.com/x", "a.b", "a?b", "A", "x" * 64, "-x", "x-", ""):
        bad = SourceConfig(IngestionSourceKind.PINPOINT, identifier, None, "X")
        with pytest.raises(ValueError):
            pinpoint.ADAPTER.url(bad)


# --- redirects, rate limits, body bounds ---------------------------------------------------------


def serve(routes: dict[str, Any]) -> tuple[httpx2.MockTransport, list[str]]:
    seen: list[str] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        seen.append(str(request.url))
        route = routes.get(str(request.url))
        return httpx2.Response(404) if route is None else route

    return httpx2.MockTransport(handle), seen


def redirect(to: str, status: int = 302) -> httpx2.Response:
    return httpx2.Response(status, headers={"Location": to})


def ok(body: str = '{"jobs": []}') -> httpx2.Response:
    return httpx2.Response(200, content=body, headers={"Content-Type": "application/json"})


WK_API = "https://www.workable.com/api/accounts/acme?details=true"
PP_API = "https://acme.pinpointhq.com/postings.json"
WK_WIDGET = "https://apply.workable.com/api/v1/widget/accounts/acme?details=true"


def test_workable_documented_redirect_to_apply_host_is_followed() -> None:
    transport, seen = serve({WK_API: redirect(WK_WIDGET), WK_WIDGET: ok()})
    assert fetch_json(WK_API, transport=transport, sleep=no_sleep).data == {"jobs": []}
    assert len(seen) == 2


@pytest.mark.parametrize(
    "target",
    [
        "https://other.pinpointhq.com/postings.json",  # a pinpoint tenant of ANOTHER company
        "https://evil.example/x",
        "http://apply.workable.com/x",
        "https://apply.workable.com@other.pinpointhq.com/x",
        "//other.pinpointhq.com/postings.json",
        "https://acme.pinpointhq.com.evil.example/x",
    ],
)
def test_workable_redirect_cannot_reach_a_pinpoint_tenant_or_anything_else(target: str) -> None:
    transport, seen = serve({WK_API: redirect(target), target: ok('{"data": []}')})
    with pytest.raises(FetchError) as caught:
        fetch_json(WK_API, transport=transport, sleep=no_sleep)
    assert caught.value.code == "blocked_url"
    assert seen == [WK_API]  # the hostile target was never requested


@pytest.mark.parametrize(
    "target",
    [
        "https://other.pinpointhq.com/postings.json",  # tenant -> another tenant
        "https://acme.pinpointhq.com.evil.example/postings.json",
        "https://careers.acme.example/postings.json",  # customer custom domain
    ],
)
def test_pinpoint_tenant_cannot_redirect_elsewhere(target: str) -> None:
    transport, seen = serve({PP_API: redirect(target, 301), target: ok('{"data": []}')})
    with pytest.raises(FetchError) as caught:
        fetch_json(PP_API, transport=transport, sleep=no_sleep)
    assert caught.value.code == "blocked_url"
    assert seen == [PP_API]


def test_pinpoint_same_host_redirect_and_chain_limit() -> None:
    transport, _ = serve(
        {
            PP_API: redirect("/postings.json?x=1"),
            "https://acme.pinpointhq.com/postings.json?x=1": ok('{"data": []}'),
        }
    )
    assert fetch_json(PP_API, transport=transport, sleep=no_sleep).data == {"data": []}
    loop, _ = serve({PP_API: redirect(PP_API)})
    with pytest.raises(FetchError) as caught:
        fetch_json(PP_API, transport=loop, sleep=no_sleep)
    assert caught.value.code == "too_many_redirects"


def test_rate_limit_is_a_fetch_failure_never_an_empty_snapshot() -> None:
    sleeps: list[float] = []
    transport, seen = serve({PP_API: httpx2.Response(429, headers={"Retry-After": "2"})})
    with pytest.raises(FetchError) as caught:
        fetch_json(PP_API, transport=transport, sleep=sleeps.append)
    assert caught.value.code == "rate_limited"
    assert len(seen) == 3 and sleeps == [2.0, 2.0]
    huge, seen = serve({PP_API: httpx2.Response(429, headers={"Retry-After": "86400"})})
    with pytest.raises(FetchError) as caught:
        fetch_json(PP_API, transport=huge, sleep=no_sleep)
    assert caught.value.code == "rate_limited" and len(seen) == 1


@pytest.mark.parametrize(
    "response",
    [
        httpx2.Response(
            200,
            content=b"{}",
            headers={"Content-Type": "application/json", "Content-Length": str(MAX_BYTES + 1)},
        ),
        httpx2.Response(
            200, content=b" " * (MAX_BYTES + 1), headers={"Content-Type": "application/json"}
        ),
    ],
)
def test_oversized_body_is_refused(response: httpx2.Response) -> None:
    transport, _ = serve({PP_API: response})
    with pytest.raises(FetchError) as caught:
        fetch_json(PP_API, transport=transport, sleep=no_sleep)
    assert caught.value.code == "response_too_large"


def test_html_200_is_not_a_snapshot() -> None:
    page = httpx2.Response(200, content="<html>{}</html>", headers={"Content-Type": "text/html"})
    transport, _ = serve({PP_API: page})
    with pytest.raises(FetchError) as caught:
        fetch_json(PP_API, transport=transport, sleep=no_sleep)
    assert caught.value.code == "unexpected_content_type"


# --- schema drift: nothing may look like "the board is empty" ------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"results": []},  # renamed key
        {"Jobs": []},
        {"jobs": None},
        {"jobs": {}},
        {"jobs": "[]"},
        {"data": []},  # the other provider's key
        {"name": "Acme"},
        [],
        None,
        "",
        0,
    ],
)
def test_workable_schema_drift_fails_the_snapshot(payload: Any) -> None:
    with pytest.raises(SnapshotError):
        workable.parse(payload, WK)


@pytest.mark.parametrize(
    "payload",
    [
        {"postings": []},
        {"Data": []},
        {"data": None},
        {"data": {}},
        {"data": "[]"},
        {"jobs": []},
        [],
    ],
)
def test_pinpoint_schema_drift_fails_the_snapshot(payload: Any) -> None:
    with pytest.raises(SnapshotError):
        pinpoint.parse(payload, PP)


def test_item_level_drift_is_item_errors_not_empty() -> None:
    renamed: list[Any] = [wk_job() | {"shortcode": None}, {"id": "x"}, [], 7, None]
    assert all(isinstance(i, ItemError) for i in wk_items(*renamed))
    assert all(isinstance(i, ItemError) for i in pp_items({"key": "1"}, [], 7, None))


# --- Workable URL / identity spoofing ------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        f"https://apply.workable.com/other/j/{CODE}/",  # another account's page for this code
        f"https://apply.workable.com/other/j/{OTHER}/",  # another account's job
        f"https://apply.workable.com/acme/j/{OTHER}/",  # this account, another job
        f"https://apply.workable.com/j/{OTHER}",
        "https://apply.workable.com/acme/",  # account home is not a job identity
        "https://apply.workable.com/acme",
        "https://apply.workable.com/",
        f"https://apply.workable.com/acme/x/j/{CODE}",
        f"https://apply.workable.com/acme/jobs/{CODE}",
        f"https://boards.greenhouse.io/acme/jobs/{CODE}",
        "https://boards.greenhouse.io/acme/jobs/4001",
        f"https://acme.pinpointhq.com/en/postings/{CODE}",
        f"https://apply.workable.com.evil.example/acme/j/{CODE}",
        f"https://apply.workable.com@evil.example/acme/j/{CODE}",
    ],
)
def test_workable_url_must_name_this_job_and_account(url: str) -> None:
    item = only(wk_items(wk_job(CODE, url=url, shortlink=None, application_url=None)))
    assert item.application_url is None
    assert {i.namespace for i in item.identifiers} == {"workable"}


@pytest.mark.parametrize(
    "url",
    [
        f"https://apply.workable.com/acme/j/{CODE}/",
        f"https://apply.workable.com/ACME/j/{CODE.lower()}/",
        f"https://apply.workable.com/j/{CODE}",
        f"https://apply.workable.com/acme/j/{CODE}/apply/",
    ],
)
def test_workable_own_urls_are_kept(url: str) -> None:
    item = only(wk_items(wk_job(CODE, url=url)))
    assert item.application_url == url
    assert {i.namespace for i in item.identifiers} == {"workable", "url"}


def test_workable_identity_is_namespaced_by_account() -> None:
    a = only(wk_items(wk_job(CODE)))
    beta = SourceConfig(IngestionSourceKind.WORKABLE, "beta", None, "Beta")
    b = only(wk_items(wk_job(CODE, url=f"https://apply.workable.com/beta/j/{CODE}/"), source=beta))
    shared = {(i.namespace, i.value) for i in a.identifiers} & {
        (i.namespace, i.value) for i in b.identifiers
    }
    assert shared == set()  # same shortcode under two accounts never shares an identity


def test_workable_payload_naming_another_company_does_not_rename_the_org() -> None:
    body = {"name": "Evil Corp", "jobs": [wk_job() | {"company": "Evil Corp"}]}
    assert only(workable.parse(body, WK).items).organization == "Acme"


# --- Pinpoint wrong-company data -----------------------------------------------------------------


def test_pinpoint_response_for_another_tenant_fails_the_snapshot() -> None:
    other = "https://other.pinpointhq.com/en/postings/9"
    with pytest.raises(SnapshotError) as caught:
        pinpoint.parse({"data": [pp_posting("1"), pp_posting("2", url=other)]}, PP)
    assert caught.value.code == "wrong_company"


@pytest.mark.parametrize(
    "url",
    [
        "https://Other.PinpointHQ.com/x",
        "https://other.pinpointhq.com:8443/x",
        "https://acme.pinpointhq.com.other.pinpointhq.com/x",
    ],
)
def test_pinpoint_wrong_company_detection_is_case_and_port_insensitive(url: str) -> None:
    with pytest.raises(SnapshotError):
        pinpoint.parse({"data": [pp_posting(url=url)]}, PP)


def test_pinpoint_foreign_non_pinpoint_urls_are_dropped_not_fatal() -> None:
    items = pp_items(
        pp_posting("1", url="https://careers.acme.example/job/1"),
        pp_posting("2", url="https://boards.greenhouse.io/acme/jobs/4001"),
        pp_posting("3", url=None),
        pp_posting("4", url=12345),  # type drift
    )
    for item in items[:3]:
        assert isinstance(item, NormalizedOpportunity) and item.application_url is None
    assert isinstance(items[3], ItemError)


def test_pinpoint_identity_is_company_scoped_and_ids_cannot_forge_a_prefix() -> None:
    beta = SourceConfig(IngestionSourceKind.PINPOINT, "beta", None, "Beta")
    a = only(pp_items(pp_posting("1")))
    b = only(pp_items(pp_posting("1", url="https://beta.pinpointhq.com/p/1"), source=beta))
    assert {i.value for i in a.identifiers if i.namespace == "pinpoint"} == {"acme:1"}
    assert {i.value for i in b.identifiers if i.namespace == "pinpoint"} == {"beta:1"}
    for forged in ("beta:1", "acme:1:2", "x/../1"):
        assert isinstance(pp_items(pp_posting(forged))[0], ItemError)


# --- text injection ------------------------------------------------------------------------------

INJECTION = (
    "<p>Hello</p><script>alert(1)</script><img src=x onerror=alert(2)>"
    '<a href="javascript:alert(3)">click</a><style>body{display:none}</style>'
    "<iframe src=//evil.example></iframe><!-- c --><svg onload=alert(4)></svg>"
)


def test_workable_description_is_text_only() -> None:
    desc = only(wk_items(wk_job(description=INJECTION))).description or ""
    for needle in ("<", ">", "alert(1)", "display:none", "onerror"):
        assert needle not in desc
    assert "Hello" in desc and "click" in desc


def test_pinpoint_every_html_field_is_text_only() -> None:
    row = pp_posting(
        description=INJECTION, key_responsibilities=INJECTION, skills_knowledge_expertise=INJECTION
    )
    desc = only(pp_items(row)).description or ""
    for needle in ("<", ">", "alert(1)", "display:none", "onerror"):
        assert needle not in desc


def test_unclosed_script_and_huge_description_are_bounded() -> None:
    item = only(wk_items(wk_job(description="<p>ok</p><script>" + "x" * 100_000)))
    assert item.description == "ok"
    big = only(wk_items(wk_job(description="a " * 100_000)))
    assert big.description is not None and len(big.description) <= 50_000


def test_title_and_location_are_bounded_single_lines() -> None:
    item = only(wk_items(wk_job(title="Intern\n\n" + "x" * 1000, city="a\nb", locations=[])))
    assert "\n" not in item.title and len(item.title) <= 300
    assert item.location == "a b"


# --- dates ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    ["", "0000-00-00", "2040-13-01", "2040-02-30", "9999-99-99", "yesterday", "-1", "20401"],
)
def test_workable_unreadable_published_on_is_none(value: str) -> None:
    assert only(wk_items(wk_job(published_on=value))).posted_at is None


def test_workable_published_on_forms() -> None:
    assert only(wk_items(wk_job(published_on="2040-09-05T23:59:59-11:00"))).posted_at is not None
    for bad in (5, ["2040-01-01"], {"a": 1}):
        assert isinstance(wk_items(wk_job(published_on=bad))[0], ItemError)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0001-01-01", date(1, 1, 1)),
        ("9999-12-31", date(9999, 12, 31)),
        ("2040-10-01T23:59:59-23:59", date(2040, 10, 1)),
        ("2040-10-01 23:59", date(2040, 10, 1)),
        ("2040-02-30", None),
        ("2040-13-01T00:00:00Z", None),
        ("0000-01-01", None),
        ("2040-10-01T25:00:00Z", None),
        ("\n", None),
    ],
)
def test_pinpoint_deadline_edges(value: str, expected: date | None) -> None:
    assert only(pp_items(pp_posting(deadline_at=value))).application_deadline == expected


def test_pinpoint_non_string_deadline_is_an_item_error_not_a_crash() -> None:
    for bad in (20401001, ["2040-10-01"], {"a": 1}):
        assert isinstance(pp_items(pp_posting(deadline_at=bad))[0], ItemError)


# --- pipeline: false closures and merges (PostgreSQL) --------------------------------------------

WK_URL = "https://www.workable.com/api/accounts/{}?details=true"
PP_URL = "https://{}.pinpointhq.com/postings.json"


def make(db: Session, kind: IngestionSourceKind, identifier: str) -> IngestionSource:
    source = IngestionSource(
        kind=kind, identifier=identifier, display_name=identifier.title(), scope=SourceScope.ALL
    )
    db.add(source)
    db.commit()
    return source


def active(db: Session, source: IngestionSource) -> set[str | None]:
    return set(
        db.scalars(
            select(OpportunitySourceRecord.external_id).where(
                OpportunitySourceRecord.ingestion_source_id == source.id,
                OpportunitySourceRecord.is_active,
            )
        )
    )


def wk_sync(db: Session, source: IngestionSource, fake: FakeSource, body: Any) -> Any:
    fake.json(WK_URL.format(source.identifier), body)
    return sync_source(db, source, transport=fake.transport())


def pp_sync(db: Session, source: IngestionSource, fake: FakeSource, body: Any) -> Any:
    fake.json(PP_URL.format(source.identifier), body)
    return sync_source(db, source, transport=fake.transport())


def wk_acct(account: str, *codes: str) -> dict[str, Any]:
    return {"jobs": [wk_job(c, url=f"https://apply.workable.com/{account}/j/{c}/") for c in codes]}


def pp_acct(company: str, *ids: str) -> dict[str, Any]:
    return {
        "data": [
            pp_posting(i, url=f"https://{company}.pinpointhq.com/en/postings/{i}") for i in ids
        ]
    }


@pytest.mark.postgres
@pytest.mark.parametrize("bad", [{"results": []}, {"jobs": None}, {"jobs": {}}, [], None])
def test_workable_drift_never_closes(db: Session, bad: Any) -> None:
    fake, source = FakeSource(), make(db, IngestionSourceKind.WORKABLE, "acme")
    first = wk_sync(db, source, fake, wk_acct("acme", CODE, OTHER))
    assert first.status is IngestionRunStatus.SUCCESS
    assert wk_sync(db, source, fake, bad).status is IngestionRunStatus.FAILED
    assert active(db, source) == {CODE, OTHER}


@pytest.mark.postgres
@pytest.mark.parametrize("bad", [{"postings": []}, {"data": None}, {"data": {}}, [], None])
def test_pinpoint_drift_never_closes(db: Session, bad: Any) -> None:
    fake, source = FakeSource(), make(db, IngestionSourceKind.PINPOINT, "acme")
    assert pp_sync(db, source, fake, pp_acct("acme", "1", "2")).status is IngestionRunStatus.SUCCESS
    assert pp_sync(db, source, fake, bad).status is IngestionRunStatus.FAILED
    assert active(db, source) == {"1", "2"}


@pytest.mark.postgres
def test_pinpoint_snapshot_of_another_tenant_never_closes_or_imports(db: Session) -> None:
    fake, source = FakeSource(), make(db, IngestionSourceKind.PINPOINT, "acme")
    pp_sync(db, source, fake, pp_acct("acme", "1", "2"))
    run = pp_sync(db, source, fake, pp_acct("beta", "7", "8"))
    assert run.status is IngestionRunStatus.FAILED
    assert active(db, source) == {"1", "2"}
    assert len(db.scalars(select(OpportunitySourceRecord)).all()) == 2


@pytest.mark.postgres
def test_pinpoint_redirected_tenant_never_closes(db: Session) -> None:
    fake, source = FakeSource(), make(db, IngestionSourceKind.PINPOINT, "acme")
    pp_sync(db, source, fake, pp_acct("acme", "1", "2"))
    target = "https://beta.pinpointhq.com/postings.json"
    fake.respond(PP_URL.format("acme"), lambda _r: redirect(target))
    fake.json(target, pp_acct("beta", "9"))
    run = sync_source(db, source, transport=fake.transport())
    assert run.status is IngestionRunStatus.FAILED
    assert active(db, source) == {"1", "2"}


@pytest.mark.postgres
def test_partial_and_duplicate_snapshots_never_close(db: Session) -> None:
    fake = FakeSource()
    wk = make(db, IngestionSourceKind.WORKABLE, "acme")
    pp = make(db, IngestionSourceKind.PINPOINT, "acme")
    wk_sync(db, wk, fake, wk_acct("acme", CODE, OTHER))
    pp_sync(db, pp, fake, pp_acct("acme", "1", "2"))
    # One valid job, one broken one: partial run, the missing/broken posting stays open.
    broken = wk_acct("acme", CODE)
    broken["jobs"].append({"shortcode": OTHER})  # no title
    assert wk_sync(db, wk, fake, broken).status is IngestionRunStatus.PARTIAL
    assert active(db, wk) == {CODE, OTHER}
    # Duplicate ids: the pipeline flags it and closes nothing.
    assert pp_sync(db, pp, fake, pp_acct("acme", "1", "1")).status is IngestionRunStatus.PARTIAL
    assert active(db, pp) == {"1", "2"}
    # A complete, valid snapshot does close what's missing (the intended behaviour).
    assert wk_sync(db, wk, fake, wk_acct("acme", CODE)).status is IngestionRunStatus.SUCCESS
    assert active(db, wk) == {CODE}


@pytest.mark.postgres
def test_workable_cannot_steal_another_accounts_opportunity(db: Session) -> None:
    fake = FakeSource()
    beta = make(db, IngestionSourceKind.WORKABLE, "beta")
    acme = make(db, IngestionSourceKind.WORKABLE, "acme")
    wk_sync(db, beta, fake, wk_acct("beta", OTHER))
    victim = db.scalars(select(Opportunity)).one()
    hostile = {
        "jobs": [
            # Claims beta's job page, a greenhouse URL, and beta's shortlink.
            wk_job(CODE, url=f"https://apply.workable.com/beta/j/{OTHER}/"),
            wk_job("11AA22BB33", url="https://boards.greenhouse.io/x/jobs/1"),
            wk_job("44CC55DD66", url=f"https://apply.workable.com/j/{OTHER}"),
        ]
    }
    run = wk_sync(db, acme, fake, hostile)
    assert run.status is IngestionRunStatus.SUCCESS
    assert run.deduplicated_count == 0 and run.created_count == 3
    assert len(db.scalars(select(Opportunity)).all()) == 4
    db.refresh(victim)
    assert victim.application_url == f"https://apply.workable.com/beta/j/{OTHER}/"
    sources = db.scalars(
        select(OpportunitySourceRecord.ingestion_source_id).where(
            OpportunitySourceRecord.opportunity_id == victim.id
        )
    ).all()
    assert sources == [beta.id]
    # The same shortcode under two accounts is two opportunities, not one merged record.
    wk_sync(db, acme, fake, wk_acct("acme", OTHER))
    values = db.scalars(
        select(OpportunityIdentifier.value).where(OpportunityIdentifier.namespace == "workable")
    ).all()
    assert f"beta:{OTHER}" in values and f"acme:{OTHER}" in values


@pytest.mark.postgres
def test_foreign_url_identifier_in_a_payload_does_not_merge(db: Session) -> None:
    """A hostile payload carrying another source's job URL (greenhouse) neither claims nor merges
    into that opportunity."""
    fake = FakeSource()
    existing = Opportunity(
        title="Greenhouse Intern", organization="Other", opportunity_type=OpportunityType.INTERNSHIP
    )
    db.add(existing)
    db.flush()
    gh = "https://boards.greenhouse.io/other/jobs/4001"
    db.add(OpportunityIdentifier(opportunity_id=existing.id, namespace="url", value=gh))
    db.commit()
    wk = make(db, IngestionSourceKind.WORKABLE, "acme")
    pp = make(db, IngestionSourceKind.PINPOINT, "acme")
    wk_sync(db, wk, fake, {"jobs": [wk_job(CODE, url=gh, shortlink=None, application_url=None)]})
    pp_sync(db, pp, fake, {"data": [pp_posting("1", url=gh)]})
    assert len(db.scalars(select(Opportunity)).all()) == 3
    owners = db.scalars(
        select(OpportunityIdentifier.opportunity_id).where(OpportunityIdentifier.value == gh)
    ).all()
    assert owners == [existing.id]


@pytest.mark.postgres
def test_legitimate_empty_board_closes_documented_limit(db: Session) -> None:
    fake, source = FakeSource(), make(db, IngestionSourceKind.WORKABLE, "acme")
    wk_sync(db, source, fake, wk_acct("acme", CODE))
    assert wk_sync(db, source, fake, {"jobs": []}).status is IngestionRunStatus.SUCCESS
    assert active(db, source) == set()


def test_json_null_is_not_mistaken_for_not_modified() -> None:
    transport, _ = serve({PP_API: ok("null")})
    with pytest.raises(FetchError) as caught:
        fetch_json(PP_API, transport=transport, sleep=no_sleep)
    assert caught.value.code == "invalid_json"
