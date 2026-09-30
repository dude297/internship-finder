"""Adversarial coverage for profile source ingestion (ADR-011), beyond
test_api_profile_sources.py: real/malformed/encrypted PDFs, content-type spoofing, XSS-shaped
fact names, filename/header injection, error/log leakage of uploaded text, cross-source fact
ids, eligibility-fact isolation, batch catalog passes, cross-source skill survival, and parser
version bumps. Synthetic data only."""

import logging
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import FactCategory, FactReviewState
from app.models import OpportunityEvaluation, Profile, ProfileFact, ProfileSourceArtifact
from app.profile import resume_parser
from tests.resume_fixtures import (
    SYNTHETIC_RESUME_PDF_LINES,
    make_encrypted_pdf,
    make_text_pdf,
)
from tests.test_api_fit import put_match
from tests.test_api_profile_sources import (
    _fact_id,  # pyright: ignore[reportPrivateUsage]
    resume_bytes,
    upload,
    upload_ok,
)
from tests.test_api_workflow import count, create, put_profile

pytestmark = pytest.mark.postgres

SOURCES = "/api/profile/sources"

# A marker string that stands in for the applicant's private contact line. It must never leak
# into an API response body or a log record, no matter what happens to the upload.
SECRET_MARKER = "SynthAdversarialContactLine-do-not-leak"


def resume_with_marker() -> bytes:
    return f"Objective\n{SECRET_MARKER}\n\nSkills\nSynthetic Skill\n".encode()


# --- Real and malformed PDFs --------------------------------------------------------------------


def test_real_pdf_upload_extracts_facts(client: TestClient) -> None:
    pdf = make_text_pdf(SYNTHETIC_RESUME_PDF_LINES)
    body = upload_ok(client, data=pdf, filename="synthetic.pdf", content_type="application/pdf")
    assert body["content_type"] == "application/pdf"
    assert any(f["name"] == "Python" for f in body["facts"])
    assert any(f["name"] == "Synthetic Robot Arm" for f in body["facts"])


def test_malformed_pdf_is_generic_422(client: TestClient) -> None:
    data = b"%PDF-1.4\nthis is not a real pdf body at all\n%%EOF"
    response = upload(client, data=data, filename="broken.pdf", content_type="application/pdf")
    assert response.status_code == 422
    assert response.json()["detail"] == "Couldn't read that PDF."


def test_encrypted_pdf_is_422(client: TestClient) -> None:
    data = make_encrypted_pdf()
    response = upload(client, data=data, filename="locked.pdf", content_type="application/pdf")
    assert response.status_code == 422
    assert response.json()["detail"] == "Password-protected PDFs aren't supported."


def test_pdf_bytes_with_txt_extension_are_still_detected_as_pdf(client: TestClient) -> None:
    pdf = make_text_pdf(["Skills", "Python"])
    body = upload_ok(client, data=pdf, filename="not-really.txt", content_type="text/plain")
    assert body["content_type"] == "application/pdf"


def test_text_bytes_with_pdf_extension_are_detected_as_text(client: TestClient) -> None:
    body = upload_ok(
        client,
        data=b"Skills\nSynthetic Skill\n",
        filename="not-really.pdf",
        content_type="application/pdf",
    )
    assert body["content_type"] == "text/plain"


# --- Stored-as-plain-text, never rendered --------------------------------------------------------


def test_html_in_a_fact_name_is_stored_and_returned_verbatim(client: TestClient) -> None:
    payload = "<img src=x onerror=alert(1)>Synthetic"
    body = upload_ok(client, data=f"Skills\n{payload}\n".encode())
    [fact] = body["facts"]
    assert fact["name"] == payload  # verbatim: no server-side escaping/rendering


# --- Filename and header safety -------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw_name",
    [
        "../../../etc/passwd",
        "..\\..\\windows\\system32\\config",
        "resume\x00.txt",
        "resume‮.txt",  # RTL override
    ],
)
def test_path_traversal_and_control_char_filenames_are_sanitized(
    client: TestClient, raw_name: str
) -> None:
    body = upload_ok(client, filename=raw_name)
    stored = body["original_filename"]
    assert stored is None or ("/" not in stored and "\\" not in stored)
    assert stored is None or all(ch not in "\x00‮" for ch in stored)


