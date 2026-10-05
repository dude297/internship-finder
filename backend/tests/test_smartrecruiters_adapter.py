"""SmartRecruiters adapter (ADR-014 §1-§4) without a database: list walk, detail budget, reuse,
partial semantics, normalization, company parsing, and feed identity. Synthetic data only."""

import json
from collections.abc import Callable
from functools import partial
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx2
import pytest

from app.enums import (
    IngestionSourceKind,
    OpportunityType,
    RemoteMode,
    SourceScope,
)
from app.ingestion.adapters import CollectRequest, SourceConfig, smartrecruiters
from app.ingestion.adapters.community_feed import provider_identity
from app.ingestion.adapters.smartrecruiters import (
    MAX_DETAIL_FETCHES,
    MAX_PAGES,
    collect,
    parse,
    parse_company_reference,
)
from app.ingestion.http import fetch_json
from app.ingestion.normalize import (
    SMARTRECRUITERS,
    Identifier,
    ItemError,
    NormalizedOpportunity,
    SnapshotError,
)

COMPANY = "examplerobotics"
SOURCE = SourceConfig(IngestionSourceKind.SMARTRECRUITERS, COMPANY, None, "Example Robotics")
BASE = f"https://api.smartrecruiters.com/v1/companies/{COMPANY}/postings"


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    sleeps: list[float] = []
    monkeypatch.setattr(smartrecruiters, "fetch_json", partial(fetch_json, sleep=sleeps.append))
    return sleeps


def pid(n: int) -> str:
    return f"{100000000000000 + n}"


def list_item(n: int, name: str | None = None, **changes: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": pid(n),
        "name": name or f"Synthetic Engineering Intern {n}",
        "uuid": f"00000000-0000-4000-8000-{n:012d}",
        "jobAdId": f"ad-{n}",
        "refNumber": f"REF{n}",
        "company": {"identifier": "ExampleRobotics", "name": "Example Robotics"},
        "releasedDate": "2040-09-20T12:00:00.000Z",
        "location": {
            "city": "Example City",
            "region": "EX",
            "country": "xx",
            "remote": False,
            "hybrid": False,
            "fullLocation": "Example City, EX, xx",
        },
        "typeOfEmployment": {"id": "permanent", "label": "Full-time"},
        "experienceLevel": {"id": "entry_level", "label": "Entry Level"},
        "department": {"label": "Engineering"},
        "function": {"id": "engineering", "label": "Engineering"},
        "industry": {"id": "software", "label": "Software"},
        "customField": [{"fieldId": "x", "valueLabel": "ignored"}],
        "visibility": "PUBLIC",
        "ref": f"{BASE}/{pid(n)}",
        "language": {"code": "en"},
    }
    return item | changes


def detail_for(item: dict[str, Any], **changes: Any) -> dict[str, Any]:
    detail: dict[str, Any] = dict(item) | {
        "jobAd": {
            "sections": {
                "companyDescription": {"title": "Company Description", "text": "<p>We build.</p>"},
                "jobDescription": {"title": "Job Description", "text": "<p>Do <b>things</b>.</p>"},
                "qualifications": {"title": "Qualifications", "text": "<ul><li>Python</li></ul>"},
                "additionalInformation": {"title": "Additional Information", "text": ""},
            }
        },
        "postingUrl": f"https://jobs.smartrecruiters.com/ExampleRobotics/{item['id']}-intern",
        "applyUrl": f"https://jobs.smartrecruiters.com/ExampleRobotics/{item['id']}-intern?oga=true",
        "referralUrl": "https://jobs.smartrecruiters.com/ref/secret",
        "active": True,
        "creator": {"name": "Synthetic Person"},
        "jobId": "job-1",
    }
    return detail | changes


