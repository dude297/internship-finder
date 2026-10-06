"""Adversarial attack corpus for `requirements-rules` v2 (synthetic sentences only).

Each case is (text, expected signatures). An empty tuple means "no proposal". A signature with a
leading "?" is a desirable-but-optional proposal: the extractor may emit it or miss it, but must
never emit anything outside the required + "?"-listed set. A false hard requirement is worse than
a miss, so most expectations are empty.
"""

from typing import Any

import pytest

from app.opportunities.requirements.extractor import MAX_EXCERPT_CHARS, extract_requirements
from app.opportunities.requirements.identity import ExtractionInput

CIT = "CIT"
NS = "WA:Authorized to work in the United States without sponsorship"
WA = "WA:Authorized to work in the United States"
CLR = "OTHER:Security clearance required"
USP = "OTHER:U.S. person (export control)"
PR = "OTHER:U.S. citizen or permanent resident"
E: tuple[str, ...] = ()


def GRAD(label: str) -> str:
    return "OTHER:Expected graduation: " + label


def STAND(label: str) -> str:
    return "OTHER:Class standing: " + label


def sig(p: Any) -> str:
    kind = p.requirement_type.value
    at = "" if p.applies_at.value == "program_start" else f"@{p.applies_at.value}"
    if kind == "citizenship":
        return CIT
    if kind == "minimum_age":
        return f"AGE{p.value['years']}{at}"
    if kind == "education":
        inc = "+inc" if p.value["accepts_incoming"] else ""
        return f"EDU:{p.value['levels'][0]}{inc}{at}"
    prefix = "WA" if kind == "work_authorization" else "OTHER"
    return f"{prefix}:{p.value['description']}"


def run(text: str, title: str = "Synthetic Internship") -> set[str]:
    return {sig(p) for p in extract_requirements(ExtractionInput(title=title, description=text))}


