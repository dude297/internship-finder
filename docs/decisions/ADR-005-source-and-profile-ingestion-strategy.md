# ADR-005: Layered Opportunity Sources and Provenance-Aware Personal Profile Ingestion

Status: Accepted

Date: 2026-09-24

> Everything in this ADR is **planned architecture**. No profile schema, parser, source adapter, or AI inference exists yet. Schemas shown are conceptual, not final.

## Context

### The user

The system serves one student who, as of 2026-09-24, is a **high-school senior** and is expected to become an **undergraduate** after graduating. Many relevant opportunities (summer research, incoming-freshman programs, first-year internships) begin *after* that transition. Their requirements refer to the user's status **when the opportunity starts**, not today.

A single static field such as `education_level = high_school` would wrongly mark those opportunities ineligible, and it would go stale the day the user graduates.

### The profile

Relevant profile information already exists in the user's own materials: a résumé, coursework, projects, GitHub, awards, activities. Re-entering all of it by hand is tedious and error-prone. But automatically extracted facts, especially AI-inferred ones, can be wrong, and the recommendation engine must not treat a guess the same as an explicit statement.

### Opportunity sources

Writing and maintaining a crawler for every site is expensive. Structured sources (public feeds, ATS APIs) already cover a lot, and several open-source projects already collect internship listings. However, the most valuable opportunities for a high-school senior or incoming undergraduate (university research programs, fellowships, government and nonprofit STEM programs) usually don't appear in standard software-engineering internship boards.

## Decision

### 1. Time-aware education status

Profile education status is **temporal**. The planned profile supports:

```text
current education level
current grade/year
expected graduation date
expected college enrollment date
expected future education level
date of birth / age (only if voluntarily stored)
location
preferred locations
remote preference
availability windows
work authorization / citizenship (where relevant)
```

Eligibility evaluates the user's **projected status at the date the requirement applies**, normally the opportunity **start date**, rather than only the status today.

```text
Today:          high-school senior (expected graduation 2027-06)
Opportunity:    summer program starting 2027-06-20
Requirement:    incoming undergraduate / enrolled college student
Projected:      incoming undergraduate on 2027-06-20
Result:         eligible (based on projected status; reason says so)
```

Rules for this:

- The reference date is chosen per requirement. "Must be enrolled when the program starts" uses the start date. "Must be currently enrolled to apply" uses the application date/deadline. Age uses the date the posting specifies, otherwise the start date.
- If the needed date is unknown or the projection is ambiguous, the result is `needs_verification`, not a guess ([ADR-001](ADR-001-separate-eligibility-and-fit.md) statuses are unchanged).
- A result that depends on a **projected** status records that in its reasons, so the user can see it relies on expected graduation or enrollment.
- Once the user's actual status changes (graduation, enrollment), the profile is updated and evaluations are recomputed.

Detailed rules live in [docs/eligibility.md](../eligibility.md).

### 2. Profile ingestion pipeline

The user should not have to re-enter every relevant detail by hand. The long-term pipeline is:

```text
User files / profile sources
        ↓
Raw profile source          (original artifact, stored unchanged)
        ↓
Parser                      (deterministic first; AI optional)
        ↓
Structured profile facts    (each with provenance)
        ↓
Validation / user review
        ↓
Canonical profile
        ↓
Eligibility + ranking
```

Planned inputs include: résumé, coursework history, projects, skills, extracurricular activities, awards, leadership, research, work experience, GitHub/project information, preferences, location preferences, and application history.

### 3. Résumé and document parsing

A résumé should eventually be uploadable and parseable. Extraction targets: education, coursework, skills, languages, projects, activities, leadership, awards, experience, certifications, research, technologies, and dates.

- The **original résumé stays the source artifact**. Extracted data is stored separately as structured profile facts.
- Source data is never overwritten or discarded by parsing.
- Re-parsing (with a better parser or model) produces new facts linked to the same source. It doesn't edit the source.
- Where the original file is stored is decided when this is implemented. Per [ADR-004](ADR-004-technology-stack.md), no external object storage is added unless a real need emerges.

