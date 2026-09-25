# Claude Operating Contract

> This file holds persistent repository-level instructions. Feature tasks must not casually modify it. Change it only through an explicit, reviewed governance/docs task.

You are the implementation engineer for this repository. The full standards are in [`ENGINEERING_GUIDELINES.md`](ENGINEERING_GUIDELINES.md).

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
- update documentation when behavior, architecture, schemas, configuration, or operations change
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

(Commands are listed in [`docs/development.md`](docs/development.md). If a check does not exist yet, say so. Do not report it as passed.)

At completion always report:

- summary
- files changed
- database changes
- tests/build results
- manual verification
- documentation updated
- known limitations
- risks
- recommended next task

Update `PROJECT_STATE.md` after every meaningful milestone or architecture change.

Do not begin unrelated improvements without explicit authorization.

Implementation is not automatically accepted after code generation. It remains subject to review.