CASES: list[tuple[str, tuple[str, ...]]] = [
    # ---- citizenship: negation / hedge ----------------------------------------------------
    ("US citizenship is not required.", E),
    ("Citizenship status does not affect consideration.", E),
    ("There is no citizenship requirement.", E),
    ("Applicants are considered regardless of citizenship.", E),
    ("We do not require U.S. citizenship.", E),
    ("This program is not limited to U.S. citizens.", E),
    ("Non-US citizens are welcome.", E),
    ("U.S. citizenship preferred.", E),
    ("Ideally a U.S. citizen.", E),
    ("U.S. citizens are encouraged to apply.", E),
    ("Applicants need not be U.S. citizens.", E),
    ("You don't have to be a U.S. citizen.", E),
    ("Open to U.S. citizens and non-citizens alike.", E),
    ("Open to U.S. citizens and international students.", E),
    ("Open to US citizens, international students, and refugees.", E),
    ("Open to U.S. citizens and dual citizens.", E),
    ("Some roles require U.S. citizenship.", E),
    ("Certain positions require U.S. citizenship.", E),
    ("Select teams require U.S. citizenship.", E),
    ("Must be a U.S. citizen — or hold equivalent status.", E),
    ("Must be a U.S. citizen - or have comparable standing.", E),
    ("U.S. citizens only. Non-U.S. citizens may also apply.", E),
    ("Must be a U.S. citizen. International students are also eligible.", E),
    ("Citizenship is required. Exceptions are possible for international students.", E),
    # controls
    ("Must be a U.S. citizen.", (CIT,)),
    ("U.S. citizenship is required.", (CIT,)),
    ("MUST BE A U.S. CITIZEN.", (CIT,)),
    ("US CITIZENSHIP REQUIRED", (CIT,)),
    ("• Must be a U.S. citizen", (CIT,)),
    ("Must be a U.S. citizen.", (CIT,)),
    ("Only U.S. citizens may apply.", (CIT,)),
    ("Must be 18 years old and a U.S. citizen.", ("?AGE18", CIT)),
    # ---- citizenship: other role / scope --------------------------------------------------
    ("Mentors must be US citizens.", E),
    ("Our engineers must be U.S. citizens; interns have no such requirement.", E),
    ("Full-time hires must be authorized to work in the U.S.", E),
    ("Full-time conversion requires U.S. citizenship.", E),
    ("Return offers require U.S. citizenship.", E),
    ("Post-graduation employment requires U.S. citizenship.", E),
    ("Interns work across the U.S. Mentors must be U.S. citizens.", E),
    ("Our staff are located across the U.S. Staff must be U.S. citizens.", E),
    ("Supervisors are required to be U.S. citizens.", E),
    ("Contractors must be U.S. citizens.", E),
    ("Parents must be U.S. citizens to sign the consent form.", E),
    # ---- citizenship: lists / disjunctions ------------------------------------------------
    ("Open to US citizens, permanent residents, or asylees.", E),
    ("Must be a U.S. citizen or national.", E),
    ("Must be a citizen of the US or Canada.", E),
    ("Dual citizens welcome.", E),
    ("Must be a citizen of an EU member state.", E),
    ("Canadian citizens only.", E),
    ("Must be a U.S. citizen (or eligible to obtain a clearance).", E),
    ("Must be a U.S. citizen or a lawful permanent resident.", (PR,)),
    ("Must be a permanent resident or U.S. citizen.", (PR,)),
    ("Must be a U.S. citizen or hold a green card.", E),
    ("Must be a U.S. citizen, or authorized to work in the U.S.", (WA,)),
    ("Must be either a U.S. citizen or a permanent resident.", E),
    ("Must be a US citizen/national.", E),
    ("Must be a US citizen and a resident of California.", E),
    ("Must be a U.S. citizen, U.K. citizen, or Australian citizen.", E),
    ("Must be a citizen of the United States or a protected individual.", E),
    # ---- export control / U.S. person -----------------------------------------------------
    ("Subject to ITAR; applicants must be U.S. persons.", (USP,)),
    ("Export-controlled technology may require a license.", E),
    ("This role may require access to export-controlled information.", E),
    ("All interns are required to complete export control training.", E),
    ("Interns must comply with export control regulations.", E),
    ("Applicants must acknowledge the export control policy.", E),
    ("Export control compliance is required for all staff.", E),
    ("You must complete the ITAR awareness course in week one.", E),
    ("Our products are subject to the Export Administration Regulations.", E),
    ("U.S. persons are encouraged to apply.", E),
    ("Non-U.S. persons may need an export license.", E),
    ("Candidates must be U.S. persons.", (USP,)),
    (
        "This position requires access to information subject to U.S. export controls "
        "(including a federal energy regulation).",
        E,
    ),
    ("This role requires access to export controlled data.", E),
    ("Work involves ITAR-controlled hardware and requires a badge.", E),
    ("Must be eligible for ITAR access.", (USP,)),
    # ---- clearance ------------------------------------------------------------------------
    ("Ability to obtain a clearance.", E),
    ("Security clearance not required but preferred.", E),
    ("Eligible for a security clearance.", E),
    ("Must be able to obtain and maintain a Secret clearance.", E),
    ("Must be eligible to obtain a Top Secret clearance.", E),
    ("Our engineers must hold a Secret clearance; this internship does not.", E),
    ("Employees must hold an active clearance.", E),
    ("Mentors must have a Top Secret clearance.", E),
    ("Must hold an active clearance or be eligible to obtain one.", E),
    ("Must have a Secret clearance or equivalent.", ("?" + CLR,)),
    ("Must have clearance eligibility.", E),
    ("Must have a clearance-eligible background.", E),
    ("Some projects require an active clearance.", E),
    ("Clearance is not required for this internship.", E),
    ("Must have an active Secret clearance.", (CLR,)),
    ("An active Top Secret clearance is required.", (CLR,)),
    ("Must hold a security clearance.", (CLR,)),
    # ---- work authorization / sponsorship -------------------------------------------------
    ("No sponsorship questions during application.", E),
    ("We will answer sponsorship questions.", E),
    ("Sponsorship is available.", E),
    ("We do sponsor visas.", E),
    ("Sponsorship may be available.", E),
    ("H-1B sponsorship available for full-time conversion.", E),
    ("Please indicate whether you require sponsorship.", E),
    ("This role does not require sponsorship.", E),
    ("Visa sponsorship: no", ("?" + NS,)),
    ("Sponsorship: Not available", ("?" + NS,)),
    ("We do not provide sponsorship for conferences.", E),
    ("We do not offer sponsorship opportunities to vendors.", E),
    ("We do not sponsor hackathons.", E),
    ("We do not sponsor interns' housing.", E),
    ("We cannot sponsor visas for contractors.", E),
    ("We are unable to sponsor H-1B visas for full-time conversion.", E),
    ("We cannot sponsor visas for our European offices.", E),
    ("Applicants will be asked whether they are authorized to work in the U.S.", E),
    ("You will be asked if you are legally authorized to work in the United States.", E),
    ("The application form asks whether candidates are authorized to work in the U.S.", E),
    ("Must be authorized to work in the U.S. now or in the future without sponsorship.", (NS,)),
    ("We are unable to sponsor visas for interns.", (NS,)),
    ("We cannot sponsor.", (NS,)),
    ("Must be authorized to work in the United States.", (WA,)),
    ("Must be authorized to work in the US or Canada.", E),
    ("Must be authorized to work in the U.S.; we do sponsor visas for conversions.", (WA,)),
    ("Authorized to work in the United States is a plus.", E),
    ("Interns must be authorized to work in the U.S. and are paid hourly.", (WA,)),
    (
        "U.S. Person status (U.S. citizen or lawful permanent resident) is required, and the "
        "company does not provide visa sponsorship.",
        (NS, "?" + USP, "?" + PR),
    ),
    # ---- age ------------------------------------------------------------------------------
    ("We welcome students of all ages.", E),
    ("Must be under 18.", E),
    ("Ages 14-18.", E),
    ("Participants are ages 14 to 18.", E),
    ("18 or older preferred.", E),
    ("Must complete at least 18 credit hours.", E),
    ("Must have at least 18 credit hours.", E),
    ("Must be 21 to drive company vehicles.", E),
    ("Must be at least 21 to drive company vehicles.", E),
    ("Must be 18 or older to rent a car.", E),
    ("Must be 16+ to operate the equipment.", E),
    ("Interns must be at least 18 years old to attend the company happy hour.", E),
    ("Employees must be 18; interns must be 16 or older.", ("AGE16",)),
    ("Staff must be at least 21 years old.", E),
    ("Parental consent is required for participants under 18.", E),
    ("Parents must be at least 18 to sign the consent form.", E),
    ("Must be 18 or older, or have parental consent.", E),
    ("Must be 18 or older. Younger applicants need parental consent.", E),
    ("Must be 18 or older (or 16 with parental consent).", E),
    ("Candidates aged 16 and up.", ("?AGE16",)),
    ("Students 16+ only.", ("?AGE16",)),
    ("Ages 14 and up.", ("?AGE14",)),
    ("Interns must be at least 18 years of age.", ("AGE18",)),
    ("Must be at least 18 years old by June 1.", E),
    ("Must be at least 18 years old as of June 1, 2027.", ("AGE18@explicit_date",)),
    ("Must be at least 18 years old at the time of application.", ("AGE18@application",)),
    ("Must be at least 18 years old and able to lift 50 pounds.", ("AGE18",)),
    ("At least 18 years of experience is not needed.", E),
    ("Must be at least 3 years into a degree.", E),
    ("Minimum age: 18 for night shifts.", E),
    ("Must be 18+ to apply.", ("AGE18",)),
    ("Must be at least 18 years of age to drive.", E),
    # ---- graduation -----------------------------------------------------------------------
    ("Preferred graduation date: June 2028.", E),
    ("Graduation date flexible.", E),
    ("Graduating in 2028 is a plus.", E),
    ("Typically juniors.", E),
    ("Most interns are rising juniors.", E),
    ("Class of 2028 welcome.", E),
    ("Graduated in 2020.", E),
    ("Must have graduated in 2020 or later.", E),
    ("Alumni who graduated in 2021 may apply.", E),
    ("By 2028 we will host 100 interns.", E),
    ("We were founded in 2028.", E),
    ("The company graduates forty interns into full-time roles by 2028.", E),
    ("Applicants must complete the graduate program application by 2027.", E),
    ("Graduate students must submit transcripts by 2027-01-15.", ("?EDU:graduate",)),
    ("Applicants must not graduate before 2027.", E),
    ("Employees who graduated in 2022 mentor interns.", E),
    ("Mentors must have graduated in 2019 or earlier.", E),
    ("Must graduate by 2028.", (GRAD("on or before 2028"),)),
    ("Must be graduating between May 2027 and May 2028.", (GRAD("May 2027 – May 2028"),)),
    ("Applicants must be graduating in 2027 or 2028.", (GRAD("2027 – 2028"),)),
    ("Expected graduation date: June 5, 2028.", E),
    ("Must be graduating in 2028; the program starts in 2027.", (GRAD("2028"),)),
    # ---- enrollment / standing ------------------------------------------------------------
    ("Currently pursuing a bachelor's or master's.", E),
    ("Pursuing a BS/MS.", E),
    ("Recent graduates.", E),
    ("Must have graduated.", E),
    ("Enrolled in a graduate program or recent bachelor's graduate.", E),
    ("Must be an undergraduate student or recent graduate.", E),
    ("Applicants must be undergraduate students or recent graduates.", E),
    ("Must be an undergraduate student or a bootcamp participant.", E),
    ("Must be pursuing a bachelor's degree or higher.", E),
    ("Open to high school students and undergraduates.", E),
    ("Open to high school students and graduates.", E),
    ("Open to high school students, undergraduates, and graduate students.", E),
    ("Must be pursuing a degree, or be a career changer.", E),
    (
        "Must be a continuing college student pursuing a bachelor's degree, an associate degree, "
        "or be a recent graduate in engineering.",
        E,
    ),
    ("Must be pursuing a bachelor's degree or an associate degree.", E),
    ("Must be pursuing an associate degree, or a bachelor's degree.", E),
    (
        "Must be enrolled in a college or university (undergraduate at least a rising senior, "
        "or enrolled in a Master's or Ph.D. program).",
        E,
    ),
    ("Must be a rising senior or enrolled in a graduate program.", E),
    ("Must be a rising junior, or a graduate student.", E),
    ("Rising sophomores and juniors only.", (STAND("rising sophomore or junior"),)),
    ("Sophomore year of high school.", E),
    ("A junior developer will pair with you.", E),
    ("Senior engineers mentor interns.", E),
    ("First-year PhD students receive a stipend.", E),
    ("Freshmen dorms are available for housing.", E),
    ("Currently enrolled is not required.", E),
    ("Must not be enrolled in school.", E),
    ("Must have completed one semester of data structures.", E),
    ("Must have completed 2 semesters of calculus.", E),
    ("Must have completed two terms of mentoring.", E),
    ("Must have completed 2 years at a startup.", E),
    ("Must have completed at least 2 years of college.", ("OTHER:Completed at least 2 years",)),
    ("Must be enrolled in a graduate program.", ("EDU:graduate",)),
    ("Undergraduate students must apply by March 1, 2027.", ("?EDU:undergraduate",)),
    ("Undergraduate students must submit the form by 2027-03-01.", ("?EDU:undergraduate",)),
    ("Must be a graduate of an accredited university.", E),
    ("Must have a graduate degree.", E),
    ("Seniors in the program present at demo day.", E),
    ("Must be a student.", E),
    ("Graduate students may apply.", E),
    ("Must not be a graduate student.", E),
    # ---- round 2 probes -------------------------------------------------------------------
    ("Must be enrolled in a four-year university or community college.", E),
    ("Must be enrolled in a four-year college or university.", ("EDU:undergraduate",)),
    ("Must be a rising senior at a university or recent alumnus.", E),
    ("Must be graduating in 2027 or later, or be a current graduate student.", E),
    ("Applicants must be at least 18 years old, unless otherwise approved.", E),
    (
        "Must be at least 18 years of age at the start of the program and a U.S. citizen.",
        ("AGE18", CIT),
    ),
    ("Must be a US citizen. Visa holders are not eligible.", (CIT,)),
    ("U.S. citizens and permanent residents are eligible; others are not.", (PR,)),
    ("Candidates must not require visa sponsorship, now or in the future.", (NS,)),
    ("Applicants must hold or be able to obtain a Secret clearance.", E),
    ("Open to undergraduates and graduate students.", E),
    ("Must be a high school student aged 16 to 18.", ("?EDU:high_school",)),
    ("Must be a U.S. citizen (dual citizens are not eligible).", E),
    ("Applicants must be U.S. citizens, or in the process of becoming one.", E),
    ("US citizens, US nationals, and lawful permanent residents only.", E),
    ("Eligible: U.S. citizens, green card holders, and refugees.", E),
    ("No visa sponsorship is available.", ("?" + NS,)),
    ("This position is not eligible for visa sponsorship.", ("?" + NS,)),
    # ---- structure tricks -----------------------------------------------------------------
    ("Must be a U.S.\ncitizen.", ("?" + CIT,)),
    ("Applicants must be enrolled in a\nbachelor's program.", E),
    ("Requirements:\n• Must be 18 or older\n• Must be a U.S. citizen", ("AGE18", CIT)),
    ("Must be 18 or older; mentors must be 25 or older.", ("AGE18",)),
    ("Must be a U.S. citizen (some exceptions apply).", E),
    ("MUST BE ENROLLED IN AN UNDERGRADUATE PROGRAM.", ("EDU:undergraduate",)),
    ("Must be pursuing a bachelor’s degree.", ("EDU:undergraduate",)),
    ("Must be at least 18 years old.", ("AGE18",)),
    ("Must be at least 18 years old — or older.", ("?AGE18",)),
    ("Must be a U.S. citizen – required for the defense program.", ("?" + CIT,)),
]


