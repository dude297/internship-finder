# Requirement extractor v1 recall analysis

Offline and read-only. Date: 2026-10-04. Extractor: `requirements-rules` v1 (`backend/app/opportunities/requirements/extractor.py`, `extract_requirements(ExtractionInput)`). No product code changed; the throwaway script is not committed. **v2 is not implemented in M8; it needs its own review (ADR-012 precision-over-recall stance).**

Why this matters: production produced only 4 pending candidates (all education) after M7. Eligibility reads only canonical (owner-accepted) requirements, so every missed or wrong candidate costs owner review time or leaves eligibility at "unknown". Also per `eligibility/schemas.py`, value schemas exist only for `minimum_age`, `education`, `citizenship`; `work_authorization` and `other` are free-text and not evaluated, and there is **no graduation-year requirement type at all**.

## Method

69 synthetic sentences (paraphrased typical wording, no real postings) were each run as the whole description of a posting titled "Intern". Result: **24 of 69 produced a proposal** (35%). Of the 24, 3 are lossy or questionable (marked below).

## Results by category

| Category | Example phrasing | v1 result | Why |
|---|---|---|---|
| Graduation year | "Class of 2028 or 2029"; "graduating between Dec 2027 and Jun 2029"; "expect to graduate in 2028" (4 tried) | none (4/4) | No rule; also no requirement type or evaluator for it (needs a new type, outside the extractor) |
| Degree program | "pursuing a BS in CS or EE"; "pursuing a Bachelor's degree in STEM"; "currently pursuing an undergraduate degree" | none | `_EDU_RE` accepts only "must be [an] LEVEL student/program", "currently enrolled in LEVEL", "must be enrolled in a LEVEL program"; "pursuing" is not a lead-in |
| Enrollment (level) | "Must be currently enrolled in an undergraduate program" | proposal (undergraduate) | correct |
| | "Must be a current undergraduate student" | none | "current" before the level is not an accepted lead-in |
| | "Must be a college student"; "enrolled at an accredited college or university" | none | "college/university" is not a level word |
| | "Must be a graduate student", "enrolled in a graduate program" | proposal (graduate) | correct |
| Incoming | "Must be an incoming / rising undergraduate student" | proposal, `accepts_incoming` true | correct |
| | "Open to incoming freshmen"; "rising sophomore, junior, or senior" | none | no level word |
| Enrollment (status) | "returning to school after the internship"; "completed at least 2 semesters"; "enrolled full-time" | none | No requirement type for these (not age/level/citizenship); correct to ignore until a type exists |
| Age | "Must be at least 18 years old / of age" | proposal (18) | `_AGE_PATTERNS` |
| | "at least 16 years of age by June 1" | proposal (16), **`program_start`, date "June 1" dropped** (questionable) | `by` is in `_AGE_END`, but the cutoff date is not parsed; age is later checked at the opportunity start date, not June 1 |
| | "16 years of age or older at the time of application" | proposal (16), `application` | `_applies_at` phrase match |
| | "18 years of age or older by the start date" | proposal (18) | pattern 3 |
| | "Minimum age: 16" | proposal (16) | pattern 2 |
| | "Must be 18 or older" | none | patterns need the word "years" |
| | "Students must be age 14 or older" | none | no "age N" pattern |
| | "between the ages of 16 and 19" | none | ranges deliberately skipped |
| US person / export control | "U.S. person as defined by ITAR/EAR" (3 tried) | none (3/3) | `_CITIZENSHIP_RE` does not match "person"; correct to avoid mapping (US persons include permanent residents, so mapping to citizenship would be wrong). No type represents it except free-text `other` |
| Citizenship | "U.S. citizenship is required"; "Must be a U.S. citizen"; "Open to U.S. citizens only" | proposal (US) | `_CITIZENSHIP_RE` |
| | "Applicants must be US citizens" (plural, no dots); "US citizenship required"; "citizens of the United States" | none | regex needs singular `must be a(n) ... citizen`, `U.S.`/`United States` spelling, and "citizenship required" only with "U.S." dots |
| | "Open to US citizens or permanent residents"; "U.S. citizen or lawful permanent resident" | **work_authorization** proposal labelled "Authorized to work in the United States" (wrong/lossy) | `_OTHER_STATUS_RE` blocks citizenship, but `_WORK_AUTH_RE` has a `citizens? or (lawful )?permanent residents?` branch; label overstates (a foreign national with a work visa is authorized but not eligible); value is free-text and not evaluated |
| Work authorization | "Must be legally authorized to work in the United States"; "authorized to work in the U.S."; "Work authorization is required" | proposal | `_WORK_AUTH_RE` |
| | "authorized to work in the US without sponsorship" | none | needs `the United States` or `U.S.` with dots; "the US" misses |
| | "will not sponsor visas now or in the future"; "must not require visa sponsorship"; "Sponsorship is not available" | none | `_NEGATION_RE` ("not") skips the whole sentence. Correct as a no-claim; it is not a work-authorization statement |
| Clearance | "An active security clearance is required" | proposal (`other`) | `_OTHER_RE` |
| | "Must hold a Secret clearance" | none | pattern requires "security clearance" |
| High school | "Must be a high school student"; "currently enrolled in high school" | proposal (high school) | `_EDU_RE` |
| | "Applicants must be current high school students"; "Current high school students only" | none | "current" lead-in not accepted; no "must be" |
| | "rising high school senior"; "incoming high school junior or senior" | none | pattern needs "rising/incoming high school student(s)" (`_EDU_INCOMING_RE`); "senior/junior" nouns are not level words |
| | "rising juniors and seniors"; "entering 11th or 12th grade"; "grades 9 through 12"; "a senior in high school" | none | grade/class words unmodelled |
| | "high school students and recent graduates" | none | alternatives; also "graduate" matches a different level (safe skip) |
| | "Must be a high school graduate" | none | `graduate` as noun is correctly not enrollment (guard works) |
| Hedge/alternative guards | "Ideally you are a current undergraduate student"; "Must be a U.S. citizen (or hold a green card)" | none | `_HEDGE_RE`, `_OTHER_STATUS_RE` (correct) |

