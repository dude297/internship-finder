"""The curated program registry's schema and normalization (ADR-014 §5-§7), no database.
Synthetic entries only."""

import copy
import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.enums import IngestionSourceKind, OpportunityType, RemoteMode, SourceScope
from app.ingestion.adapters import CollectRequest, SourceConfig, adapter_for
from app.ingestion.adapters import program_registry as registry
from app.ingestion.normalize import CURATED, ItemError, NormalizedOpportunity, SnapshotError

SOURCE = SourceConfig(
    IngestionSourceKind.CURATED_REGISTRY, "program-registry", None, "Program registry"
)

ENTRY: dict[str, Any] = {
    "slug": "example-summer-research",
    "cycle": "2027",
    "title": "Example Summer Research Program",
    "organization": "Example Institute",
    "opportunity_type": "research",
    "application_url": "https://apply.example.org/summer",
    "source_url": "https://www.example.org/summer",
    "location": "Example City",
    "remote_mode": "onsite",
    "verified": {
        "open_date": "2027-01-05",
        "deadline": "2027-02-15",
        "start_date": "2027-06-20",
        "end_date": "2027-08-01",
    },
    "typical_open_window": "January",
    "typical_close_window": "February",
    "verify_by": "2027-01-01",
    "eligibility_summary": "Applicants must be at least 16 years old.",
    "description": "A paraphrased summary of the program.",
    "last_verified": "2026-10-04",
}


def entry(**changes: Any) -> dict[str, Any]:
    result = copy.deepcopy(ENTRY)
    result.update(changes)
    return result


def file(*programs: dict[str, Any], version: int = 1) -> dict[str, Any]:
    return {"schema_version": version, "programs": list(programs)}


def only(payload: Any) -> NormalizedOpportunity | ItemError:
    [item] = registry.parse(payload, SOURCE).items
    return item


def normalized(**changes: Any) -> NormalizedOpportunity:
    item = only(file(entry(**changes)))
    assert isinstance(item, NormalizedOpportunity), item
    return item


def test_the_adapter_is_wired_for_the_registry_kind() -> None:
    assert adapter_for(IngestionSourceKind.CURATED_REGISTRY) is registry.ADAPTER


# --- Schema accept/reject matrix -----------------------------------------------------------------


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {"application_url": None, "location": None, "remote_mode": None},
        {"cycle": "2027-summer"},
        {"verified": {}},
        {"verify_by": None, "eligibility_summary": None, "typical_open_window": None},
        {"verified": {"start_date": "2027-06-20", "end_date": "2027-06-20"}},
        {"slug": "ab"},
    ],
)
def test_valid_entries_are_accepted(changes: dict[str, Any]) -> None:
    assert isinstance(only(file(entry(**changes))), NormalizedOpportunity)


@pytest.mark.parametrize(
    "changes",
    [
        {"slug": "Bad_Slug"},
        {"slug": "a"},
        {"slug": "-leading"},
        {"slug": "x" * 64},
        {"slug": "good-slug\n"},
        {"cycle": "27"},
        {"cycle": "2027-Summer"},
        {"cycle": "2027-ab"},
        {"cycle": "2027-summer-extra"},
        {"cycle": "2027\n"},
        {"application_url": "http://apply.example.org/summer"},
        {"source_url": "http://www.example.org/x"},
        {"source_url": "https://user:pw@www.example.org/x"},
        {"source_url": "https://www.example.org:8443/x"},
        {"source_url": "https://localhost/x"},
        {"source_url": "https://www.example.org/a b"},
        {"source_url": "https://www.example.org/" + "a" * 2048},
        {"source_url": "ftp://www.example.org/x"},
        {"source_url": None},
        {"unknown": "key"},
        {"verified": {"deadline": "2027-02-15", "extra": 1}},
        {"verified": {"start_date": "2027-08-01", "end_date": "2027-06-20"}},
        {"opportunity_type": "job"},
        {"remote_mode": "moon"},
        {"title": ""},
        {"title": "t" * 301},
        {"organization": "o" * 201},
        {"location": "l" * 201},
        {"typical_open_window": "w" * 101},
        {"eligibility_summary": "e" * 1001},
        {"description": ""},
        {"description": "d" * 2001},
        {"last_verified": None},
        {"verify_by": "soon"},
    ],
)
def test_invalid_entries_are_item_errors(changes: dict[str, Any]) -> None:
    assert isinstance(only(file(entry(**changes))), ItemError)


def test_a_missing_required_key_is_an_item_error() -> None:
    bad = entry()
    del bad["last_verified"]
    assert isinstance(only(file(bad)), ItemError)


