# Eligibility

Eligibility is **separate from fit** ([ADR-001](decisions/ADR-001-separate-eligibility-and-fit.md)). Eligibility answers "can the user apply and participate?" Fit answers "how good a match is it?" A high fit score never overrides explicit ineligibility.

## Statuses (planned)

| Status | Meaning |
|---|---|
| `eligible` | No rule excludes the user and nothing requires verification |
| `ineligible` | At least one rule explicitly excludes the user |
| `needs_verification` | A requirement exists that the profile or posting can't settle |

Suggested precedence when combining rule results: `ineligible` > `needs_verification` > `eligible`.

Rules should be deterministic. AI may help **extract** requirements from postings, but it doesn't decide eligibility ([ADR-003](decisions/ADR-003-ai-as-enrichment.md)). Each evaluation should record the reasons (rule IDs), the rules version, and the reference date(s) used.

## Time-Aware Evaluation (planned)

The user's status changes over time. The current user is a **high-school senior** who is expected to become an **undergraduate** after graduation ([ADR-005](decisions/ADR-005-source-and-profile-ingestion-strategy.md)). Rules evaluate the user's **projected status at the date the requirement applies**, not only their status today.

- **Reference date.** Default: the opportunity start date. If the requirement applies at application time ("must be currently enrolled to apply"), use the application date/deadline. For age, use the date the posting specifies, otherwise the start date.
- **Projection.** From the profile's expected graduation date, expected enrollment date, and expected future education level, derive the user's education status on the reference date.
- **Unknown dates.** If the reference date or the needed profile dates are missing or ambiguous, return `needs_verification`. Don't guess.
- **Transparency.** If a result depends on a projected (expected, not yet actual) status, the reason says so.
- **Inputs.** Hard eligibility inputs come only from user-entered or user-verified profile facts, never from unverified AI inference.

Example:

```text
Today:        high-school senior, expected graduation 2027-06-10,
              expected enrollment 2027-08-25 (undergraduate)
Opportunity:  summer research program, starts 2027-06-20
Requirement:  open to incoming undergraduates / admitted college students
Reference:    2027-06-20 → projected status: graduated HS, incoming undergraduate
Result:       eligible (reason notes that it depends on projected status)
```

Don't mark such opportunities ineligible just because the user is in high school today.

## Version

| Version | Status | Date | Notes |
|---|---|---|---|
| v1 | Planned | — | Initial rule set below, time-aware per ADR-005. Not implemented. |

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

**All rules below are planned and remain so until implemented and tested.**

### ELIG-AGE-001

```text
Rule ID: ELIG-AGE-001
Description: User will be below the opportunity's minimum age on the reference date.
Inputs: profile date of birth, opportunity minimum age, reference date
Reference date: date specified by posting; otherwise opportunity start date
Output: ineligible (needs_verification if date of birth or reference date is unknown)
Reason: "Minimum age {min} exceeds user age {age} on {date}."
Example: Minimum age 18 at program start 2027-06-20; user turns 18 on 2027-09-01 → ineligible.
Status: Planned
```

### ELIG-EDU-001

```text
Rule ID: ELIG-EDU-001
Description: Opportunity requires undergraduate (or incoming undergraduate) status, and the user's
             projected education status on the reference date does not satisfy it.
Inputs: profile current education level, expected graduation date, expected enrollment date,
        expected future education level; opportunity education requirement; reference date
Reference date: opportunity start date; application date if the requirement applies at application time
Output: ineligible if the projected status does not satisfy the requirement;
        eligible (with a "projected status" reason) if it does;
        needs_verification if the reference date or expected dates are unknown
Reason: "Requires undergraduate status on {date}; projected status is {status}."
Examples:
  - Requires undergraduates, program starts 2027-06-20, user projected incoming undergraduate → eligible (projected).
  - "Must be currently enrolled in college to apply", deadline 2027-01-15, user in high school then → ineligible.
  - Requires undergraduates, start date not stated → needs_verification.
Status: Planned
```

### ELIG-CIT-001

```text
Rule ID: ELIG-CIT-001
Description: Citizenship is required but the profile does not establish citizenship.
Inputs: profile citizenship, opportunity citizenship requirement
Reference date: not applicable
Output: needs_verification
Reason: "Citizenship requirement {req} cannot be confirmed from profile."
Example: "U.S. citizens only"; profile citizenship not set → needs_verification.
Status: Planned
```

## Maintenance

Any rule change updates this file and bumps the rules version. Each implemented rule needs unit tests for its eligible, ineligible, and ambiguous cases. Temporal rules also need tests on both sides of the graduation and enrollment dates.
