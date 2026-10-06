"""Large-board Greenhouse collection (ADR-022): list-first, size-selected detail mode, bounds, and
the guarantee that no failed or partial run closes anything. Synthetic data only."""

import gzip
import json
from functools import partial
from typing import Any

import httpx2
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.enums import IngestionRunStatus, IngestionSourceKind, SourceScope
from app.ingestion import http
from app.ingestion.adapters import CollectRequest, SourceConfig, greenhouse
from app.ingestion.adapters.greenhouse import collect, parse
from app.ingestion.http import FetchError, fetch_json
from app.ingestion.normalize import NormalizedOpportunity, SnapshotError
from app.ingestion.pipeline import sync_source
from app.models import IngestionSource, OpportunitySourceRecord
from tests.ingestion_fixtures import GREENHOUSE_BOARD, greenhouse_job

SOURCE = SourceConfig(IngestionSourceKind.GREENHOUSE, GREENHOUSE_BOARD, None, "Example Robotics")
BASE = f"https://boards-api.greenhouse.io/v1/boards/{GREENHOUSE_BOARD}/jobs"
JSON_HEADERS = {"Content-Type": "application/json"}


@pytest.fixture(autouse=True)
def _fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(greenhouse, "fetch_json", partial(fetch_json, sleep=lambda _s: None))
    monkeypatch.setattr(greenhouse, "LARGE_BOARD_JOBS", 5)  # "large" = more than 5 jobs here


def job(n: int, title: str | None = None, **changes: Any) -> dict[str, Any]:
    return greenhouse_job(n, title=title or f"Synthetic Robotics Intern {n}") | changes


def listing(*jobs: dict[str, Any]) -> dict[str, Any]:
    stripped = [{k: v for k, v in j.items() if k != "content"} for j in jobs]
    return {"jobs": stripped, "meta": {"total": len(stripped)}}


class Server:
    def __init__(self, *jobs: dict[str, Any]) -> None:
        self.jobs = list(jobs)
        self.urls: list[str] = []
        self.list_override: httpx2.Response | None = None
        self.detail_override: dict[str, Any] = {}
        self.total: int | None = None
        self.transport = httpx2.MockTransport(self._handle)

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        url = str(request.url)
        self.urls.append(url)
        if url == BASE:
            if self.list_override is not None:
                return self.list_override
            body = listing(*self.jobs)
            if self.total is not None:
                body["meta"]["total"] = self.total
            return httpx2.Response(200, json=body)
        if url == f"{BASE}?content=true":
            return httpx2.Response(200, json={"jobs": self.jobs, "meta": {"total": len(self.jobs)}})
        job_id = url.rsplit("/", 1)[1]
        if job_id in self.detail_override:
            action = self.detail_override[job_id]
            if isinstance(action, Exception):
                raise action
            return action
        for j in self.jobs:
            if str(j["id"]) == job_id:
                return httpx2.Response(200, json=j)
        return httpx2.Response(404)

    @property
    def details(self) -> list[str]:
        return [u for u in self.urls if u.rsplit("/", 1)[1].isdigit()]

    def request(
        self, scope: SourceScope = SourceScope.ALL, known: dict[str, Any] | None = None
    ) -> CollectRequest:
        return CollectRequest(SOURCE, scope, known or {}, self.transport)


def big(n: int = 8) -> Server:
    """A large (> 5 jobs) board: even ids are internships, odd ids are not."""
    return Server(
        *(
            job(i, title=None if i % 2 == 0 else f"Synthetic Staff Engineer {i}")
            for i in range(1, n + 1)
        )
    )


def run(server: Server, **kw: Any) -> dict[str, NormalizedOpportunity]:
    items = parse(collect(server.request(**kw)), SOURCE).items
    assert all(isinstance(i, NormalizedOpportunity) for i in items), items
    return {i.external_id: i for i in items if isinstance(i, NormalizedOpportunity)}


def detail_ids(server: Server) -> list[str]:
    return sorted((u.rsplit("/", 1)[1] for u in server.details), key=int)


# --- selection -----------------------------------------------------------------------------------


def test_small_board_reads_the_list_then_one_content_list() -> None:
    server = Server(job(1), job(2))
    items = run(server)
    assert server.urls == [BASE, f"{BASE}?content=true"]
    assert all(i.description for i in items.values())


def test_board_at_the_threshold_is_small_and_one_over_is_large() -> None:
    at = Server(*(job(n) for n in range(1, 6)))
    run(at)
    assert at.urls[-1].endswith("content=true")
    over = Server(*(job(n) for n in range(1, 7)))
    run(over)
    assert not any("content=true" in u for u in over.urls)


def test_large_board_fetches_details_only_for_internship_titles() -> None:
    server = big()
    items = run(server)
    assert detail_ids(server) == ["2", "4", "6", "8"]
    assert len(items) == 8  # the complete snapshot: every listed job, with or without text
    assert items["2"].description and items["1"].description is None


