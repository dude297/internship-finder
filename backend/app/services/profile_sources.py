"""Profile source ingestion service (ADR-011): upload, review, reparse, and delete résumé
sources. Routes commit; this module only flushes, so a route's whole request is one transaction.
"""

import hashlib
import re
import unicodedata
import uuid
from typing import Any, cast

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.enums import ExtractionMethod, FactCategory, FactReviewState, ProfileSourceKind
from app.models import Profile, ProfileFact, ProfileSource, ProfileSourceArtifact
from app.profile.resume_parser import (
    PARSER_NAME,
    PARSER_VERSION,
    Candidate,
    canonical_name,
    parse_document,
)
from app.repositories import FIT_FACT_CATEGORIES, get_profile
from app.schemas.profile_source import (
    AcceptItem,
    DeleteResponse,
    ImportedFact,
    ProfileSourceDetail,
    ProfileSourceSummary,
    ReviewRequest,
    ReviewResponse,
)
from app.services.opportunities import evaluate_all

FACT_KEY_PREFIX = "resume."
# M5.1: a candidate's fact_key is `resume.` + 24 hex chars of SHA-256 over (category, canonical
# original name) -- a stable identity for the *original parsed candidate*, independent of parser
# version and of any later edit to the accepted/rejected value (ADR-011 §7, M5.1 note). Rows from
# before M5.1 instead have a legacy `resume.NNN` positional key; this pattern recognizes those so
# reparse can keep applying the old by-value skip rule to them.
_LEGACY_FACT_KEY_RE = re.compile(r"^resume\.\d{3}$")  # the old zero-padded index, e.g. resume.007
_FACT_KEY_HASH_LEN = 24
NO_DESCRIPTION_CATEGORIES = (FactCategory.SKILL, FactCategory.COURSE)
NAME_LIMITS = {FactCategory.SKILL: 100, FactCategory.COURSE: 150}
DEFAULT_NAME_LIMIT = 150
DESCRIPTION_LIMIT = 2_000


class DuplicateSource(Exception):
    """This file's bytes were already uploaded for this profile (HTTP 409)."""


class FactNotFound(Exception):
    """A review targets a fact id that isn't one of this source's facts (HTTP 404)."""


class InvalidReview(Exception):
    """A review request fails a validation rule (HTTP 422)."""


# --- Filenames -------------------------------------------------------------------------------


def sanitize_filename(raw: str | None) -> str | None:
    """Basename only, control characters stripped, capped at 255 (ADR-011 §4). A storage label,
    never a path."""
    if not raw:
        return None
    base = raw.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = "".join(ch for ch in base if unicodedata.category(ch) not in ("Cc", "Cf"))
    cleaned = cleaned.strip()[:255]
    return cleaned or None


# --- Reading ---------------------------------------------------------------------------------


def _counts(
    db: Session, source_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict[FactReviewState, int]]:
    result: dict[uuid.UUID, dict[FactReviewState, int]] = {sid: {} for sid in source_ids}
    if not source_ids:
        return result
    rows = db.execute(
        select(ProfileFact.profile_source_id, ProfileFact.review_state, func.count())
        .where(ProfileFact.profile_source_id.in_(source_ids))
        .group_by(ProfileFact.profile_source_id, ProfileFact.review_state)
    ).all()
    for source_id, state, n in rows:
        assert source_id is not None
        result[source_id][state] = n
    return result


def _summary(source: ProfileSource, counts: dict[FactReviewState, int]) -> ProfileSourceSummary:
    return ProfileSourceSummary(
        id=source.id,
        kind=source.kind,
        original_filename=source.original_filename,
        content_type=source.content_type or "",
        byte_size=source.byte_size or 0,
        parser_name=source.parser_name or "",
        parser_version=source.parser_version or "",
        ingested_at=source.ingested_at,
        pending_count=counts.get(FactReviewState.PENDING, 0),
        accepted_count=counts.get(FactReviewState.ACCEPTED, 0),
        rejected_count=counts.get(FactReviewState.REJECTED, 0),
    )