@pytest.mark.parametrize(
    "payload",
    [
        file(entry(), version=2),
        {"programs": []},
        {"schema_version": 1},
        {"schema_version": 1, "programs": [], "extra": 1},
        {"schema_version": 1, "programs": "nope"},
        [],
        file(entry(), entry(title="Same slug and cycle")),
    ],
)
def test_a_bad_file_fails_the_whole_snapshot(payload: Any) -> None:
    with pytest.raises(SnapshotError):
        registry.parse(payload, SOURCE)


def test_the_same_slug_in_two_cycles_is_fine() -> None:
    snapshot = registry.parse(file(entry(), entry(cycle="2028")), SOURCE)
    assert [i.external_id for i in snapshot.items if isinstance(i, NormalizedOpportunity)] == [
        "example-summer-research:2027",
        "example-summer-research:2028",
    ]


def test_a_malformed_entry_is_an_item_error_while_others_parse() -> None:
    good, bad, non_object = entry(), entry(slug="BAD", title="Broken"), "nope"
    snapshot = registry.parse({"schema_version": 1, "programs": [good, bad, non_object]}, SOURCE)
    first, second, third = snapshot.items
    assert isinstance(first, NormalizedOpportunity)
    assert isinstance(second, ItemError) and second.external_id == "BAD:2027"
    assert isinstance(third, ItemError)


# --- Normalization -------------------------------------------------------------------------------


def test_normalization_maps_the_entry() -> None:
    item = normalized()
    assert item.external_id == "example-summer-research:2027"
    assert item.title == "Example Summer Research Program"
    assert item.organization == "Example Institute"  # the entry's, not the source's display name
    assert item.opportunity_type is OpportunityType.RESEARCH
    assert item.application_url == "https://apply.example.org/summer"
    assert (item.location, item.remote_mode) == ("Example City", RemoteMode.ONSITE)
    assert item.application_deadline == date(2027, 2, 15)
    assert (item.start_date, item.end_date) == (date(2027, 6, 20), date(2027, 8, 1))
    assert item.program_cycle == "2027"
    assert (item.typical_open_window, item.typical_close_window) == ("January", "February")
    assert item.verify_by == date(2027, 1, 1)
    assert item.posted_at is None
    assert item.raw_payload == ENTRY


def test_only_a_curated_identifier_is_emitted() -> None:
    item = normalized()
    assert [(i.namespace, i.value) for i in item.identifiers] == [
        (CURATED, "example-summer-research:2027")
    ]


def test_the_application_url_falls_back_to_the_source_url() -> None:
    assert normalized(application_url=None).application_url == "https://www.example.org/summer"


def test_the_description_includes_the_eligibility_summary() -> None:
    assert normalized().description == (
        "A paraphrased summary of the program."
        "\n\nEligibility (summary): Applicants must be at least 16 years old."
    )
    assert normalized(eligibility_summary=None).description == (
        "A paraphrased summary of the program."
    )


def test_a_typical_window_never_becomes_a_date() -> None:
    item = normalized(verified={}, typical_open_window="January", typical_close_window="February")
    assert (item.application_deadline, item.start_date, item.end_date) == (None, None, None)
    assert item.typical_close_window == "February"


def test_open_date_is_not_a_canonical_field() -> None:
    assert not hasattr(normalized(), "open_date")


# --- collect -------------------------------------------------------------------------------------


def request() -> CollectRequest:
    return CollectRequest(SOURCE, SourceScope.ALL, {}, None)


def test_collect_reads_the_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "r.json"
    path.write_text(json.dumps(file(entry())), encoding="utf-8")
    monkeypatch.setattr(registry, "REGISTRY_PATH", path)
    assert registry.collect(request()) == file(entry())


@pytest.mark.parametrize(
    "content",
    [
        b"{not json",
        b"\xff\xfe",
        b"[]",
        json.dumps(file(version=9)).encode(),
        pytest.param(b"x" * (1024 * 1024 + 1), id="too-large"),
    ],
)
def test_collect_rejects_a_bad_file(
    content: bytes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "r.json"
    path.write_bytes(content)
    monkeypatch.setattr(registry, "REGISTRY_PATH", path)
    with pytest.raises(SnapshotError):
        registry.collect(request())


def test_collect_rejects_a_missing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "REGISTRY_PATH", tmp_path / "missing.json")
    with pytest.raises(SnapshotError):
        registry.collect(request())


def test_the_bundled_file_is_valid() -> None:
    payload = json.loads(registry.REGISTRY_PATH.read_text(encoding="utf-8"))
    assert all(
        isinstance(item, NormalizedOpportunity) for item in registry.parse(payload, SOURCE).items
    )
