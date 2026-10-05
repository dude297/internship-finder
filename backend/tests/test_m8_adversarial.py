"""Adversarial review of Milestone 8 (ADR-014 §1-§4): SmartRecruiters company parsing, request URL
construction, identity spoofing, discovery network isolation, and request bounds against a hostile
provider. Synthetic data only.

Unit tests need no database; API-level tests are marked postgres individually."""

from __future__ import annotations

import json
import re
import socket
from collections.abc import Callable
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import IngestionSourceKind, SourceScope
from app.ingestion.adapters import CollectRequest, SourceConfig, smartrecruiters
from app.ingestion.adapters.community_feed import provider_identity
from app.ingestion.adapters.smartrecruiters import (
    MAX_DETAIL_FETCHES,
    MAX_PAGES,
    PAGE_SIZE,
    collect,
    parse,
    parse_company_reference,
)
from app.ingestion.http import ALLOWED_HOSTS, FetchError, check_url
from app.ingestion.normalize import (
    SMARTRECRUITERS,
    Identifier,
    ItemError,
    NormalizedOpportunity,
    SnapshotError,
)
from app.models import IngestionSource
from app.services import source_discovery
from tests.test_smartrecruiters_adapter import (
    BASE,
    COMPANY,
    SOURCE,
    Server,
    detail_for,
    list_item,
    pid,
)
from tests.test_source_discovery import (
    builtin_source,
    make_opportunity,
    make_record,
)

IDENT = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}\Z")
# The only request shapes the adapter may ever make.
ALLOWED_REQUEST = re.compile(
    rf"^https://api\.smartrecruiters\.com/v1/companies/{COMPANY}/postings"
    r"(\?limit=100&offset=[0-9]+&destination=PUBLIC|/[0-9]+)\Z"
)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    from functools import partial

    from app.ingestion.http import fetch_json

    monkeypatch.setattr(smartrecruiters, "fetch_json", partial(fetch_json, sleep=lambda _s: None))


# --- parse_company_reference ---------------------------------------------------------------------

HOSTILE_REFERENCES = [
    "smartrecruiters.com.evil",
    "jobs.smartrecruiters.com.evil/x",
    "https://jobs.smartrecruiters.com.evil/x",
    "https://evil.com/jobs.smartrecruiters.com/x",
    "evil.com/jobs.smartrecruiters.com/x",
    "https://jobs.smartrecruiters.com@evil.com/x",
    "https://user@jobs.smartrecruiters.com/acme",
    "https://user:pw@jobs.smartrecruiters.com/acme",
    "https://jobs.smartrecruiters.com:8443/acme",
    "https://jobs.smartrecruiters.com:443/acme",
    "https://jobs.smartrecruiters.com./acme",
    "http://jobs.smartrecruiters.com/acme",
    "ftp://jobs.smartrecruiters.com/acme",
    "javascript:alert(1)",
    "javascript://jobs.smartrecruiters.com/acme",
    "data:text/html,acme",
    "//jobs.smartrecruiters.com/acme",
    "///jobs.smartrecruiters.com/acme",
    "https://jobs.smartrecruiters.com//acme",
    "https://jobs.smartrecruiters.com/acme%2Fx",
    "https://jobs.smartrecruiters.com/%2e%2e",
    "https://jobs.smartrecruiters.com/..",
    "https://jobs.smartrecruiters.com/../acme",
    "https://jobs.smartrecruiters.com/./acme",
    "https://jobs.smartrecruiters.com\\evil.com/acme",
    "https://jobs.smartrecruiters.com/ac me",
    "https://jobs.smartrecruiters.com/acme\nx",
    "ac\nme",
    "ac\tme",
    "ac\x00me",
    "ac\rme",
    "https://jobs.smartrecruiters.com/ac\x00me",
    "https://jobs.smartrecruiters.com/",
    "https://jobs.smartrecruiters.com",
    # Unicode / IDN lookalikes.
    "аcme",  # Cyrillic a
    "https://jobs.smartrecruiters.com/аcme",
    "https://jоbs.smartrecruiters.com/acme",  # Cyrillic o in the host
    "https://ｊｏｂｓ.smartrecruiters.com/acme",  # fullwidth host
    "https://jobs.smartrecruiters．com/acme",  # fullwidth full stop
    "https://jobs.smartrecruiters.com/ａｃｍｅ",  # fullwidth identifier
    "https://xn--jobs-smartrecruiters.com/acme",
    "café",
    # Wrong host family: the API host is never accepted.
    "api.smartrecruiters.com/v1/companies/acme/postings",
    "https://api.smartrecruiters.com/v1/companies/acme/postings",
    "https://www.smartrecruiters.com/acme",
    "https://smartrecruiters.com/acme",
    # Malformed identifiers.
    "-acme",
    ".acme",
    "_acme",
    "acme.com",
    "ac/me/",  # bare "x/y" is treated as host/path: host ac is not jobs.smartrecruiters.com
    "a" * 65,
    "acme!",
    "acme%41",
    "",
    "   ",
]