Take-aways: precision guards behave as designed (no false positives found in the 69 sentences except the two work-authorization label cases and the dropped age cutoff date). Recall loss for the target user (high-school senior / incoming freshman) is mainly (1) phrasing variants of a level statement ("current", "pursuing", "rising ... senior"), (2) plural/spelling variants of citizenship, (3) bare "N or older".

## Recommended v2 rules (not for M8)

Ranked by expected value for a high-school senior or incoming freshman. Each needs unit tests with the negative cases listed, a rules version bump to `requirements-rules` v2, and review before building.

| # | Rule | Adds | Precision conditions | False-positive risk |
|---|---|---|---|---|
| 1 | **High-school level variants**: allow lead-ins `current(ly)`, `only`, and `rising/incoming/entering` + `high school` + (`student(s)` / `senior(s)` / `junior(s)`); also "grades 9-12" / "11th or 12th grade" only when the word "high school" is in the same sentence | Turns most high-school programs' core line into a proposal. Value is `levels=[high_school]`, `accepts_incoming` true for rising/incoming | Keep the multiple-level skip, hedge and negation filters; keep "high school graduate/diploma" blocked | Low-moderate: "high school students and recent graduates" must stay skipped (alternatives); "rising seniors" without "high school" must stay unmatched (college seniors) |
| 2 | **Undergraduate variants**: "current(ly) undergraduate student", "pursuing an undergraduate degree / bachelor's / BS", "enrolled in a (four-year) college/university" as undergraduate | Covers the common college wording incl. incoming freshmen programs ("incoming freshman" only when "college/university" is in the same sentence) | Require explicit "undergraduate" or "bachelor's/BS/BA" (not bare "pursuing a degree", which could be graduate); keep the multi-level skip ("Bachelor's or Master's" must not match) | Moderate: "pursuing a BS ... or MS" lists; "incoming freshmen" in a high-school program (9th graders). Use the sentence guard and keep proposals pending for owner review |
| 3 | **Citizenship/age/work-auth spelling fixes**: `U\.?S\.?` and "United States"; plural "U.S. citizens"; "citizenship (is) required" without dots; bare "must be N or older" (N 10-30); "age N or older"; fix `citizens or permanent residents` branch to stop emitting a work-authorization proposal labelled "Authorized to work" (drop it, or emit `other` with an accurate label such as "U.S. citizens or permanent residents") | More citizenship (evaluated) and age (evaluated) proposals; removes a wrong label | Existing `_OTHER_STATUS_RE` and negation guards stay; keep the 10-30 age bound | Low. "US" without dots is also a pronoun-ish token only in uppercase "US" in "join US"; require adjacent "citizen(s)/citizenship/work" |

Further candidates (lower value or higher risk): parse "by June 1" into an `explicit_date` reference date for age cutoffs (needs year inference and eligibility date semantics; moderate risk, currently the proposal silently becomes `program_start`); "Secret/TS clearance" into `other` (clearance is irrelevant to high-school users); graduation year (needs a new requirement type, schema and evaluator via ADR, not extractor-only); US-person/ITAR as `other` free text (no evaluator; mapping to citizenship would be wrong).

Process: build a labelled corpus of reviewed real excerpts (privately; commit only synthetic equivalents, public repo) to measure precision before enabling v2; v2 proposals stay pending and never auto-accept; bumping the version re-extracts only on material text change per ADR-012 section 6, so confirm the re-run behaviour before release.
