# ADR-001: Separate Eligibility and Fit

Status: Accepted

Date: 2026-09-24

## Context

Opportunities differ in two independent ways: whether the user is allowed to apply (age, education, citizenship, and similar requirements), and how well they match the user's skills and interests. Blending the two into one score lets a strong match hide a hard disqualifier, and wastes the user's time on applications they can't submit.

## Decision

- **Eligibility** is a hard or uncertain qualification assessment with three outcomes: `eligible`, `ineligible`, `needs_verification`. It's produced by deterministic rules ([docs/eligibility.md](../eligibility.md)).
- **Fit** is a personalized ranking score ([docs/scoring.md](../scoring.md)).
- Eligibility is evaluated first. A high fit score must not override explicit ineligibility, and ranking orders by eligibility status before fit.

## Consequences

- Two separately versioned and separately tested components.
- Evaluation records store eligibility status, reasons, rules version, fit score, and scoring version.
- `needs_verification` must be shown to the user, not silently treated as eligible or ineligible.

## Alternatives Considered

- **Single combined score with eligibility penalties.** Rejected: penalties can be outweighed and hide the reason.
- **Filter out ineligible opportunities entirely.** Rejected as the default: it hides useful information and misclassification errors. It can still be offered as a UI filter.
