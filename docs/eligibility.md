# Eligibility

Eligibility is **separate from fit** ([ADR-001](decisions/ADR-001-separate-eligibility-and-fit.md)). Eligibility answers "can the user apply and participate?" Fit answers "how good a match is it?" A high fit score never overrides explicit ineligibility.

## Statuses

| Status | Meaning |
|---|---|
| `eligible` | No rule excludes the user and nothing requires verification |
| `ineligible` | At least one rule explicitly excludes the user |
| `needs_verification` | A requirement exists that the profile or posting can't settle |

Precedence when combining rule results: `ineligible` > `needs_verification` > `eligible`.

## Requirement Assessment

An empty requirement list is ambiguous: the opportunity may truly have no hard requirements, or nobody has extracted them yet. So each opportunity stores `requirements_assessment_status` ([data-model.md](data-model.md#opportunities)). It's never inferred from the number of requirement rows.

| Assessment | Meaning | Effect on the final status |
|---|---|---|
| `unassessed` (default) | Hard requirements haven't been (sufficiently) assessed | At least `needs_verification` |
| `partial` | Some requirements are represented; others may exist | At least `needs_verification`, even if every known rule passes |
| `complete` | Every hard requirement is represented | None: normal precedence over the requirement rules |

This is applied as a rule result (ELIG-REQ-000), so the reason is stored with the evaluation and normal precedence does the combining. Known requirements are always evaluated, whatever the assessment: an explicit `ineligible` stays `ineligible`, because a known failure is definitive. Only `complete` with zero requirements, or `complete` with all requirements passing, gives `eligible`.

| Assessment | Requirement results | Final |
|---|---|---|
| `unassessed` | none | `needs_verification` |
| `partial` | all known requirements pass | `needs_verification` |
| `partial` | a known citizenship mismatch (`ineligible`) | `ineligible` |
| `complete` | none | `eligible` |
| `complete` | all pass | `eligible` |
| `complete` | one `needs_verification` | `needs_verification` |

Rules should be deterministic. AI may help **extract** requirements from postings, but it doesn't decide eligibility ([ADR-003](decisions/ADR-003-ai-as-enrichment.md)). Each evaluation records the rules version, the ELIG-REQ-000 assessment result, and one result per requirement (rule ID, status, reason, reference date, projected-status flag, structured details). See [data-model.md](data-model.md#opportunity_evaluations).

Implementation: `backend/app/opportunities/eligibility/`. The single entry point is `evaluate_eligibility(profile, opportunity, requirements)`. Persisting is `app.repositories.evaluate_and_save`.

### When evaluations run

- Creating or updating an opportunity (by hand or by a source sync) appends an evaluation if a profile exists **and** the eligibility inputs changed since the latest evaluation. The inputs are compared by a SHA-256 fingerprint of the rules version, the canonical profile inputs, the opportunity's reference dates and assessment status, and its requirements ([ADR-008 §9](decisions/ADR-008-opportunity-ingestion-and-deduplication.md#9-evaluation-without-history-explosion)), so a title-only edit or an unchanged sync adds nothing. Without a profile, nothing is evaluated and the UI says so. An evaluation is never faked.
- Imported opportunities start `unassessed` (ELIG-REQ-000 → at least `needs_verification`). Source fields such as the discovery feed's sponsorship, H-1B, or skill tags never become requirements. The owner records requirements with **Review requirements** (the regular editor) and marks the assessment `partial` or `complete`; later syncs never overwrite that review.
- Saving the profile re-evaluates every opportunity when an input the rules read changed (the fields of `ProfileInput`: the education timeline, date of birth, and citizenships). Changing only the grade, location, or work authorizations doesn't, because no v1 rule reads them.
- A rules or scoring version bump makes every evaluation stale ([ADR-018](decisions/ADR-018-evaluation-staleness.md)): both versions are part of the fingerprints. `python -m app.cli reevaluate` runs the catalog pass and appends the new rows (a release step). Time passing never makes an evaluation stale: rules resolve the education status and age at each requirement's reference date, never at today, so an evaluation is a pure function of the profile and the opportunity's dates.
- `POST /api/opportunities/{id}/evaluate` appends one on demand.
- Application tracking never affects eligibility.

Every evaluation appends history; nothing is overwritten. The rules (and `v1`) are unchanged since Milestone 1.

### How the UI presents results

The UI shows `needs_verification` as its own state ("Needs verification") and never folds it into eligible. Opportunities without an evaluation show "Not evaluated". Each rule result gets a plain-language line (e.g. "Education — Eligible: based on your projected status on …: incoming undergraduate") rephrased from the stored status and details, with the stored reason and rule ID under "More detail". When the evaluation's `depends_on_projected_status` is true, the UI shows "This result depends on expected future education dates." with the resolver's explanation.

### Requirement suggestions (since Milestone 6)

Imported and manual postings get deterministic requirement **suggestions** (`requirements-rules` v2 since Milestone 8.1, [ADR-012](decisions/ADR-012-opportunity-requirement-intelligence-and-automation.md)). They live in `opportunity_requirement_candidates` and **never affect eligibility**: the engine still reads only `opportunity_requirements` and `requirements_assessment_status`. Accepting a suggestion (optionally edited) creates a canonical requirement with `extraction_method = deterministic_parser`; that, not the suggestion, is what the rules evaluate. The extractor collapses runs of spaces/tabs before splitting sentences (linear time on any input; a suggestion's wording and the proposals themselves are unchanged).

- Extraction never changes `requirements_assessment_status`. Accepting the first requirement while `unassessed` moves it to `partial`. Only the owner's explicit choice makes it `complete` (zero requirements allowed). Rejecting every suggestion never implies `complete`.
- If a sync later changes a reviewed posting's text, a `complete` assessment is downgraded (to `partial`, or `unassessed` if no canonical requirement remains), the opportunity is flagged "Posting changed since requirement review", accepted requirements are kept, and the opportunity is re-evaluated.
- An accepted work-authorization suggestion evaluates to `needs_verification` (ELIG-REQ-001) until a work-authorization rule exists (design: [work-authorization-eligibility-design.md](research/work-authorization-eligibility-design.md); not implemented).
- Suggestions need posting text: the discovery feed has no description, so feed-only postings stay `unassessed` (`needs_verification`) until the owner enters requirements or a board source with descriptions supplies text. Production figures: [deployment.md](deployment.md), [CHANGELOG.md](../CHANGELOG.md).

## Time-Aware Evaluation

The user's status changes over time. For example, a high-school senior is expected to become an undergraduate after graduation ([ADR-005](decisions/ADR-005-source-and-profile-ingestion-strategy.md)). Rules evaluate the user's **projected status at the date the requirement applies**, not only their status today.

- **Reference date.** Set per requirement by `applies_at`: `program_start` (default) uses the opportunity start date; `application` ("must be currently enrolled to apply") uses the application deadline; `explicit_date` uses the date the posting states (`reference_date`). This covers age too: the posting's date if stated, otherwise the start date.
- **Projection.** From the profile's expected graduation date, expected enrollment date, and expected future education level, derive the user's education status on the reference date.
- **Unknown dates.** If the reference date or the needed profile dates are missing or ambiguous, return `needs_verification`. Don't guess.
- **Transparency.** If a result depends on a projected (expected, not yet actual) status, the reason says so.
- **Evaluation-level flag.** `depends_on_projected_status` on the evaluation is true only when the overall eligibility outcome depends on one or more projected-status rule results. It is not merely an indication that a projected rule was evaluated. `eligible` requires every result to pass, so any projected pass makes it true. For `ineligible` or `needs_verification`, it's true only when **every** result with the final status is projected; a non-projected result with that status (e.g. an explicit citizenship mismatch, or a partial ELIG-REQ-000) decides the outcome on its own, so the flag is false.
- **Inputs.** Hard eligibility reads only the canonical `profiles` columns (user-entered or user-confirmed). It never reads `profile_facts`, so an unverified AI inference can't affect it ([ADR-006](decisions/ADR-006-core-domain-persistence-model.md)).

Example:

```text
Today:        high-school senior, expected graduation 2041-06-10,
              expected enrollment 2041-08-25 (undergraduate)   (fictional dates)
Opportunity:  summer research program, starts 2041-06-20
Requirement:  open to incoming undergraduates / admitted college students
Reference:    2041-06-20 → projected status: graduated HS, incoming undergraduate
Result:       eligible (reason notes that it depends on projected status)
```

Don't mark such opportunities ineligible just because the user is in high school today.

### Temporal education resolver

`app.profile.education.resolve_education_status(timeline, reference_date)` returns a phase (`enrolled`, `incoming`, `unknown`), a level, a `projected` flag, and an explanation. Semantics (implemented 2026-09-25):

| Reference date | Result |
|---|---|
| before `education_status_as_of` | `unknown` (the resolver doesn't project backwards) |
| before `expected_graduation_date` | `enrolled` at the current level, not projected |
| on/after graduation, before `expected_enrollment_date` | `incoming` at the expected future level, **projected** |
| on/after enrollment | `enrolled` at the expected future level, **projected** |

Transitions take effect **on** their date. `unknown` (insufficient information) is returned when: there's no current level; there's no graduation date and the reference date is after the as-of date; the reference date is on/after graduation but the future level or enrollment date is missing; or enrollment is before graduation. "Projected" means an expected transition was applied. Continuing at the current level before graduation is not counted as projected.

## Version

| Version | Status | Date | Notes |
|---|---|---|---|
| v1 | Implemented | 2026-09-25 | ELIG-REQ-000, ELIG-AGE-001, ELIG-EDU-001, ELIG-CIT-001, ELIG-REQ-001. Time-aware per ADR-005. Rules version string: `v1`. Requirement-assessment semantics (ELIG-REQ-000) added 2026-09-26 in PR review, before v1 was merged or released. |

## Rule Format

```text
Rule ID:
Description:
Inputs:
Reference date:
Output:
Reason:
Example:
Status: Planned / Implemented
```

## Rules

All rules below are implemented in `backend/app/opportunities/eligibility/rules.py` and tested in `backend/tests/test_eligibility.py`. ELIG-REQ-000 runs once per evaluation. Every other rule evaluates one structured requirement ([data-model.md](data-model.md#opportunity_requirements) lists the `value` shapes).

### ELIG-REQ-000

```text
Rule ID: ELIG-REQ-000
Description: Requirement assessment completeness. Is the opportunity's requirement set complete?
Inputs: opportunity requirements_assessment_status
Reference date: not applicable
Output: needs_verification if unassessed or partial; eligible (never blocking) if complete.
        Always recorded, first in the evaluation, with requirement_id = null and
        details {"requirements_assessment_status": ...}.
Reason: unassessed: "The opportunity's hard eligibility requirements haven't been assessed yet,
          so eligibility can't be confirmed."
        partial: "The opportunity's hard eligibility requirements are only partially assessed;
          requirements that aren't represented yet may apply."
        complete: "All of the opportunity's hard eligibility requirements are assessed and represented."
Example: Opportunity with an age requirement the user meets, assessment partial → needs_verification.
Notes: ELIG-REQ-000 is about the completeness of the requirement set. ELIG-REQ-001 is about one
       requirement that v1 can't evaluate. They solve different problems.
Status: Implemented (2026-09-26)
```

### ELIG-AGE-001

```text
Rule ID: ELIG-AGE-001
Description: User will be below the opportunity's minimum age on the reference date.
Inputs: profile date of birth, requirement {"years": n}, reference date
Reference date: date specified by posting (applies_at = explicit_date); otherwise opportunity start date
Output: ineligible if age on the reference date < minimum; eligible otherwise;
        needs_verification if date of birth or reference date is unknown
Age: completed years, compared by (month, day), never reference_year - birth_year.
     The birthday itself counts (exactly the minimum age is eligible).
     A 29 February birthday is reached on 1 March in non-leap years.
Reason: "Minimum age {min} exceeds user age {age} on {date}."
Example: Minimum age 18 at program start 2041-06-20; user born 2023-06-20 is 18 → eligible.
         With a start of 2041-06-19 the user is 17 → ineligible.
Status: Implemented (2026-09-25)
```

### ELIG-EDU-001

```text
Rule ID: ELIG-EDU-001
Description: The opportunity requires an education level (optionally accepting incoming students),
             evaluated against the user's projected education status on the reference date.
Inputs: canonical profile education timeline; requirement {"levels": [...], "accepts_incoming": bool};
        reference date
Reference date: opportunity start date; application deadline if the requirement applies at application time
Satisfied: the resolved level is listed and the phase is enrolled, or incoming when accepts_incoming
Output: eligible if satisfied, ineligible if not. When the status is projected,
        depends_on_projected_status = true and the reason says so.
        needs_verification if the reference date is unknown or the resolver returns unknown
Reason: "Requires {levels} status on {date}; {projected|current} status is {phase} {level}."
        Projected results add: "This relies on expected, not actual, dates: ..."
Examples (fictional profile: graduation 2041-06-10, enrollment 2041-08-25):
  - Undergraduates or incoming undergraduates, program starts 2041-06-20
    → incoming undergraduate → eligible (projected).
  - "Must be currently enrolled in college to apply", deadline 2041-01-15
    → enrolled high_school → ineligible.
  - Enrolled undergraduates only, program starts 2041-08-24 → incoming, not enrolled → ineligible (projected).
  - Start date not stated, or graduation/enrollment date missing → needs_verification.
Status: Implemented (2026-09-25)
```

### ELIG-CIT-001

```text
Rule ID: ELIG-CIT-001
Description: Citizenship of one of the listed countries is required.
Inputs: canonical profile citizenships (ISO alpha-2 list); requirement {"countries": [...]}
Reference date: not applicable
Output: needs_verification if the profile does not state citizenship (NULL or empty list);
        eligible if a profile citizenship is listed;
        ineligible if the profile states citizenship and none of it is listed
Reason: "Citizenship requirement {req} cannot be confirmed from profile."
Example: "U.S. citizens only"; profile citizenship not set → needs_verification.
Notes: Citizenship is never inferred (from résumé text, location, school, name, language, or
       anything else). The explicit-mismatch outcome is deterministic because canonical profile
       fields are user-entered or user-confirmed. Only strict citizenship restrictions use this
       requirement type. "Citizens or permanent residents"-style conditions are
       work_authorization requirements, which v1 marks needs_verification (ELIG-REQ-001).
Status: Implemented (2026-09-25)
```

### ELIG-REQ-001

```text
Rule ID: ELIG-REQ-001
Description: A requirement v1 can't evaluate: its type has no v1 rule (work_authorization, other),
             or its value doesn't match the schema for its type.
Output: needs_verification. Requirements are never silently ignored.
Reason: "Requirement type {type} isn't evaluated by eligibility rules v1; verify it manually."
Status: Implemented (2026-09-25)
```

## Clarifications Made When Implementing v1

- ELIG-CIT-001 also decides the explicit cases: a stated citizenship that matches is `eligible`, and one that doesn't is `ineligible`. The planned text covered only the unknown case.
- ELIG-EDU-001 is generalized from "undergraduate" to any listed levels, with `accepts_incoming`.
- ELIG-REQ-001 was added so requirements without a v1 rule, or with malformed values, surface as `needs_verification` instead of being ignored.
- ELIG-REQ-000 and `requirements_assessment_status` were added in PR review (2026-09-26) so an empty or partial requirement list can't produce `eligible`. Before that, zero requirements meant `eligible`. v1 wasn't bumped because it hadn't been merged or released.

## Maintenance

Any rule change updates this file and bumps the rules version. Each implemented rule needs unit tests for its eligible, ineligible, and ambiguous cases. Temporal rules also need tests on both sides of the graduation and enrollment dates.
