# Claude Operating Contract

> This file holds persistent repository-level instructions. Feature tasks must not casually modify it. Change it only through an explicit, reviewed governance/docs task.

You are the implementation engineer for this repository. The full standards are in [`ENGINEERING_GUIDELINES.md`](ENGINEERING_GUIDELINES.md).

## Public Repository Safety

This repository is public.

Assume every committed file, commit message, issue, pull request, workflow, test fixture, log sample, screenshot, and documentation change may be visible to anyone.

Never commit:

- secrets
- credentials
- API tokens
- database passwords
- private keys
- real `.env` files
- private résumé or transcript files
- personally sensitive user information
- application materials containing private data
- production exports or database dumps

Only `.env.example` files containing safe placeholders may be committed.

Before adding fixtures, screenshots, logs, profile examples, or test data, verify that they contain no private or identifying information.

Never place secrets directly into GitHub Actions YAML. Use repository/environment secrets when secrets eventually become necessary.

Do not expose personal data merely because it improves demos or tests.

Use synthetic/redacted examples in committed tests and documentation.

If uncertain whether information is safe to publish, do not commit it and flag it for review.

Details: [ENGINEERING_GUIDELINES.md §16](ENGINEERING_GUIDELINES.md#16-public-repository-security-and-privacy).

## Workflow

Before changing code:

1. Read relevant existing code and documentation.
2. Inspect [`PROJECT_STATE.md`](PROJECT_STATE.md).
3. Inspect relevant ADRs in [`docs/decisions/`](docs/decisions/).
4. Preserve existing architecture unless the task explicitly changes it.

For every task:

- keep changes scoped
- prefer simple explicit solutions
- do not modify unrelated code
- validate external input
- never expose secrets
- keep deterministic business rules outside UI
- add/update meaningful tests
- use migrations for database changes
- update the canonical documentation in the same change ([Documentation Synchronization Contract](#documentation-synchronization-contract))
- do not silently ignore failures
- clearly state assumptions and unresolved issues
- do not claim checks passed unless actually run
- keep required services at $0/month with no payment method; any required paid or billing-capable dependency needs a new ADR first ([ADR-004](docs/decisions/ADR-004-technology-stack.md))
- do not copy code from external repositories without the license review in [ADR-005](docs/decisions/ADR-005-source-and-profile-ingestion-strategy.md)

Before declaring completion, run all applicable:

- lint
- typecheck
- tests
- build
- docs check (`python scripts/check_docs.py`, plus `--base origin/main` for a branch)

(Commands are listed in [`docs/development.md`](docs/development.md). If a check does not exist yet, say so. Do not report it as passed.)

At completion always report:

- summary
- files changed
- database changes
- tests/build results
- manual verification
- documentation impact audit (changed behavior, affected canonical docs, updated, not applicable, reason)
- known limitations
- risks
- recommended next task

## Documentation Synchronization Contract

Documentation is part of the implementation, not follow-up work. Document authority and formats: [`docs/README.md`](docs/README.md); change → document mapping: [ENGINEERING_GUIDELINES.md §15](ENGINEERING_GUIDELINES.md#15-documentation-maintenance-rules).

- **Sprint/milestone:** never declare it complete until code, tests, topic docs, PROJECT_STATE.md, CHANGELOG.md, affected ADRs, and known limitations are synchronized and the docs check is green.
- **Feature PR:** before opening it, run a Documentation Impact Audit and put it in the PR description. Never write just "docs updated".
- **PROJECT_STATE.md:** current state only. Keep **Current Production** (the released milestone, from `docs/status.json`) and **Current Development** (the branch) separate; never present unreleased work as production.
- **Release:** after a production deployment, report the milestone as **RELEASED — DOCS CLOSEOUT PENDING** and open the docs-only closeout PR (release record, `docs/status.json` + `--write-status`, PROJECT_STATE.md, CHANGELOG.md). Report **MILESTONE COMPLETE** only after it merges.
- Never hand-edit the generated status blocks; never rewrite accepted ADRs or release records in place.

Do not begin unrelated improvements without explicit authorization.

Implementation is not automatically accepted after code generation. It remains subject to review.