@pytest.mark.parametrize("value", HOSTILE_REFERENCES)
def test_hostile_company_references_are_refused(value: str) -> None:
    with pytest.raises(ValueError):
        parse_company_reference(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Acme", "acme"),
        ("  ACME2  ", "acme2"),
        ("a" * 64, "a" * 64),
        ("HTTPS://JOBS.SMARTRECRUITERS.COM/BoschGroup", "boschgroup"),
        ("https://jobs.smartrecruiters.com/BoschGroup/743999-intern", "boschgroup"),
        ("jobs.smartrecruiters.com/BoschGroup", "boschgroup"),
        # Query strings and fragments never reach the identifier.
        ("https://jobs.smartrecruiters.com/acme?x=y&z=1", "acme"),
        ("https://jobs.smartrecruiters.com/acme#frag", "acme"),
        ("https://jobs.smartrecruiters.com/acme/?x=../../etc", "acme"),
        ("a-b_c", "a-b_c"),
        ("https://jobs.smartrecruiters.com:/acme", "acme"),  # empty port == default
    ],
)
def test_good_company_references_normalize(value: str, expected: str) -> None:
    assert parse_company_reference(value) == expected


@pytest.mark.parametrize("value", ["acme?x=y", "acme#x", "acme/?x=y", "acme?"])
def test_bare_identifier_with_query_or_fragment_never_leaks(value: str) -> None:
    try:
        result = parse_company_reference(value)
    except ValueError:
        return
    # "acme/?x=y" reads as host "acme": refused. Anything accepted must be clean.
    assert IDENT.match(result) and "?" not in result and "#" not in result


def test_trailing_newline_is_stripped_not_embedded() -> None:
    # Surrounding whitespace is trimmed like the other adapters; it is never stored.
    result = parse_company_reference("acme\n")
    assert result == "acme"
    assert IDENT.match(result)


def test_kelvin_sign_folds_to_clean_ascii_or_is_refused() -> None:
    # U+212A lowercases to ASCII "k": the stored identifier is still always clean ASCII.
    try:
        result = parse_company_reference("Kacme")
    except ValueError:
        return
    assert result.isascii() and IDENT.match(result)


@pytest.mark.parametrize(
    "value",
    [
        "Acme",
        "https://jobs.smartrecruiters.com/AcMe/1-x?q=1",
        "x" + "-" * 63,
        "0abc",
    ],
)
def test_accepted_identifier_always_matches_stored_pattern(value: str) -> None:
    result = parse_company_reference(value)
    assert result == result.lower() and IDENT.match(result)


# --- POST /api/sources ---------------------------------------------------------------------------


