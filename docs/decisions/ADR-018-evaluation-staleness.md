# ADR-018: Evaluation Staleness and Re-evaluation

Status: Proposed (on the feature branch `feature/m9-eligibility-reevaluation`; subject to owner review)

Date: 2026-10-06

## Context

The known debt was "nothing re-evaluates when the eligibility rules version changes or when time passes an expected graduation/enrollment date". Reading the code shows:

1. **Versions are already fingerprinted.** `RULES_VERSION` is part of `eligibility_fingerprint` (ADR-008 §9) and `SCORING_VERSION` of `fit_fingerprint` (ADR-010 §8). A bump already makes every opportunity stale for the catalog pass. The real gap is that nothing *runs* the pass after a version bump: it runs only on a profile or Match Profile save.
2. **Time never changes an evaluation.** `resolve_education_status(profile, reference_date)` is a pure function of the profile timeline and the requirement's reference date (the posting's start date, deadline, or an explicit date). Age is computed the same way. Neither reads "today". An evaluation is therefore a pure function of the profile and the opportunity's own dates; it cannot become wrong, or different, because time passed. The "time passes a graduation date" debt describes a staleness that does not exist in the rules. It is resolved by analysis, not by code.

## Decision

### 1. No time-triggered re-evaluation

No "today", no epoch, no stale flag, and no change to any fingerprint (an epoch tried on this branch only appended byte-identical rows). If a future rule reads today or an expiry date (for example the work-authorization expiry in [the design note](../research/work-authorization-eligibility-design.md)), that rule's ADR must add its own date-dependent input to the fingerprint; that is a rules change and a `RULES_VERSION` bump anyway.

### 2. `python -m app.cli reevaluate`

Runs the existing `evaluate_catalog` pass for the owner's profile: keyset batches of 200 (`--batch-size`), one transaction, counts-only output. `--dry-run` counts what would be evaluated and writes nothing. `--stale-only` is accepted and is the only mode (the pass never re-evaluates a current pair).

Exit codes: `0` success (including "no profile"); `2` and the fixed database-error line on a connection or configuration error (`OperationalError`, `ArgumentError`, `RuntimeError`); `1` on any other exception, printing a fixed line and the exception class name only (never the message or parameters).

### 3. Run it as a release step

[Release Procedure](../deployment.md#release-procedure): after deploying a release that bumps `RULES_VERSION` or `SCORING_VERSION`, run `reevaluate --dry-run`, then `reevaluate`. No workflow change: the scheduled sync stays a sync.

## Effect

- No fingerprint changes: this change appends no rows by itself.
- A version bump followed by `reevaluate` appends one evaluation row per opportunity (batched, one transaction); it is the same cost as a changed Match Profile save ([operations.md](../operations.md#evaluation-history-and-re-evaluation-implemented-not-scheduled)).

## Alternatives considered

- **A temporal epoch in the fingerprint** (the education status as of today). Rejected: the rules never read today, so every crossing would only append identical rows.
- **A scheduled workflow step.** Rejected for now: version bumps are rare and release-driven, and a production-secret workflow shouldn't grow for a rare, manual-friendly operation.
- **Rule results stored with a `stale_after` date.** Rejected: nothing in v1 expires.

## Consequences

- Eligibility and fit remain separate; suggestions still never affect eligibility; no AI is involved.
- A release that forgets the step leaves rows from the old version as current until the next profile save or opportunity change; the rules version stored on each row (`eligibility_rules_version`) shows which version produced it.