@pytest.mark.parametrize(
    "raw_name",
    ['resume".txt', "resume\r\nX-Injected: 1.txt", 'a"; filename="b.txt'],
)
def test_content_disposition_cannot_be_header_injected(client: TestClient, raw_name: str) -> None:
    created = upload_ok(client, filename=raw_name)
    response = client.get(f"{SOURCES}/{created['id']}/file")
    assert response.status_code == 200
    disposition = response.headers["content-disposition"]
    assert "\r" not in disposition and "\n" not in disposition
    # The quoted ASCII fallback name never contains an unescaped quote or backslash.
    quoted = disposition.split('filename="', 1)[1].split('"; filename*=')[0]
    assert '"' not in quoted and "\\" not in quoted
    assert "X-Injected" not in response.headers


# --- Errors and logs never leak uploaded text -----------------------------------------------------


def _all_response_text(response: Any) -> str:
    return response.text


def test_error_responses_never_contain_uploaded_text(client: TestClient) -> None:
    # Force a 422 (malformed PDF) whose bytes also contain the marker.
    data = b"%PDF-1.4\n" + SECRET_MARKER.encode() + b"\nnot a real pdf\n%%EOF"
    response = upload(client, data=data, filename="broken.pdf", content_type="application/pdf")
    assert response.status_code == 422
    assert SECRET_MARKER not in _all_response_text(response)


def test_list_and_detail_never_contain_raw_text_beyond_fact_fields(
    client: TestClient,
) -> None:
    created = upload_ok(client, data=resume_with_marker())
    detail = client.get(f"{SOURCES}/{created['id']}").json()
    listing = client.get(SOURCES).json()
    assert SECRET_MARKER not in str(created)
    assert SECRET_MARKER not in str(detail)
    assert SECRET_MARKER not in str(listing)


def test_artifact_bytes_are_only_served_by_the_file_route(client: TestClient) -> None:
    created = upload_ok(client, data=resume_with_marker())
    detail_response = client.get(f"{SOURCES}/{created['id']}")
    list_response = client.get(SOURCES)
    assert SECRET_MARKER not in detail_response.text
    assert SECRET_MARKER not in list_response.text
    file_response = client.get(f"{SOURCES}/{created['id']}/file")
    assert SECRET_MARKER.encode() in file_response.content