@pytest.mark.postgres
@pytest.mark.parametrize(
    "board",
    [
        "smartrecruiters.com.evil",
        "https://jobs.smartrecruiters.com@evil.com/x",
        "https://jobs.smartrecruiters.com:443/acme",
        "https://api.smartrecruiters.com/v1/companies/acme/postings",
        "ac\x00me",
        "https://jobs.smartrecruiters.com/%2e%2e",
        "аcme",
    ],
)
def test_api_refuses_hostile_smartrecruiters_board(
    client: TestClient, db: Session, board: str
) -> None:
    response = client.post(
        "/api/sources", json={"kind": "smartrecruiters", "display_name": "X", "board": board}
    )
    assert response.status_code == 422, response.text
    assert (
        db.scalars(
            select(IngestionSource).where(
                IngestionSource.kind == IngestionSourceKind.SMARTRECRUITERS
            )
        ).first()
        is None
    )


@pytest.mark.postgres
@pytest.mark.parametrize("region", ["global", "eu"])
def test_api_refuses_a_region_for_smartrecruiters(client: TestClient, region: str) -> None:
    response = client.post(
        "/api/sources",
        json={"kind": "smartrecruiters", "display_name": "X", "board": "acme", "region": region},
    )
    assert response.status_code == 422, response.text


@pytest.mark.postgres
def test_api_stores_a_lowercase_clean_identifier_and_dedupes_by_case(
    client: TestClient, db: Session
) -> None:
    first = client.post(
        "/api/sources",
        json={
            "kind": "smartrecruiters",
            "display_name": "Bosch",
            "board": "https://jobs.smartrecruiters.com/BoschGroup/123-x?utm=1#f",
        },
    )
    assert first.status_code == 201, first.text
    assert first.json()["identifier"] == "boschgroup"
    assert first.json()["region"] is None
    assert IDENT.match(first.json()["identifier"])
    again = client.post(
        "/api/sources",
        json={"kind": "smartrecruiters", "display_name": "Bosch 2", "board": "BOSCHGROUP"},
    )
    assert again.status_code == 409, again.text


@pytest.mark.postgres
def test_api_refuses_unknown_extra_field_and_builtin_kinds(client: TestClient) -> None:
    for kind in ("community_feed", "curated_registry"):
        response = client.post(
            "/api/sources", json={"kind": kind, "display_name": "X", "board": "acme"}
        )
        assert response.status_code == 422, response.text


# --- URL building --------------------------------------------------------------------------------


def _requested(server: Server) -> list[str]:
    return server.list_urls + server.detail_urls


def test_only_allowlisted_request_shapes_are_ever_requested() -> None:
    server = Server([list_item(n) for n in range(3)])
    parse(collect(server.request()), SOURCE)
    urls = _requested(server)
    assert len(urls) == 1 + 3
    for url in urls:
        assert ALLOWED_REQUEST.match(url), url
        check_url(url, None)  # passes the real allowlist check


HOSTILE_IDS = [
    "../../x",
    "1?x=y",
    "1/../../",
    "1/2",
    "1#f",
    "12 3",
    "123\n",
    "١٢٣",  # Arabic-Indic digits
    "%31%32",
    "1%2F..%2F",
    "",
    "9" * 31,
    "https://evil.example/1",
]


@pytest.mark.parametrize("hostile", HOSTILE_IDS)
def test_non_numeric_posting_id_is_never_interpolated_into_a_request(hostile: str) -> None:
    good = list_item(1)
    bad = list_item(2, id=hostile)
    server = Server([good, bad])
    items = parse(collect(server.request()), SOURCE).items
    assert server.detail_urls == [f"{BASE}/{good['id']}"]
    assert all(ALLOWED_REQUEST.match(u) for u in _requested(server))
    assert isinstance(items[0], NormalizedOpportunity)
    assert isinstance(items[1], ItemError)