### 4. Provenance

Provenance is a core concept. Every profile fact is traceable to where it came from:

```text
manual
resume
transcript
project
GitHub
course list
user preference
AI inference
```

Conceptual shape (not implemented, not final):

```text
ProfileFact
- value
- category
- source              (one of the kinds above)
- source document     (link to the raw profile source, if any)
- extraction method   (manual / deterministic parser / AI model + version)
- confidence
- verified_by_user
```

This lets eligibility and scoring distinguish "the user explicitly stated Python" from "AI guessed Python from vague text", for example by weighting unverified inferred facts lower in fit scoring. Hard eligibility inputs (age, education status, citizenship/work authorization, graduation and enrollment dates) are taken **only from user-entered or user-verified facts**.

### 5. AI inference boundaries

AI may help interpret user materials. For example:

```text
"Built a machine-learning classification project using Python and TensorFlow."
  → Skill: Python
  → Skill: TensorFlow
  → Area: Machine Learning
  → Experience type: Project
```

Consistent with [ADR-003](ADR-003-ai-as-enrichment.md):

- AI output never silently becomes authoritative. Inferred facts are stored with `source = AI inference`, model/version, and confidence.
- Output follows a schema and is validated (Pydantic) before storage.
- Important inferred facts are reviewable, and the user can accept, edit, or reject them.
- AI is optional. Manual entry and deterministic parsing must work without it, and no paid AI API is required ([ADR-004](ADR-004-technology-stack.md)).

### 6. Eligibility vs fit stay separate

[ADR-001](ADR-001-separate-eligibility-and-fit.md) is unchanged. Given a profile with Python, TensorFlow, AI projects, and advanced math, and a posting that says "Python preferred, ML experience preferred, undergraduate required":

- **Eligibility** asks: will the user be an undergraduate when the internship begins?
- **Fit** asks: how well do skills, interests, and experience match?

Profile facts feed both, but they are evaluated independently.

### 7. Layered opportunity sources

Don't build every crawler from scratch. Sources are adopted in priority order:

| Priority | Layer | Examples | Notes |
|---|---|---|---|
| 1 | Existing public structured feeds | Public internship datasets/feeds | Only where legally and technically appropriate (license, terms of use) |
| 2 | Direct ATS sources | Greenhouse, Lever, Ashby, other structured ATS | Structured APIs with stable IDs |
| 3 | High-school / early-college specific sources | University summer research, university labs, research internships, fellowships, government and nonprofit STEM programs, startup internships, hackathons, technical summer programs, accelerators, scholarships with technical/project components, incoming-freshman and first-year undergraduate programs | Strategically important. These are often missing from standard SWE boards |
| 4 | Custom career pages | Specific organization sites | HTML parsing where needed |
| 5 | Browser automation | JS-heavy sites | Only when simpler structured approaches aren't available |

Priority 3 is ordered by implementation difficulty, not importance. It's the layer most specific to this user.

Sourcing is not crawler-only: feeds, APIs, manual import, and parsing are all first-class.

### 8. Source adapter boundary

Every source conforms to a common internal interface (conceptual):

```python
class OpportunitySource:
    async def fetch(self) -> list[RawOpportunity]:
        ...

    def normalize(
        self,
        raw: RawOpportunity,
    ) -> NormalizedOpportunity:
        ...
```

Sources may use any transport (JSON API, RSS, HTML, file, browser). The common boundary begins **after fetch**. All sources then flow through the shared pipeline ([ADR-002](ADR-002-shared-ingestion-pipeline.md)):

```text
Source → RawOpportunity → Normalization → Validation → Deduplication
       → Persistence → Eligibility → Fit Scoring → Ranking
```

Source adapters must not implement their own scoring, eligibility, database schema, or deduplication.

### 9. Open-source reuse policy

External open-source projects are **references, optional sources, or optional adapters**, not **core foundations**, unless explicitly approved.

Before copying any code:

