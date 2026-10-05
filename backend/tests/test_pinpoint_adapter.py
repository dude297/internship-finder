"""Pinpoint adapter without a database or network. All payloads are synthetic."""

from datetime import date
from typing import Any

import pytest

from app.enums import IngestionSourceKind, OpportunityType, RemoteMode
from app.ingestion.adapters import SourceConfig, pinpoint
from app.ingestion.normalize import ItemError, NormalizedOpportunity, SnapshotError

COMPANY = "example-space"
SOURCE = SourceConfig(IngestionSourceKind.PINPOINT, COMPANY, None, "Example Space")
POSTING_URL = f"https://{COMPANY}.pinpointhq.com/en/postings/00000000-0000-4000-8000-000000000001"


def posting(posting_id: str = "1001", **changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": posting_id,
        "title": "Avionics Engineering Intern (Summer 2040)",
        "url": POSTING_URL,
        "path": "/en/postings/00000000-0000-4000-8000-000000000001",
        "description": "<div><!--block-->Build <b>flight</b> computers.</div>",
        "key_responsibilities": "<ul><li>Test boards</li></ul>",
        "skills_knowledge_expertise": "<p>C and Python</p>",
        "employment_type": "internship",
        "workplace_type": "hybrid",
        "deadline_at": None,
        "location": {"id": "1", "city": "Example City", "name": "Example City, Example State "},
        "job": {"id": "9", "requisition_id": "R1"},
    }
    return body | changes


def payload(*postings: Any) -> dict[str, Any]:
    return {"data": list(postings)}


def items(snapshot_items: list[Any]) -> list[NormalizedOpportunity]:
    assert all(isinstance(i, NormalizedOpportunity) for i in snapshot_items)
    return snapshot_items


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("example-space", COMPANY),
        ("Example-Space", COMPANY),
        ("  example-space\n", COMPANY),
        ("a", "a"),
        ("https://example-space.pinpointhq.com", COMPANY),
        ("https://Example-Space.pinpointhq.com/en/postings/abc?x=1", COMPANY),
        ("example-space.pinpointhq.com/en/postings", COMPANY),
    ],
)
def test_reference_accepts(value: str, expected: str) -> None:
    assert pinpoint.parse_company_reference(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "-bad",
        "bad-",
        "a.b",
        "a" * 64,
        "exämple",
        "example space",
        "example\nspace",
        "example-space.pinpointhq.com",  # a bare host isn't a label
        "evil.com/.pinpointhq.com",
        "https://evil.com/example-space.pinpointhq.com",
        "https://example-space.pinpointhq.com.evil.com/",
        "https://a.b.pinpointhq.com/",
        "https://pinpointhq.com/",
        "http://example-space.pinpointhq.com/",
        "ftp://example-space.pinpointhq.com/",
        "https://user:pw@example-space.pinpointhq.com/",
        "https://example-space.pinpointhq.com:8443/",
        "https://exämple.pinpointhq.com/",
    ],
)
def test_reference_rejects(value: str) -> None:
    with pytest.raises(ValueError):
        pinpoint.parse_company_reference(value)


def test_url_building() -> None:
    assert pinpoint.ADAPTER.url(SOURCE) == f"https://{COMPANY}.pinpointhq.com/postings.json"
    bad = SourceConfig(IngestionSourceKind.PINPOINT, "evil.com/x", None, "X")
    with pytest.raises(ValueError):
        pinpoint.ADAPTER.url(bad)


def test_mapping() -> None:
    [item] = items(pinpoint.parse(payload(posting()), SOURCE).items)

    assert item.external_id == "1001"
    assert item.organization == "Example Space"
    assert item.opportunity_type is OpportunityType.INTERNSHIP
    assert item.remote_mode is RemoteMode.HYBRID
    assert item.location == "Example City, Example State"
    assert item.application_url == POSTING_URL
    assert item.posted_at is None and item.source_published_at is None
    assert item.application_deadline is None
    assert item.description == "Build flight computers.\n\n• Test boards\n\nC and Python"
    assert {(i.namespace, i.value) for i in item.identifiers} == {
        ("pinpoint", f"{COMPANY}:1001"),
        ("url", POSTING_URL),
    }
    assert pinpoint.ADAPTER.normalize(item.raw_payload, SOURCE) == item


def test_remote_only_when_explicit() -> None:
    modes = [
        items(pinpoint.parse(payload(posting(workplace_type=w)), SOURCE).items)[0].remote_mode
        for w in ("remote", "onsite", "hybrid", None, "weird")
    ]
    assert modes == [RemoteMode.REMOTE, RemoteMode.ONSITE, RemoteMode.HYBRID, None, None]


