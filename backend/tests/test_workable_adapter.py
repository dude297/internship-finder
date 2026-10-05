"""Workable widget adapter: unit tests on fabricated payloads (no DB, no network)."""

from typing import Any

import pytest

from app.enums import IngestionSourceKind, OpportunityType, RemoteMode
from app.ingestion.adapters import SourceConfig
from app.ingestion.adapters.workable import ADAPTER, parse, parse_account_reference
from app.ingestion.normalize import ItemError, NormalizedOpportunity, SnapshotError

SOURCE = SourceConfig(IngestionSourceKind.WORKABLE, "example-robotics", None, "Example Robotics")
CODE = "AB12CD34EF"


def job(code: str = CODE, **changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "title": "Robotics Software Intern",
        "code": "",
        "shortcode": code,
        "employment_type": "Internship",
        "telecommuting": False,
        "city": "Example City",
        "state": "Example State",
        "country": "Exampleland",
        "locations": [
            {"country": "Exampleland", "city": "Example City", "region": "Example State"}
        ],
        "published_on": "2040-09-05",
        "created_at": "2039-01-01",
        "url": f"https://apply.workable.com/j/{code}",
        "shortlink": f"https://apply.workable.com/j/{code}",
        "application_url": f"https://apply.workable.com/j/{code}/apply",
        "description": "<p>Build <b>fictional</b> robots.</p><ul><li>Python</li></ul>",
    }
    return base | changes


def run(*jobs: Any) -> list[NormalizedOpportunity | ItemError]:
    return parse({"name": "Example Robotics", "jobs": list(jobs)}, SOURCE).items


def one(**changes: Any) -> NormalizedOpportunity:
    (item,) = run(job(**changes))
    assert isinstance(item, NormalizedOpportunity)
    return item


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("example-robotics", "example-robotics"),
        ("  Example-Robotics ", "example-robotics"),
        ("https://apply.workable.com/example-robotics", "example-robotics"),
        ("https://apply.workable.com/Example-Robotics/j/AB12CD34EF/", "example-robotics"),
        ("apply.workable.com/example-robotics/", "example-robotics"),
        ("https://example-robotics.workable.com", "example-robotics"),
        ("example-robotics.workable.com", "example-robotics"),
    ],
)
def test_reference_accepts(value: str, expected: str) -> None:
    assert parse_account_reference(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "example\nrobotics",  # embedded newline (a trailing one is stripped, like Ashby)
        "example-robotics\n/x",
        "-bad",
        "has space",
        "a/b",
        "http://apply.workable.com/example-robotics",
        "https://user@apply.workable.com/example-robotics",
        "https://apply.workable.com:8443/example-robotics",
        "https://apply.workable.com/",
        "https://www.workable.com/example-robotics",
        "https://evil.example/example-robotics",
        "https://apply.workable.com.evil.example/example-robotics",
        "https://a.b.workable.com",
        "https://example-robotics.workable.com@evil.example",
        "ftp://apply.workable.com/example-robotics",
        "example-robotics?x=1",
        "x" * 65,
    ],
)
def test_reference_rejects(value: str) -> None:
    with pytest.raises(ValueError):
        parse_account_reference(value)


def test_url_is_hard_coded_host_with_quoted_slug() -> None:
    assert (
        ADAPTER.url(SOURCE) == "https://www.workable.com/api/accounts/example-robotics?details=true"
    )
    odd = SourceConfig(IngestionSourceKind.WORKABLE, "a/b?c", None, "X")
    assert ADAPTER.url(odd).startswith("https://www.workable.com/api/accounts/a%2Fb%3Fc?")


def test_parses_fabricated_payload() -> None:
    item = one()
    assert item.external_id == CODE
    assert item.title == "Robotics Software Intern"
    assert item.organization == "Example Robotics"
    assert item.opportunity_type is OpportunityType.INTERNSHIP
    assert item.location == "Example City, Example State, Exampleland"
    assert item.remote_mode is None  # telecommuting false is not on-site
    assert item.posted_at is not None and item.posted_at.isoformat() == "2040-09-05T00:00:00+00:00"
    assert item.source_published_at == item.posted_at  # created_at is not used
    assert item.application_url == f"https://apply.workable.com/j/{CODE}"
    assert {(i.namespace, i.value) for i in item.identifiers} == {
        ("workable", CODE),
        ("url", f"https://apply.workable.com/j/{CODE}"),
    }
    assert item.raw_payload["shortcode"] == CODE
    assert item.application_deadline is None


