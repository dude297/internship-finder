"""Synthetic corpus for `requirements-rules` v2 (public repo: paraphrased typical wording only, no
verbatim real postings, no private data).

Each case is one posting text (the description; `title` defaults to a neutral one) with the
IDEAL expected output: a list of (requirement_type, value, applies_at, reference_date) or an empty
list for "no hard requirement". `CASES` must match exactly (order-insensitive); `KNOWN_MISSES`
are ideal expectations v2 deliberately does not reach (precision first): v2 must return a strict
subset of them (never a wrong proposal).
"""

from typing import NamedTuple

Expected = tuple[str, dict[str, object], str, str | None]

D = "–"  # en dash used in graduation-window labels


class Case(NamedTuple):
    family: str
    text: str
    expected: tuple[Expected, ...]
    title: str = "Synthetic Internship"
    description_none: bool = False  # title-only: pass description=None


def AGE(years: int, at: str = "program_start", ref: str | None = None) -> Expected:
    return ("minimum_age", {"years": years}, at, ref)


def EDU(
    level: str, incoming: bool = False, at: str = "program_start", ref: str | None = None
) -> Expected:
    return ("education", {"levels": [level], "accepts_incoming": incoming}, at, ref)


def CIT(at: str = "program_start") -> Expected:
    return ("citizenship", {"countries": ["US"]}, at, None)


def OTHER(label: str, at: str = "program_start") -> Expected:
    return ("other", {"description": label}, at, None)


def WA(label: str = "Authorized to work in the United States") -> Expected:
    return ("work_authorization", {"description": label}, "program_start", None)


WA_NS = "Authorized to work in the United States without sponsorship"
PR = "U.S. citizen or permanent resident"
USP = "U.S. person (export control)"
CLR = "Security clearance required"
RTS = "Must be returning to school after the internship"


def GRAD(label: str) -> Expected:
    return OTHER("Expected graduation: " + label)


def STAND(label: str) -> Expected:
    return OTHER("Class standing: " + label)


APP = "application"
EXPL = "explicit_date"

NONE: tuple[Expected, ...] = ()


def c(family: str, text: str, *expected: Expected) -> Case:
    return Case(family, text, expected)