def list_sources(db: Session) -> list[ProfileSourceSummary]:
    profile = get_profile(db)
    if profile is None:
        return []
    sources = db.scalars(
        select(ProfileSource)
        .where(ProfileSource.profile_id == profile.id)
        .order_by(ProfileSource.ingested_at.desc(), ProfileSource.id)
    ).all()
    counts = _counts(db, [s.id for s in sources])
    return [_summary(s, counts[s.id]) for s in sources]


def get_source(db: Session, source_id: uuid.UUID) -> ProfileSource | None:
    profile = get_profile(db)
    if profile is None:
        return None
    return db.scalars(
        select(ProfileSource).where(
            ProfileSource.id == source_id, ProfileSource.profile_id == profile.id
        )
    ).first()


def _fact_to_imported(fact: ProfileFact) -> ImportedFact:
    value = _as_value(fact.value)
    return ImportedFact(
        id=fact.id,
        category=fact.category,
        name=value.get("name", ""),
        description=value.get("description"),
        review_state=fact.review_state,
    )


def source_detail(db: Session, source: ProfileSource) -> ProfileSourceDetail:
    counts = _counts(db, [source.id])[source.id]
    # M5.1: fact_key is now a content hash, so it no longer doubles as a parse-order sort key
    # (it used to be a zero-padded position). created_at/id is stable (not parse order, since a
    # whole upload or reparse call is one transaction and so shares one created_at).
    facts = db.scalars(
        select(ProfileFact)
        .where(ProfileFact.profile_source_id == source.id)
        .order_by(ProfileFact.created_at, ProfileFact.id)
    ).all()
    return ProfileSourceDetail(
        **_summary(source, counts).model_dump(), facts=[_fact_to_imported(f) for f in facts]
    )


def artifact_bytes(db: Session, source_id: uuid.UUID) -> bytes | None:
    """Loaded only here (never for list/detail): a separate query, not the ORM relationship."""
    return db.scalar(
        select(ProfileSourceArtifact.content).where(
            ProfileSourceArtifact.profile_source_id == source_id
        )
    )


# --- Candidates --------------------------------------------------------------------------------


def _as_value(raw: object) -> dict[str, Any]:
    """A fact's `value` column is untyped JSON; treat anything but a JSON object as empty rather
    than crash on malformed data."""
    if not isinstance(raw, dict):
        return {}
    return cast("dict[str, Any]", raw)


def _candidate_value(candidate: Candidate) -> dict[str, Any]:
    if candidate.category in (FactCategory.SKILL, FactCategory.COURSE):
        return {"name": candidate.name}
    return {"name": candidate.name, "description": candidate.description}


def _candidate_fact_key(category: FactCategory, name: str) -> str:
    """The stable identity (M5.1) of a parsed candidate: deterministic, and independent of the
    parser version and of any edit made after the owner accepts or rejects it."""
    digest = hashlib.sha256(f"{category.value}\x00{canonical_name(name)}".encode()).hexdigest()
    return f"{FACT_KEY_PREFIX}{digest[:_FACT_KEY_HASH_LEN]}"


def _is_legacy_fact_key(fact_key: str) -> bool:
    """True for a pre-M5.1 `resume.NNN` positional key, which carries no identity of its own and
    must keep falling back to a by-value skip rule on reparse."""
    return bool(_LEGACY_FACT_KEY_RE.match(fact_key))


def _fact_row(
    profile: Profile, source: ProfileSource, candidate: Candidate, fact_key: str
) -> ProfileFact:
    return ProfileFact(
        profile_id=profile.id,
        profile_source_id=source.id,
        category=candidate.category,
        fact_key=fact_key,
        value=_candidate_value(candidate),
        source_kind=ProfileSourceKind.RESUME,
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_name=PARSER_NAME,
        extractor_version=PARSER_VERSION,
        review_state=FactReviewState.PENDING,
        verified_by_user=False,
    )


def _accepted_names(db: Session, profile_id: uuid.UUID) -> set[tuple[FactCategory, str]]:
    """Every accepted fact's (category, casefolded name), from any source (ADR-011 §7)."""
    rows = db.execute(
        select(ProfileFact.category, ProfileFact.value).where(
            ProfileFact.profile_id == profile_id,
            ProfileFact.review_state == FactReviewState.ACCEPTED,
        )
    ).all()
    names: set[tuple[FactCategory, str]] = set()
    for category, raw_value in rows:
        value = _as_value(raw_value)
        name = value.get("name")
        if isinstance(name, str):
            names.add((category, name.casefold()))
    return names