class Server:
    """A counting fake of the Posting API."""

    def __init__(self, items: list[dict[str, Any]]) -> None:
        self.items = items
        self.list_urls: list[str] = []
        self.detail_urls: list[str] = []
        self.detail_override: dict[str, Callable[[], httpx2.Response]] = {}
        self.total_override: Callable[[int], int] | None = None
        self.transport = httpx2.MockTransport(self._handle)

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        url = request.url
        path = url.path
        if path.endswith("/postings"):
            self.list_urls.append(str(url))
            query = parse_qs(urlsplit(str(url)).query)
            assert query["destination"] == ["PUBLIC"]
            limit, offset = int(query["limit"][0]), int(query["offset"][0])
            total = len(self.items)
            if self.total_override:
                total = self.total_override(len(self.list_urls))
            return httpx2.Response(
                200,
                json={
                    "offset": offset,
                    "limit": limit,
                    "totalFound": total,
                    "content": self.items[offset : offset + limit],
                },
            )
        posting_id = path.rsplit("/", 1)[1]
        self.detail_urls.append(str(url))
        if posting_id in self.detail_override:
            return self.detail_override[posting_id]()
        for item in self.items:
            if item.get("id") == posting_id:
                return httpx2.Response(200, json=detail_for(item))
        return httpx2.Response(404)

    def request(
        self,
        scope: SourceScope = SourceScope.ALL,
        known: dict[str, Any] | None = None,
    ) -> CollectRequest:
        return CollectRequest(SOURCE, scope, known or {}, self.transport)


def run(server: Server, **kw: Any) -> list[NormalizedOpportunity | ItemError]:
    return parse(collect(server.request(**kw)), SOURCE).items


def ok(items: list[NormalizedOpportunity | ItemError]) -> list[NormalizedOpportunity]:
    out = [i for i in items if isinstance(i, NormalizedOpportunity)]
    assert len(out) == len(items), [i for i in items if isinstance(i, ItemError)]
    return out


# --- list walk -----------------------------------------------------------------------------------


def test_single_page_fetches_one_list_and_each_detail() -> None:
    server = Server([list_item(1), list_item(2)])
    items = ok(run(server))
    assert [i.external_id for i in items] == [pid(1), pid(2)]
    assert len(server.list_urls) == 1 and len(server.detail_urls) == 2
    assert server.list_urls[0] == f"{BASE}?limit=100&offset=0&destination=PUBLIC"


def test_multi_page_walks_in_order() -> None:
    server = Server([list_item(n, name=f"Staff Engineer {n}") for n in range(250)])
    items = ok(run(server, scope=SourceScope.INTERNSHIPS_ONLY))
    assert len(items) == 250
    assert [u.split("offset=")[1].split("&")[0] for u in server.list_urls] == ["0", "100", "200"]
    assert server.detail_urls == []  # none are internship titles


