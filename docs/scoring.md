# Fit Scoring

Scoring is **versioned behavior**. Status: **Planned v1, not implemented.**

## Principles

- Eligibility is evaluated **before** fit ranking ([ADR-001](decisions/ADR-001-separate-eligibility-and-fit.md)).
- Ineligible opportunities must never outrank eligible ones because of fit score. Rank by eligibility status first, then by fit.
- Weights should eventually live in **one** configurable location, not scattered through code.
- Every evaluation record stores the `scoring_version` that produced it.

## Planned v1 Weights

| Component | Weight |
|---|---|
| Technical match | 35% |
| Academic match | 20% |
| Project/research match | 15% |
| Interest match | 10% |
| Location/schedule match | 10% |
| Opportunity quality | 10% |
| **Total** | **100%** |

The exact definition of each component score (inputs, 0–1 or 0–100 scale, handling of missing data) is TBD during implementation and must be documented here when decided.

## Version History

| Version | Status | Date | Notes |
|---|---|---|---|
| v1 | Planned | — | Initial weights above. |

## Maintenance

Any change to weights or component definitions bumps the version and updates this file. Old evaluations keep their original version so results stay comparable.