def test_uploaded_text_never_appears_in_logs(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    created = upload_ok(client, data=resume_with_marker())
    fact_id = _fact_id(created, "Synthetic Skill")
    client.post(
        f"{SOURCES}/{created['id']}/review", json={"accept": [{"id": fact_id}], "reject": []}
    )
    client.post(f"{SOURCES}/{created['id']}/reparse")
    client.delete(f"{SOURCES}/{created['id']}")

    # A failed parse too: same marker, bad PDF bytes.
    bad = b"%PDF-1.4\n" + SECRET_MARKER.encode() + b"\nnope\n%%EOF"
    upload(client, data=bad, filename="broken.pdf", content_type="application/pdf")

    for record in caplog.records:
        assert SECRET_MARKER not in record.getMessage()


# --- Cross-source and cross-category isolation ----------------------------------------------------


def test_cross_source_fact_id_in_review_is_404(client: TestClient) -> None:
    mine = upload_ok(client, data=resume_bytes("Synthetic Skill"))
    other = upload_ok(client, data=resume_bytes("Other Skill"), filename="other.txt")
    other_fact_id = _fact_id(other, "Other Skill")
    response = client.post(
        f"{SOURCES}/{mine['id']}/review",
        json={"accept": [{"id": other_fact_id}], "reject": []},
    )
    assert response.status_code == 404


def test_accepting_an_education_fact_never_changes_the_profile_row(
    client: TestClient, db: Session
) -> None:
    put_profile(client)
    before = client.get("/api/profile").json()

    created = upload_ok(client, data=b"Education\nSynthetic High School\n")
    fact_id = created["facts"][0]["id"]
    assert created["facts"][0]["category"] == "education"

    response = client.post(
        f"{SOURCES}/{created['id']}/review", json={"accept": [{"id": fact_id}], "reject": []}
    )
    assert response.status_code == 200, response.text
    assert response.json()["catalog_pass"] is False  # education isn't a fit category

    after = client.get("/api/profile").json()
    assert after == before


# --- Batching -------------------------------------------------------------------------------------


def test_150_pending_facts_accepted_in_one_batch_is_one_catalog_pass(
    client: TestClient, db: Session
) -> None:
    put_profile(client)
    opportunities = [
        create(client, title=f"Synthetic Batch150 {n}", requirements_assessment_status="complete")
        for n in range(3)
    ]
    skills = [f"BatchSkill{n:03d}" for n in range(150)]
    created = upload_ok(client, data=resume_bytes(*skills))
    assert len(created["facts"]) == 150
    accept = [{"id": f["id"]} for f in created["facts"]]

    before = count(db, OpportunityEvaluation)
    response = client.post(
        f"{SOURCES}/{created['id']}/review", json={"accept": accept, "reject": []}
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["evaluated_opportunities"] == len(opportunities)
    # One catalog pass evaluates each opportunity once, not once per accepted fact.
    assert count(db, OpportunityEvaluation) == before + len(opportunities)


# --- Delete keeps a skill accepted via another source --------------------------------------------


def test_deleting_a_source_keeps_a_skill_also_accepted_via_another_source(
    client: TestClient, db: Session
) -> None:
    put_profile(client)
    opp = create(
        client,
        description="Looking for Shared Skill experience.",
        requirements_assessment_status="complete",
    )

    first = upload_ok(client, data=resume_bytes("Shared Skill"), filename="first.txt")
    first_fact_id = _fact_id(first, "Shared Skill")
    client.post(
        f"{SOURCES}/{first['id']}/review", json={"accept": [{"id": first_fact_id}], "reject": []}
    )

    # A second source's copy of the same skill is skipped as a candidate (already accepted), so
    # exercise the "another source accepted it" path via a manually inserted accepted fact on a
    # second source instead of relying on candidate extraction.
    second = upload_ok(client, data=resume_bytes("Second Source Skill"), filename="second.txt")
    profile = db.scalars(select(Profile)).one()
    also_shared = ProfileFact(
        profile_id=profile.id,
        profile_source_id=uuid.UUID(second["id"]),
        category=FactCategory.SKILL,
        fact_key="resume.999",
        value={"name": "Shared Skill"},
        source_kind=first["kind"],
        extraction_method="deterministic_parser",
        extractor_name="resume-sections",
        extractor_version="1",
        review_state=FactReviewState.ACCEPTED,
        verified_by_user=True,
    )
    db.add(also_shared)
    db.commit()

    response = client.delete(f"{SOURCES}/{first['id']}")
    assert response.status_code == 200, response.text

    after = client.get(f"/api/opportunities/{opp['id']}").json()["latest_evaluation"][
        "score_breakdown"
    ]["components"]["technical"]
    assert "Shared Skill" in after["matched"]


# --- Reparse after a parser version bump ---------------------------------------------------------


def test_reparse_after_parser_version_bump_updates_version_without_duplicating(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = upload_ok(client, data=resume_bytes("Kept Skill"))
    fact_id = _fact_id(created, "Kept Skill")
    client.post(
        f"{SOURCES}/{created['id']}/review", json={"accept": [{"id": fact_id}], "reject": []}
    )
    assert created["parser_version"] == resume_parser.PARSER_VERSION

    monkeypatch.setattr(resume_parser, "PARSER_VERSION", "2")
    import app.services.profile_sources as service

    monkeypatch.setattr(service, "PARSER_VERSION", "2")

    response = client.post(f"{SOURCES}/{created['id']}/reparse")
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["parser_version"] == "2"
    names = [f["name"] for f in detail["facts"]]
    assert names.count("Kept Skill") == 1  # the accepted fact wasn't duplicated

    fact_keys = db.scalars(
        select(ProfileFact.fact_key)
        .where(ProfileFact.profile_source_id == uuid.UUID(created["id"]))
        .order_by(ProfileFact.fact_key)
    ).all()
    assert len(fact_keys) == len(set(fact_keys))


# --- Sanity: skip-already-accepted respects other sources too ------------------------------------


def test_upload_skips_candidate_accepted_via_a_different_source(client: TestClient) -> None:
    put_match(client, skills=["Cross Source Skill"])
    created = upload_ok(client, data=resume_bytes("Cross Source Skill", "Fresh Skill"))
    names = [f["name"] for f in created["facts"]]
    assert names == ["Fresh Skill"]


def test_artifact_row_removed_on_delete(client: TestClient, db: Session) -> None:
    created = upload_ok(client, data=resume_bytes("Synthetic Skill"))
    source_id = uuid.UUID(created["id"])
    assert db.get(ProfileSourceArtifact, source_id) is not None
    client.delete(f"{SOURCES}/{source_id}")
    assert db.get(ProfileSourceArtifact, source_id) is None
