# Requirement extractor v2 (`requirements-rules` version "2")

Implements the recommendations of [requirement-extractor-recall.md](requirement-extractor-recall.md) (the v1 recall analysis). Same architecture as v1: a pure function `extract_requirements(ExtractionInput) -> tuple[Proposal, ...]`, no network, AI, clock or randomness, same `Proposal` model, no schema, service, database or eligibility change. Precision first: a false hard requirement is worse than a miss, and every proposal still goes through owner review (ADR-012).

Code: `backend/app/opportunities/requirements/extractor.py`. Tests: `backend/tests/test_requirement_extractor.py` (updated v1 tests), `backend/tests/test_requirement_extractor_v2.py` (corpus), `backend/tests/requirement_corpus_v2.py` (corpus data), `backend/tests/_extractor_v1_reference.py` (frozen test-only copy of v1 for the comparison; not shipped in `app/`).

## How text is read

1. Title clauses, then description clauses, in order. Sentences end at `. ! ?`, line breaks and bullets; dotted abbreviations (`U.S.`, `B.S.`, `Ph.D.`, `e.g.`) are protected. A sentence is then split at `;` into **clauses**; every guard and matcher works on one clause, so "Employees must be 18; interns must be 16" cannot leak the employee clause into the intern one.
2. A clause is dropped if it is about another role only (employees, staff, mentors, supervisors, managers, parents, guardians, chaperones, instructors, teachers, drivers, alumni, judges) and does not also name the intern side (intern, student, applicant, candidate, participant, you, fellow), or if it contains a hedge.
3. The no-sponsorship matcher runs next (it is negative in form, see below), then the generic negation guard, then every other matcher. Several proposals may come from one clause when they are different families and each is independently unambiguous ("Must be a U.S. citizen and at least 18 years old" gives citizenship plus age).
4. Proposals are deduped by semantic key (first occurrence wins), capped at `MAX_PROPOSALS` (20). `source_text` is the clause (or a 300-character window around the match).
5. A **title** is scanned with a prefix that defeats the "bare bullet" lead-in (below), so a title only yields a proposal with explicit wording ("U.S. Citizens Only Internship", "Work Authorization Required - Intern"). "Undergraduate Research Intern", "Summer Intern (Rising Juniors)" and "Class of 2028 Software Intern" propose nothing.

"Mandatory lead": most families need requirement wording somewhere in the clause (must, only, required, requires, eligible, open to, restricted/limited to, need/have to, you are, applicant(s), candidate(s), participant(s), who are, qualifications, requirements) **or** the matched phrase must open the clause (a bare bullet such as "Currently pursuing a BS" or "Authorized to work in the United States"). "Our interns are currently pursuing undergraduate degrees at top universities" has neither and proposes nothing.

## Label table (exact strings; fixed, never copied text)

Free-text `description` values are part of semantic identity, so every one comes from this table.

| Type | Label | Source wording (examples) |
|---|---|---|
| work_authorization | `Authorized to work in the United States` (v1, unchanged) | "authorized/eligible to work in the US", "work authorization required", "must have valid work authorization" |
| work_authorization | `Authorized to work in the United States without sponsorship` | "without (current or future) sponsorship", "will not / cannot / unable to sponsor", "sponsorship is not available", "must not require sponsorship" |
| other | `Security clearance required` (v1, unchanged) | "must hold an active Secret / Top Secret / TS/SCI / DoD Secret clearance", "clearance required" |
| other | `U.S. citizen or permanent resident` | citizen OR (lawful) permanent resident / green card holder, United States named |
| other | `U.S. person (export control)` | "U.S. person" with mandatory wording, ITAR / EAR / export control with mandatory wording |
| other | `Must be returning to school after the internship` | "must return to school following the internship", "must be returning to their studies" |
| other | `Expected graduation: Dec 2027 – Jun 2029` | window between two month/year or year points (en dash) |
| other | `Expected graduation: 2028`, `Expected graduation: May 2028` | single year or month-year |
| other | `Expected graduation: 2028 – 2029`, `Expected graduation: 2027 or 2029` | "Class of 2028 or 2029" (consecutive years collapse to a range, otherwise joined with "or") |
| other | `Expected graduation: after Aug 2027`, `on or after ...`, `before ...`, `on or before ...` | bounds ("after", "no earlier than", "before", "no later than", "by", "or later") |
| other | `Class standing: rising sophomore`, `rising sophomore or junior`, `rising junior or senior` | "rising ..." (see ambiguity rule) |
| other | `Class standing: first-year`, `junior`, `sophomore or junior`, `junior or above`, `senior` | "first-year student", "junior standing", "junior standing or above" |
| other | `Completed at least 2 semesters` (also quarters, terms, years) | "completed two semesters", "completed at least 1 year of college" |

