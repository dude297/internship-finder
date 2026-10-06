# ADR-026: Work-Authorization Eligibility (Rules v2)

Status: Accepted (Milestone 15, on the feature branch; subject to owner review)

Date: 2026-10-06

## Context

Accepted `work_authorization` requirements, and the `other` requirements for "citizen or permanent resident", "U.S. person (export control)" and "security clearance", always evaluated to `needs_verification` (ELIG-REQ-001, rules v1). The profile held only a country list (`work_authorizations`) that no rule read and that cannot say what postings ask: authorized now, needs sponsorship now, may need it later, citizen, permanent resident, U.S. person and clearance are different questions. Conflating any two gives a wrong "eligible" or "ineligible", the worst failure here. The [design note](../research/work-authorization-eligibility-design.md) proposed a per-country JSONB document with dates and clearance levels. Reviewed critically, that is more than the extractor's output can use today.

## Decision

### 1. Seven nullable boolean columns on `profiles`

`work_authorized_us`, `needs_sponsorship_now`, `needs_sponsorship_future`, `us_citizen`, `us_permanent_resident`, `us_person_export_control`, `active_security_clearance`. `NULL` is "not provided" and never means "no". Each is the owner's own explicit answer. **No column is ever derived from another** (a citizen is not assumed authorized; no answer implies "U.S. person"). The API takes strict `true` / `false` / `null` (a string or number is a `422`). Plain columns beat the design note's JSONB: the set is small and fixed, the types are checked by the database and the schema, and the rules read named fields. Migration `c8d2f4a6b0e3` (additive, no backfill).

Deliberately left out of the design note's model: per-country entries (the extractor only emits U.S. labels), `as_of` / expiry dates (they would put a time input into the fingerprint, [ADR-018](ADR-018-evaluation-staleness.md) §1), clearance level, and "can obtain a clearance". Each can be added later as another additive column with its own rule and version.

The old `work_authorizations` country list stays stored and unread (unchanged). It is never converted: it is ambiguous.

### 2. Requirement semantics: the extractor's fixed labels

No new requirement type or column. The extractor ([ADR-012](ADR-012-opportunity-requirement-intelligence-and-automation.md)) already emits fixed-label descriptions, and an accepted suggestion copies that value. A requirement has explicit semantics only if its `description` is exactly one of these labels; any other wording, including an owner-edited one, has none and stays `needs_verification` (ELIG-REQ-001). Extractor `requirements-rules` v3 is unchanged (no precision change, no version bump). `tests/test_work_authorization.py` asserts the label map equals the extractor constants.

| Requirement (type, fixed description) | Rule |
|---|---|
| `work_authorization`: "Authorized to work in the United States" | ELIG-WA-001 |
| `work_authorization`: "Authorized to work in the United States without sponsorship" | ELIG-WA-002 |
| `other`: "U.S. citizen or permanent resident" | ELIG-WA-003 |
| `other`: "U.S. person (export control)" | ELIG-WA-004 |
| `other`: "Security clearance required" | ELIG-WA-005 |

"U.S. citizens only" stays a `citizenship` requirement evaluated by ELIG-CIT-001 against the profile's `citizenships` list only. The `us_citizen` answer is read by ELIG-WA-003 only. The two sources are not reconciled (no inference), so a user who answers `us_citizen` but leaves `citizenships` empty still gets `needs_verification` for a citizenship-only posting.

### 3. Rules (each rule reads only the facts it names)

| Rule | Eligible | Ineligible | Otherwise `needs_verification` |
|---|---|---|---|
| ELIG-WA-001 (`work_authorized_us`) | yes | never | no (it describes today and the requirement applies later), not provided |
| ELIG-WA-002 (`work_authorized_us`, `needs_sponsorship_now`, `needs_sponsorship_future`) | authorized yes, need now no, need later no | need now yes | anything else (the posting may mean "now" or "ever") |
| ELIG-WA-003 (`us_citizen`, `us_permanent_resident`) | either yes | both no | one answered no and the other not provided, or neither provided |
| ELIG-WA-004 (`us_person_export_control`) | yes | no | not provided |
| ELIG-WA-005 (`active_security_clearance`) | yes (held) | never ("required" may allow obtaining one) | no, not provided |

Reasons are plain language built from the owner's own answers. Precedence is unchanged (ineligible > needs_verification > eligible); ELIG-REQ-000 is unchanged.

### 4. Version and re-evaluation

`RULES_VERSION` `v1` to `v2`; the profile inputs (`ProfileInput`) gain the seven facts, so they are part of the fingerprint and a changed answer re-evaluates opportunities on profile save. Release step: after deploy, `python -m app.cli reevaluate --dry-run` then `reevaluate` ([ADR-018](ADR-018-evaluation-staleness.md) §3). With every answer not provided, results are unchanged apart from the version and the new rule IDs on matching requirements (still `needs_verification`).

### 5. Privacy

Immigration status is sensitive. It is stored only on the single owner's profile, behind the authenticated API; the landing page and the public API never carry it; it is not sent to any AI call ([ADR-003](ADR-003-ai-as-enrichment.md)), not logged, and never committed (tests use synthetic values). The profile form words each question plainly, explains "U.S. person" neutrally (a citizen, a permanent resident, or a protected individual), and defaults every answer to "Prefer not to say / not provided".

## Alternatives considered

- **Per-country JSONB with dates and clearance levels** (the design note): richer, but the extractor emits only U.S. labels, dates need fingerprint inputs, and ineligibility from a dated "no" cannot be justified without posting-date semantics we do not extract. Deferred.
- **Add a `kind` key to requirement values and bump the extractor:** explicit, but changes stored suggestion identities and needs a rescan for no new capability; the fixed labels already are the kinds.
- **Derive citizen to authorized, or a U.S. person from citizen or permanent resident:** rejected: wrong for protected individuals, and a hidden inference is the failure this ADR exists to prevent.

## Consequences

- Owners can record the facts; accepted requirements with the five fixed labels now evaluate, and only when the matching answer was given.
- Free-text or edited work-authorization requirements stay `needs_verification`.
- Known gaps: no per-country answers, no expiry, no clearance level; "no" answers for WA-001 and WA-005 never produce `ineligible`; citizenship-only requirements still read `citizenships`.