def test_description_is_text() -> None:
    desc = one().description or ""
    assert "Build fictional robots." in desc and "• Python" in desc and "<" not in desc


def test_shortcode_is_uppercased() -> None:
    assert one(shortcode="ab12cd34ef").external_id == "AB12CD34EF"


def test_remote_mode_only_when_stated() -> None:
    assert one(telecommuting=True).remote_mode is RemoteMode.REMOTE
    assert one(workplace_type="hybrid").remote_mode is RemoteMode.HYBRID
    assert one(workplace_type="on_site", telecommuting=True).remote_mode is RemoteMode.ONSITE
    assert one(telecommuting=None).remote_mode is None


def test_location_falls_back_to_flat_fields() -> None:
    assert one(locations=[]).location == "Example City, Example State, Exampleland"
    assert one(locations=[], city=None, state=None, country=None).location is None


@pytest.mark.parametrize(
    "url",
    [
        "http://apply.workable.com/j/AB12CD34EF",
        "https://evil.example/j/AB12CD34EF",
        "https://apply.workable.com.evil.example/j/AB12CD34EF",
        "https://user@apply.workable.com/j/AB12CD34EF",
        "https://apply.workable.com:444/j/AB12CD34EF",
        "javascript:alert(1)",
    ],
)
def test_application_url_host_check(url: str) -> None:
    item = one(url=url, shortlink=None, application_url=None)
    assert item.application_url is None
    assert [i.namespace for i in item.identifiers] == ["workable"]


def test_application_url_falls_back_to_next_valid_link() -> None:
    item = one(url="https://evil.example/x", shortlink=None)
    assert item.application_url == f"https://apply.workable.com/j/{CODE}/apply"


def test_no_published_date_is_none() -> None:
    assert one(published_on=None).posted_at is None
    assert one(published_on="not a date").posted_at is None


def test_type_classification() -> None:
    assert one(title="Marketing Manager", employment_type="Full-time").opportunity_type is (
        OpportunityType.OTHER
    )
    assert one(title="Marketing Manager", employment_type="Intern").opportunity_type is (
        OpportunityType.INTERNSHIP
    )
    assert one(title="Robotics Co-op").opportunity_type is OpportunityType.INTERNSHIP


@pytest.mark.parametrize(
    "bad",
    [
        job(shortcode="bad code!"),
        job(shortcode="AB1"),
        job(shortcode="AB12CD34EF\n"),
        {k: v for k, v in job().items() if k != "shortcode"},
        {k: v for k, v in job().items() if k != "title"},
        job(title="   "),
    ],
)
def test_bad_item_is_an_item_error_not_a_snapshot_failure(bad: dict[str, Any]) -> None:
    items = run(bad, job("FF00FF00FF"))
    assert isinstance(items[0], ItemError)
    assert isinstance(items[1], NormalizedOpportunity) and items[1].external_id == "FF00FF00FF"


def test_non_object_item_is_an_item_error() -> None:
    assert isinstance(run("nope")[0], ItemError)


def test_item_error_carries_the_shortcode() -> None:
    (error,) = run(job(title=None))
    assert isinstance(error, ItemError) and error.external_id == CODE


def test_duplicate_shortcodes_are_both_emitted_for_the_pipeline_to_reject() -> None:
    items = run(job(), job())
    assert [type(i) for i in items] == [NormalizedOpportunity, NormalizedOpportunity]


@pytest.mark.parametrize(
    "payload", [[], "x", None, {}, {"name": "X"}, {"jobs": None}, {"jobs": {"a": 1}}]
)
def test_schema_mismatch_fails_the_snapshot(payload: Any) -> None:
    with pytest.raises(SnapshotError) as caught:
        parse(payload, SOURCE)
    assert caught.value.code == "schema_mismatch"


def test_empty_jobs_is_a_valid_empty_snapshot() -> None:
    assert run() == []