1. inspect the license
2. determine compatibility with this project
3. record attribution requirements
4. determine whether copyleft obligations apply
5. document the reused components (in [docs/sources.md](../sources.md) or a new ADR)

Don't copy code just because it's on GitHub. Architectural ideas may be implemented independently.

Consuming a project's published **data** (for example, a JSON listing file) as a feed is a separate question from copying its **code**. It also requires checking the license/terms for that data, and it's implemented as an ordinary source adapter, so the project remains replaceable.

### 10. GitHub research references

Recorded as research references only. None is a dependency. Details and status are tracked in [docs/sources.md](../sources.md#research-references).

| Repository | Useful ideas | Policy |
|---|---|---|
| `pleasedodisturb/kestrel` | FastAPI backend, React frontend, profile-based job scoring, application pipeline tracking, source registry, AI-provider abstraction, scoring evaluation harness, extensive tests | **AGPL-3.0.** Don't copy implementation code unless the licensing implications are separately reviewed and explicitly approved. Architectural reference only. |
| `zshah101/Automated-List-Of-Summer-2027-and-Fall-2026-Tech-Internships` | Large ATS source registry, automated collection, structured JSON output, skill extraction, citizenship/visa indicators, posting dates, dedupe, recurring GitHub Actions refresh | Research reference; possible source seed list or external feed adapter if its license/terms permit. Don't couple core architecture to it. |
| `SuryaHarikrishnan/2027-internship-tracker` | Large listings, category organization, GitHub Actions refresh, application tracking, ranking/freshness concepts | Reference or optional external feed only, not a foundation. |

Licenses other than Kestrel's haven't been verified yet. Verify each before any use beyond reading.

## Consequences

- The profile schema is more complex than a flat record: it needs dated status fields, raw profile sources, and profile facts with provenance.
- Eligibility rules take a reference date and a projected status, and must be tested at the boundaries around graduation and enrollment dates.
- Evaluations may change over time without any posting changing, because the user's projected status moves. Re-evaluation is expected.
- A user-review step is part of profile ingestion, so imported data isn't immediately authoritative.
- Early source work favors structured feeds and ATS APIs, which are cheaper to maintain than scrapers. Priority-3 sources will need more manual curation.
- External projects can be swapped out or dropped without architectural change.

## Alternatives Considered

- **Static education level on the profile.** Simple, but wrong for this user: it marks post-graduation opportunities ineligible and goes stale at graduation. Rejected.
- **Manual profile entry only.** Accurate, but tedious enough that the profile would stay incomplete. Kept as a first-class input, but not the only one.
- **Parse the résumé directly into the canonical profile.** Fewer tables, but it loses provenance, can't distinguish inferred from stated facts, and makes re-parsing destructive. Rejected.
- **AI-first profile extraction with automatic acceptance.** Convenient, but violates [ADR-003](ADR-003-ai-as-enrichment.md): errors would flow silently into eligibility. Rejected.
- **Custom crawlers for every source.** Maximum control, but high build and maintenance cost. Rejected as the default. Scraping and browser automation are the last layers, not the first.
- **Build on an existing open-source internship project (fork Kestrel or a listing repo).** Faster start, but it imports licensing obligations (AGPL for Kestrel), couples the architecture to someone else's design, and those projects target standard tech internships more than this user's early-college needs. Rejected as a foundation. They remain references.

## Clarification (2026-09-25): Public repository boundary

This clarification extends the decision above. It doesn't change it. The repository is public ([ENGINEERING_GUIDELINES.md §16](../../ENGINEERING_GUIDELINES.md#16-public-repository-security-and-privacy)), so raw profile sources, profile facts, and the canonical profile are **runtime data only**. They are never repository content.

When résumé ingestion is implemented:

- Uploaded résumé files are never committed.
- Default local upload and storage directories are gitignored before any code writes to them.
- Tests use synthetic résumés.
- Documentation examples are fabricated or redacted.
- Parsed profile facts containing real personal data are never committed.
- Database dumps containing profile facts are never committed.

"Where the original file is stored" (§3) is still an implementation decision, but the answer can't be Git.