Typed values (unchanged shapes): `minimum_age {"years": n}`, `education {"levels": [...], "accepts_incoming": bool}`, `citizenship {"countries": ["US"]}` (only for citizenship alone).

## Rule families

**1. Enrollment / degree pursuit** (`education`, or `other` for returning to school)
- Pursuit: "(currently) pursuing / enrolled in / working toward" + an explicit level (`undergraduate`, bachelor's, BS/BA/BSc, graduate, master's, MS/MA, PhD, high school) followed by degree/program/student(s)/studies or a clause end or "in ...". "Pursuing a BS in CS or EE" is undergraduate; "Currently pursuing a degree in CS" has no level and proposes nothing.
- Student nouns: "(current) LEVEL student(s)"; for high school also senior/junior/sophomore/freshman. "Rising/incoming/entering" sets `accepts_incoming` and is itself a mandatory statement (as in v1). "Rising seniors in high school" is incoming high school. "Incoming freshmen" counts only with college/university and no high-school context.
- "Enrolled in a four-year / 4-year college, university or institution" is undergraduate. A bare "accredited college or university", "college student" or "community college" is **not** undergraduate-only (graduate students are enrolled too) and proposes nothing.
- Multi-level clauses ("Bachelor's or Master's", "undergraduate and graduate students", "high school student, undergraduate, or graduate student") and "or equivalent / in lieu" proposals are skipped. "A graduate of", "a high school graduate", "a high school diploma" are finished levels, never enrollment.
- "Must return to school following the internship" and "returning to school" cannot be an education value, so they become the `other` label above (mandatory wording required; "returning students welcome" is a hedge).

**2. Graduation window** (`other`): a graduation keyword (expected/anticipated graduation (date), graduation date/year, graduating, graduate(s), class of) followed by a window (between/from X and Y, X - Y), a bound (after, on or after, before, on or before, no earlier/later than, by, "or later"), or a year list. Needs mandatory wording or must open the clause. Skipped: a specific day ("May 15, 2028"), a seasons-only date ("spring of 2028"), an inverted range, a list of months ("December 2027 or June 2028"), past tense ("graduated in 2005"), years outside 2015-2060, hedged forms ("preferred graduation date", "typically").

**3. Academic standing** (`other`): "rising sophomore/junior/senior(s)", "first-year student", "sophomore/junior/senior standing (or above)", "completed (at least) N semesters/quarters/terms/years". Ambiguity rule: any standing clause that mentions high school or grades is skipped; **"senior" in any label requires college/university/undergraduate/degree context** ("Open to rising seniors." proposes nothing, "Open to rising seniors at four-year universities." proposes `Class standing: rising senior`); "completed N years" needs study context (not "2 years of industry experience"). "Incoming" is never standing (incoming freshmen are enrollment).

**4. Citizenship / residency / export control / work authorization / clearance** (never collapsed into one another)
- Citizenship alone (`citizenship US`): "must be / hold / have a U.S. citizen / U.S. citizenship", "must be a citizen of the (United States | U.S. | U.S.A.)", "U.S. citizens only", "only U.S. citizens", "open/limited/restricted to U.S. citizens", "U.S. citizenship required/mandatory", "requires U.S. citizenship", and a coordinated "and a U.S. citizen" when the clause says must/required. `US`/`USA` only match in capitals, so "join us" cannot match. Any other status in the clause (permanent resident, national, refugee, visa, DACA, TPS, authorized to work, "either", another country, or a following "or ...") blocks it.
- Citizen OR permanent resident / green card holder, United States named, mandatory wording: `other` `U.S. citizen or permanent resident`. Extra statuses (nationals, refugees, visas, DACA) block it. Without a named country it proposes nothing (v1 labelled "Must be a citizen or permanent resident" as work authorization).
- U.S. person with mandatory wording, or ITAR / International Traffic in Arms / Export Administration Regulations / EAR / export control with must/required/requires/only/eligible: `other` `U.S. person (export control)`. Descriptive mentions ("export control compliance training is provided", "may be subject to export control") propose nothing.
- Work authorization: the `Authorized to work in the United States` patterns (needs United States / U.S. / US named; "UK", "Canada" etc. in the clause block it). No-sponsorship patterns are evaluated before the negation guard with narrow regexes; "no sponsorship questions during application", "sponsorship is available", "we do sponsor", "we typically do not sponsor", "visa sponsorship may be available" and "if you require sponsorship" never produce the no-sponsorship label. When the no-sponsorship label fires, the plain label is not also emitted for that clause.
- Clearance: `Security clearance required` for "must have/hold/possess/maintain ... [active|current|valid] [Secret|Top Secret|TS|TS/SCI|SCI|DoD|public trust] clearance", "requires a ... clearance", "... clearance required". "Must be able to obtain a clearance", "eligible for clearance" and "clearance is a plus" propose nothing.