def test_type_classification() -> None:
    structured, by_title, other = items(
        pinpoint.parse(
            payload(
                posting("a", title="Avionics Engineer", employment_type="internship"),
                posting("b", title="Summer Intern", employment_type="full_time"),
                posting("c", title="Avionics Engineer", employment_type="full_time"),
            ),
            SOURCE,
        ).items
    )
    assert structured.opportunity_type is OpportunityType.INTERNSHIP
    assert by_title.opportunity_type is OpportunityType.INTERNSHIP
    assert other.opportunity_type is OpportunityType.OTHER


@pytest.mark.parametrize(
    "url",
    [
        # (another tenant's URL fails the whole snapshot instead: test_m81_adapters_adversarial)
        "https://example-space.pinpointhq.com.evil.com/en/postings/x",
        "https://evil.com/example-space.pinpointhq.com/x",
        "http://example-space.pinpointhq.com/en/postings/x",
        "https://user@example-space.pinpointhq.com/x",
        "https://example-space.pinpointhq.com:444/x",
        "javascript:alert(1)",
        None,
    ],
)
def test_application_url_must_be_own_https_host(url: str | None) -> None:
    [item] = items(pinpoint.parse(payload(posting(url=url)), SOURCE).items)
    assert item.application_url is None
    assert {i.namespace for i in item.identifiers} == {"pinpoint"}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2040-10-01", date(2040, 10, 1)),
        ("2040-10-01T23:59:00-07:00", date(2040, 10, 1)),  # provider-local calendar date kept
        ("2040-10-01T23:59:00.000Z", date(2040, 10, 1)),
        ("soon", None),
        ("", None),
        (None, None),
    ],
)
def test_deadline(value: str | None, expected: date | None) -> None:
    [item] = items(pinpoint.parse(payload(posting(deadline_at=value)), SOURCE).items)
    assert item.application_deadline == expected


def test_description_conversion_drops_scripts_and_missing_parts() -> None:
    [item] = items(
        pinpoint.parse(
            payload(
                posting(
                    description="<p>Hi</p><script>bad()</script>",
                    key_responsibilities=None,
                    skills_knowledge_expertise=None,
                )
            ),
            SOURCE,
        ).items
    )
    assert item.description == "Hi"
    [bare] = items(
        pinpoint.parse(
            payload(
                posting(
                    description=None, key_responsibilities=None, skills_knowledge_expertise=None
                )
            ),
            SOURCE,
        ).items
    )
    assert bare.description is None


def test_location_fallback_and_missing() -> None:
    city, none = items(
        pinpoint.parse(
            payload(
                posting("a", location={"city": "Example City", "name": None}),
                posting("b", location=None),
            ),
            SOURCE,
        ).items
    )
    assert city.location == "Example City" and none.location is None


@pytest.mark.parametrize("bad_id", [None, 5, "", "a b", "x" * 65, "1001\n", "../x"])
def test_bad_ids_are_item_errors(bad_id: Any) -> None:
    [error] = pinpoint.parse(payload(posting(id=bad_id)), SOURCE).items
    assert isinstance(error, ItemError)


def test_bad_items_are_item_errors_not_snapshot_failures() -> None:
    snapshot = pinpoint.parse(
        payload(posting(), posting("no-title", title=None), "not an object"), SOURCE
    )
    assert [type(i).__name__ for i in snapshot.items] == [
        "NormalizedOpportunity",
        "ItemError",
        "ItemError",
    ]
    errors = [i for i in snapshot.items if isinstance(i, ItemError)]
    assert errors[0].external_id == "no-title"


def test_duplicate_ids_are_passed_through_for_the_pipeline_to_flag() -> None:
    snapshot = pinpoint.parse(payload(posting("same"), posting("same")), SOURCE)
    assert [i.external_id for i in items(snapshot.items)] == ["same", "same"]


def test_empty_list_is_a_valid_snapshot() -> None:
    assert pinpoint.parse(payload(), SOURCE).items == []


@pytest.mark.parametrize("body", [[], {"data": "nope"}, {"data": None}, {"jobs": []}, "text", None])
def test_top_level_mismatch(body: Any) -> None:
    with pytest.raises(SnapshotError) as error:
        pinpoint.parse(body, SOURCE)
    assert error.value.code == "schema_mismatch"