# --- Upload ------------------------------------------------------------------------------------


def create_source(db: Session, data: bytes, filename: str | None) -> ProfileSourceDetail:
    sha = hashlib.sha256(data).hexdigest()
    profile = get_profile(db)
    if profile is None:
        profile = Profile()
        db.add(profile)
        db.flush()

    existing = db.scalars(
        select(ProfileSource).where(
            ProfileSource.profile_id == profile.id, ProfileSource.content_sha256 == sha
        )
    ).first()
    if existing is not None:
        raise DuplicateSource("That file has already been uploaded.")

    parsed = parse_document(data)  # UnsupportedFileType / UnreadableFile propagate to the caller

    source = ProfileSource(
        profile_id=profile.id,
        kind=ProfileSourceKind.RESUME,
        original_filename=sanitize_filename(filename),
        content_sha256=sha,
        content_type=parsed.content_type,
        byte_size=len(data),
        parser_name=PARSER_NAME,
        parser_version=PARSER_VERSION,
    )
    db.add(source)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateSource("That file has already been uploaded.") from exc

    db.add(ProfileSourceArtifact(profile_source_id=source.id, content=data))

    skip = _accepted_names(db, profile.id)
    for candidate in parsed.candidates:
        if (candidate.category, candidate.name.casefold()) in skip:
            continue
        fact_key = _candidate_fact_key(candidate.category, candidate.name)
        db.add(_fact_row(profile, source, candidate, fact_key))

    db.flush()
    return source_detail(db, source)


# --- Review ------------------------------------------------------------------------------------


def _validated_value(fact: ProfileFact, item: AcceptItem) -> dict[str, Any]:
    """Compute (without mutating) the fact's value if `item` is applied. Raises InvalidReview."""
    value = dict(_as_value(fact.value))  # a copy: `fact.value` itself must stay untouched
    if item.name is not None:
        name = item.name.strip()
        limit = NAME_LIMITS.get(fact.category, DEFAULT_NAME_LIMIT)
        if not 1 <= len(name) <= limit:
            raise InvalidReview(f"name must be 1-{limit} characters.")
        value["name"] = name
    if "description" in item.model_fields_set:
        if fact.category in NO_DESCRIPTION_CATEGORIES:
            if item.description:
                raise InvalidReview(f"{fact.category.value} facts don't have a description.")
        else:
            description = (item.description or "").strip() or None
            if description and len(description) > DESCRIPTION_LIMIT:
                raise InvalidReview(f"description must be at most {DESCRIPTION_LIMIT} characters.")
            value["description"] = description
    return value


def review_source(db: Session, source: ProfileSource, body: ReviewRequest) -> ReviewResponse:
    """One transaction: validate everything first (nothing is mutated on failure), apply, then
    run at most one catalog pass (ADR-011 §8)."""
    accept_ids = [item.id for item in body.accept]
    reject_ids = list(body.reject)
    if not accept_ids and not reject_ids:
        raise InvalidReview("Provide at least one fact to accept or reject.")
    all_ids = accept_ids + reject_ids
    if len(set(all_ids)) != len(all_ids):
        raise InvalidReview("A fact id can't appear twice.")

    facts = {
        f.id: f
        for f in db.scalars(
            select(ProfileFact).where(ProfileFact.profile_source_id == source.id)
        ).all()
    }
    for fact_id in all_ids:
        if fact_id not in facts:
            raise FactNotFound("Fact not found.")

    planned_accepts = [
        (facts[item.id], _validated_value(facts[item.id], item)) for item in body.accept
    ]

    changed_fit = False
    for fact, new_value in planned_accepts:
        was_fit_accepted = (
            fact.review_state == FactReviewState.ACCEPTED and fact.category in FIT_FACT_CATEGORIES
        )
        if fact.category in FIT_FACT_CATEGORIES and (
            not was_fit_accepted or new_value != fact.value
        ):
            changed_fit = True
        fact.value = new_value
        fact.review_state = FactReviewState.ACCEPTED
        fact.verified_by_user = True

    for fact_id in reject_ids:
        fact = facts[fact_id]
        was_fit_accepted = (
            fact.review_state == FactReviewState.ACCEPTED and fact.category in FIT_FACT_CATEGORIES
        )
        fact.review_state = FactReviewState.REJECTED
        fact.verified_by_user = False
        if was_fit_accepted:
            changed_fit = True

    db.flush()

    profile = get_profile(db)
    assert profile is not None
    if changed_fit:
        pass_result = evaluate_all(db, profile)
        catalog_pass, evaluated, unchanged = True, pass_result.evaluated, pass_result.unchanged
    else:
        catalog_pass, evaluated, unchanged = False, 0, 0

    return ReviewResponse(
        source=source_detail(db, source),
        catalog_pass=catalog_pass,
        evaluated_opportunities=evaluated,
        unchanged_opportunities=unchanged,
    )


