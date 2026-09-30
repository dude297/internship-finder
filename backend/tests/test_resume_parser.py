"""Unit tests for app.profile.resume_parser (ADR-011 §2, §6, §7). No DB, no `postgres` marker:
this parser is pure (bytes in, candidates out)."""

import multiprocessing
import threading
import time
from typing import Any

import pytest

from app.enums import FactCategory
from app.profile import resume_parser
from app.profile.resume_parser import (
    APPLICATION_PDF,
    MAX_CANDIDATES,
    MAX_UPLOAD_BYTES,
    TEXT_PLAIN,
    Candidate,
    ParsedDocument,
    ParserBusy,
    UnreadableFile,
    UnsupportedFileType,
    extract_candidates,
    parse_document,
)
from tests.resume_fixtures import (
    SYNTHETIC_RESUME_PDF_LINES,
    SYNTHETIC_RESUME_TEXT,
    exit_immediately_worker,
    garbled_reply_worker,
    make_encrypted_pdf,
    make_flate_bomb_pdf,
    make_text_pdf,
)

# --- Sniffing -----------------------------------------------------------------------------


def test_plain_text_is_parsed() -> None:
    doc = parse_document(SYNTHETIC_RESUME_TEXT.encode("utf-8"))
    assert doc.content_type == TEXT_PLAIN
    assert len(doc.candidates) > 0


def test_utf8_bom_is_accepted() -> None:
    data = b"\xef\xbb\xbf" + b"Skills\nPython\n"
    doc = parse_document(data)
    assert doc.content_type == TEXT_PLAIN
    assert doc.candidates == (Candidate(FactCategory.SKILL, "Python"),)


def test_nul_byte_is_unsupported() -> None:
    with pytest.raises(UnsupportedFileType) as excinfo:
        parse_document(b"Skills\nPython\x00Java\n")
    assert "Python" not in str(excinfo.value)
    assert "Java" not in str(excinfo.value)


def test_invalid_utf8_is_unsupported() -> None:
    # A lone 0x92 (a right single quote in Windows-1252, "smart apostrophe") isn't valid UTF-8.
    with pytest.raises(UnsupportedFileType):
        parse_document(b"Skills\nDon\x92t panic\n")


def test_fake_extension_is_irrelevant_png_magic_bytes() -> None:
    # The parser never sees a filename or Content-Type; only the bytes matter.
    with pytest.raises(UnsupportedFileType):
        parse_document(b"\x89PNG\r\n\x1a\n" + b"rest of a fake resume.png")


def test_empty_is_unreadable() -> None:
    with pytest.raises(UnreadableFile):
        parse_document(b"")


def test_whitespace_only_is_unreadable() -> None:
    with pytest.raises(UnreadableFile):
        parse_document(b"   \n\t\n  ")


def test_oversized_upload_is_rejected_defensively() -> None:
    # The API enforces MAX_UPLOAD_BYTES before calling the parser (ADR-011 §2); this is a
    # defensive backstop, so it's a ValueError, not one of the parser's public exceptions.
    with pytest.raises(ValueError):
        parse_document(b"a" * (MAX_UPLOAD_BYTES + 1))


def test_text_is_truncated_before_extraction() -> None:
    # 20,000 repeats is 160,000 chars, well past the 100,000-char cap: the tail is cut off
    # mid-item, but the first (deduped) "Python" is still there and nothing crashes or hangs.
    huge = "Skills\n" + ("Python, " * 20_000)
    doc = parse_document(huge.encode("utf-8"))
    assert doc.candidates[0] == Candidate(FactCategory.SKILL, "Python")
    assert len(doc.candidates) <= 2


# --- PDF ------------------------------------------------------------------------------------


def test_text_pdf_round_trips_through_pypdf() -> None:
    data = make_text_pdf(SYNTHETIC_RESUME_PDF_LINES)
    doc = parse_document(data)
    assert doc.content_type == APPLICATION_PDF
    assert Candidate(FactCategory.SKILL, "Python") in doc.candidates
    expected = Candidate(
        FactCategory.PROJECT, "Synthetic Robot Arm", "Built a controller in Python"
    )
    assert expected in doc.candidates


