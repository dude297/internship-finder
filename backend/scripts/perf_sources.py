"""Scheduled-sync performance at scale (ADR-013 §7, §9). Manual only, never in CI.

Seeds N direct ATS sources (Greenhouse/Lever/Ashby boards, ~20 internship postings each, some
deduping onto a synthetic ~1,000-item discovery feed) into a DISPOSABLE database, for
N in (10, 25, 50), and times `sync_enabled_sources` for: a first sync, an unchanged second sync,
and a third sync where one source answers 500 (failure isolation) and one source closes all its
postings (exercising the ADR-013 §5 fallback onto the feed). Also times `discover()` on ~1,200
feed rows and the opportunity list query (`app.services.discovery.list_page`) after authority
changes. All HTTP is synthetic, served by `httpx2.MockTransport`; nothing touches the network.

    PERF_DATABASE_URL=postgresql+psycopg://…/if_m7_perf python scripts/perf_sources.py

The database is migrated to head; its non-built-in sources and all opportunities are wiped at
the start of each N. Timings vary by machine; they are reported, never asserted.
"""

import json
import os
import sys
import time
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx2
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, delete, event
from sqlalchemy.orm import Session

from app.enums import IngestionSourceKind, SourceRegion
from app.ingestion.adapters import SourceConfig, adapter_for
from app.ingestion.pipeline import sync_enabled_sources
from app.models import IngestionRun, IngestionSource, Opportunity
from app.services.discovery import Filters, list_page
from app.services.source_discovery import discover

CITIZENSHIP = " Must be a U.S. citizen."
KINDS = [IngestionSourceKind.GREENHOUSE, IngestionSourceKind.LEVER, IngestionSourceKind.ASHBY]
POSTINGS_PER_BOARD = 20
FEED_SIZE = 1_000


def _uuid(seed: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))


def _config(kind: IngestionSourceKind, identifier: str) -> SourceConfig:
    region = SourceRegion.GLOBAL if kind is IngestionSourceKind.LEVER else None
    return SourceConfig(kind, identifier, region, identifier)


def greenhouse_payload(board: str, n: int, with_text: bool) -> dict[str, Any]:
    jobs = [
        {
            "id": i,
            "title": f"Synthetic Robotics Intern {board}-{i}",
            "absolute_url": f"https://job-boards.greenhouse.io/{board}/jobs/{i}",
            "location": {"name": "Example City"},
            "content": f"Build synthetic robots.{CITIZENSHIP if i % 2 == 0 else ''}",
        }
        for i in range(1, n + 1)
    ]
    if not with_text:
        jobs = []
    return {"jobs": jobs, "meta": {"total": len(jobs)}}


def lever_payload(site: str, n: int, with_text: bool) -> list[dict[str, Any]]:
    if not with_text:
        return []
    return [
        {
            "id": _uuid(f"lever:{site}:{i}"),
            "text": f"Synthetic Research Intern {site}-{i}",
            "categories": {"location": "Example City"},
            "hostedUrl": f"https://jobs.lever.co/{site}/{_uuid(f'lever:{site}:{i}')}",
            "description": f"Study synthetic data.{CITIZENSHIP if i % 2 == 0 else ''}",
        }
        for i in range(1, n + 1)
    ]


def ashby_payload(board: str, n: int, with_text: bool) -> dict[str, Any]:
    jobs = [
        {
            "id": _uuid(f"ashby:{board}:{i}"),
            "title": f"Synthetic Data Science Intern {board}-{i}",
            "location": "Example City",
            "employmentType": "Intern",
            "isListed": True,
            "jobUrl": f"https://jobs.ashbyhq.com/{board}/{_uuid(f'ashby:{board}:{i}')}",
            "descriptionPlain": f"Build synthetic pipelines.{CITIZENSHIP if i % 2 == 0 else ''}",
        }
        for i in range(1, n + 1)
    ]
    if not with_text:
        jobs = []
    return {"apiVersion": "1", "jobs": jobs}


def feed_item(kind: IngestionSourceKind, board: str, index: int, url: str) -> dict[str, Any]:
    prefix = {
        IngestionSourceKind.GREENHOUSE: f"greenhouse:{board}:{index}",
        IngestionSourceKind.LEVER: f"lever:{board}:{_uuid(f'lever:{board}:{index}')}",
        IngestionSourceKind.ASHBY: f"ashby:{board}:{_uuid(f'ashby:{board}:{index}')}",
    }[kind]
    return {
        "id": prefix,
        "company": f"Example {board}",
        "title": f"Synthetic Feed Intern {board}-{index}",
        "url": url,
        "posted_at": "2040-09-20T00:00:00Z",
        "program": "Internship",
    }


