# ADR-011: Private Profile Source Ingestion and Review

Status: Accepted

Date: 2026-09-30

## Context

Milestone 4 scores fit from a Match Profile the owner types by hand ([ADR-010](ADR-010-fit-scoring-v1.md)). Most of that information is already in the owner's résumé. [ADR-005](ADR-005-source-and-profile-ingestion-strategy.md) requires provenance-aware profile ingestion: an imported fact is a candidate until the owner confirms it. [ADR-006](ADR-006-core-domain-persistence-model.md) reserved `profile_sources` and `profile_facts` for this and keeps hard eligibility on canonical `profiles` columns only. [ADR-003](ADR-003-ai-as-enrichment.md) and [ADR-004](ADR-004-technology-stack.md) rule out AI as a requirement, paid services, and new infrastructure. Render's filesystem isn't durable ([ADR-009](ADR-009-hosted-deployment-architecture.md)), and the repository is public.

## Decision

### 1. Pipeline

```text
upload (≤ 2 MB) → content sniffing → immutable artifact (PostgreSQL) → deterministic parser
  → pending candidate facts → owner review (accept / edit + accept / reject, in batches)
  → accepted facts → Fit Scoring v1 (one catalog pass per review batch)
```

No AI, OCR, embeddings, queues, background workers, schedulers, or new services. Upload, parsing, and review run synchronously in the request, like the Milestone 4 catalog pass.

### 2. Formats and limits

| | |
|---|---|
| Accepted | Plain text (`text/plain`): strict UTF-8 (a BOM is allowed), no NUL bytes. Text-based PDF (`application/pdf`): starts with `%PDF-`, not encrypted |
| Type detection | By content only. The filename and the client's `Content-Type` are never trusted |
| Upload size | 2 MB. Vercel limits proxied request bodies to about 4.5 MB, and the whole file is held in memory on a 512 MB Render instance. `Content-Length` is checked first, then the body is read in chunks and abandoned past the limit (`413`) |
| PDF bounds | First 20 pages only; extraction stops at 100,000 characters; any exception from the PDF library is an unreadable file (`422`). A PDF with no extractable text (scanned) is `422`: OCR isn't supported |
| Candidates | At most 200 per source |
| Not supported | DOCX (zip and XML parsing add attack surface for little gain; export to PDF instead), images, OCR |