**5. Age** (`minimum_age`): "must be at least N (years old)", "must be N or older / N+ / N and up", "age N or older", "minimum age (of|:) N", "applicants must be N years of age", "at least N years old" (with a requirement subject). The number needs a requirement subject (must / need to / should be / you|applicants|candidates|participants are), so "other interns who are 18 or older" is not a requirement. Plausible range 10-30 as in v1. Number-not-age guards: months, hours, weeks, "years of experience".

## applies_at rules

- Age: `application` for "at the time of application / applying / application deadline"; `program_start` for "by the program start date / start of the internship / on the first day / at hire" and the default; `explicit_date` + `reference_date` for a year-bearing date ("by June 1, 2027"). **A date without a year ("at least 16 by June 1") proposes nothing** (decision: v1 silently used `program_start`; the alternative `other` "Minimum age 16 by a stated date" would be an unevaluated candidate the owner has to decode, and a wrong evaluated candidate is the risk we are avoiding).
- Education: `explicit_date` for a year-bearing date after as of / by / before / on / starting / beginning / from ("enrolled ... as of September 1, 2027"); a month-only or year-less date ("as of September 2027", "by September 1") proposes nothing; `program_start` for "during the internship / program / summer / throughout / at the start" (wins over "current"); `application` for "current(ly)" or "at the time of application"; default `program_start`.
- Everything else: `application` for "at the time of application / by the application deadline / when you apply", otherwise `program_start`.

## Guard list

Hedges (clause skipped): preferred, prefer(s), preference, nice to have, bonus, ideally, ideal, desirable, desired, favo(u)red, typically, generally, normally, commonly, often, sometimes, mostly, primarily, most, usually, encouraged, welcome, might, could, unless, except, exception(s), waiver(s), depending, if, plus / a plus, case-by-case, and "may" (except "may apply / participate / be considered|eligible" and the month "May 2028").
Negations (clause skipped, except the narrow no-sponsorship family and date bounds): not, no, never, cannot, can't, don't, doesn't, isn't, aren't, won't, nor, neither, ineligible, regardless, irrespective, without regard, no matter, optional, exempt, waived, all ages, any age, all nationalities, any nationality, `non-`, "or younger / under / less", "under the age", "under N". "No earlier / later than" and "not before" are neutralized as date bounds.
Scope: other-role clauses, peer descriptions (age), descriptive employer wording (no mandatory lead), titles (explicit wording only), foreign-country mentions for citizenship/work authorization, multi-level and alternative education wording.

## Corpus and results

