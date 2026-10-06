# ADR-022: Large-Response Source Architecture (Greenhouse)

Status: Proposed (on the feature branch `feature/m12-large-board-greenhouse`; subject to owner review)

Date: 2026-10-06

## Context

`GET boards-api.greenhouse.io/v1/boards/<board>/jobs?content=true` returns every job with its full HTML, so a board of ~2,500 jobs is ~30 MB. `greenhouse:andurilindustries` (2,457 jobs) failed in production with "The source response is too large" and was disabled; `greenhouse:spacex` (2,665) fails identically. The 20 MiB per-request cap (`http.MAX_BYTES`) is a security boundary ([ADR-008 §10](ADR-008-opportunity-ingestion-and-deduplication.md)): raising it globally, or streaming without a bound, would let any provider response consume unbounded memory.

Measured 2026-10-06 against the public API: `/jobs` without `content` is ~2.5 MB for both boards and carries `meta.total` (equal to the number of jobs); `/jobs/<id>` returns one job with its `content` (~10 KB). A live run of the design below fetched Anduril in 26 requests / 3.1 MB / 11.6 s and SpaceX in 16 requests / 2.7 MB / 7.8 s.

## Decision

Greenhouse becomes a multi-request adapter (`collect`, [ADR-014 §2](ADR-014-structured-source-expansion-and-program-registry.md)), modelled on SmartRecruiters. The per-request cap is unchanged.

1. **The complete snapshot is the content-free list.** The first request is always `/jobs` (no `content`). `meta.total` must equal the number of jobs (`incomplete_snapshot` otherwise); more than `MAX_JOBS` (10,000) fails (`too_many_jobs`); a duplicate job id fails (`inconsistent_listing`); a list that is truncated, not JSON, the wrong shape, or over the cap is a fetch/validation failure. Any of these means **no snapshot**, so the pipeline fails the run and closes nothing.
2. **The path is chosen by the stored job count, deterministically.** With at most `LARGE_BOARD_JOBS` (500) stored records the adapter makes one conditional `?content=true` request (ETag/Last-Modified from the source; a 304 is `no_change` and the stored validators are kept), exactly the pre-existing behaviour (observed <= ~6 MiB for such boards). Only if that request fails with `response_too_large` or the body lists more than 500 jobs does it switch to the list-first mode below, so an oversized download happens at most once per newly large board (afterwards the stored count is large). With more than 500 stored records it goes straight to the content-free list. Any other content failure propagates.
3. **Detail mode** requests `/jobs/<id>` only for jobs whose title passes `is_internship_title`, whatever the source scope. Scope `all` on a large board therefore still imports every posting, but only internship-titled ones get a description; the rest have none (they can't produce requirement suggestions). That is the deliberate trade-off: scope `all` plus 2,500 detail requests per run is neither polite nor within a sync's time budget, and non-internship text isn't used for fit of an internship finder.
4. **Reuse.** A stored raw item with `content` is reused without a request while the `updated_at` the content belongs to equals the listed one. That is a separate field, `_content_updated_at`, written only when a detail succeeds and carried forward with reused text (falling back to the item's `updated_at` for items stored before it existed): copying the new `updated_at` onto old text would make a failed refetch look current forever. A job whose detail isn't fetched this run (budget, failure, deferral) keeps its stored `content` and the old stamp, so the next run retries it, or has none. It is still in the snapshot, so it is never closed or dropped, and no `ItemError` is raised (unlike SmartRecruiters, where an item error makes the run `partial`): descriptions are enrichment, completeness is the list.
5. **Bounds**, all constants in `adapters/greenhouse.py` except the first:

   | Bound | Value | Why |
   |---|---|---|
   | Per-request bytes (`http.MAX_BYTES`) | 20 MiB, **unchanged**, applied to decoded bytes | Security boundary; a gzip bomb is capped because `iter_bytes()` yields decoded chunks |
   | Per-detail bytes (`MAX_DETAIL_BYTES`, via the new `fetch_json(max_bytes=)`, which can only tighten) | 1 MiB | Observed ~10 KiB |
   | Jobs per board (`MAX_JOBS`) | 10,000 | A 10,000-job content-free list is ~10 MiB, under the cap |
   | Detail attempts per run (`MAX_DETAIL_FETCHES`) | 100, failed attempts included | Observed 15-38 internship titles; the rest retried next run |
   | Cumulative detail bytes per run (`MAX_DETAIL_TOTAL_BYTES`) | 8 MiB of successful responses | Stops fetching, snapshot stays complete (`Fetched.size` carries the decoded size). A failed read isn't counted but is capped at 1 MiB, and failures are capped (next row), so the worst case is bounded |
   | Detail phase deadline (`MAX_DETAIL_SECONDS`, passed to `fetch_json(deadline=)`) | 120 s | Checked before every attempt and before every retry sleep (a sleep that would pass it is refused). Not a hard wall: a server dripping bytes can hold one request open while each read stays inside the 20 s read timeout |
   | Detail failures (`MAX_DETAIL_FAILURES`) | 5 per run in total, never reset by a success | A failing provider isn't hit 100 times at 3 attempts each |
   | Timeouts, redirects, attempts | 5 s connect / 20 s read, 3, 3 | Existing, unchanged |

## Alternatives considered

- **Raise `MAX_BYTES` (to ~40 MiB) or stream-parse the content list.** Rejected: weakens the boundary for every provider, and a streaming parser is more code than the documented per-job endpoint.
- **Catch `response_too_large` and fall back.** Rejected: downloads 20 MiB first and makes behaviour depend on a failure path.
- **Detail for every job.** Rejected: ~2,500 requests per run.
- **List first for every board.** Rejected after review: it cost every small board an extra request per run and its conditional requests (a 304 became a full run).

## Consequences

- A small board is unchanged: one conditional request, `no_change` on 304. A board that newly crosses 500 jobs pays one oversized download (or one 500+ job content list) on its first run, then lists first. A large board has no validators and always runs in full (list plus any due details).
- A collect adapter may return a `Fetched` so the pipeline keeps validators; plain payloads (SmartRecruiters) carry none, as before.
- A large board's non-internship jobs have no description until (and unless) their title matches; existing stored text is kept.
- Newly imported internships on a large board get text within one to a few runs (at most 100 per run).
- A job edited in place changes `updated_at` and is refetched; a stale description persists only while its detail fetch keeps failing, and each run retries it.
- Anduril and SpaceX can be activated after the owner reviews the first sync; no catalog or schema change, no migration.