def board_url(kind: IngestionSourceKind, board: str, index: int) -> str:
    if kind is IngestionSourceKind.GREENHOUSE:
        return f"https://job-boards.greenhouse.io/{board}/jobs/{index}"
    if kind is IngestionSourceKind.LEVER:
        return f"https://jobs.lever.co/{board}/{_uuid(f'lever:{board}:{index}')}"
    return f"https://jobs.ashbyhq.com/{board}/{_uuid(f'ashby:{board}:{index}')}"


def wipe(db: Session) -> None:
    db.execute(delete(Opportunity))
    db.execute(
        delete(IngestionSource).where(IngestionSource.kind != IngestionSourceKind.COMMUNITY_FEED)
    )
    db.commit()


def seed_sources(db: Session, n: int) -> list[IngestionSource]:
    sources: list[IngestionSource] = []
    for i in range(n):
        kind = KINDS[i % len(KINDS)]
        identifier = f"perfboard{i}"
        region = SourceRegion.GLOBAL if kind is IngestionSourceKind.LEVER else None
        source = IngestionSource(
            kind=kind, identifier=identifier, region=region, display_name=identifier
        )
        db.add(source)
        sources.append(source)
    db.commit()
    return sources


def transport_for(
    sources: list[IngestionSource],
    feed_body: dict[str, Any],
    *,
    fail_index: int | None = None,
    close_index: int | None = None,
) -> httpx2.MockTransport:
    routes: dict[str, httpx2.Response] = {}
    feed_config = _config(IngestionSourceKind.COMMUNITY_FEED, "zshah-tech-internships")
    feed_adapter = adapter_for(IngestionSourceKind.COMMUNITY_FEED)

    for i, source in enumerate(sources):
        config = _config(source.kind, source.identifier)
        url = adapter_for(source.kind).url(config)
        with_text = i != close_index
        if source.kind is IngestionSourceKind.GREENHOUSE:
            body: Any = greenhouse_payload(source.identifier, POSTINGS_PER_BOARD, with_text)
        elif source.kind is IngestionSourceKind.LEVER:
            body = lever_payload(source.identifier, POSTINGS_PER_BOARD, with_text)
        else:
            body = ashby_payload(source.identifier, POSTINGS_PER_BOARD, with_text)
        if i == fail_index:
            routes[url] = httpx2.Response(500)
        else:
            routes[url] = httpx2.Response(200, content=json.dumps(body).encode())

    # Hard-code the feed's own URL from its adapter (never rebuilt by hand).
    routes[feed_adapter.url(feed_config)] = httpx2.Response(
        200, content=json.dumps(feed_body).encode()
    )

    def handle(request: httpx2.Request) -> httpx2.Response:
        return routes.get(str(request.url), httpx2.Response(404))

    return httpx2.MockTransport(handle)


def build_feed(sources: list[IngestionSource], size: int) -> dict[str, Any]:
    jobs: list[dict[str, Any]] = []
    for source in sources:  # one feed item dedupes onto each board's first posting
        url = board_url(source.kind, source.identifier, 1)
        jobs.append(feed_item(source.kind, source.identifier, 1, url))
    filler = size - len(jobs)
    for i in range(max(filler, 0)):
        jobs.append(
            {
                "id": f"workday:example:/job/Synthetic-Intern-{i}",
                "company": f"Example Filler {i % 40}",
                "title": f"Synthetic Filler Intern {i}",
                "url": f"https://careers.example.com/jobs/{i}",
                "posted_at": "2040-09-20T00:00:00Z",
                "program": "Internship",
            }
        )
    return {
        "generated_at": "2040-09-21T06:00:00Z",
        "data_as_of": "2040-09-21T06:00:00Z",
        "source": "https://example.org/synthetic-feed",
        "count": len(jobs),
        "jobs": jobs,
    }


@contextmanager
def statements(db: Session) -> Generator[list[int]]:
    count = [0]

    def before(*_args: Any) -> None:
        count[0] += 1

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", before)
    try:
        yield count
    finally:
        event.remove(engine, "before_cursor_execute", before)


def timed_sync(
    db: Session, label: str, transport: httpx2.MockTransport
) -> tuple[float, int, list[IngestionRun]]:
    with statements(db) as count:
        started = time.perf_counter()
        runs = sync_enabled_sources(db, transport=transport)
        elapsed = time.perf_counter() - started
    print(f"  {label:<28} {elapsed:6.3f} s  {count[0]:5d} SQL statements  runs={len(runs)}")
    return elapsed, count[0], runs


