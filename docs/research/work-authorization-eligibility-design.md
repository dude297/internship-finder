# Work authorization eligibility: design

> **Research only (non-normative).** Date: 2026-10-06. Last verified: 2026-10-06.
> Used by / superseded by: partly adopted by [ADR-026](../decisions/ADR-026-work-authorization-eligibility.md) (Milestone 15): seven boolean profile columns and five fixed-label rules instead of the per-country JSONB, dates, and clearance levels below, which stay deferred.

## Problem

`work_authorization` requirements are stored but always evaluate to `needs_verification` (ELIG-REQ-001, no rule). The profile stores `work_authorizations` (a list of country codes) but no v1 rule reads it, and a single list cannot say what employers actually ask. Postings use six different questions that look alike and are not:

| Posting wording (examples) | What is really asked |
|---|---|
| "Must be authorized to work in the U.S." | Authorized to work **now / at program start**, any basis |
| "We do not sponsor visas" / "no sponsorship now or in the future" | The candidate must **never need** employer sponsorship |
| "Must not require sponsorship at start" | No sponsorship needed **at start** (a later need, e.g. OPT to H-1B, may be allowed) |
| "U.S. citizens only" | Citizenship (already `citizenship`, ADR-012) |
| "Citizens or permanent residents" | Citizenship **or** permanent residency |
| "U.S. person" (ITAR/EAR) | Citizen, permanent resident, or protected individual (asylee/refugee); **not** the same as work authorization |
| "Active Secret / TS clearance", "eligible to obtain a clearance" | Clearance status; usually implies U.S. citizenship |

The extractor v2 already splits these as *suggestions* ([requirement-extractor-v2.md](requirement-extractor-v2.md)); the profile and rules cannot yet receive them. Conflating any two produces a wrong "eligible" or a wrong "ineligible", the worst failures this product can have.

## Hard constraints

- Eligibility and fit stay separate (ADR-001); a pending suggestion never affects eligibility (ADR-012); AI is never authoritative (ADR-003). Only owner-accepted canonical requirements are evaluated, and only against owner-entered profile facts.
- Nothing is inferred across categories. "Citizen of country X" is not the same as "authorized to work in X"; a permanent resident is authorized but not a citizen; an F-1 student on OPT is authorized now but will need sponsorship later; a U.S. person is a legal term of art that includes some people who are neither citizens nor permanent residents.
- Unknown stays unknown. `null`/unanswered is `needs_verification`, never "no".
- No profile fields are ever published (public repo): examples here are synthetic.

## Profile representation

Keep the existing `citizenships` (ISO list) and add one structured, per-country object instead of reusing `work_authorizations`. Proposed `profile_work_authorization` JSONB on `profiles`, or a small child table if per-country rows read more simply (a JSONB document is the shorter path and matches `citizenships`; decide in the ADR). Each entry is for one country `country` (ISO alpha-2) and carries independent, individually nullable answers:

| Field | Values | Meaning |
|---|---|---|
| `authorized_now` | `yes` / `no` / null | Legally allowed to work in `country`, any basis (citizenship, PR, EAD, visa category). The basis is not stored: citizenship and permanent residency each have their own single source of truth. |
| `as_of` | date | The day the owner last confirmed these answers. Rules use it, never the clock. |
| `authorization_expires_on` | date or null | When the current authorization ends (for example an OPT end date). Null means no known end. |
| `needs_sponsorship_now` | `yes` / `no` / null | Would need an employer to sponsor to work at the start. |
| `needs_sponsorship_future` | `yes` / `no` / null | Will need sponsorship later (for example a student who will need an H-1B). Independent of `needs_sponsorship_now`. |
| `permanent_resident` | `yes` / `no` / null | Holds permanent residency in `country`. |
| `us_person` | `yes` / `no` / null | U.S. person for export-control purposes (U.S. only). **Always asked explicitly**, never derived. |
| `clearance` | `none` / `active_confidential` / `active_secret` / `active_top_secret` / `active_ts_sci` / null | Highest clearance currently held. Never derived from citizenship. |
| `can_obtain_clearance` | `yes` / `no` / null | The owner's own answer to "eligible to obtain a clearance". Never derived from citizenship or from `clearance`. |

`citizenships` is unchanged and remains the only source for citizenship rules. `null` means unanswered (rules give `needs_verification`); `[]` means the owner answered "none" (a rule may then conclude "not a citizen"). `permanent_resident` is likewise the only source for residency. The existing `work_authorizations` country list is migrated, not deleted (see below).

Each field is optional and the UI states what is unanswered. A "this profile is incomplete for work-authorization rules" prompt is shown only when a canonical work-authorization requirement exists for the opportunity, not as onboarding.

## Requirement shapes

Replace the free-form `{"description": ...}` for new accepted requirements with a typed value (`WorkAuthorizationValue`, `extra="forbid"`, like the other three). Existing free-form values remain valid and keep evaluating to `needs_verification` (unchanged behavior, no backfill risk).

```
{"country": "US", "kind": "<kind>", "timing": "program_start" | "application" | "any_time"}
kind ∈ authorized_now | no_sponsorship_now | no_sponsorship_ever | permanent_resident_or_citizen | us_person | clearance_active | clearance_eligible
clearance_level: required for the two clearance kinds
```

`citizenship` stays its own requirement type; "U.S. citizens only" never becomes a work-authorization kind. The owner picks `kind` when accepting a suggestion; the extractor may propose a kind but a proposal is still pending.

## Deterministic rule outcomes

Rule ID `ELIG-WA-001` family; precedence stays ineligible > needs_verification > eligible. "Unknown" always means `needs_verification` with the reason naming the unanswered field.

