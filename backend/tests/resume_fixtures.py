"""Synthetic résumé fixtures shared by parser and (future) API tests. Everything here is
fabricated: no real person, no real employer, no real school (ADR-011; CLAUDE.md public-repo
safety)."""

# Covers: contact header (must be ignored), a Summary section (must be ignored and must end
# before Skills content leaks into it), every alias family, a "Label: ..." skill line, an
# entry section with bullet continuations, an Education entry, and a duplicate skill to
# exercise dedupe.
SYNTHETIC_RESUME_TEXT = """\
Synthetic Student
synthetic.student@example.com | (555) 010-1234 | example.com/in/synthetic

Summary
Motivated synthetic student seeking a synthetic internship.

Skills
Python, Java, SQL
Languages: JavaScript, TypeScript
- Git

Relevant Coursework
AP Computer Science A, Data Structures; Linear Algebra

Projects
Synthetic Robot Arm
- Built a controller in Python
- Tested it

Research
Synthetic Lab Assistant
- Studied synthetic materials under a synthetic advisor.

Experience
Example Corp — Synthetic Intern
- Wrote synthetic reports
- Reviewed synthetic code

Activities & Leadership
Synthetic Robotics Club — Captain
- Led a team of five

Awards
Synthetic Merit Award

Education
Synthetic High School — Class of 2027

Skills
Python
"""

# A short synthetic résumé, one line per PDF page/line, for make_text_pdf-based tests.
SYNTHETIC_RESUME_PDF_LINES = [
    "Synthetic Student",
    "Skills",
    "Python, Java, SQL",
    "Projects",
    "Synthetic Robot Arm",
    "- Built a controller in Python",
]


def _pdf_escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def make_text_pdf(lines: list[str], page_breaks: set[int] | None = None) -> bytes:
    """Hand-build a minimal, valid single- or multi-page PDF (Helvetica Type1 font, BT/ET Tj
    text operators) that pypdf can extract text from.

    `page_breaks` is a set of indices into `lines`: a new page starts before `lines[i]` for each
    `i` in that set. Without it, everything goes on one page.
    """
    page_breaks = page_breaks or set()
    pages: list[list[str]] = [[]]
    for index, line in enumerate(lines):
        if index in page_breaks:
            pages.append([])
        pages[-1].append(line)

    objects: list[bytes] = []

    def add_object(body: bytes) -> int:
        objects.append(body)
        return len(objects)  # 1-indexed PDF object number

    font_obj = add_object(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    )

    content_obj_numbers: list[int] = []
    page_obj_numbers: list[int] = []
    # Reserve object numbers for pages before writing content streams that reference them via
    # the pages tree (pages tree itself is written after, so we pre-allocate).
    for page_lines in pages:
        stream_lines = ["BT", "/F1 12 Tf", "14 TL", "72 750 Td"]
        for i, line in enumerate(page_lines):
            if i > 0:
                stream_lines.append("T*")
            stream_lines.append(f"({_pdf_escape(line)}) Tj")
        stream_lines.append("ET")
        stream = "\n".join(stream_lines).encode("latin-1")
        content_obj_numbers.append(
            add_object(
                b"<< /Length "
                + str(len(stream)).encode("ascii")
                + b" >>\nstream\n"
                + stream
                + b"\nendstream"
            )
        )

    pages_obj_number = len(objects) + 1 + len(pages)  # placeholder, fixed below after page objs

    for content_number in content_obj_numbers:
        page_obj_numbers.append(
            add_object(
                b"<< /Type /Page /Parent "
                + str(pages_obj_number).encode("ascii")
                + b" 0 R /Resources << /Font << /F1 "
                + str(font_obj).encode("ascii")
                + b" 0 R >> >> /MediaBox [0 0 612 792] /Contents "
                + str(content_number).encode("ascii")
                + b" 0 R >>"
            )
        )

    kids = b" ".join(f"{n} 0 R".encode("ascii") for n in page_obj_numbers)
    pages_obj_number_actual = add_object(
        b"<< /Type /Pages /Kids [" + kids + b"] /Count " + str(len(pages)).encode("ascii") + b" >>"
    )
    assert pages_obj_number_actual == pages_obj_number

    catalog_obj = add_object(
        b"<< /Type /Catalog /Pages " + str(pages_obj_number).encode("ascii") + b" 0 R >>"
    )

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0] * (len(objects) + 1)
    for number, body in enumerate(objects, start=1):
        offsets[number] = len(out)
        out += str(number).encode("ascii") + b" 0 obj\n" + body + b"\nendobj\n"

    xref_offset = len(out)
    out += b"xref\n0 " + str(len(objects) + 1).encode("ascii") + b"\n"
    out += b"0000000000 65535 f \n"
    for number in range(1, len(objects) + 1):
        out += f"{offsets[number]:010d} 00000 n \n".encode("ascii")
    out += (
        b"trailer\n<< /Size "
        + str(len(objects) + 1).encode("ascii")
        + b" /Root "
        + str(catalog_obj).encode("ascii")
        + b" 0 R >>\nstartxref\n"
        + str(xref_offset).encode("ascii")
        + b"\n%%EOF"
    )
    return bytes(out)


def make_encrypted_pdf() -> bytes:
    """A minimal single-page PDF encrypted with pypdf's own writer, for the encrypted-PDF test."""
    import io

    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt(user_password="synthetic-password")
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def make_flate_bomb_pdf(decompressed_bytes: int = 70 * 1024 * 1024) -> bytes:
    """A small PDF whose one content stream inflates to `decompressed_bytes` of text operators:
    under pypdf's own inflate cap, but far too much to interpret in the request (ADR-011 §2)."""
    import io

    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    operator = b"BT /F1 12 Tf 72 700 Td (Synthetic) Tj ET\n"
    stream = DecodedStreamObject()
    stream.set_data(operator * (decompressed_bytes // len(operator)))
    writer = PdfWriter()
    page = writer.add_blank_page(612, 792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}  # pyright: ignore[reportPrivateUsage]
    )
    page[NameObject("/Contents")] = writer._add_object(stream.flate_encode())  # pyright: ignore[reportPrivateUsage]
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