# --- Reparse -----------------------------------------------------------------------------------


def reparse_source(db: Session, source: ProfileSource) -> ProfileSourceDetail:
    """Re-run the current parser on the stored bytes. Only this source's pending facts are
    replaced; accepted/rejected facts (here or anywhere) are never resurrected or duplicated
    (ADR-011 §7). No catalog pass: pending facts don't score."""
    data = artifact_bytes(db, source.id)
    assert data is not None
    parsed = parse_document(data)  # UnsupportedFileType / UnreadableFile -> 422

    db.execute(
        delete(ProfileFact).where(
            ProfileFact.profile_source_id == source.id,
            ProfileFact.review_state == FactReviewState.PENDING,
        )
    )
    db.flush()

    profile = get_profile(db)
    assert profile is not None
    # Only accepted/rejected facts remain (pending ones were just deleted above).
    remaining = db.scalars(
        select(ProfileFact).where(ProfileFact.profile_source_id == source.id)
    ).all()

    # M5.1 identity rule: a candidate whose fact_key (computed from its original category and
    # name, never from an edit) matches a remaining reviewed fact's fact_key is the same original
    # candidate the owner already decided on -- skip it even if the owner edited its value.
    reviewed_keys = {f.fact_key for f in remaining}

    # Legacy by-value fallback (pre-M5.1 `resume.NNN` keys carry no identity of their own): keep
    # skipping by current value for those, as reparse always has.
    legacy_value_keys: set[tuple[FactCategory, str]] = set()
    for fact in remaining:
        if not _is_legacy_fact_key(fact.fact_key):
            continue
        name = _as_value(fact.value).get("name")
        if isinstance(name, str):
            legacy_value_keys.add((fact.category, name.casefold()))

    # Cross-source accepted-name skip (ADR-011 §7), unchanged by M5.1.
    skip_by_value = _accepted_names(db, profile.id) | legacy_value_keys

    for candidate in parsed.candidates:
        fact_key = _candidate_fact_key(candidate.category, candidate.name)
        if fact_key in reviewed_keys:
            continue
        if (candidate.category, candidate.name.casefold()) in skip_by_value:
            continue
        db.add(_fact_row(profile, source, candidate, fact_key))

    source.parser_name = PARSER_NAME
    source.parser_version = PARSER_VERSION
    db.flush()
    return source_detail(db, source)


# --- Delete ------------------------------------------------------------------------------------


def delete_source(db: Session, source: ProfileSource) -> DeleteResponse:
    """Delete the source (its artifact and facts cascade). One catalog pass only if it had
    accepted fit facts; manual Match Profile facts (profile_source_id NULL) are untouched."""
    had_accepted_fit = (
        db.scalar(
            select(func.count())
            .select_from(ProfileFact)
            .where(
                ProfileFact.profile_source_id == source.id,
                ProfileFact.review_state == FactReviewState.ACCEPTED,
                ProfileFact.category.in_(FIT_FACT_CATEGORIES),
            )
        )
        or 0
    ) > 0
    db.delete(source)
    db.flush()
    if not had_accepted_fit:
        return DeleteResponse(
            catalog_pass=False, evaluated_opportunities=0, unchanged_opportunities=0
        )
    profile = get_profile(db)
    assert profile is not None
    result = evaluate_all(db, profile)
    return DeleteResponse(
        catalog_pass=True,
        evaluated_opportunities=result.evaluated,
        unchanged_opportunities=result.unchanged,
    )