CASES: tuple[Case, ...] = (
    # ---- 1. enrollment / degree pursuit -------------------------------------------------------
    c(
        "enrollment",
        "Must be currently pursuing a bachelor's degree.",
        EDU("undergraduate", at=APP),
    ),
    c(
        "enrollment",
        "Currently pursuing a BS in Computer Science or Electrical Engineering.",
        EDU("undergraduate", at=APP),
    ),
    c("enrollment", "You are currently pursuing a BA in economics.", EDU("undergraduate", at=APP)),
    c("enrollment", "Applicants must be pursuing an undergraduate degree.", EDU("undergraduate")),
    c("enrollment", "Must be a current undergraduate student.", EDU("undergraduate", at=APP)),
    c("enrollment", "Current undergraduate students only.", EDU("undergraduate", at=APP)),
    c(
        "enrollment",
        "Currently enrolled in an accredited four-year college or university.",
        EDU("undergraduate", at=APP),
    ),
    c(
        "enrollment",
        "Must be enrolled in a four-year university during the internship.",
        EDU("undergraduate"),
    ),
    c(
        "enrollment",
        "Must be currently enrolled in a graduate program.",
        EDU("graduate", at=APP),
    ),
    c("enrollment", "Must be a graduate student.", EDU("graduate")),
    c("enrollment", "Applicants must be pursuing a PhD.", EDU("graduate")),
    c("enrollment", "Must be a current high school student.", EDU("high_school", at=APP)),
    c("enrollment", "Current high school students only.", EDU("high_school", at=APP)),
    c("enrollment", "Open to rising high school seniors.", EDU("high_school", incoming=True)),
    c(
        "enrollment",
        "Open to incoming high school juniors or seniors.",
        EDU("high_school", incoming=True),
    ),
    c("enrollment", "Open to rising seniors in high school.", EDU("high_school", incoming=True)),
    c(
        "enrollment",
        "Rising juniors and seniors in high school are eligible.",
        EDU("high_school", incoming=True),
    ),
    c(
        "enrollment",
        "Open to incoming undergraduate students.",
        EDU("undergraduate", incoming=True),
    ),
    c(
        "enrollment",
        "Open to incoming freshmen at four-year universities.",
        EDU("undergraduate", incoming=True),
    ),
    c(
        "enrollment",
        "Must be enrolled in an undergraduate program as of September 1, 2027.",
        EDU("undergraduate", at=EXPL, ref="2027-09-01"),
    ),
    c(
        "enrollment",
        "Must be enrolled in a graduate program by August 15, 2028.",
        EDU("graduate", at=EXPL, ref="2028-08-15"),
    ),
    c(
        "enrollment",
        "Must be enrolled in an undergraduate program at the time of application.",
        EDU("undergraduate", at=APP),
    ),
    c(
        "enrollment",
        "Currently enrolled full-time in a bachelor's program.",
        EDU("undergraduate", at=APP),
    ),
    c(
        "enrollment",
        "Current high school freshmen, sophomores, juniors and seniors are eligible.",
        EDU("high_school", at=APP),
    ),
    c("enrollment", "Must return to school following the internship.", OTHER(RTS)),
    c(
        "enrollment",
        "Applicants must be returning to school in the fall after the internship.",
        OTHER(RTS),
    ),
    # enrollment: deliberately NOT extracted
    c("enrollment", "Must be enrolled in an undergraduate program as of September 2027."),
    c("enrollment", "Must be enrolled in an undergraduate program by September 1."),
    c("enrollment", "Must be pursuing a Bachelor's or Master's degree."),
    c("enrollment", "Open to undergraduate and graduate students."),
    c("enrollment", "Must be a current undergraduate or graduate student."),
    c("enrollment", "Must be a high school student, undergraduate, or graduate student."),
    c("enrollment", "Must be a high school graduate."),
    c("enrollment", "Must have a bachelor's degree or equivalent experience."),
    c("enrollment", "Currently pursuing a degree in computer science."),
    c("enrollment", "Currently pursuing a Bachelor's degree is preferred."),
    c("enrollment", "Ideally you are a current undergraduate student."),
    c("enrollment", "Applicants currently enrolled in a graduate program are not eligible."),
    c("enrollment", "You must not be currently enrolled in high school."),
    c("enrollment", "She is a high school senior."),
    c(
        "enrollment",
        "Our interns are currently pursuing undergraduate degrees at top universities.",
    ),
    c("enrollment", "We mentor high school students from the local district."),
    c("enrollment", "Undergraduate students (rising juniors preferred)."),
    c("enrollment", "Open to incoming freshmen."),
    c("enrollment", "Must be a college student."),
    c("enrollment", "Currently enrolled in an accredited college or university."),
    c("enrollment", "Entering 12th grade in fall 2028."),
    c("enrollment", "Interns are not required to return to school."),
    # ---- 2. graduation window -----------------------------------------------------------------
    c(
        "graduation",
        "Expected graduation date between December 2027 and June 2029.",
        GRAD(f"Dec 2027 {D} Jun 2029"),
    ),
    c(
        "graduation",
        "Graduating between December 2027 and June 2029.",
        GRAD(f"Dec 2027 {D} Jun 2029"),
    ),
    c(
        "graduation",
        "Must graduate between May 2028 and August 2029.",
        GRAD(f"May 2028 {D} Aug 2029"),
    ),
    c("graduation", "Expected graduation in 2028.", GRAD("2028")),
    c("graduation", "Expected to graduate in 2028.", GRAD("2028")),
    c(
        "graduation",
        "Applicants graduating in December 2027 or later.",
        GRAD("on or after Dec 2027"),
    ),
    c("graduation", "Class of 2028 or 2029", GRAD(f"2028 {D} 2029")),
    c("graduation", "Class of 2027 or 2029.", GRAD("2027 or 2029")),
    c("graduation", "Class of 2028, 2029, or 2030 only.", GRAD(f"2028 {D} 2030")),
    c("graduation", "Graduation date after August 2027.", GRAD("after Aug 2027")),
    c("graduation", "Must graduate no earlier than May 2028.", GRAD("on or after May 2028")),
    c("graduation", "Graduating no later than June 2029.", GRAD("on or before Jun 2029")),
    c("graduation", "Must graduate before June 2029.", GRAD("before Jun 2029")),
    c("graduation", "Expected graduation date of May 2028.", GRAD("May 2028")),
    c("graduation", "Graduating in 2028 or 2029.", GRAD(f"2028 {D} 2029")),
    c(
        "graduation",
        "Students graduating between December 2027 and June 2029 are eligible.",
        GRAD(f"Dec 2027 {D} Jun 2029"),
    ),
    c(
        "graduation",
        "Applicants must have an expected graduation date of 2028.",
        GRAD("2028"),
    ),
    c("graduation", "Open to students graduating after 2027.", GRAD("after 2027")),
    c(
        "graduation",
        "Anticipated graduation no later than December 2028.",
        GRAD("on or before Dec 2028"),
    ),
    c("graduation", "Preferred graduation date is May 2028."),
    c("graduation", "Candidates typically graduate in 2028."),
    c("graduation", "Graduating between May 2028 and May 2027."),
    c("graduation", "Graduating on May 15, 2028."),
    c("graduation", "Our founder graduated in 2005."),
    c("graduation", "Graduate students may apply."),
    c("graduation", "Must be a graduating senior."),
    c("graduation", "Expected graduation in December 2027 or June 2028."),
    c("graduation", "Graduating in the spring of 2028."),
    c("graduation", "Students graduating in 2028 are encouraged to apply."),
    # ---- 3. academic standing -----------------------------------------------------------------
    c("standing", "Must be a rising sophomore.", STAND("rising sophomore")),
    c("standing", "Open to rising sophomores and juniors.", STAND("rising sophomore or junior")),
    c(
        "standing",
        "Open to rising juniors and seniors in college.",
        STAND("rising junior or senior"),
    ),
    c(
        "standing",
        "Open to rising seniors at four-year universities.",
        STAND("rising senior"),
    ),
    c("standing", "Must be a first-year student.", STAND("first-year")),
    c("standing", "Must have junior standing.", STAND("junior")),
    c("standing", "Sophomore or junior standing required.", STAND("sophomore or junior")),
    c("standing", "Junior standing or above.", STAND("junior or above")),
    c("standing", "Senior standing at a four-year college is required.", STAND("senior")),
    c("standing", "Junior or senior standing at a university.", STAND("junior or senior")),
    c(
        "standing",
        "Must have completed at least two semesters of college.",
        OTHER("Completed at least 2 semesters"),
    ),
    c("standing", "Must have completed two semesters.", OTHER("Completed at least 2 semesters")),
    c(
        "standing",
        "Completed at least 3 quarters of coursework.",
        OTHER("Completed at least 3 quarters"),
    ),
    c(
        "standing",
        "Must have completed at least 1 year of college.",
        OTHER("Completed at least 1 year"),
    ),
    c(
        "standing",
        "Applicants must have completed 2 years of college.",
        OTHER("Completed at least 2 years"),
    ),
    c(
        "standing",
        "Have completed at least four semesters toward a degree.",
        OTHER("Completed at least 4 semesters"),
    ),
    c("standing", "Must be a rising junior at a four-year college.", STAND("rising junior")),
    c("standing", "Open to rising seniors."),
    c("standing", "Senior standing is required."),
    c("standing", "Must have completed 2 years of industry experience."),
    c("standing", "Typically juniors and seniors apply."),
    c("standing", "Rising seniors are encouraged to apply."),
    c("standing", "Must be a sophomore, junior, or senior."),
    # ---- 4a. citizenship alone ----------------------------------------------------------------
    c("citizenship", "Must be a U.S. citizen.", CIT()),
    c("citizenship", "U.S. citizenship is required.", CIT()),
    c("citizenship", "US citizenship required.", CIT()),
    c("citizenship", "Applicants must be US citizens.", CIT()),
    c("citizenship", "Applicants must be citizens of the United States.", CIT()),
    c("citizenship", "Open to U.S. citizens only.", CIT()),
    c("citizenship", "United States citizens only.", CIT()),
    c("citizenship", "Only U.S. citizens may apply.", CIT()),
    c("citizenship", "Must be a citizen of the U.S.", CIT()),
    c("citizenship", "Must be a citizen of the U.S.A.", CIT()),
    c("citizenship", "This position requires U.S. citizenship.", CIT()),
    c("citizenship", "Must be a U.S. citizen by the application deadline.", CIT(at=APP)),
    c("citizenship", "U.S. citizenship is required at the time of application.", CIT(at=APP)),
    c("citizenship", "US citizenship is not required."),
    c("citizenship", "Citizenship status does not affect consideration."),
    c("citizenship", "U.S. citizenship is preferred."),
    c("citizenship", "We welcome applicants regardless of citizenship."),
    c("citizenship", "Join US in building the future."),
    c("citizenship", "Help us serve U.S. citizens through better software."),
    c("citizenship", "Our customers include U.S. citizens and permanent residents."),
    c("citizenship", "Non-U.S. citizens are encouraged to apply."),
    c("citizenship", "Must be a U.S. citizen or national."),
    c("citizenship", "Must be a U.S. citizen, permanent resident, or DACA recipient."),
    c("citizenship", "Must be a citizen."),
    c("citizenship", "Must be a US citizen or authorized to work in Canada."),
    c("citizenship", "Do not apply if you are not a U.S. citizen."),
    # ---- 4b. citizen-or-resident / export control ---------------------------------------------
    c("residency", "Must be a U.S. citizen or permanent resident.", OTHER(PR)),
    c("residency", "Applicants must be U.S. citizens or lawful permanent residents.", OTHER(PR)),
    c("residency", "Open to US citizens and green card holders.", OTHER(PR)),
    c("residency", "U.S. citizens or permanent residents only.", OTHER(PR)),
    c(
        "residency",
        "Must be a citizen or permanent resident of the United States.",
        OTHER(PR),
    ),
    c("residency", "Must be a U.S. citizen or green card holder.", OTHER(PR)),
    c("residency", "Only permanent residents or U.S. citizens may apply.", OTHER(PR)),
    c("residency", "Must be a citizen or permanent resident."),
    c("residency", "U.S. citizens or permanent residents preferred."),
    c("residency", "Must be a US citizen or permanent resident, or hold a valid visa."),
    c("residency", "Must be a U.S. person as defined by ITAR.", OTHER(USP)),
    c("residency", "Applicants must be U.S. persons under export control regulations.", OTHER(USP)),
    c("residency", "This role is subject to ITAR and requires U.S. person status.", OTHER(USP)),
    c("residency", "Subject to export control laws; must be a U.S. person.", OTHER(USP)),
    c("residency", "ITAR-regulated work; U.S. persons only.", OTHER(USP)),
    c("residency", "Must be eligible for ITAR access.", OTHER(USP)),
    c("residency", "This position may be subject to export control regulations."),
    c("residency", "Export control compliance training is provided."),
    c("residency", "Non-U.S. persons are not eligible."),
    c("residency", "A U.S. person is someone who holds certain statuses."),
    # ---- 4c. work authorization ---------------------------------------------------------------
    c("work_auth", "Must be authorized to work in the United States.", WA()),
    c("work_auth", "Authorized to work in the US.", WA()),
    c("work_auth", "Applicants need authorization to work in the United States.", WA()),
    c("work_auth", "Work authorization is required.", WA()),
    c("work_auth", "Must have valid work authorization in the United States.", WA()),
    c("work_auth", "Candidates must be eligible to work in the United States.", WA()),
    c("work_auth", "Must be authorized to work in the US without sponsorship.", WA(WA_NS)),
    c(
        "work_auth",
        "Applicants must be able to work in the U.S. without current or future sponsorship.",
        WA(WA_NS),
    ),
    c("work_auth", "We will not sponsor visas now or in the future.", WA(WA_NS)),
    c("work_auth", "Sponsorship is not available for this role.", WA(WA_NS)),
    c("work_auth", "Candidates must not require visa sponsorship.", WA(WA_NS)),
    c("work_auth", "We are unable to sponsor work visas.", WA(WA_NS)),
    c("work_auth", "We cannot sponsor visas, but we will consider OPT candidates.", WA(WA_NS)),
    c(
        "work_auth",
        "Must be authorized to work in the United States. Sponsorship is not available.",
        WA(),
        WA(WA_NS),
    ),
    c("work_auth", "No sponsorship questions during application."),
    c("work_auth", "Sponsorship is available for exceptional candidates."),
    c("work_auth", "We do sponsor visas for eligible interns."),
    c("work_auth", "We typically do not sponsor visas."),
    c("work_auth", "Visa sponsorship may be available."),
    c("work_auth", "If you require sponsorship, please indicate it in the application."),
    c("work_auth", "You do not need to be authorized to work in the United States."),
    c("work_auth", "Must be authorized to work in the UK."),
    c("work_auth", "Authorized to work in the US or Canada."),
    # ---- 4d. security clearance ---------------------------------------------------------------
    c("clearance", "An active security clearance is required.", OTHER(CLR)),
    c("clearance", "Must hold an active Secret clearance.", OTHER(CLR)),
    c("clearance", "Must possess an active TS/SCI clearance.", OTHER(CLR)),
    c("clearance", "Requires a current security clearance.", OTHER(CLR)),
    c("clearance", "Active Secret clearance required.", OTHER(CLR)),
    c("clearance", "Must have a clearance.", OTHER(CLR)),
    c("clearance", "No security clearance is required."),
    c("clearance", "Security clearance preferred."),
    c("clearance", "Must be able to obtain a security clearance."),
    c("clearance", "Experience with clearance processes is a plus."),
    c("clearance", "You do not need a security clearance."),
    c("clearance", "Staff must hold an active Secret clearance."),
    # ---- 5. age -------------------------------------------------------------------------------
    c("age", "Must be at least 18 years old.", AGE(18)),
    c("age", "Must be 18 or older.", AGE(18)),
    c("age", "Applicants must be age 16 or older.", AGE(16)),
    c("age", "Minimum age: 16.", AGE(16)),
    c(
        "age",
        "Must be at least 16 years of age at the time of application.",
        AGE(16, at=APP),
    ),
    c("age", "Must be at least 18 by the program start date.", AGE(18)),
    c("age", "Must be at least 16 by June 1, 2027.", AGE(16, at=EXPL, ref="2027-06-01")),
    c("age", "Must be 18+ to apply.", AGE(18)),
    c("age", "Participants must be 16 and up.", AGE(16)),
    c("age", "You must be at least 18.", AGE(18)),
    c("age", "Applicants should be 18 or older.", AGE(18)),
    c("age", "Applicants must be at least 18 years of age on the first day.", AGE(18)),
    c("age", "Age 16+.", AGE(16)),
    c(
        "age",
        "Employees must be 18 or older; interns must be at least 16 years old.",
        AGE(16),
    ),
    c("age", "Must be at least 16 by June 1."),
    c("age", "We welcome students of all ages."),
    c("age", "Most interns are 18."),
    c("age", "Applicants must be 18 years of age or younger."),
    c("age", "Must be under 18."),
    c("age", "Students must be at least 18 months into their degree."),
    c("age", "You must be available at least 20 hours per week."),
    c("age", "The program must be at least 16 weeks long."),
    c("age", "Must have at least 5 years of experience."),
    c("age", "Interns under 18 need a parent's consent."),
    c("age", "Employees must be 18 or older; interns have separate rules."),
    c("age", "Our full-time employees must be at least 18 years old."),
    c("age", "Open to students between the ages of 16 and 19."),
    c("age", "Must be at least 18 years old unless accompanied by a parent."),
    # ---- multiple requirements in one text ----------------------------------------------------
    c("multi", "Must be a U.S. citizen and at least 18 years old.", CIT(), AGE(18)),
    c("multi", "Must be at least 18 years old and a U.S. citizen.", AGE(18), CIT()),
    c(
        "multi",
        "Must be a current undergraduate student and authorized to work in the United States.",
        EDU("undergraduate", at=APP),
        WA(),
    ),
    c(
        "multi",
        "Must be at least 18 years old, authorized to work in the U.S., and currently enrolled "
        "in an undergraduate program.",
        AGE(18),
        WA(),
        EDU("undergraduate", at=APP),
    ),
    c(
        "multi",
        "Must be a U.S. citizen and must hold an active Secret clearance.",
        CIT(),
        OTHER(CLR),
    ),
    c(
        "multi",
        "Must be authorized to work in the U.S. and be at least 18 years of age.",
        WA(),
        AGE(18),
    ),
    c(
        "multi",
        "Requirements:\n• Must be a U.S. citizen\n• Must be at least 18 years old\n"
        "• Python experience preferred",
        CIT(),
        AGE(18),
    ),
    c(
        "multi",
        "Requirements:\n- Currently pursuing a BS\n- Graduating between May 2028 and May 2029\n"
        "- Authorized to work in the US",
        EDU("undergraduate", at=APP),
        GRAD(f"May 2028 {D} May 2029"),
        WA(),
    ),
    c(
        "multi",
        "Must be a high school student. Must be at least 14 years old. U.S. residents only.",
        EDU("high_school"),
        AGE(14),
    ),
    c("multi", "Must be a U.S. citizen. Must be a U.S. citizen.", CIT()),
    c("multi", "Must be 18 or older. Minimum age: 18.", AGE(18)),
    c(
        "multi",
        "Qualifications\n\nMust be a high school student\n\nMust be a U.S. citizen\n\n"
        "Strong communication skills",
        EDU("high_school"),
        CIT(),
    ),
    c(
        "multi",
        "Must be a rising sophomore or junior. Must be authorized to work in the U.S.",
        STAND("rising sophomore or junior"),
        WA(),
    ),
    c(
        "multi",
        "Must be a rising sophomore or junior and a U.S. citizen.",
        STAND("rising sophomore or junior"),
        CIT(),
    ),
    # ---- neutral / soft text ------------------------------------------------------------------
    c("neutral", "strong communication skills"),
    c("neutral", "High-school age applicants welcome."),
    c("neutral", "College experience preferred."),
    c("neutral", "Python experience required."),
    c("neutral", "Must be available 40 hours per week."),
    c("neutral", ""),
    # ---- second-pass wording written after the main rules (3 of these exposed bugs, since fixed)
    c("age", "You will work with other interns who are 18 or older."),
    c("age", "A minimum age of 16 is required.", AGE(16)),
    c("age", "Applicants who are at least 18 years old may apply.", AGE(18)),
    c("clearance", "Must have an active DoD Secret clearance.", OTHER(CLR)),
    c("citizenship", "Mentors must be U.S. citizens."),
    c("graduation", "Must be graduating in May 2028 or December 2028."),
    c("work_auth", "We are not able to provide sponsorship.", WA(WA_NS)),
    # ---- title-only / title+description -------------------------------------------------------
    Case("title", "", NONE, title="Undergraduate Research Intern", description_none=True),
    Case("title", "", NONE, title="Summer Intern (Rising Juniors)", description_none=True),
    Case("title", "", NONE, title="Class of 2028 Software Intern", description_none=True),
    Case("title", "", NONE, title="High School Students Program", description_none=True),
    Case("title", "", (CIT(),), title="U.S. Citizens Only Internship", description_none=True),
    Case("title", "", (WA(),), title="Work Authorization Required - Intern", description_none=True),
    Case("title", "Must be 18 or older.", (AGE(18),), title="Intern"),
    Case(
        "title", "Open to students from any background.", NONE, title="Rising Sophomore Fellowship"
    ),
    Case(
        "title",
        "Active TS/SCI clearance required.",
        (OTHER(CLR),),
        title="Cybersecurity Intern",
    ),
    Case(
        "title",
        "Must be at least 16 years old.",
        (AGE(16), CIT()),
        title="U.S. Citizens Only: Park Ranger Intern",
    ),
)