def test_provider_ref_and_posting_url_pointing_elsewhere_are_never_fetched() -> None:
    evil = "https://evil.example/steal"
    items = [
        list_item(1, ref=evil, postingUrl=evil, applyUrl=evil),
        list_item(2, ref="https://jobs.smartrecruiters.com/other/1"),
    ]
    server = Server(items)
    server.detail_override[pid(1)] = lambda: httpx2.Response(
        200, json=detail_for(items[0], postingUrl=evil, applyUrl=evil, ref=evil)
    )
    parsed = parse(collect(server.request()), SOURCE).items
    assert all(ALLOWED_REQUEST.match(u) for u in _requested(server))
    assert not any("evil" in u or "jobs.smartrecruiters" in u for u in _requested(server))
    assert all(isinstance(i, NormalizedOpportunity) for i in parsed)


@pytest.mark.parametrize(
    "location",
    [
        "https://evil.example/x",
        "https://jobs.smartrecruiters.com/acme/1",  # not on the allowlist either
        "https://api.smartrecruiters.com:8443/v1/companies/x/postings",
        "http://api.smartrecruiters.com/v1/companies/x/postings",
        "https://user@api.smartrecruiters.com/x",
        "//evil.example/x",
        "file:///etc/passwd",
    ],
)
def test_redirects_off_the_allowlist_are_never_followed(location: str) -> None:
    server = Server([list_item(1)])
    server.detail_override[pid(1)] = lambda: httpx2.Response(302, headers={"Location": location})
    parsed = parse(collect(server.request()), SOURCE).items
    # Only the one detail request was made; the redirect target was refused before any request.
    assert server.detail_urls == [f"{BASE}/{pid(1)}"]
    [item] = parsed
    assert isinstance(item, ItemError) and item.code == "detail_failed"


def test_allowlist_has_only_the_one_new_host() -> None:
    assert "api.smartrecruiters.com" in ALLOWED_HOSTS
    assert "jobs.smartrecruiters.com" not in ALLOWED_HOSTS
    assert set(ALLOWED_HOSTS) == {
        "zshah101.github.io",
        "boards-api.greenhouse.io",
        "api.lever.co",
        "api.eu.lever.co",
        "api.ashbyhq.com",
        "api.smartrecruiters.com",
    }
    for url in (
        "https://jobs.smartrecruiters.com/acme",
        "https://api.smartrecruiters.com.evil/x",
        "https://evil.api.smartrecruiters.com/x",
        "https://api.smartrecruiters.com:8443/x",
        "https://u@api.smartrecruiters.com/x",
        "http://api.smartrecruiters.com/x",
    ):
        with pytest.raises(FetchError):
            check_url(url, None)


def test_detail_url_for_company_uses_the_validated_identifier_only() -> None:
    # A source whose stored identifier somehow held path characters is still quoted, never raw.
    hostile = SourceConfig(IngestionSourceKind.SMARTRECRUITERS, "a/../b?x=1", None, "X")
    seen: list[str] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        seen.append(str(request.url))
        return httpx2.Response(404)

    transport = httpx2.MockTransport(handle)
    with pytest.raises(FetchError):
        collect(CollectRequest(hostile, SourceScope.ALL, {}, transport))
    assert seen
    assert all(
        u.startswith("https://api.smartrecruiters.com/v1/companies/a%2F..%2Fb%3Fx%3D1/")
        for u in seen
    )


# --- Identity ------------------------------------------------------------------------------------


def test_detail_with_another_posting_id_is_a_mismatch_not_data() -> None:
    items = [list_item(1)]
    server = Server(items)
    server.detail_override[pid(1)] = lambda: httpx2.Response(200, json=detail_for(list_item(2)))
    [item] = parse(collect(server.request()), SOURCE).items
    assert isinstance(item, ItemError) and item.code == "detail_mismatch"


