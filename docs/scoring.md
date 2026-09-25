# Fit Scoring

Scoring is **versioned behavior**. Status: **Planned v1, not implemented.**

## Principles

- Eligibility is evaluated **before** fit ranking ([ADR-001](decisions/ADR-001-separate-eligibility-and-fit.md)).
- Ineligible opportunities must never outrank eligible ones because of fit score. Rank by eligibility status first, then by fit.
- Weights should eventually live in **one** configurable location, not scattered through code.
- Every evaluation record stores the `scoring_version` that produced it.
- v1 scoring is deterministic and works without AI or any paid API: rules, structured profile data, and keyword/semantic logic that needs no paid service ([ADR-003](decisions/ADR-003-ai-as-enrichment.md), [ADR-004](decisions/ADR-004-technology-stack.md)). AI or local-model signals may be added later as optional inputs.
- Profile facts carry provenance ([ADR-005](decisions/ADR-005-source-and-profile-ingestion-strategy.md)). Scoring should distinguish user-stated or user-verified facts from unverified AI-inferred ones, for example by weighting unverified facts lower. The exact treatment is decided when components are defined.

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