| `kind` | eligible when | ineligible when | otherwise |
|---|---|---|---|
| `authorized_now` (timing `program_start` / `application`) | `authorized_now = yes` and `authorization_expires_on` is null or after the reference date | `authorized_now = no` **and** the reference date is on or before `as_of` (profile-provable: the answer describes that day) | `needs_verification`: unanswered; `authorized_now = no` with a later reference date (it may change before then); or `authorization_expires_on` on or before the reference date (may be extended) |
| `authorized_now` (timing `any_time`, throughout) | `authorized_now = yes` and `authorization_expires_on` is null | never | `needs_verification` for everything else, including a known expiry, because the posting's span isn't known |
| `no_sponsorship_now` | `needs_sponsorship_now = no` | `needs_sponsorship_now = yes` | `needs_verification` |
| `no_sponsorship_ever` | `needs_sponsorship_now = no` **and** `needs_sponsorship_future = no` | either is `yes` | `needs_verification` if either is unanswered and none is `yes` |
| `permanent_resident_or_citizen` | `permanent_resident = yes`, or the country is in `citizenships` | `permanent_resident = no` and `citizenships` is answered (`[]` or a list) without the country | `needs_verification` when `permanent_resident` is null or `citizenships` is null |
| `us_person` | `us_person = yes` (owner's explicit answer) | `us_person = no` (owner's explicit answer) | `needs_verification` when null. **Never** derived from citizenship, permanent residency, or anything else: the term includes categories the profile cannot otherwise express |
| `clearance_active` (level L) | `clearance` is at or above L in the fixed order confidential < secret < top secret < TS/SCI | `clearance` is `none` or below L and the reference date is on or before `as_of` | `needs_verification` when null, or when a later reference date could allow a grant |
| `clearance_eligible` | `clearance` is any active level, or `can_obtain_clearance = yes` | never: eligibility to obtain depends on adjudication and usually citizenship, which the profile can't prove | `needs_verification` (including `clearance = none` and `can_obtain_clearance` null or `no`; the reason says so) |

Never inferred: authorization from citizenship (the owner answers `authorized_now` per country), sponsorship need from visa type, clearance from citizenship, `us_person` from anything.

## What stays `needs_verification`

- Any requirement whose value does not match `WorkAuthorizationValue` (legacy free-form text, `other`).
- Country other than the profile's answered countries.
- Wording the extractor cannot classify to a single `kind` (for example "must be legally able to work, sponsorship considered case by case"): the owner records it as `other`; it is never mapped to a strict kind.
- Eligibility to obtain a clearance, sponsorship exceptions ("we sponsor for exceptional candidates"), and any requirement tied to a date the posting does not state.
- Anything with a missing profile answer. The reason names the field, and the UI links to it.

## Time interaction

Rules never read today. Expiry and confirmation are explicit profile inputs (`authorization_expires_on`, `as_of`) compared with the requirement's reference date, so an evaluation stays a pure function of the profile and the opportunity, and no re-evaluation trigger is needed beyond a profile change or a version bump ([ADR-018](../decisions/ADR-018-evaluation-staleness.md)). The new inputs must be part of the profile fingerprint inputs when implemented.

## Migration and backfill plan

1. **ADR first** (profile shape, requirement value, rule table above), then one Alembic migration: add `profiles.work_authorization` JSONB (nullable, default null). No change to `citizenships`. No change to existing `opportunity_requirements` rows.
2. **No automatic backfill.** The old `work_authorizations` list is ambiguous (authorized now? in future? citizen?). Treat it as a hint: the profile form pre-fills `authorized_now = yes` as an *unconfirmed suggestion* the owner confirms per country; nothing is written until the owner saves. The old column stays, unread by rules, until a later migration removes it after confirmation (never in the same release).
3. **Rules ship dark first:** `RULES_VERSION` bump to `v2` with the new rule, deployed with no profile answers, so every work-authorization result stays `needs_verification` (unchanged). The version bump re-evaluates the catalog once through the existing pass ([ADR-018](../decisions/ADR-018-evaluation-staleness.md)), appending rows; nothing changes for the owner until they answer.
4. **Requirement migration is opt-in:** existing accepted `work_authorization` requirements keep their free-form value. The review screen offers "convert to a structured requirement" per row; unconverted rows keep evaluating to `needs_verification`.
5. Tests before release: synthetic profiles for each row of the table, the "never conflated" cases (citizen but sponsorship unknown; permanent resident asked for U.S. person; OPT student for "no sponsorship ever"; clearance asked of a citizen with no clearance answer), and a regression that old free-form requirements still give `needs_verification`.

## Risks

- **Wrong "ineligible" from an ambiguous posting.** Mitigation: the owner chooses `kind` at acceptance; unclassifiable wording stays `other`.
- **Wrong "eligible" from a stale authorization.** Mitigation: `authorization_expires_on`, plus the staleness epoch. A reviewer-visible reason shows the expiry used.
- **Legal-term drift (U.S. person, clearance eligibility).** These are explicit owner answers with no derivation; the UI explains the term once and links to the posting.
- **Sensitive data.** Immigration status is sensitive. Stored only in the single owner's profile, never in logs, fixtures, screenshots, or the public repo; tests use synthetic values; not sent to any AI call (ADR-003).
- **Scope creep into fit.** Sponsorship friendliness of an employer (the feed's H-1B/sponsorship tags) is a fit or informational signal, never a requirement or an eligibility input (ADR-001).
- **Free-form legacy requirements** never silently change meaning: they stay `needs_verification`.