`backend/tests/requirement_corpus_v2.py`: 258 synthetic sentences (paraphrased typical wording, no verbatim real postings, no private data). 246 are `CASES` that v2 must match exactly (order-insensitive, by semantic key); 12 are `KNOWN_MISSES`, ideal expectations v2 deliberately does not reach, asserted to produce a strict subset (a miss is acceptable, a wrong proposal is a bug). 145 of the 246 cases have an expected proposal, 101 expect none. 7 of the sentences were written in a second pass after the main rules (3 of them exposed bugs that were then fixed, so the corpus is not a clean held-out set, and v2's numbers are optimistic by construction).

| Family | Sentences | v1 exactly correct | v2 exactly correct | Expected requirements | v1 found | v2 found |
|---|---|---|---|---|---|---|
| enrollment | 51 | 24 | 48 | 29 | 4 | 26 |
| graduation | 31 | 11 | 30 | 20 | 0 | 19 |
| standing | 25 | 6 | 23 | 19 | 0 | 17 |
| citizenship (alone) | 29 | 20 | 27 | 15 | 6 | 13 |
| residency / export control | 21 | 5 | 20 | 14 | 0 | 13 |
| work authorization | 24 | 11 | 24 | 16 | 3 | 16 |
| clearance | 14 | 8 | 13 | 9 | 3 | 8 |
| age | 31 | 19 | 31 | 16 | 7 | 16 |
| multiple requirements | 16 | 5 | 14 | 32 | 16 | 30 |
| neutral / soft text | 6 | 6 | 6 | 0 | 0 | 0 |
| title-only / title+description | 10 | 8 | 10 | 6 | 4 | 6 |
| **Total** | **258** | **123 (48%)** | **246 (95%)** | **176** | **43** | **164** |

| Metric | v1 | v2 |
|---|---|---|
| Proposals emitted | 61 | 164 |
| True positives | 43 | 164 |
| False proposals (wrong or mislabelled) | 18 | 0 |
| Precision | 0.705 | 1.000 |
| Recall (of 176 expected) | 0.244 | 0.932 |

The v1 "false proposals" are: 7 citizen-or-permanent-resident sentences mislabelled `work_authorization "Authorized to work"` (the bug this fixes), 2 age sentences with the date dropped or silently `program_start` ("by June 1"), 7 education sentences whose timing differs on purpose (`currently` is now `application`; explicit dates; month-only or year-less dates that v1 turned into `program_start` and v2 declines), 1 "Our full-time employees must be at least 18" (other role) and 1 "at least 18 years old unless accompanied by a parent" (exception). Seven of the 18 are therefore definitional (the corpus encodes the v2 timing rules); the other 11 are genuine v1 errors. Run `pytest tests/test_requirement_extractor_v2.py -q -s` to print the live table (`test_v1_vs_v2_corpus_comparison`).

The 12 known misses: "Must be an incoming undergraduate" (no student noun), "This program is for undergraduate students", "Students should be currently enrolled ..." ("should" is soft), "Students expected to graduate in 2028" (no mandatory wording), "Must be a freshman or sophomore student", "Open to sophomores and juniors only", "Citizenship: U.S. only", a bare "U.S. citizens.", "Currently enrolled undergraduates who are U.S. citizens", "Must be a U.S. citizen and hold an active Secret clearance" (clearance needs its own "must hold"), "Must be a U.S. citizen with an active Secret clearance", "Applicants should be U.S. persons".

## Decisions worth reviewing

- **Employees / interns:** an other-role clause is dropped, and a `;` separates clauses. "Employees must be 18 or older; interns must be at least 16 years old." proposes only age 16. "Employees must be 18 or older; interns have separate rules." proposes nothing.
- **v1 key compatibility:** the two v1 labels are unchanged, but v1 education candidates for "currently enrolled / current ..." had `program_start`; v2 gives them `application`, a different semantic key. Candidates already reviewed under v1 for such sentences will re-appear as new pending candidates after re-extraction (see open question in the hand-off).
- **Same-meaning stability:** `test_rewording_keeps_the_semantic_key` pins groups of differently worded sentences to one key (citizen-or-PR, graduation windows, no-sponsorship, clearance, citizenship, undergraduate enrollment, age).

## Known limitations

- Sentence ending in "U.S." swallows the boundary (inherited from v1): "Must be authorized to work in the U.S. Sponsorship is not available." is one sentence, so the no-sponsorship hit replaces the plain label.
- Negated phrasings of a positive requirement ("Non-U.S. persons are not eligible", "Do not apply if you are not a U.S. citizen") propose nothing: the negation guard has no inversion logic by design.
- No HTML handling (inputs are plain text), no non-English text, no season-only graduation dates, no grades ("11th or 12th grade"), no "community college", no GPA, no major/field of study, no location, no hours, no skills.
- The graduation, standing and returning-to-school labels are verification-oriented `other` values: they are **not evaluated** (no evaluator exists), so they cannot make a user ineligible; they only surface for owner review.
- The corpus is synthetic and partly developed alongside the rules; precision on real postings must be measured with a private labelled sample before activation (recall analysis, "Process").

## Deliberately NOT extracted

Hedged or preferred wording; negated wording; upper bounds and ranges ("ages 14-18", "under 18"); alternative-level lists; bare college wording; "rising senior" without college context; ages with a year-less deadline date; clearance eligibility ("able to obtain"); peer or employer descriptions; other-role requirements; country-less citizenship or residency; descriptive export-control or ITAR mentions; hours, months, weeks and years-of-experience numbers; anything inside a title without explicit wording.