@pytest.mark.parametrize("text,expected", CASES, ids=[c[0][:70] for c in CASES])
def test_attack(text: str, expected: tuple[str, ...]) -> None:
    required = {e for e in expected if not e.startswith("?")}
    allowed = required | {e[1:] for e in expected if e.startswith("?")}
    got = run(text)
    assert required <= got <= allowed, (sorted(got), sorted(expected))


def test_long_sentence_excerpt_window() -> None:
    filler = "this is a very long descriptive sentence about the team, " * 15
    text = f"{filler}and applicants must be at least 18 years old, {filler}"
    proposals = extract_requirements(ExtractionInput(title="T", description=text))
    assert [sig(p) for p in proposals] == ["AGE18"]
    assert len(proposals[0].source_text) <= MAX_EXCERPT_CHARS
    assert "at least 18" in proposals[0].source_text


def test_duplicate_requirement_title_and_description_dedupes() -> None:
    got = extract_requirements(
        ExtractionInput(title="Intern (U.S. Citizens Only)", description="Must be a U.S. citizen.")
    )
    assert [sig(p) for p in got] == [CIT]


def test_contradictory_ages_both_hold() -> None:
    assert run("Must be 18 or older. Must be 16 or older.") == {"AGE18", "AGE16"}


def test_unicode_lookalike_and_fullwidth_do_not_crash() -> None:
    assert run("Must be a У.S. citizen") == set()
    run("Must be １８ or older.")
    run("")
    run("\x00\x00 must be a U.S. citizen ")


@pytest.mark.parametrize("space", [" ", "\t", " "])
def test_long_whitespace_run_is_linear(space: str) -> None:
    # A provider's plain-text description can hold a huge whitespace run; the sentence splitter
    # used to backtrack quadratically over it (50,000 spaces took ~140 s).
    import time

    text = "Must be 18 or older." + space * 50_000 + "Applicants must be U.S. citizens."
    started = time.perf_counter()
    proposals = extract_requirements(ExtractionInput(title="T", description=text))
    assert time.perf_counter() - started < 2
    assert {p.requirement_type.value for p in proposals} >= {"minimum_age", "citizenship"}