def test_malformed_pdf_is_unreadable_with_generic_message() -> None:
    with pytest.raises(UnreadableFile) as excinfo:
        parse_document(b"%PDF-1.7\n garbage, not a real pdf structure at all")
    assert str(excinfo.value) == "Couldn't read that PDF."


def test_truncated_pdf_is_unreadable() -> None:
    data = make_text_pdf(SYNTHETIC_RESUME_PDF_LINES)
    with pytest.raises(UnreadableFile):
        parse_document(data[: len(data) // 2])


def test_encrypted_pdf_is_unreadable() -> None:
    with pytest.raises(UnreadableFile) as excinfo:
        parse_document(make_encrypted_pdf())
    assert "password" in str(excinfo.value).lower()


def test_pdf_with_more_than_20_pages_only_reads_20() -> None:
    lines = [f"Page{index} unique marker text" for index in range(25)]
    data = make_text_pdf(lines, page_breaks=set(range(1, 25)))
    doc = parse_document(data)
    # None of the extracted candidates can come from page 21 onward, because reading stops at
    # page 20 (index 19).
    for candidate in doc.candidates:
        assert "Page20" not in candidate.name
        assert "Page21" not in candidate.name


def test_scanned_pdf_with_no_text_is_unreadable() -> None:
    data = make_text_pdf([])  # a page with no text at all
    with pytest.raises(UnreadableFile) as excinfo:
        parse_document(data)
    assert "Scanned" in str(excinfo.value)


def test_pdf_errors_never_contain_fixture_text() -> None:
    with pytest.raises(UnreadableFile) as excinfo:
        parse_document(b"%PDF-1.7\nnot really a pdf and definitely not SYNTHETIC_MARKER")
    assert "SYNTHETIC_MARKER" not in str(excinfo.value)


# --- Section detection: every alias family -------------------------------------------------


@pytest.mark.parametrize(
    "heading",
    [
        "Skills",
        "Technical Skills",
        "Technologies",
        "Skills & Technologies",
        "Tools",
        "Programming Languages",
        "Languages & Tools",
    ],
)
def test_skill_aliases(heading: str) -> None:
    candidates = extract_candidates(f"{heading}\nPython\n")
    assert candidates == (Candidate(FactCategory.SKILL, "Python"),)


@pytest.mark.parametrize(
    "heading", ["Coursework", "Relevant Coursework", "Courses", "Relevant Courses"]
)
def test_course_aliases(heading: str) -> None:
    candidates = extract_candidates(f"{heading}\nData Structures\n")
    assert candidates == (Candidate(FactCategory.COURSE, "Data Structures"),)


@pytest.mark.parametrize(
    "heading", ["Projects", "Personal Projects", "Selected Projects", "Academic Projects"]
)
def test_project_aliases(heading: str) -> None:
    candidates = extract_candidates(f"{heading}\nSynthetic Robot Arm\n")
    assert candidates == (Candidate(FactCategory.PROJECT, "Synthetic Robot Arm"),)


@pytest.mark.parametrize("heading", ["Research", "Research Experience"])
def test_research_aliases(heading: str) -> None:
    candidates = extract_candidates(f"{heading}\nSynthetic Lab\n")
    assert candidates == (Candidate(FactCategory.RESEARCH, "Synthetic Lab"),)


@pytest.mark.parametrize(
    "heading", ["Experience", "Work Experience", "Employment", "Professional Experience"]
)
def test_experience_aliases(heading: str) -> None:
    candidates = extract_candidates(f"{heading}\nExample Corp\n")
    assert candidates == (Candidate(FactCategory.EXPERIENCE, "Example Corp"),)


@pytest.mark.parametrize(
    "heading",
    [
        "Activities",
        "Leadership",
        "Activities & Leadership",
        "Leadership & Activities",
        "Extracurricular Activities",
        "Extracurriculars",
        "Volunteering",
        "Volunteer Experience",
    ],
)
def test_activity_aliases(heading: str) -> None:
    candidates = extract_candidates(f"{heading}\nSynthetic Robotics Club\n")
    assert candidates == (Candidate(FactCategory.ACTIVITY, "Synthetic Robotics Club"),)


@pytest.mark.parametrize(
    "heading", ["Awards", "Honors", "Honors & Awards", "Awards & Honors", "Achievements"]
)
def test_award_aliases(heading: str) -> None:
    candidates = extract_candidates(f"{heading}\nSynthetic Merit Award\n")
    assert candidates == (Candidate(FactCategory.AWARD, "Synthetic Merit Award"),)


def test_education_alias() -> None:
    candidates = extract_candidates("Education\nSynthetic High School\n")
    assert candidates == (Candidate(FactCategory.EDUCATION, "Synthetic High School"),)


def test_markdown_heading_and_ampersand_and_and_are_interchangeable() -> None:
    a = extract_candidates("## Skills & Technologies\nPython\n")
    b = extract_candidates("Skills and Technologies:\nPython\n")
    assert a == b == (Candidate(FactCategory.SKILL, "Python"),)


# --- List sections: splitting, labels, caps -------------------------------------------------


def test_list_splits_on_all_separators_and_line_breaks() -> None:
    text = "Skills\nPython, Java; C++ | Go • Rust · Kotlin\nSwift\n"
    candidates = extract_candidates(text)
    names = [c.name for c in candidates]
    assert names == ["Python", "Java", "C++", "Go", "Rust", "Kotlin", "Swift"]


def test_label_prefix_is_dropped() -> None:
    candidates = extract_candidates("Skills\nLanguages: Python, Java\n")
    assert candidates == (
        Candidate(FactCategory.SKILL, "Python"),
        Candidate(FactCategory.SKILL, "Java"),
    )


def test_long_label_is_not_treated_as_a_label() -> None:
    long_label = "A" * 31
    candidates = extract_candidates(f"Skills\n{long_label}: Python\n")
    # The "label" is over 30 chars, so nothing is stripped and the whole line (one item, no
    # separators) is kept as-is since it's within the 100-char skill cap.
    assert candidates == (Candidate(FactCategory.SKILL, f"{long_label}: Python"),)


def test_bulleted_list_line() -> None:
    candidates = extract_candidates("Skills\n- Python\n* Java\n• SQL\n")
    assert candidates == (
        Candidate(FactCategory.SKILL, "Python"),
        Candidate(FactCategory.SKILL, "Java"),
        Candidate(FactCategory.SKILL, "SQL"),
    )


def test_ap_course_with_internal_letter_is_one_item() -> None:
    candidates = extract_candidates("Coursework\nAP Computer Science A\n")
    assert candidates == (Candidate(FactCategory.COURSE, "AP Computer Science A"),)


def test_skill_over_100_chars_is_dropped_not_truncated() -> None:
    too_long = "x" * 101
    candidates = extract_candidates(f"Skills\nPython, {too_long}\n")
    assert candidates == (Candidate(FactCategory.SKILL, "Python"),)


def test_course_over_150_chars_is_dropped_not_truncated() -> None:
    too_long = "y" * 151
    candidates = extract_candidates(f"Coursework\n{too_long}\n")
    assert candidates == ()


def test_empty_list_items_are_dropped() -> None:
    candidates = extract_candidates("Skills\nPython,, , Java\n")
    assert candidates == (
        Candidate(FactCategory.SKILL, "Python"),
        Candidate(FactCategory.SKILL, "Java"),
    )


# --- Entry sections: name/description, truncation -------------------------------------------


def test_entry_with_bullet_description() -> None:
    text = "Projects\nSynthetic Robot Arm\n- Built a controller in Python\n- Tested it\n"
    candidates = extract_candidates(text)
    expected_description = "Built a controller in Python Tested it"
    assert candidates == (
        Candidate(FactCategory.PROJECT, "Synthetic Robot Arm", expected_description),
    )


def test_entry_without_bullets_has_no_description() -> None:
    candidates = extract_candidates("Projects\nSynthetic Robot Arm\n")
    assert candidates == (Candidate(FactCategory.PROJECT, "Synthetic Robot Arm", None),)


def test_blank_line_ends_an_entry() -> None:
    text = "Projects\nFirst Project\n- Did a thing\n\nSecond Project\n- Did another thing\n"
    candidates = extract_candidates(text)
    assert candidates == (
        Candidate(FactCategory.PROJECT, "First Project", "Did a thing"),
        Candidate(FactCategory.PROJECT, "Second Project", "Did another thing"),
    )


def test_entry_name_over_150_chars_is_truncated_at_word_boundary() -> None:
    name = ("word " * 40).strip()  # 40 words * 5 chars - 1 = 199 chars, well over 150
    candidates = extract_candidates(f"Projects\n{name}\n")
    assert len(candidates) == 1
    assert len(candidates[0].name) <= 150
    assert not candidates[0].name.endswith(" ")
    assert candidates[0].name == name[:150].rsplit(" ", 1)[0]


def test_entry_description_over_2000_chars_is_truncated_at_word_boundary() -> None:
    bullet_text = "word " * 500  # 2500 chars, one bullet line
    text = f"Projects\nBig Project\n- {bullet_text.strip()}\n"
    candidates = extract_candidates(text)
    assert len(candidates) == 1
    description = candidates[0].description
    assert description is not None
    assert len(description) <= 2000
    assert not description.endswith(" ")


def test_unknown_heading_ends_section_and_is_not_extracted() -> None:
    text = "Experience\nExample Corp\n- Did work\n\nReferences\nAvailable upon request.\n"
    candidates = extract_candidates(text)
    assert candidates == (Candidate(FactCategory.EXPERIENCE, "Example Corp", "Did work"),)


def test_text_outside_sections_is_ignored() -> None:
    text = "Synthetic Student\nsynthetic.student@example.com\n(555) 010-1234\n\nSkills\nPython\n"
    candidates = extract_candidates(text)
    assert candidates == (Candidate(FactCategory.SKILL, "Python"),)


def test_summary_section_is_ignored() -> None:
    text = "Summary\nA motivated synthetic student.\n\nSkills\nPython\n"
    candidates = extract_candidates(text)
    assert candidates == (Candidate(FactCategory.SKILL, "Python"),)


def test_education_entry_is_informational_only() -> None:
    candidates = extract_candidates("Education\nSynthetic High School — Class of 2027\n")
    assert candidates == (
        Candidate(FactCategory.EDUCATION, "Synthetic High School — Class of 2027"),
    )


def test_no_dob_citizenship_or_work_authorization_terms_are_ever_produced() -> None:
    # The parser has no concept of these fields at all; this just documents and locks that in.
    text = (
        "Education\nDate of Birth: 2007-01-01, Citizenship: Exampleland, Work Authorization: Yes\n"
    )
    candidates = extract_candidates(text)
    assert len(candidates) == 1
    assert candidates[0].category == FactCategory.EDUCATION
    # It's captured as an opaque, informational education entry name/description only; nothing
    # is ever written back to eligibility fields (the parser never touches `profiles`).


# --- Dedupe, caps, determinism ----------------------------------------------------------------


def test_dedupe_case_insensitive_keeps_first_in_document_order() -> None:
    text = "Skills\npython, Python, PYTHON, Java\n"
    candidates = extract_candidates(text)
    assert candidates == (
        Candidate(FactCategory.SKILL, "python"),
        Candidate(FactCategory.SKILL, "Java"),
    )


def test_more_than_200_candidates_are_capped() -> None:
    items = ", ".join(f"Skill{i}" for i in range(250))
    candidates = extract_candidates(f"Skills\n{items}\n")
    assert len(candidates) == MAX_CANDIDATES
    assert candidates[0].name == "Skill0"
    assert candidates[-1].name == "Skill199"


def test_same_bytes_twice_produce_equal_output() -> None:
    data = SYNTHETIC_RESUME_TEXT.encode("utf-8")
    assert parse_document(data) == parse_document(data)


def test_parsed_document_and_candidate_are_plain_value_objects() -> None:
    doc = parse_document(b"Skills\nPython\n")
    assert isinstance(doc, ParsedDocument)
    assert isinstance(doc.candidates[0], Candidate)
    with pytest.raises(AttributeError):
        doc.candidates[0].name = "changed"  # type: ignore[misc]


def test_decompression_bomb_pdf_is_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 0.2 MB PDF whose content stream inflates to 70 MB: extraction runs in a child process
    that is killed at the time limit (or, on Linux, stopped by its memory limit)."""
    monkeypatch.setattr(resume_parser, "PDF_TIMEOUT_SECONDS", 3.0)
    data = make_flate_bomb_pdf()
    assert len(data) < MAX_UPLOAD_BYTES
    started = time.monotonic()
    with pytest.raises(UnreadableFile) as caught:
        parse_document(data)
    assert time.monotonic() - started < 10
    assert str(caught.value) in {"That PDF took too long to read.", "Couldn't read that PDF."}
    assert not resume_parser._PDF_SLOT.locked()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    # The slot was released: a normal PDF parses right after, with the real (unpatched) timeout.
    monkeypatch.setattr(resume_parser, "PDF_TIMEOUT_SECONDS", 15.0)
    doc = parse_document(make_text_pdf(SYNTHETIC_RESUME_PDF_LINES))
    assert doc.content_type == APPLICATION_PDF
    assert not resume_parser._PDF_SLOT.locked()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]


# --- Single-PDF-at-a-time slot (Render Free: ~512 MB host, one worker) -----------------------


def test_second_concurrent_pdf_is_rejected_without_spawning_a_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered = threading.Event()
    release = threading.Event()
    calls: list[bytes] = []

    def fake_run_pdf_child(data: bytes) -> str:
        calls.append(data)
        entered.set()
        assert release.wait(timeout=5)
        return "Skills\nPython\n"

    monkeypatch.setattr(resume_parser, "_run_pdf_child", fake_run_pdf_child)

    result: dict[str, ParsedDocument] = {}

    def run_first() -> None:
        result["doc"] = parse_document(b"%PDF-1.4\nfirst")

    thread = threading.Thread(target=run_first)
    thread.start()
    try:
        assert entered.wait(timeout=5)

        with pytest.raises(ParserBusy) as excinfo:
            parse_document(b"%PDF-1.4\nsecond")
        assert str(excinfo.value) == "Another PDF is being processed. Try again shortly."
        assert len(calls) == 1  # no second child was spawned

        release.set()
    finally:
        thread.join(timeout=5)
    assert not thread.is_alive()
    assert result["doc"].candidates == (Candidate(FactCategory.SKILL, "Python"),)
    assert not resume_parser._PDF_SLOT.locked()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    # The slot was released after success: a later PDF parses normally.
    calls.clear()
    release.clear()
    entered.clear()

    def fake_run_pdf_child_again(data: bytes) -> str:
        return "Skills\nJava\n"

    monkeypatch.setattr(resume_parser, "_run_pdf_child", fake_run_pdf_child_again)
    doc = parse_document(b"%PDF-1.4\nthird")
    assert doc.candidates == (Candidate(FactCategory.SKILL, "Java"),)
    assert not resume_parser._PDF_SLOT.locked()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]


def test_pdf_slot_is_released_after_unreadable_file(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run_pdf_child(data: bytes) -> str:
        raise UnreadableFile("Couldn't read that PDF.")

    monkeypatch.setattr(resume_parser, "_run_pdf_child", fake_run_pdf_child)
    with pytest.raises(UnreadableFile):
        parse_document(b"%PDF-1.4\nbad")
    assert not resume_parser._PDF_SLOT.locked()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]


def test_pdf_slot_is_released_after_an_unexpected_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Design decision: an exception from `_run_pdf_child` that isn't `UnreadableFile` (a bug,
    not a hostile-file outcome) propagates as-is rather than being wrapped or swallowed — the
    slot still must be released so the next request isn't permanently blocked."""

    def fake_run_pdf_child(data: bytes) -> str:
        raise RuntimeError("boom")

    monkeypatch.setattr(resume_parser, "_run_pdf_child", fake_run_pdf_child)
    with pytest.raises(RuntimeError, match="boom"):
        parse_document(b"%PDF-1.4\nbad")
    assert not resume_parser._PDF_SLOT.locked()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]


def test_text_parses_while_the_pdf_slot_is_held(monkeypatch: pytest.MonkeyPatch) -> None:
    """Text parsing is never gated by the PDF slot."""
    entered = threading.Event()
    release = threading.Event()

    def fake_run_pdf_child(data: bytes) -> str:
        entered.set()
        assert release.wait(timeout=5)
        return "Skills\nPython\n"

    monkeypatch.setattr(resume_parser, "_run_pdf_child", fake_run_pdf_child)
    thread = threading.Thread(target=lambda: parse_document(b"%PDF-1.4\nblocked"))
    thread.start()
    try:
        assert entered.wait(timeout=5)
        doc = parse_document(b"Skills\nJava\n")
        assert doc.content_type == TEXT_PLAIN
        assert doc.candidates == (Candidate(FactCategory.SKILL, "Java"),)
    finally:
        release.set()
        thread.join(timeout=5)


def test_pdf_slot_is_released_when_the_child_dies_without_reporting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real spawned child (not a fake) that exits without sending anything on the pipe: the
    parent sees EOF, raises the same generic UnreadableFile as any other child death, and
    releases the slot. `_pdf_worker` itself can't be monkeypatched here because the spawned
    child re-imports this module fresh; `exit_immediately_worker` is a module-level function in
    tests.resume_fixtures instead, importable by the child by qualified name."""
    real_run_pdf_child = resume_parser._run_pdf_child  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    def fake_run_pdf_child(data: bytes) -> str:
        return real_run_pdf_child(data, target=exit_immediately_worker)

    monkeypatch.setattr(resume_parser, "_run_pdf_child", fake_run_pdf_child)
    with pytest.raises(UnreadableFile) as excinfo:
        parse_document(b"%PDF-1.4\ndying")
    assert str(excinfo.value) == "Couldn't read that PDF."
    assert not resume_parser._PDF_SLOT.locked()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    monkeypatch.undo()
    doc = parse_document(make_text_pdf(SYNTHETIC_RESUME_PDF_LINES))
    assert doc.content_type == APPLICATION_PDF
    assert not resume_parser._PDF_SLOT.locked()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]


def test_garbled_child_reply_is_unreadable_and_releases_the_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_run_pdf_child = resume_parser._run_pdf_child  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    def fake_run_pdf_child(data: bytes) -> str:
        return real_run_pdf_child(data, target=garbled_reply_worker)

    monkeypatch.setattr(resume_parser, "_run_pdf_child", fake_run_pdf_child)
    with pytest.raises(UnreadableFile) as excinfo:
        parse_document(b"%PDF-1.4\ngarbled")
    assert str(excinfo.value) == "Couldn't read that PDF."
    assert not resume_parser._PDF_SLOT.locked()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]


def test_failed_child_start_closes_the_pipe_and_releases_the_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[str] = []
    context = multiprocessing.get_context("spawn")
    real_pipe = context.Pipe

    def tracking_pipe(duplex: bool = True) -> tuple[Any, Any]:
        receiver, sender = real_pipe(duplex)
        for name, end in (("receiver", receiver), ("sender", sender)):
            original = end.close

            def close(name: str = name, original: Any = original) -> None:
                closed.append(name)
                original()

            end.close = close
        return receiver, sender

    def failing_start(self: object) -> None:
        raise OSError("synthetic spawn failure")

    monkeypatch.setattr(context, "Pipe", tracking_pipe)
    monkeypatch.setattr(context.Process, "start", failing_start)
    with pytest.raises(OSError):
        parse_document(b"%PDF-1.4\nnever-started")
    assert sorted(closed) == ["receiver", "sender"]
    assert not resume_parser._PDF_SLOT.locked()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