def test_detail_for_another_company_is_a_mismatch() -> None:
    item = list_item(1)
    server = Server([item])
    other = detail_for(item, company={"identifier": "someoneelse", "name": "Else"})
    server.detail_override[pid(1)] = lambda: httpx2.Response(200, json=other)
    [parsed] = parse(collect(server.request()), SOURCE).items
    assert isinstance(parsed, ItemError) and parsed.code == "detail_mismatch"


def test_detail_without_company_is_a_mismatch() -> None:
    item = list_item(1)
    server = Server([item])
    body = detail_for(item)
    del body["company"]
    server.detail_override[pid(1)] = lambda: httpx2.Response(200, json=body)
    [parsed] = parse(collect(server.request()), SOURCE).items
    assert isinstance(parsed, ItemError) and parsed.code == "detail_mismatch"


def test_list_item_from_another_company_is_not_fetched_or_imported() -> None:
    foreign = list_item(1, company={"identifier": "someoneelse"})
    missing = list_item(2)
    del missing["company"]
    server = Server([foreign, missing, list_item(3)])
    items = parse(collect(server.request()), SOURCE).items
    assert server.detail_urls == [f"{BASE}/{pid(3)}"]
    kinds = [type(i) for i in items]
    assert kinds == [ItemError, ItemError, NormalizedOpportunity]
    assert [i.code for i in items if isinstance(i, ItemError)] == ["company_mismatch"] * 2


def test_same_numeric_id_across_two_companies_stays_two_identities() -> None:
    from app.ingestion.adapters.smartrecruiters import _normalize  # pyright: ignore

    results: list[NormalizedOpportunity] = []
    for company in ("alpha", "beta"):
        source = SourceConfig(IngestionSourceKind.SMARTRECRUITERS, company, None, company)
        posting = list_item(1, company={"identifier": company})
        entry = {"posting": posting, "detail": {"postingUrl": None}}
        results.append(_normalize(entry, source))
    values = {i.value for r in results for i in r.identifiers if i.namespace == SMARTRECRUITERS}
    assert values == {f"alpha:{pid(1)}", f"beta:{pid(1)}"}


def test_ids_that_look_like_other_companies_are_not_cross_matched() -> None:
    # Colon-bearing company can't exist: the identifier regex forbids it.
    for company in ("a:b", "a b", "A"):
        source = SourceConfig(IngestionSourceKind.SMARTRECRUITERS, company, None, "x")
        from app.ingestion.adapters.smartrecruiters import _normalize  # pyright: ignore

        entry = {"posting": list_item(1, company={"identifier": "a"})}
        with pytest.raises(ItemError):
            _normalize(entry, source)


SR_ID = "smartrecruiters:acme:743999"
SR_HOST = "https://jobs.smartrecruiters.com"