Dependencies: `pypdf` (BSD-3-Clause, pure Python, `>=6.19`: every published advisory is fixed by 6.16.1) and `python-multipart` (Apache-2.0, FastAPI's form parser, `>=0.0.32`: every published advisory is fixed by 0.0.31). Both are installed from PyPI; no code is copied.

### 3. Artifact storage

The original bytes go into `profile_source_artifacts` (`profile_source_id` primary key and foreign key, `ON DELETE CASCADE`; `content` BYTEA), never onto disk, Git, or object storage. They're written once and never updated. A separate table keeps file content out of every query that lists sources. At 2 MB per file, even 50 uploads (100 MB) fit in Neon Free's 0.5 GB. `profile_sources` gains `content_type`, `byte_size`, `parser_name`, and `parser_version`; `content_sha256` and `original_filename` already exist. `storage_ref` stays unused.

Deleting a source removes its row, its artifact, and its facts in one transaction. PostgreSQL frees the space when autovacuum runs, so deletion is logical, not an immediate wipe of the disk pages. That's acceptable for a single-tenant database the owner controls.

### 4. Identity, filenames, and downloads

- SHA-256 of the bytes. `UNIQUE (profile_id, content_sha256)`: uploading the same file again is `409` (re-parse the existing source instead).
- The filename is only a label: basename after the last `/` or `\`, control characters removed, at most 255 characters, `NULL` when nothing is left. It never names a storage location.
- `GET /api/profile/sources/{id}/file` returns the original bytes with the stored allowlisted type, `Content-Disposition: attachment` (RFC 6266 / 5987 `filename*`), `X-Content-Type-Options: nosniff`, and `Cache-Control: no-store`. Nothing else ever returns file content or extracted text.

### 5. Review state

`profile_facts.review_state` is `pending`, `accepted`, or `rejected`. It's NOT NULL with **no default**, so every code path that creates a fact has to choose one.

| Fact | `review_state` | `verified_by_user` |
|---|---|---|
| Manual (Match Profile) | `accepted` | `true` |
| New parser candidate | `pending` | `false` |
| Accepted by the owner (value possibly edited) | `accepted` | `true` |
| Rejected by the owner | `rejected` | `false` |

CHECK `ck_profile_facts_review_state_matches_verified`: a non-manual fact is `accepted` exactly when `verified_by_user`. **Fit reads only `accepted` facts** (`fit_profile_input`). The migration backfills `accepted` for facts that the Milestone 4 filter already used (manual or verified) and `pending` for everything else, so upgrading changes no fit input and no fingerprint.

Accepted facts can be rejected later, and rejected ones accepted. There is no way back to `pending`.

### 6. What the parser may produce

Categories: `skill`, `course`, `project`, `research`, `experience`, `activity`, `award`, `education`. Values have the Match Profile shapes: `{"name"}` for skills (≤ 100 characters) and courses (≤ 150), and `{"name", "description"}` (name ≤ 150, description ≤ 2,000 or `null`) for the rest. Only skills, courses, projects, and research affect fit v1 ([scoring.md](../scoring.md)); the rest are kept as information.

The parser never writes `profiles`. Date of birth, citizenship, work authorization, and the education timeline stay canonical fields that only the owner edits on the Eligibility Profile. An accepted `education` fact changes nothing about eligibility.

Parser facts: `source_kind = resume`, `extraction_method = deterministic_parser`, `extractor_name`/`extractor_version` = the parser's name and version, `confidence = NULL`, `fact_key = "resume.NNN"` (position in the parser's output).

### 7. Deterministic parsing

`app.profile.resume_parser` (`PARSER_NAME = "resume-sections"`, `PARSER_VERSION = "1"`) is pure: bytes in, candidates out, no I/O. It finds section headings by a fixed alias table (Skills, Technical Skills, Technologies; Relevant Coursework, Coursework; Projects; Research; Experience, Work Experience; Activities, Leadership; Awards, Honors; Education), splits skill and course lists on commas, semicolons, pipes, and bullets, and turns other sections into entries (a name line plus description lines). Same bytes, same version → same output, in the same order. Candidates are deduplicated within a document (case-insensitive by category and name).

Upload and re-parse skip a candidate whose category and name (case-insensitive) match a fact the profile has already accepted, from any source, and one that this source already accepted or rejected. Re-parsing (`POST …/reparse`) replaces only this source's pending facts, so it never duplicates or resurrects anything the owner decided.

### 8. API

All under the private router (`require_owner`: session required, CSRF on every unsafe method). Errors never echo file content or extracted text.

| Method and path | Purpose |
|---|---|
| `GET /api/profile/sources` | List sources with review counts (no facts, no content) |
| `POST /api/profile/sources` | Multipart field `file`. `201` source with its facts. `409` duplicate, `413` too large, `415` unsupported type, `422` unreadable or no text. Creates the profile row if none exists |
| `GET /api/profile/sources/{id}` | One source with its facts |
| `GET /api/profile/sources/{id}/file` | Download the original (§4) |
| `POST /api/profile/sources/{id}/review` | `{"accept": [{"id", "value"?}], "reject": [id]}`: one batch, one transaction, **at most one catalog pass**, and only when an accepted fit fact was added, changed, or removed |
| `POST /api/profile/sources/{id}/reparse` | Re-run the current parser on the stored bytes (§7). No catalog pass: pending facts don't score |
| `DELETE /api/profile/sources/{id}` | Delete the source, artifact, and its facts. One catalog pass if it had accepted fit facts. Manual Match Profile facts are never touched |

### 9. Frontend

The Profile area gets a third tab, **Sources**, next to Eligibility Profile and Match Profile. It uploads a file, lists sources (file name, type, size, parser and version, counts), and reviews candidates grouped by category with Pending / Accepted / Rejected and Imported labels, edit before accepting, select-all, and one **Apply** per batch that reports the catalog pass. It states that imported facts don't affect matching until accepted. It never renders file content as HTML or shows raw JSON.

## Consequences

- The owner fills most of the Match Profile from a résumé in a few clicks, and nothing imported is trusted until accepted.
- File bytes are stored in the database: small, private, and backed up with it, at the cost of database space (bounded by the 2 MB limit).
- A PDF parse runs in the request. Page, character, and size limits bound it, but a hostile PDF can still use CPU until the limits stop it; single-user access limits the exposure.
- Lexical, heading-based parsing misses unusual layouts. The owner can still type facts into the Match Profile.
- Accepted imported facts appear under Sources, not in the Match Profile editor; both feed fit.

## Alternatives Considered

- **Render disk or object storage** for artifacts: not durable, or a new service or public bucket.
- **AI or LLM parsing:** optional enrichment later ([ADR-003](ADR-003-ai-as-enrichment.md)), never required.
- **DOCX in Milestone 5:** deferred (zip-bomb and XML-entity hardening).
- **Review without a stored state** (only `verified_by_user`): can't tell "not reviewed yet" from "rejected", so a re-parse would resurrect rejected facts.
- **A catalog pass per fact:** up to N × 1,055 evaluations; one pass per batch instead.