# Ideal expectations v2 deliberately does not reach. v2 must return a strict subset (no wrong
# proposal): a miss here is acceptable, a wrong proposal is a bug.
KNOWN_MISSES: tuple[Case, ...] = (
    c("enrollment", "Must be an incoming undergraduate.", EDU("undergraduate", incoming=True)),
    c("enrollment", "This program is for undergraduate students.", EDU("undergraduate")),
    c(
        "enrollment",
        "Students should be currently enrolled in an undergraduate program.",
        EDU("undergraduate", at=APP),
    ),
    c("graduation", "Students expected to graduate in 2028.", GRAD("2028")),
    c("standing", "Must be a freshman or sophomore student.", STAND("first-year or sophomore")),
    c("standing", "Open to sophomores and juniors only.", STAND("sophomore or junior")),
    c("citizenship", "Citizenship: U.S. only.", CIT()),
    c("citizenship", "U.S. citizens.", CIT()),
    c(
        "multi",
        "Currently enrolled undergraduate students who are U.S. citizens.",
        EDU("undergraduate", at=APP),
        CIT(),
    ),
    c(
        "multi",
        "Must be a U.S. citizen and hold an active Secret clearance.",
        CIT(),
        OTHER(CLR),
    ),
    c("clearance", "Must be a U.S. citizen with an active Secret clearance.", CIT(), OTHER(CLR)),
    c("residency", "Applicants should be U.S. persons.", OTHER(USP)),
)