@pytest.mark.parametrize("count", [100, 500])
def test_request_counts_are_bounded(count: int) -> None:
    server = Server([list_item(n) for n in range(count)])
    payload = collect(server.request())
    assert len(server.list_urls) == -(-count // 100) <= 50
    assert len(server.detail_urls) == min(count, MAX_DETAIL_FETCHES)
    errors = [e for e in payload["postings"] if "error" in e]
    assert len(errors) == count - MAX_DETAIL_FETCHES
    assert {e["error"]["code"] for e in errors} <= {"detail_deferred"}
    assert all(isinstance(i, ItemError) for i in parse(payload, SOURCE).items[MAX_DETAIL_FETCHES:])


def test_empty_company_is_a_complete_empty_snapshot() -> None:
    assert run(Server([])) == []


def test_total_changing_mid_walk_fails_the_snapshot() -> None:
    server = Server([list_item(n) for n in range(250)])
    server.total_override = lambda call: 250 if call == 1 else 251
    with pytest.raises(SnapshotError) as error:
        collect(server.request())
    assert error.value.code == "inconsistent_listing"


def test_empty_page_before_total_fails_the_snapshot() -> None:
    server = Server([list_item(n) for n in range(150)])
    server.total_override = lambda _call: 300  # claims more than it serves
    with pytest.raises(SnapshotError) as error:
        collect(server.request())
    assert error.value.code == "incomplete_listing"


def test_more_than_max_pages_fails_before_walking_on() -> None:
    server = Server([list_item(n) for n in range(100)])
    server.total_override = lambda _call: MAX_PAGES * 100 + 1
    with pytest.raises(SnapshotError) as error:
        collect(server.request())
    assert error.value.code == "too_many_pages"
    assert len(server.list_urls) == 1


def test_exactly_max_pages_is_allowed() -> None:
    server = Server([list_item(n, name="Staff Engineer") for n in range(MAX_PAGES * 100)])
    payload = collect(server.request(scope=SourceScope.INTERNSHIPS_ONLY))
    assert len(server.list_urls) == MAX_PAGES and server.detail_urls == []
    assert len(payload["postings"]) == MAX_PAGES * 100


def test_wrong_shapes_fail_the_snapshot() -> None:
    bodies: list[Any] = [[], {"offset": 0, "limit": 100, "content": []}, {"totalFound": 1}]
    for body in bodies:
        transport = httpx2.MockTransport(lambda _r, b=body: httpx2.Response(200, json=b))
        with pytest.raises(SnapshotError):
            collect(CollectRequest(SOURCE, SourceScope.ALL, {}, transport))


def test_mismatched_offset_or_limit_fails_the_snapshot() -> None:
    for body in (
        {"offset": 100, "limit": 100, "totalFound": 1, "content": [list_item(1)]},
        {"offset": 0, "limit": 50, "totalFound": 1, "content": [list_item(1)]},
    ):
        transport = httpx2.MockTransport(lambda _r, b=body: httpx2.Response(200, json=b))
        with pytest.raises(SnapshotError):
            collect(CollectRequest(SOURCE, SourceScope.ALL, {}, transport))


def test_duplicate_ids_fail_the_snapshot() -> None:
    with pytest.raises(SnapshotError):
        collect(Server([list_item(1), list_item(1)]).request())


def test_list_page_fetch_error_propagates() -> None:
    from app.ingestion.http import FetchError

    transport = httpx2.MockTransport(lambda _r: httpx2.Response(404))
    with pytest.raises(FetchError):
        collect(CollectRequest(SOURCE, SourceScope.ALL, {}, transport))


def test_429_with_retry_after_then_success(_no_sleep: list[float]) -> None:
    server = Server([list_item(1)])
    calls = {"n": 0}

    def flaky(request: httpx2.Request) -> httpx2.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx2.Response(429, headers={"Retry-After": "2"})
        return server._handle(request)  # pyright: ignore[reportPrivateUsage]

    request = CollectRequest(SOURCE, SourceScope.ALL, {}, httpx2.MockTransport(flaky))
    ok(parse(collect(request), SOURCE).items)
    assert _no_sleep == [2.0]


# --- admission, detail, reuse ---------------------------------------------------------


def test_internships_only_fetches_details_for_internship_titles_only() -> None:
    server = Server([list_item(1), list_item(2, name="Staff Engineer"), list_item(3, "Co-op")])
    payload = collect(server.request(scope=SourceScope.INTERNSHIPS_ONLY))
    assert [u.rsplit("/", 1)[1] for u in server.detail_urls] == [pid(1), pid(3)]
    assert "detail" not in payload["postings"][1]
    # The non-admitted item still normalizes (the pipeline drops it afterwards).
    items = ok(parse(payload, SOURCE).items)
    assert items[1].description is None and items[0].description is not None


def test_stored_detail_is_reused_with_zero_detail_requests() -> None:
    server = Server([list_item(1), list_item(2)])
    first = collect(server.request())
    known = {e["posting"]["id"]: e for e in first["postings"]}
    again = Server([list_item(1), list_item(2)])
    second = collect(again.request(known=known))
    assert again.detail_urls == [] and len(again.list_urls) == 1  # steady state: list only
    assert second == first


def test_changed_list_item_refetches_only_that_detail() -> None:
    server = Server([list_item(1), list_item(2)])
    known = {e["posting"]["id"]: e for e in collect(server.request())["postings"]}
    changed = Server([list_item(1), list_item(2, name="Synthetic Engineering Intern II")])
    collect(changed.request(known=known))
    assert [u.rsplit("/", 1)[1] for u in changed.detail_urls] == [pid(2)]


def test_stored_item_without_detail_is_refetched() -> None:
    server = Server([list_item(1)])
    known = {pid(1): {"posting": collect(server.request())["postings"][0]["posting"]}}
    again = Server([list_item(1)])
    collect(again.request(known=known))
    assert len(again.detail_urls) == 1


def test_detail_404_and_500_become_item_errors() -> None:
    server = Server([list_item(1), list_item(2), list_item(3)])
    server.detail_override[pid(1)] = lambda: httpx2.Response(404)
    server.detail_override[pid(2)] = lambda: httpx2.Response(500)
    items = run(server)
    errors = [i for i in items if isinstance(i, ItemError)]
    assert [(e.code, e.external_id) for e in errors] == [
        ("detail_failed", pid(1)),
        ("detail_failed", pid(2)),
    ]
    assert isinstance(items[2], NormalizedOpportunity)


def test_detail_mismatch_is_an_item_error() -> None:
    server = Server([list_item(1), list_item(2), list_item(3)])
    server.detail_override[pid(1)] = lambda: httpx2.Response(
        200, json=detail_for(list_item(9, id=pid(9)))
    )
    other_company = detail_for(list_item(2), company={"identifier": "OtherCo"})
    server.detail_override[pid(2)] = lambda: httpx2.Response(200, json=other_company)
    server.detail_override[pid(3)] = lambda: httpx2.Response(200, json=[1])
    errors = [i for i in run(server) if isinstance(i, ItemError)]
    assert [e.code for e in errors] == ["detail_mismatch"] * 3


def test_detail_budget_defers_the_rest() -> None:
    server = Server([list_item(n) for n in range(MAX_DETAIL_FETCHES + 3)])
    items = run(server)
    assert len(server.detail_urls) == MAX_DETAIL_FETCHES
    deferred = [i for i in items if isinstance(i, ItemError)]
    assert [e.code for e in deferred] == ["detail_deferred"] * 3


def test_reused_details_do_not_spend_the_budget() -> None:
    items = [list_item(n) for n in range(MAX_DETAIL_FETCHES + 5)]
    known = {e["posting"]["id"]: e for e in collect(Server(items).request())["postings"]}
    del known[pid(0)]
    again = Server(items)
    ok(parse(collect(again.request(known=known)), SOURCE).items)
    assert len(again.detail_urls) == 6  # pid(0) plus the 5 deferred last time, not the 99 reused


# --- exclusion and company checks ---------------------------------------------------------------


def test_non_public_visibility_is_excluded() -> None:
    server = Server([list_item(1), list_item(2, visibility="INTERNAL"), list_item(3)])
    assert [i.external_id for i in ok(run(server))] == [pid(1), pid(3)]
    assert len(server.detail_urls) == 2


def test_company_mismatch_is_an_item_error_without_a_detail_fetch() -> None:
    other = list_item(2, company={"identifier": "OtherCo"})
    server = Server([list_item(1), other])
    items = run(server)
    assert isinstance(items[1], ItemError) and items[1].code == "company_mismatch"
    assert len(server.detail_urls) == 1


def test_company_match_is_case_insensitive() -> None:
    assert ok(run(Server([list_item(1, company={"identifier": "EXAMPLEROBOTICS"})])))


def test_missing_or_blank_id_is_an_item_error() -> None:
    bad = list_item(1)
    del bad["id"]
    items = run(Server([bad, list_item(2, id=""), list_item(3, id="12abc"), list_item(4)]))
    assert [isinstance(i, ItemError) for i in items] == [True, True, True, False]


def test_non_object_entry_is_an_item_error() -> None:
    items = parse({"postings": ["nope", 3]}, SOURCE).items
    assert [i.code for i in items if isinstance(i, ItemError)] == ["invalid_item"] * 2
    with pytest.raises(SnapshotError):
        parse({"jobs": []}, SOURCE)


# --- normalization --------------------------------------------------------------------------------


def test_html_sections_become_text_in_fixed_order() -> None:
    (item,) = ok(run(Server([list_item(1)])))
    assert item.description == (
        "Company Description\nWe build.\n\nJob Description\nDo things.\n\nQualifications\n• Python"
    )
    assert (
        item.application_url == f"https://jobs.smartrecruiters.com/ExampleRobotics/{pid(1)}-intern"
    )
    assert item.identifiers == (
        Identifier(namespace=SMARTRECRUITERS, value=f"{COMPANY}:{pid(1)}"),
        Identifier(
            namespace="url",
            value=f"https://jobs.smartrecruiters.com/ExampleRobotics/{pid(1)}-intern",
        ),
    )
    assert item.organization == "Example Robotics" and item.location == "Example City, EX, xx"
    assert item.posted_at is not None and item.posted_at == item.source_published_at


def test_creator_and_other_unsafe_keys_never_reach_the_payload() -> None:
    server = Server([list_item(1)])
    payload = collect(server.request())
    text = json.dumps(payload)
    for forbidden in ("creator", "Synthetic Person", "customField", "referralUrl", "secret"):
        assert forbidden not in text
    assert set(payload["postings"][0]) == {"posting", "detail"}
    (item,) = ok(parse(payload, SOURCE).items)
    assert "creator" not in json.dumps(item.raw_payload)


def test_normalize_from_stored_raw_equals_fresh() -> None:
    server = Server([list_item(1)])
    (fresh,) = ok(run(server))
    stored = json.loads(json.dumps(fresh.raw_payload))
    assert smartrecruiters.ADAPTER.normalize(stored, SOURCE) == fresh


def test_error_entry_never_normalizes() -> None:
    entry = {"posting": {"id": pid(1), "name": "Intern"}, "error": {"code": "x", "message": "y"}}
    with pytest.raises(ItemError) as error:
        smartrecruiters.ADAPTER.normalize(entry, SOURCE)
    assert error.value.code == "x"


@pytest.mark.parametrize(
    ("location", "mode"),
    [
        ({"remote": True, "hybrid": True}, RemoteMode.REMOTE),
        ({"remote": False, "hybrid": True}, RemoteMode.HYBRID),
        ({"remote": False, "hybrid": False}, None),
        ({}, None),
    ],
)
def test_remote_and_hybrid_mapping(location: dict[str, Any], mode: RemoteMode | None) -> None:
    (item,) = ok(run(Server([list_item(1, location=location)])))
    assert item.remote_mode is mode


def test_location_falls_back_to_parts() -> None:
    location = {"city": "Example City", "country": "xx"}
    (item,) = ok(run(Server([list_item(1, location=location)])))
    assert item.location == "Example City, xx"


@pytest.mark.parametrize(
    "changes",
    [
        {"typeOfEmployment": {"id": "intern", "label": "Intern"}},
        {"experienceLevel": {"id": "internship", "label": "Internship"}},
    ],
)
def test_structured_intern_beats_the_title(changes: dict[str, Any]) -> None:
    (item,) = ok(run(Server([list_item(1, name="Staff Engineer", **changes)])))
    assert item.opportunity_type is OpportunityType.INTERNSHIP
    (plain,) = ok(run(Server([list_item(1, name="Staff Engineer")])))
    assert plain.opportunity_type is OpportunityType.OTHER


# --- parse_company_reference ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "jobs.smartrecruiters.com.evil/x",
        "https://jobs.smartrecruiters.com.evil/x",
        "smartrecruiters.com.evil",
        "https://smartrecruiters.com.evil/x",
        "https://user@jobs.smartrecruiters.com/x",
        "https://user:pw@jobs.smartrecruiters.com/x",
        "https://jobs.smartrecruiters.com:8443/x",
        "https://jobs.smartrecruiters.com./x",
        "http://jobs.smartrecruiters.com/x",
        "https://jobs.smartrecruiters.com/a%2Fb",
        "https://jobs.smartrecruiters.com//x",
        "https://jobs.smartrecruiters.com/x\ny",
        "x\ny",
        "https://jobs.smartrecruiters.com/",
        "https://jobs.smartrecruiters.com",
        "https://jobs.smartrecruiters。com/x",
        "https://jobs.smartrecruiters.cоm/x",  # Cyrillic o
        "https://api.smartrecruiters.com/v1/companies/x/postings",
        "api.smartrecruiters.com/v1/companies/x/postings",
        "ftp://jobs.smartrecruiters.com/x",
        "",
        "   ",
        "-x",
        "a" * 65,
        "https://jobs.smartrecruiters.com/" + "a" * 65,
    ],
)
def test_company_reference_refusals(value: str) -> None:
    with pytest.raises(ValueError):
        parse_company_reference(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("ExampleRobotics", COMPANY),
        ("  ExampleRobotics  ", COMPANY),
        ("https://jobs.smartrecruiters.com/ExampleRobotics/123-intern", COMPANY),
        ("jobs.smartrecruiters.com/ExampleRobotics", COMPANY),
        ("https://jobs.smartrecruiters.com/ExampleRobotics/", COMPANY),
        ("AECOM2", "aecom2"),
    ],
)
def test_company_reference_accepts(value: str, expected: str) -> None:
    assert parse_company_reference(value) == expected