def test_internships_only_scope_is_identical_on_the_wire() -> None:
    server = big()
    run(server, scope=SourceScope.INTERNSHIPS_ONLY)
    assert len(server.details) == 4


def test_real_threshold_is_500(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.undo()
    monkeypatch.setattr(greenhouse, "fetch_json", partial(fetch_json, sleep=lambda _s: None))
    server = Server(*(job(n, title=f"Role {n}") for n in range(1, 502)))
    run(server)
    assert server.urls == [BASE]  # 501 jobs, none an internship: list only, never content=true


def test_stored_content_is_reused_when_updated_at_is_unchanged() -> None:
    first = collect(big().request())
    known = {str(j["id"]): j for j in first["jobs"]}
    again = big()
    second = collect(again.request(known=known))
    assert again.details == [] and second == first


def test_changed_updated_at_refetches_only_that_job() -> None:
    known = {str(j["id"]): j for j in collect(big().request())["jobs"]}
    changed = big()
    changed.jobs[3]["updated_at"] = "2040-10-01T10:00:00-04:00"
    collect(changed.request(known=known))
    assert detail_ids(changed) == ["4"]


# --- bounds --------------------------------------------------------------------------------------


def test_detail_fetches_are_capped_and_the_snapshot_stays_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(greenhouse, "MAX_DETAIL_FETCHES", 2)
    server = big()
    assert len(run(server)) == 8
    assert len(server.details) == 2


def test_cumulative_detail_byte_budget_stops_fetching(monkeypatch: pytest.MonkeyPatch) -> None:
    server = big()
    size = len(json.dumps(server.jobs[1]).encode())
    monkeypatch.setattr(greenhouse, "MAX_DETAIL_TOTAL_BYTES", size + 1)  # room for ~1 detail
    assert len(run(server)) == 8
    assert len(server.details) == 2  # the one that crosses the budget is the last


def test_oversized_detail_is_skipped_not_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(greenhouse, "MAX_DETAIL_BYTES", 100)
    items = run(big())
    assert len(items) == 8 and all(i.description is None for i in items.values())


def test_detail_timeout_and_mid_run_failure_never_fail_the_snapshot() -> None:
    server = big(12)
    server.detail_override["2"] = httpx2.ReadTimeout("slow")
    server.detail_override["4"] = httpx2.Response(500)
    server.detail_override["6"] = httpx2.Response(200, content=b"{broken", headers=JSON_HEADERS)
    items = run(server)
    assert len(items) == 12
    assert items["2"].description is None and items["8"].description


def test_consecutive_failures_stop_the_detail_phase() -> None:
    server = big(30)
    for n in range(2, 31, 2):
        server.detail_override[str(n)] = httpx2.Response(404)
    assert len(run(server)) == 30
    assert len(server.details) == greenhouse.MAX_CONSECUTIVE_DETAIL_FAILURES


def test_detail_for_another_job_is_ignored() -> None:
    server = big()
    server.detail_override["2"] = httpx2.Response(200, json=job(99))
    items = run(server)
    assert items["2"].description is None and items["4"].description


def test_failed_refetch_keeps_stored_text() -> None:
    known = {str(j["id"]): j for j in collect(big().request())["jobs"]}
    changed = big()
    changed.jobs[1]["updated_at"] = "2040-10-01T10:00:00-04:00"
    changed.detail_override["2"] = httpx2.Response(500)
    assert run(changed, known=known)["2"].description


# --- list integrity ------------------------------------------------------------------------------


def test_moving_total_is_incomplete_before_any_detail_request() -> None:
    server = big()
    server.total = 9
    with pytest.raises(SnapshotError) as error:
        collect(server.request())
    assert error.value.code == "incomplete_snapshot" and server.details == []


def test_large_board_without_a_total_is_refused() -> None:
    server = big()
    server.list_override = httpx2.Response(200, json={"jobs": listing(*server.jobs)["jobs"]})
    with pytest.raises(SnapshotError):
        collect(server.request())
    assert server.details == []


def test_duplicate_ids_fail_the_snapshot() -> None:
    server = big()
    server.jobs.append(server.jobs[0] | {"title": "Synthetic Duplicate Intern"})
    with pytest.raises(SnapshotError) as error:
        collect(server.request())
    assert error.value.code == "inconsistent_listing" and server.details == []


def test_too_many_jobs_fail_the_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(greenhouse, "MAX_JOBS", 7)
    with pytest.raises(SnapshotError) as error:
        collect(big(8).request())
    assert error.value.code == "too_many_jobs"


@pytest.mark.parametrize("body", [b'{"jobs": [{"id": 1,', b"[]", b"null", b'{"jobs": 3}'])
def test_truncated_or_invalid_list_is_no_snapshot(body: bytes) -> None:
    server = big()
    server.list_override = httpx2.Response(200, content=body, headers=JSON_HEADERS)
    with pytest.raises((FetchError, SnapshotError)):
        collect(server.request())
    assert server.details == []


@pytest.mark.parametrize("status", [404, 429, 500])
def test_list_failures_propagate(status: int) -> None:
    server = big()
    server.list_override = httpx2.Response(status)
    with pytest.raises(FetchError):
        collect(server.request())


def test_idless_entries_pass_through_for_parse_to_report() -> None:
    server = big()
    server.jobs.append({"title": "Synthetic Intern Without Id"})
    payload = collect(server.request())
    assert len(payload["jobs"]) == 9 and payload["meta"]["total"] == 9


# --- http.py caps --------------------------------------------------------------------------------


def _fetch(response: httpx2.Response, **kw: Any) -> Any:
    return fetch_json(BASE, transport=httpx2.MockTransport(lambda _r: response), **kw)


def test_oversized_list_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http, "MAX_BYTES", 1000)
    body = json.dumps({"jobs": [job(n) for n in range(10)]}).encode()
    with pytest.raises(FetchError) as error:  # chunked, no Content-Length: the stream is capped
        _fetch(httpx2.Response(200, content=iter([body[:600], body[600:]]), headers=JSON_HEADERS))
    assert error.value.code == "response_too_large"
    with pytest.raises(FetchError) as error:  # declared length
        _fetch(httpx2.Response(200, content=body, headers=JSON_HEADERS))
    assert error.value.code == "response_too_large"