@pytest.mark.parametrize(
    "url",
    [
        f"{SR_HOST}/acme/743999",
        f"{SR_HOST}/acme/743999-intern-role",
        f"{SR_HOST}/ACME/743999-Intern",
        f"{SR_HOST}/acme/743999-slug/extra",  # company + id agree; the tail is ignored
        f"{SR_HOST}/acme/743999/",
        f"{SR_HOST}/acme/743999?oga=true#x",
    ],
)
def test_identity_for_exact_agreement(url: str) -> None:
    assert provider_identity(SR_ID, url) == Identifier(
        namespace=SMARTRECRUITERS, value="acme:743999"
    )


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        f"{SR_HOST}/acme/743999extra",  # no dash: a different id
        f"{SR_HOST}/acme/7439990",
        f"{SR_HOST}/acme/74399",
        f"{SR_HOST}/acme/111111-743999",  # id only as a slug suffix
        f"{SR_HOST}/other/743999",
        f"{SR_HOST}/743999/acme",
        f"{SR_HOST}/acme",
        f"{SR_HOST}/",
        f"{SR_HOST}//acme/743999x",
        f"{SR_HOST}/acme/%37%34%33%39%39%39",  # percent-encoded id is not decoded
        f"{SR_HOST}/ac%6De/743999",  # percent-encoded company
        f"{SR_HOST}/acme%2F743999",
        f"{SR_HOST}/acme/743999%2dintern",
        "https://jobs.smartrecruiters.com./acme/743999",
        "https://jobs.smartrecruiters.com:443/acme/743999",
        "https://jobs.smartrecruiters.com:8443/acme/743999",
        "https://user@jobs.smartrecruiters.com/acme/743999",
        "https://user:pw@jobs.smartrecruiters.com/acme/743999",
        "https://jobs.smartrecruiters.com@evil.com/acme/743999",
        "https://jobs.smartrecruiters.com.evil.com/acme/743999",
        "https://evil.com/jobs.smartrecruiters.com/acme/743999",
        "https://evil.com/acme/743999",
        "https://www.smartrecruiters.com/acme/743999",
        "https://api.smartrecruiters.com/v1/companies/acme/postings/743999",
        "http://jobs.smartrecruiters.com/acme/743999",
        "//jobs.smartrecruiters.com/acme/743999",
        "https://jobs.smartrecruiters.com\\acme\\743999",
        "javascript://jobs.smartrecruiters.com/acme/743999",
    ],
)
def test_no_identity_unless_link_agrees_exactly(url: str | None) -> None:
    assert provider_identity(SR_ID, url) is None


@pytest.mark.parametrize(
    "item_id",
    [
        "smartrecruiters:acme:743999\n",
        "smartrecruiters:acme:74a399",
        "smartrecruiters:acme:٧٤٣",
        "smartrecruiters:acme:",
        "smartrecruiters::743999",
        "smartrecruiters:-acme:743999",
        "smartrecruiters:ac.me:743999",
        "smartrecruiters:acme/x:743999",
        f"smartrecruiters:{'a' * 65}:743999",
        "SmartRecruiters:acme:743999",
        "smartrecruiters:acme:743999:extra",
    ],
)
def test_no_identity_for_malformed_feed_ids(item_id: str) -> None:
    assert provider_identity(item_id, f"{SR_HOST}/acme/743999") is None


# --- Discovery: zero network ---------------------------------------------------------------------


