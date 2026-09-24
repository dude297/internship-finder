# ADR-003: AI as Enrichment

Status: Accepted

Date: 2026-09-24

## Context

LLMs are useful for reading unstructured postings: extracting requirements, summarizing, classifying, and explaining matches. They can also be wrong, inconsistent across versions, and confidently mistaken about facts such as deadlines, age limits, or citizenship requirements. Getting those wrong means missed or invalid applications.

## Decision

AI may enrich and interpret postings. It doesn't replace deterministic rules for hard eligibility or factual source data.

- AI must not be the sole authority for age eligibility, work authorization, deadlines, citizenship, education requirements, whether a posting exists, or whether an application was submitted.
- Structured AI output must follow a schema and be validated before use.
- Raw source data is always preserved alongside AI-derived data.
- AI failures are handled without breaking ingestion or evaluation.
- The model/version is recorded where appropriate, and uncertainty is surfaced (e.g. as `needs_verification`), not hidden.

## Consequences

- The core pipeline and eligibility engine must work with AI disabled.
- AI-extracted requirements feed deterministic rules as inputs. They are marked as AI-derived, and ambiguous ones lead to `needs_verification`.
- There's extra storage for raw data and enrichment metadata.
- No LLM SDK is added until an enrichment feature needs one.

## Alternatives Considered

- **AI as the primary evaluator.** Rejected: non-deterministic, hard to test, and errors are costly.
- **No AI at all.** Rejected as a long-term position: unstructured postings are common, and extraction and explanation add real value.