def main() -> None:
    url = os.environ.get("PERF_DATABASE_URL")
    if not url:
        sys.exit("Set PERF_DATABASE_URL to a disposable PostgreSQL database.")
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "alembic"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(config, "head")

    engine = create_engine(url)
    results: dict[int, dict[str, Any]] = {}

    for n in (10, 25, 50):
        print(f"\n=== N = {n} ATS sources ===")
        with Session(engine) as db:
            wipe(db)
            sources = seed_sources(db, n)
            feed_body = build_feed(sources, FEED_SIZE)

            transport = transport_for(sources, feed_body)
            t1, _, runs1 = timed_sync(db, "first sync", transport)
            created = sum(r.created_count for r in runs1)
            kinds_in_order = [r.source.kind for r in runs1]
            ats_before_feed = (
                kinds_in_order.index(IngestionSourceKind.COMMUNITY_FEED) == len(kinds_in_order) - 1
            )

            transport = transport_for(sources, feed_body)  # identical snapshot
            t2, _, runs2 = timed_sync(db, "second sync (unchanged)", transport)
            unchanged_ok = all(r.updated_count == 0 and r.created_count == 0 for r in runs2)

            fail_index = 0
            close_index = 1 if n > 1 else None
            transport = transport_for(
                sources, feed_body, fail_index=fail_index, close_index=close_index
            )
            t3, _, runs3 = timed_sync(db, "third sync (failure+close)", transport)
            failed = [r for r in runs3 if r.status.value == "failed"]
            others_ran = len(runs3) == n + 1  # every source still produced a run
            closed_count = sum(r.closed_count for r in runs3)

            db.commit()

            # discover() on ~1,200 feed rows (reuse the N=50 feed, which is already ~1,000+N).
            with statements(db) as dcount:
                started = time.perf_counter()
                response = discover(db)
                d_elapsed = time.perf_counter() - started
            print(
                f"  {'discover()':<28} {d_elapsed:6.3f} s  {dcount[0]:5d} SQL statements"
                f"  suggestions={len(response.suggestions)}"
            )

            for sort in ("recommended", "newest"):
                with statements(db) as lcount:
                    started = time.perf_counter()
                    _, total = list_page(db, Filters(), 50, 0, sort)
                    l_elapsed = time.perf_counter() - started
                print(
                    f"  {'list_page ' + sort:<28} {l_elapsed:6.3f} s  {lcount[0]:5d} SQL"
                    f" statements  total={total}"
                )

            results[n] = {
                "created": created,
                "ats_before_feed": ats_before_feed,
                "unchanged_ok": unchanged_ok,
                "failed_isolated": len(failed) == 1 and others_ran,
                "closed_count": closed_count,
                "t1": t1,
                "t2": t2,
                "t3": t3,
            }

    print("\n=== Summary ===")
    print(
        f"{'N':>4} {'created':>8} {'ATS<feed':>9} {'no-flip':>8} {'isolated':>9} {'closed':>7}"
        f" {'t1(s)':>7} {'t2(s)':>7} {'t3(s)':>7}"
    )
    for n, r in results.items():
        print(
            f"{n:>4} {r['created']:>8} {str(r['ats_before_feed']):>9} {str(r['unchanged_ok']):>8}"
            f" {str(r['failed_isolated']):>9} {r['closed_count']:>7}"
            f" {r['t1']:>7.3f} {r['t2']:>7.3f} {r['t3']:>7.3f}"
        )

    # Extrapolation: a real board fetch costs ~1-3s wall time (network + retry budget), on top
    # of the DB-only time measured above. Boards sync sequentially, one worker, no concurrency
    # (ADR-013 §7), so wall time is dominated by N * per-board latency, not DB work.
    print("\n=== Extrapolated wall time with real network latency (~1-3 s/board) ===")
    for n in results:
        low, high = n * 1 + results[n]["t2"], n * 3 + results[n]["t2"]
        print(f"  N={n:<3} -> {low:6.1f}s - {high:6.1f}s (plus feed sync)")
    print(
        f"\nRecommended operational cap: keep enabled ATS sources well under the point where"
        f" N * 3s approaches the 20-minute budget, i.e. N <~ {int(20 * 60 / 3 * 0.5)} with a"
        f" safety margin for retries and slow boards. See docs/operations.md."
    )


if __name__ == "__main__":
    main()