def test_compression_bomb_is_capped_on_decoded_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http, "MAX_BYTES", 50_000)
    bomb = gzip.compress(b'{"jobs": "' + b"a" * 5_000_000 + b'"}')
    assert len(bomb) < 50_000  # small on the wire, huge once decoded
    headers = JSON_HEADERS | {"Content-Encoding": "gzip"}
    with pytest.raises(FetchError) as error:
        _fetch(httpx2.Response(200, content=iter([bomb]), headers=headers))
    assert error.value.code == "response_too_large"


def test_max_bytes_can_only_tighten_the_global_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http, "MAX_BYTES", 100)
    body = json.dumps({"x": "y" * 200}).encode()
    with pytest.raises(FetchError):
        _fetch(httpx2.Response(200, content=iter([body]), headers=JSON_HEADERS), max_bytes=10**7)


def test_fetched_reports_the_decoded_size() -> None:
    body = json.dumps({"a": 1}).encode()
    assert _fetch(httpx2.Response(200, content=body, headers=JSON_HEADERS)).size == len(body)


# --- pipeline: a failed or partial run never closes ----------------------------------------------


@pytest.fixture
def gh(db: Session) -> IngestionSource:
    source = IngestionSource(
        kind=IngestionSourceKind.GREENHOUSE,
        identifier=GREENHOUSE_BOARD,
        display_name="Example Robotics",
        scope=SourceScope.ALL,
    )
    db.add(source)
    db.commit()
    return source


def _active(db: Session, source: IngestionSource) -> int:
    return (
        db.scalar(
            select(func.count()).where(
                OpportunitySourceRecord.ingestion_source_id == source.id,
                OpportunitySourceRecord.is_active,
            )
        )
        or 0
    )


@pytest.mark.postgres
def test_pipeline_large_board_then_failures_never_close(db: Session, gh: IngestionSource) -> None:
    server = big()
    run1 = sync_source(db, gh, transport=server.transport)
    assert run1.status is IngestionRunStatus.SUCCESS and _active(db, gh) == 8

    broken = [
        httpx2.Response(500),
        httpx2.Response(200, content=b'{"jobs": [', headers=JSON_HEADERS),
        httpx2.Response(200, json={"jobs": [], "meta": {"total": 3}}),
        httpx2.Response(200, json={"jobs": [], "meta": {"total": 0}}),  # empty-snapshot guard
    ]
    for response in broken:
        server.list_override = response
        failed = sync_source(db, gh, transport=server.transport)
        assert failed.closed_count == 0, response
        assert _active(db, gh) == 8
    server.list_override = None

    server.total = 99  # a moving total
    assert sync_source(db, gh, transport=server.transport).status is IngestionRunStatus.FAILED
    server.total = None
    assert _active(db, gh) == 8

    # Detail trouble keeps the snapshot complete and closes nothing.
    server.detail_override["2"] = httpx2.ReadTimeout("slow")
    server.jobs[1]["updated_at"] = "2040-10-01T10:00:00-04:00"
    run2 = sync_source(db, gh, transport=server.transport)
    assert run2.status is IngestionRunStatus.SUCCESS and run2.closed_count == 0
    server.jobs.pop()  # job 8 genuinely left the board
    run3 = sync_source(db, gh, transport=server.transport)
    assert run3.closed_count == 1 and _active(db, gh) == 7


@pytest.mark.postgres
def test_pipeline_duplicate_ids_close_nothing(db: Session, gh: IngestionSource) -> None:
    server = big()
    sync_source(db, gh, transport=server.transport)
    server.jobs.append(server.jobs[0])
    failed = sync_source(db, gh, transport=server.transport)
    assert failed.status is IngestionRunStatus.FAILED and _active(db, gh) == 8
