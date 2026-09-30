"""Profile source ingestion and review API (ADR-011). Synthetic data only."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import ExtractionMethod, FactCategory, FactReviewState, ProfileSourceKind
from app.models import OpportunityEvaluation, Profile, ProfileFact, ProfileSourceArtifact
from app.profile.resume_parser import MAX_UPLOAD_BYTES
from app.services.profile_sources import sanitize_filename
from tests.test_api_fit import put_match
from tests.test_api_workflow import count, create, put_profile

pytestmark = pytest.mark.postgres

SOURCES = "/api/profile/sources"
BOUNDARY = "xxxxSyntheticBoundaryxxxx"


def resume_bytes(*skills: str) -> bytes:
    return ("Skills\n" + ", ".join(skills) + "\n").encode()


def upload(
    client: TestClient,
    data: bytes = b"Skills\nSynthetic Skill\n",
    filename: str = "synthetic.txt",
    content_type: str = "text/plain",
) -> Any:
    return client.post(SOURCES, files={"file": (filename, data, content_type)})


def upload_ok(client: TestClient, **kwargs: Any) -> dict[str, Any]:
    response = upload(client, **kwargs)
    assert response.status_code == 201, response.text
    return response.json()


_UNSET = object()


def raw_upload(
    client: TestClient,
    data: bytes,
    *,
    content_length: Any = _UNSET,
    filename: str = "synthetic.txt",
    content_type: str = "text/plain",
) -> Any:
    """A hand-built multipart request, so the Content-Length header can be omitted or lied
    about independently of the actual body (httpx would otherwise always compute it)."""
    body = (
        (
            f"--{BOUNDARY}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode()
        + data
        + f"\r\n--{BOUNDARY}--\r\n".encode()
    )
    headers = {"content-type": f"multipart/form-data; boundary={BOUNDARY}"}
    request = client.build_request("POST", SOURCES, content=body, headers=headers)
    if content_length is None:
        del request.headers["content-length"]
    elif content_length is not _UNSET:
        request.headers["content-length"] = str(content_length)
    return client.send(request)


def pending_award(
    db: Session, profile: Profile, source_id: uuid.UUID, key: str = "resume.900"
) -> ProfileFact:
    fact = ProfileFact(
        profile_id=profile.id,
        profile_source_id=source_id,
        category=FactCategory.AWARD,
        fact_key=key,
        value={"name": "Synthetic Award", "description": None},
        source_kind=ProfileSourceKind.RESUME,
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_name="resume-sections",
        extractor_version="1",
        review_state=FactReviewState.PENDING,
        verified_by_user=False,
    )
    db.add(fact)
    db.flush()
    return fact


# --- Auth and CSRF -------------------------------------------------------------------------------


def test_every_route_requires_auth(anon_client: TestClient) -> None:
    fake_id = uuid.uuid4()
    assert anon_client.get(SOURCES).status_code == 401
    assert upload(anon_client).status_code == 401
    assert anon_client.get(f"{SOURCES}/{fake_id}").status_code == 401
    assert anon_client.get(f"{SOURCES}/{fake_id}/file").status_code == 401
    assert anon_client.post(f"{SOURCES}/{fake_id}/review", json={"accept": []}).status_code == 401
    assert anon_client.post(f"{SOURCES}/{fake_id}/reparse").status_code == 401
    assert anon_client.delete(f"{SOURCES}/{fake_id}").status_code == 401


def test_every_mutation_requires_csrf(client: TestClient) -> None:
    fake_id = uuid.uuid4()
    csrf = client.headers.pop("X-CSRF-Token")
    try:
        assert upload(client).status_code == 403
        assert client.post(f"{SOURCES}/{fake_id}/review", json={"accept": []}).status_code == 403
        assert client.post(f"{SOURCES}/{fake_id}/reparse").status_code == 403
        assert client.delete(f"{SOURCES}/{fake_id}").status_code == 403
    finally:
        client.headers["X-CSRF-Token"] = csrf


# --- Upload happy path -----------------------------------------------------------------------


def test_upload_creates_pending_facts_with_provenance(client: TestClient, db: Session) -> None:
    before = count(db, OpportunityEvaluation)
    body = upload_ok(client, data=resume_bytes("Synthetic Skill", "Another Skill"))

    assert body["kind"] == "resume"
    assert body["original_filename"] == "synthetic.txt"
    assert body["content_type"] == "text/plain"
    assert body["parser_name"] == "resume-sections"
    assert body["parser_version"] == "1"
    assert body["pending_count"] == 2
    assert body["accepted_count"] == 0
    assert body["rejected_count"] == 0
    names = [f["name"] for f in body["facts"]]
    assert names == ["Synthetic Skill", "Another Skill"]
    assert all(f["review_state"] == "pending" for f in body["facts"])

    facts = db.scalars(select(ProfileFact).order_by(ProfileFact.fact_key)).all()
    assert len(facts) == 2
    for fact in facts:
        assert fact.verified_by_user is False
        assert fact.source_kind is ProfileSourceKind.RESUME
        assert fact.extraction_method is ExtractionMethod.DETERMINISTIC_PARSER
        assert fact.extractor_name == "resume-sections"
        assert fact.extractor_version == "1"
        assert fact.category is FactCategory.SKILL
        assert fact.review_state is FactReviewState.PENDING

    # Pending facts don't affect fit: no catalog pass on upload.
    assert count(db, OpportunityEvaluation) == before


def test_list_has_counts_and_no_facts_or_content(client: TestClient) -> None:
    upload_ok(client, data=resume_bytes("Synthetic Skill"))
    response = client.get(SOURCES)
    assert response.status_code == 200
    [summary] = response.json()
    assert summary["pending_count"] == 1
    assert summary["accepted_count"] == 0
    assert summary["rejected_count"] == 0
    assert "facts" not in summary
    assert "content" not in summary


def test_detail_returns_facts_ordered_by_fact_key(client: TestClient) -> None:
    created = upload_ok(client, data=resume_bytes("B Skill", "A Skill"))
    source_id = created["id"]
    detail = client.get(f"{SOURCES}/{source_id}").json()
    assert [f["name"] for f in detail["facts"]] == ["B Skill", "A Skill"]  # parser order, not name


def test_response_never_echoes_raw_text_beyond_fact_names(client: TestClient) -> None:
    secret_line = "SynthPrivateObjectiveLineNotASkill"
    data = f"Objective\n{secret_line}\n\nSkills\nSynthetic Skill\n".encode()
    body = upload_ok(client, data=data)
    assert secret_line not in str(body)


# --- Size and type errors ---------------------------------------------------------------------


def test_upload_rejects_oversized_body_via_chunked_read(client: TestClient) -> None:
    # Real content and a matching header, both a little over the limit but under the
    # Content-Length overhead allowance: caught by the chunked read, not the header check.
    data = b"x" * (MAX_UPLOAD_BYTES + 10_000)
    response = upload(client, data=data)
    assert response.status_code == 413
    assert "larger than 2 MB" in response.json()["detail"]


def test_upload_rejects_lying_content_length_header_without_a_real_body(client: TestClient) -> None:
    response = raw_upload(client, data=b"tiny", content_length=50_000_000)
    assert response.status_code == 413


def test_upload_requires_content_length(client: TestClient) -> None:
    response = raw_upload(client, data=b"Skills\nX\n", content_length=None)
    assert response.status_code == 411
    assert response.json()["detail"] == "Content-Length is required."


@pytest.mark.parametrize("filename", ["synthetic.txt", "synthetic.png"])
def test_upload_rejects_non_utf8_binary_as_unsupported(client: TestClient, filename: str) -> None:
    png_magic = b"\x89PNG\r\n\x1a\n" + b"\xff" * 20
    response = upload(client, data=png_magic, filename=filename)
    assert response.status_code == 415


def test_upload_rejects_pdf_named_binary_as_unsupported(client: TestClient) -> None:
    response = upload(client, data=b"\xff\xfe\x00\x01binary", filename="resume.pdf")
    assert response.status_code == 415


def test_upload_rejects_empty_file(client: TestClient) -> None:
    response = upload(client, data=b"")
    assert response.status_code == 422


def test_upload_rejects_nul_bytes(client: TestClient) -> None:
    # The Milestone 5 parser scaffold treats embedded NUL bytes as not-plain-text (415), not as
    # unreadable text (422): it checks for `\x00` before decoding (app.profile.resume_parser).
    response = upload(client, data=b"Skills\nSynthetic\x00Skill\n")
    assert response.status_code == 415


def test_upload_duplicate_content_is_rejected(client: TestClient) -> None:
    data = resume_bytes("Synthetic Skill")
    first = upload(client, data=data, filename="a.txt")
    assert first.status_code == 201
    second = upload(client, data=data, filename="b.txt")
    assert second.status_code == 409
    assert second.json()["detail"] == "That file has already been uploaded."


# --- Filename sanitisation ---------------------------------------------------------------------


def test_filename_sanitisation() -> None:
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("dir\\sub\\file.txt") == "file.txt"
    assert sanitize_filename("na\x00me.txt") == "name.txt"
    assert sanitize_filename("x" * 300) == "x" * 255
    assert sanitize_filename("") is None
    assert sanitize_filename(None) is None


def test_upload_sanitises_the_stored_filename(client: TestClient) -> None:
    body = upload_ok(client, filename="../../etc/passwd")
    assert body["original_filename"] == "passwd"


# --- Download ----------------------------------------------------------------------------------


def test_download_returns_original_bytes_with_safe_headers(client: TestClient, db: Session) -> None:
    data = resume_bytes("Synthetic Skill")
    created = upload_ok(client, data=data, filename="synthetic résumé.txt")
    source_id = created["id"]

    response = client.get(f"{SOURCES}/{source_id}/file")
    assert response.status_code == 200
    assert response.content == data
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert "filename*=UTF-8''" in disposition
    assert "résumé" not in disposition.split(";")[1]  # the quoted fallback name is ASCII-only

    artifact = db.scalar(
        select(ProfileSourceArtifact).where(ProfileSourceArtifact.profile_source_id == source_id)
    )
    assert artifact is not None and artifact.content == data


def test_download_uses_a_fallback_name_when_none_was_kept(client: TestClient) -> None:
    created = upload_ok(client, filename="///")  # sanitizes to nothing (empty basename)
    assert created["original_filename"] is None
    response = client.get(f"{SOURCES}/{created['id']}/file")
    assert 'filename="profile-source.txt"' in response.headers["content-disposition"]


# --- Review --------------------------------------------------------------------------------------


def _fact_id(detail: dict[str, Any], name: str) -> str:
    return next(f["id"] for f in detail["facts"] if f["name"] == name)


def test_pending_facts_do_not_affect_fit(client: TestClient, db: Session) -> None:
    put_profile(client)
    opp = create(
        client,
        title="Synthetic Role",
        description="Looking for Synthetic Skill experience.",
        requirements_assessment_status="complete",
    )
    before = client.get(f"/api/opportunities/{opp['id']}").json()
    before_breakdown = before["latest_evaluation"]["score_breakdown"]

    upload_ok(client, data=resume_bytes("Synthetic Skill"))

    after = client.get(f"/api/opportunities/{opp['id']}").json()
    assert after["latest_evaluation"]["score_breakdown"] == before_breakdown


def test_accepting_a_fact_scores_it_with_one_catalog_pass(client: TestClient, db: Session) -> None:
    put_profile(client)
    opportunities = [
        create(
            client,
            title=f"Synthetic Role {n}",
            description="Looking for Synthetic Skill experience.",
            requirements_assessment_status="complete",
        )
        for n in range(3)
    ]
    created = upload_ok(client, data=resume_bytes("Synthetic Skill"))
    fact_id = _fact_id(created, "Synthetic Skill")

    before = count(db, OpportunityEvaluation)
    response = client.post(
        f"{SOURCES}/{created['id']}/review", json={"accept": [{"id": fact_id}], "reject": []}
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["catalog_pass"] is True
    assert result["evaluated_opportunities"] == 3
    assert count(db, OpportunityEvaluation) == before + 3

    [fact] = [f for f in result["source"]["facts"] if f["id"] == fact_id]
    assert fact["review_state"] == "accepted"
    db_fact = db.get(ProfileFact, uuid.UUID(fact_id))
    assert db_fact is not None and db_fact.verified_by_user is True

    technical = client.get(f"/api/opportunities/{opportunities[0]['id']}").json()[
        "latest_evaluation"
    ]["score_breakdown"]["components"]["technical"]
    assert technical["matched"] == ["Synthetic Skill"]


def test_rejecting_a_fact_excludes_it(client: TestClient, db: Session) -> None:
    put_profile(client)
    create(client, requirements_assessment_status="complete")
    created = upload_ok(client, data=resume_bytes("Synthetic Skill"))
    fact_id = _fact_id(created, "Synthetic Skill")

    response = client.post(
        f"{SOURCES}/{created['id']}/review", json={"accept": [], "reject": [fact_id]}
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["catalog_pass"] is False
    db_fact = db.get(ProfileFact, uuid.UUID(fact_id))
    assert db_fact is not None
    assert db_fact.review_state is FactReviewState.REJECTED
    assert db_fact.verified_by_user is False


def test_edit_and_accept_stores_the_edited_value(client: TestClient, db: Session) -> None:
    created = upload_ok(client, data=resume_bytes("Synthetic Skill"))
    fact_id = _fact_id(created, "Synthetic Skill")

    response = client.post(
        f"{SOURCES}/{created['id']}/review",
        json={"accept": [{"id": fact_id, "name": "Edited Synthetic Skill"}], "reject": []},
    )
    assert response.status_code == 200, response.text
    db_fact = db.get(ProfileFact, uuid.UUID(fact_id))
    assert db_fact is not None
    assert db_fact.value == {"name": "Edited Synthetic Skill"}


def test_review_with_only_non_fit_categories_has_no_catalog_pass(
    client: TestClient, db: Session
) -> None:
    put_profile(client)
    profile = db.scalars(select(Profile)).one()
    created = upload_ok(client, data=resume_bytes("Synthetic Skill"))
    award = pending_award(db, profile, uuid.UUID(created["id"]))
    db.commit()

    response = client.post(
        f"{SOURCES}/{created['id']}/review",
        json={"accept": [{"id": str(award.id)}], "reject": []},
    )
    assert response.status_code == 200, response.text
    assert response.json()["catalog_pass"] is False


def test_review_batch_evaluates_the_catalog_exactly_once(client: TestClient, db: Session) -> None:
    put_profile(client)
    opportunities = [
        create(client, title=f"Synthetic Batch {n}", requirements_assessment_status="complete")
        for n in range(4)
    ]
    created = upload_ok(client, data=resume_bytes("Skill One", "Skill Two", "Skill Three"))
    accept = [{"id": f["id"]} for f in created["facts"]]

    before = count(db, OpportunityEvaluation)
    response = client.post(
        f"{SOURCES}/{created['id']}/review", json={"accept": accept, "reject": []}
    )
    assert response.status_code == 200, response.text
    assert response.json()["evaluated_opportunities"] == len(opportunities)
    assert count(db, OpportunityEvaluation) == before + len(opportunities)


def test_review_transitions_between_accepted_and_rejected(client: TestClient, db: Session) -> None:
    put_profile(client)
    create(client, requirements_assessment_status="complete")
    created = upload_ok(client, data=resume_bytes("Synthetic Skill"))
    fact_id = _fact_id(created, "Synthetic Skill")

    accept = client.post(
        f"{SOURCES}/{created['id']}/review", json={"accept": [{"id": fact_id}], "reject": []}
    )
    assert accept.json()["catalog_pass"] is True

    to_rejected = client.post(
        f"{SOURCES}/{created['id']}/review", json={"accept": [], "reject": [fact_id]}
    )
    assert to_rejected.status_code == 200
    assert to_rejected.json()["catalog_pass"] is True  # it was accepted and fit-relevant

    back_to_accepted = client.post(
        f"{SOURCES}/{created['id']}/review", json={"accept": [{"id": fact_id}], "reject": []}
    )
    assert back_to_accepted.status_code == 200
    assert back_to_accepted.json()["catalog_pass"] is True


def test_review_id_from_another_source_is_not_found(client: TestClient) -> None:
    created = upload_ok(client, data=resume_bytes("Synthetic Skill"))
    other = upload_ok(client, data=resume_bytes("Other Skill"), filename="other.txt")
    other_fact_id = _fact_id(other, "Other Skill")

    response = client.post(
        f"{SOURCES}/{created['id']}/review", json={"accept": [{"id": other_fact_id}], "reject": []}
    )
    assert response.status_code == 404


def test_review_empty_body_is_rejected(client: TestClient) -> None:
    created = upload_ok(client, data=resume_bytes("Synthetic Skill"))
    response = client.post(f"{SOURCES}/{created['id']}/review", json={"accept": [], "reject": []})
    assert response.status_code == 422


def test_review_description_on_skill_is_rejected(client: TestClient) -> None:
    created = upload_ok(client, data=resume_bytes("Synthetic Skill"))
    fact_id = _fact_id(created, "Synthetic Skill")
    response = client.post(
        f"{SOURCES}/{created['id']}/review",
        json={"accept": [{"id": fact_id, "description": "nope"}], "reject": []},
    )
    assert response.status_code == 422


def test_review_name_too_long_is_rejected(client: TestClient) -> None:
    created = upload_ok(client, data=resume_bytes("Synthetic Skill"))
    fact_id = _fact_id(created, "Synthetic Skill")
    response = client.post(
        f"{SOURCES}/{created['id']}/review",
        json={"accept": [{"id": fact_id, "name": "x" * 101}], "reject": []},
    )
    assert response.status_code == 422


def test_review_duplicate_ids_across_accept_and_reject_is_rejected(client: TestClient) -> None:
    created = upload_ok(client, data=resume_bytes("Synthetic Skill"))
    fact_id = _fact_id(created, "Synthetic Skill")
    response = client.post(
        f"{SOURCES}/{created['id']}/review",
        json={"accept": [{"id": fact_id}], "reject": [fact_id]},
    )
    assert response.status_code == 422


def test_review_unknown_id_is_not_found(client: TestClient) -> None:
    created = upload_ok(client, data=resume_bytes("Synthetic Skill"))
    response = client.post(
        f"{SOURCES}/{created['id']}/review",
        json={"accept": [{"id": str(uuid.uuid4())}], "reject": []},
    )
    assert response.status_code == 404


# --- Upload skips already-accepted facts --------------------------------------------------------


def test_upload_skips_candidates_already_accepted_via_match_profile(client: TestClient) -> None:
    put_match(client, skills=["Synthetic Overlap"])
    created = upload_ok(client, data=resume_bytes("Synthetic Overlap", "New Skill"))
    names = [f["name"] for f in created["facts"]]
    assert names == ["New Skill"]


# --- Reparse -------------------------------------------------------------------------------------


def test_reparse_is_idempotent_and_preserves_reviewed_facts(
    client: TestClient, db: Session
) -> None:
    created = upload_ok(
        client, data=resume_bytes("Kept Accepted", "Kept Rejected", "Still Pending")
    )
    accepted_id = _fact_id(created, "Kept Accepted")
    rejected_id = _fact_id(created, "Kept Rejected")
    client.post(
        f"{SOURCES}/{created['id']}/review",
        json={"accept": [{"id": accepted_id}], "reject": [rejected_id]},
    )

    first = client.post(f"{SOURCES}/{created['id']}/reparse")
    assert first.status_code == 200, first.text
    second = client.post(f"{SOURCES}/{created['id']}/reparse")
    assert second.status_code == 200, second.text

    detail = second.json()
    by_name = {f["name"]: f["review_state"] for f in detail["facts"]}
    assert by_name == {
        "Kept Accepted": "accepted",
        "Kept Rejected": "rejected",
        "Still Pending": "pending",
    }
    # No duplicates from reparsing twice.
    names = [f["name"] for f in detail["facts"]]
    assert len(names) == len(set(names))

    fact_keys = db.scalars(
        select(ProfileFact.fact_key)
        .where(ProfileFact.profile_source_id == uuid.UUID(created["id"]))
        .order_by(ProfileFact.fact_key)
    ).all()
    assert len(fact_keys) == len(set(fact_keys))


def test_reparse_error_maps_to_422(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    created = upload_ok(client, data=resume_bytes("Synthetic Skill"))
    import app.services.profile_sources as service
    from app.profile.resume_parser import UnreadableFile

    def boom(data: bytes) -> Any:
        raise UnreadableFile("No text found in that file.")

    monkeypatch.setattr(service, "parse_document", boom)
    response = client.post(f"{SOURCES}/{created['id']}/reparse")
    assert response.status_code == 422


# --- Delete ----------------------------------------------------------------------------------


def test_delete_removes_source_artifact_and_facts_but_keeps_manual_facts(
    client: TestClient, db: Session
) -> None:
    put_match(client, skills=["Manual Skill"])
    created = upload_ok(client, data=resume_bytes("Synthetic Skill"))
    source_id = uuid.UUID(created["id"])

    response = client.delete(f"{SOURCES}/{source_id}")
    assert response.status_code == 200, response.text
    assert response.json() == {
        "catalog_pass": False,
        "evaluated_opportunities": 0,
        "unchanged_opportunities": 0,
    }

    assert db.get(ProfileSourceArtifact, source_id) is None
    remaining = db.scalars(select(ProfileFact)).all()
    assert all(f.profile_source_id is None for f in remaining)  # only manual facts survive
    assert {"name": "Manual Skill"} in [f.value for f in remaining]


def test_delete_with_accepted_fit_facts_runs_one_catalog_pass(
    client: TestClient, db: Session
) -> None:
    put_profile(client)
    create(client, requirements_assessment_status="complete")
    created = upload_ok(client, data=resume_bytes("Synthetic Skill"))
    fact_id = _fact_id(created, "Synthetic Skill")
    client.post(
        f"{SOURCES}/{created['id']}/review", json={"accept": [{"id": fact_id}], "reject": []}
    )

    before = count(db, OpportunityEvaluation)
    response = client.delete(f"{SOURCES}/{created['id']}")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["catalog_pass"] is True
    assert result["evaluated_opportunities"] == 1
    assert count(db, OpportunityEvaluation) == before + 1


# --- 404s --------------------------------------------------------------------------------------


def test_unknown_source_id_is_not_found_on_every_route(client: TestClient) -> None:
    fake_id = uuid.uuid4()
    assert client.get(f"{SOURCES}/{fake_id}").status_code == 404
    assert client.get(f"{SOURCES}/{fake_id}/file").status_code == 404
    assert (
        client.post(f"{SOURCES}/{fake_id}/review", json={"accept": [], "reject": []}).status_code
        == 404
    )
    assert client.post(f"{SOURCES}/{fake_id}/reparse").status_code == 404
    assert client.delete(f"{SOURCES}/{fake_id}").status_code == 404