# --- feed identity (provider_identity, SmartRecruiters branch) ---------------------------

_LINK = "https://jobs.smartrecruiters.com/{c}/{rest}"
_IDENT = Identifier(namespace=SMARTRECRUITERS, value=f"{COMPANY}:123")


def sr(company: str, rest: str, **kw: str) -> str:
    return _LINK.format(c=company, rest=rest, **kw)


@pytest.mark.parametrize(
    ("item_id", "url", "expected"),
    [
        (f"smartrecruiters:{COMPANY}:123", sr(COMPANY, "123"), _IDENT),
        (f"smartrecruiters:{COMPANY}:123", sr(COMPANY, "123-synthetic-intern"), _IDENT),
        ("smartrecruiters:ExampleRobotics:123", sr("ExampleRobotics", "123-x"), _IDENT),
        (f"smartrecruiters:{COMPANY}:123", sr("OtherCo", "123"), None),
        (f"smartrecruiters:{COMPANY}:123", sr(COMPANY, "124"), None),
        (f"smartrecruiters:{COMPANY}:123", sr(COMPANY, "1234"), None),
        (f"smartrecruiters:{COMPANY}:123", sr(COMPANY, "1234-x"), None),
        (f"smartrecruiters:{COMPANY}:123", None, None),
        (f"smartrecruiters:{COMPANY}:123", "https://careers.example.com/jobs/123", None),
        (
            f"smartrecruiters:{COMPANY}:123",
            f"https://jobs.smartrecruiters.com.evil/{COMPANY}/123",
            None,
        ),
        (f"smartrecruiters:{COMPANY}:123", f"http://jobs.smartrecruiters.com/{COMPANY}/123", None),
        (
            f"smartrecruiters:{COMPANY}:123",
            f"https://jobs.smartrecruiters.com:8443/{COMPANY}/123",
            None,
        ),
        (
            f"smartrecruiters:{COMPANY}:123",
            f"https://u@jobs.smartrecruiters.com/{COMPANY}/123",
            None,
        ),
        (
            f"smartrecruiters:{COMPANY}:123",
            f"https://jobs.smartrecruiters.com./{COMPANY}/123",
            None,
        ),
        (f"smartrecruiters:{COMPANY}:12a", sr(COMPANY, "12a"), None),
        (f"smartrecruiters:{COMPANY}:", sr(COMPANY, ""), None),
    ],
)
def test_feed_identity_for_smartrecruiters(
    item_id: str, url: str | None, expected: Identifier | None
) -> None:
    assert provider_identity(item_id, url) == expected