def _forbid_network(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    attempts: list[str] = []

    def boom(name: str) -> Any:
        def _boom(*_a: Any, **_k: Any) -> None:
            attempts.append(name)
            raise AssertionError(f"network attempted: {name}")

        return _boom

    monkeypatch.setattr(httpx2.HTTPTransport, "handle_request", boom("httpx2.handle_request"))
    monkeypatch.setattr(socket.socket, "connect", boom("socket.connect"))
    monkeypatch.setattr(socket, "create_connection", boom("socket.create_connection"))
    monkeypatch.setattr(socket, "getaddrinfo", boom("socket.getaddrinfo"))
    monkeypatch.setattr("app.ingestion.http._resolve", boom("_resolve"))
    monkeypatch.setattr("app.ingestion.http.fetch_json", boom("fetch_json"))
    monkeypatch.setattr("app.ingestion.adapters.smartrecruiters.fetch_json", boom("sr.fetch_json"))
    return attempts


def _seed_sr_feed_rows(db: Session) -> None:
    feed = builtin_source(db)
    good = ("smartrecruiters:acme:743999", f"{SR_HOST}/acme/743999-intern")
    rows = [
        good,
        ("smartrecruiters:evil:743999", "https://jobs.smartrecruiters.com./evil/743999"),
        ("smartrecruiters:evil2:743999", "https://jobs.smartrecruiters.com:8443/evil2/743999"),
        ("smartrecruiters:evil3:743999", "https://evil.example/evil3/743999"),
        ("smartrecruiters:evil4:743999", f"{SR_HOST}/someoneelse/743999"),
    ]
    for external_id, url in rows:
        make_record(
            db,
            make_opportunity(db),
            source=feed,
            external_id=external_id,
            source_url=url,
            company="Acme",
        )
    db.commit()


@pytest.mark.postgres
def test_discovery_and_bulk_add_make_zero_network_calls(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_sr_feed_rows(db)
    attempts = _forbid_network(monkeypatch)

    direct = source_discovery.discover(db)
    assert [s.key for s in direct.suggestions] == ["smartrecruiters:acme"]

    listed = client.get("/api/sources/discovery")
    assert listed.status_code == 200, listed.text
    assert [s["key"] for s in listed.json()["suggestions"]] == ["smartrecruiters:acme"]

    forged = client.post(
        "/api/sources/discovery/add",
        json={"sources": [{"kind": "smartrecruiters", "identifier": "evil"}]},
    )
    assert forged.status_code == 422, forged.text

    added = client.post(
        "/api/sources/discovery/add",
        json={"sources": [{"kind": "smartrecruiters", "identifier": "acme"}]},
    )
    assert added.status_code == 201, added.text
    [created] = added.json()["created"]
    assert created["kind"] == "smartrecruiters" and created["region"] is None
    assert created["scope"] == "internships_only"
    assert attempts == []


@pytest.mark.postgres
def test_discovery_add_refuses_a_region_for_smartrecruiters(
    client: TestClient, db: Session
) -> None:
    _seed_sr_feed_rows(db)
    response = client.post(
        "/api/sources/discovery/add",
        json={"sources": [{"kind": "smartrecruiters", "identifier": "acme", "region": "eu"}]},
    )
    assert response.status_code == 422, response.text


# --- Stored raw payload --------------------------------------------------------------------------


def test_raw_payload_never_stores_creator_custom_field_or_referral_url() -> None:
    item = list_item(1, creator={"name": "Synthetic Person"}, referralUrl="https://x/ref")
    server = Server([item])
    payload = collect(server.request())
    parsed = parse(payload, SOURCE).items
    [opp] = [i for i in parsed if isinstance(i, NormalizedOpportunity)]
    for blob in (json.dumps(payload), json.dumps(opp.raw_payload)):
        for banned in ("creator", "customField", "referralUrl", "Synthetic Person", "valueLabel"):
            assert banned not in blob, banned


def test_javascript_posting_url_is_not_stored_as_application_url() -> None:
    item = list_item(1)
    server = Server([item])
    server.detail_override[pid(1)] = lambda: httpx2.Response(
        200, json=detail_for(item, postingUrl="javascript:alert(1)")
    )
    [opp] = parse(collect(server.request()), SOURCE).items
    assert isinstance(opp, NormalizedOpportunity)
    assert opp.application_url is None
    assert not any(i.namespace != SMARTRECRUITERS for i in opp.identifiers)


# --- Request bounds ------------------------------------------------------------------------------


def _hostile_server(
    handler: Callable[[httpx2.Request, int], httpx2.Response],
) -> tuple[httpx2.MockTransport, list[str]]:
    seen: list[str] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        seen.append(str(request.url))
        return handler(request, len(seen))

    return httpx2.MockTransport(handle), seen


def _page(offset: int, total: int, content: list[Any], limit: int = PAGE_SIZE) -> httpx2.Response:
    return httpx2.Response(
        200, json={"offset": offset, "limit": limit, "totalFound": total, "content": content}
    )


def _offset(request: httpx2.Request) -> int:
    return int(request.url.params["offset"])


def _req(transport: httpx2.MockTransport) -> CollectRequest:
    return CollectRequest(SOURCE, SourceScope.ALL, {}, transport)


def test_huge_total_found_is_refused_after_one_request() -> None:
    transport, seen = _hostile_server(lambda r, n: _page(_offset(r), 10**9, [list_item(1)]))
    with pytest.raises(SnapshotError) as info:
        collect(_req(transport))
    assert info.value.code == "too_many_pages"
    assert len(seen) == 1


def test_negative_total_found_is_refused() -> None:
    transport, seen = _hostile_server(lambda r, n: _page(_offset(r), -5, []))
    with pytest.raises(SnapshotError):
        collect(_req(transport))
    assert len(seen) == 1


def test_page_with_more_than_the_limit_is_refused_immediately() -> None:
    items = [list_item(n) for n in range(PAGE_SIZE + 1)]
    transport, seen = _hostile_server(lambda r, n: _page(_offset(r), 500, items))
    with pytest.raises(SnapshotError) as info:
        collect(_req(transport))
    assert info.value.code == "schema_mismatch"
    assert len(seen) == 1


def test_echoed_limit_that_is_not_ours_is_refused() -> None:
    transport, seen = _hostile_server(lambda r, n: _page(_offset(r), 5, [], limit=10**6))
    with pytest.raises(SnapshotError):
        collect(_req(transport))
    assert len(seen) == 1


def test_content_past_total_found_is_an_error_not_a_closure() -> None:
    full = [list_item(n) for n in range(PAGE_SIZE)]
    transport, seen = _hostile_server(lambda r, n: _page(_offset(r), 150, full))
    with pytest.raises(SnapshotError) as info:
        collect(_req(transport))
    assert info.value.code == "inconsistent_listing"
    assert len(seen) == 2


def test_total_found_zero_with_content_is_an_error() -> None:
    transport, seen = _hostile_server(lambda r, n: _page(_offset(r), 0, [list_item(1)]))
    with pytest.raises(SnapshotError):
        collect(_req(transport))
    assert len(seen) == 1


def test_total_found_that_changes_mid_walk_is_an_error() -> None:
    full = [list_item(n) for n in range(PAGE_SIZE)]
    transport, _ = _hostile_server(lambda r, n: _page(_offset(r), 150 if n == 1 else 151, full))
    with pytest.raises(SnapshotError) as info:
        collect(_req(transport))
    assert info.value.code == "inconsistent_listing"


def test_endless_empty_pages_stop_immediately() -> None:
    transport, seen = _hostile_server(lambda r, n: _page(_offset(r), 500, []))
    with pytest.raises(SnapshotError) as info:
        collect(_req(transport))
    assert info.value.code == "incomplete_listing"
    assert len(seen) == 1


def test_one_item_pages_cannot_force_thousands_of_requests() -> None:
    """A hostile or broken provider that honours offsets but returns one posting per page, with
    totalFound at the 5000 cap, must not drive an unbounded number of sequential requests."""

    def handler(request: httpx2.Request, n: int) -> httpx2.Response:
        offset = _offset(request)
        return _page(offset, MAX_PAGES * PAGE_SIZE, [list_item(offset)])

    transport, seen = _hostile_server(handler)
    with pytest.raises(SnapshotError):
        collect(_req(transport))
    assert len(seen) <= MAX_PAGES


def test_detail_fetches_are_capped_and_never_close_anything() -> None:
    items = [list_item(n, name=f"Engineering Intern {n}") for n in range(250)]
    server = Server(items)
    parsed = parse(collect(server.request()), SOURCE).items
    assert len(server.detail_urls) == MAX_DETAIL_FETCHES
    deferred = [i for i in parsed if isinstance(i, ItemError)]
    assert len(deferred) == 250 - MAX_DETAIL_FETCHES
    assert {i.code for i in deferred} == {"detail_deferred"}


def test_failing_details_do_not_exceed_the_budget() -> None:
    items = [list_item(n, name=f"Engineering Intern {n}") for n in range(150)]
    server = Server(items)
    for item in items:
        server.detail_override[item["id"]] = lambda: httpx2.Response(500)
    parse(collect(server.request()), SOURCE)
    # Each failing fetch is retried at most MAX_ATTEMPTS (3) times, for at most the budget.
    assert len(server.detail_urls) <= MAX_DETAIL_FETCHES * 3
