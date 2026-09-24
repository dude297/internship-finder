# Eligibility

Eligibility is **separate from fit** ([ADR-001](decisions/ADR-001-separate-eligibility-and-fit.md)). Eligibility answers "can the user apply?" Fit answers "how good a match is it?" A high fit score never overrides explicit ineligibility.

## Statuses (planned)

| Status | Meaning |
|---|---|
| `eligible` | No rule excludes the user and nothing requires verification |
| `ineligible` | At least one rule explicitly excludes the user |
| `needs_verification` | A requirement exists that the profile or posting can't settle |

Suggested precedence when combining rule results: `ineligible` > `needs_verification` > `eligible`.

Rules should be deterministic. AI may help **extract** requirements from postings, but it doesn't decide eligibility ([ADR-003](decisions/ADR-003-ai-as-enrichment.md)). Each evaluation should record the reasons (rule IDs) and the rules version.

## Version

| Version | Status | Date | Notes |
|---|---|---|---|
| v1 | Planned | — | Initial rule set below. Not implemented. |

## Rule Format

```text
Rule ID:
Description:
Inputs:
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
Description: User is below the opportunity's minimum age.
Inputs: profile age (as of the relevant date), opportunity minimum age
Output: ineligible
Reason: "Minimum age {min} exceeds user age {age}."
Example: Minimum age 18, user age 17 → ineligible.
Status: Planned
```

### ELIG-EDU-001

```text
Rule ID: ELIG-EDU-001
Description: Opportunity explicitly requires undergraduate enrollment and the user is not an undergraduate.
Inputs: profile education level/enrollment, opportunity education requirement
Output: ineligible
Reason: "Requires current undergraduate enrollment."
Example: "Open to current undergraduates only"; user is a high-school student → ineligible.
Status: Planned
```

### ELIG-CIT-001

```text
Rule ID: ELIG-CIT-001
Description: Citizenship is required but the profile does not establish citizenship.
Inputs: profile citizenship, opportunity citizenship requirement
Output: needs_verification
Reason: "Citizenship requirement {req} cannot be confirmed from profile."
Example: "U.S. citizens only"; profile citizenship not set → needs_verification.
Status: Planned
```

## Maintenance

Any rule change updates this file and bumps the rules version. Each implemented rule needs unit tests for its eligible, ineligible, and ambiguous cases.
