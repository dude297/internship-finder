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

## Time-Aware Evaluation

The user's status changes over time. For example, a high-school senior is expected to become an undergraduate after graduation ([ADR-005](decisions/ADR-005-source-and-profile-ingestion-strategy.md)). Rules evaluate the user's **projected status at the date the requirement applies**, not only their status today.

- **Reference date.** Set per requirement by `applies_at`: `program_start` (default) uses the opportunity start date; `application` ("must be currently enrolled to apply") uses the application deadline; `explicit_date` uses the date the posting states (`reference_date`). This covers age too: the posting's date if stated, otherwise the start date.
- **Projection.** From the profile's expected graduation date, expected enrollment date, and expected future education level, derive the user's education status on the reference date.
- **Unknown dates.** If the reference date or the needed profile dates are missing or ambiguous, return `needs_verification`. Don't guess.
- **Transparency.** If a result depends on a projected (expected, not yet actual) status, the reason says so.
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
