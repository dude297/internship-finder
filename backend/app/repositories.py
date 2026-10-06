"""Persistence helpers that add something beyond plain `session.add` / `session.get`.

Callers own the transaction; these functions only flush.
"""

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session, selectinload

from app.enums import FactCategory, FactReviewState
from app.models import (
    EligibilityRuleResult,
    Opportunity,
    OpportunityEvaluation,
    Profile,
    ProfileFact,
)
from app.opportunities.eligibility import RULES_VERSION, evaluate_eligibility
from app.opportunities.eligibility.schemas import OpportunityInput, ProfileInput, RequirementInput
from app.opportunities.scoring import (
    SCORING_VERSION,
    FitOpportunityInput,
    FitProfileInput,
    NamedItem,
    score_fit,
)

logger = logging.getLogger(__name__)


def get_profile(session: Session) -> Profile | None:
    """The owner's canonical profile. Single-user: the API only ever creates one row."""
    return session.scalars(
        select(Profile).order_by(Profile.created_at, Profile.id).limit(1)
    ).first()


def get_opportunity(session: Session, opportunity_id: uuid.UUID) -> Opportunity | None:
    """Opportunity with its requirements and source records loaded."""
    return session.get(
        Opportunity,
        opportunity_id,
        options=[
            selectinload(Opportunity.requirements),
            selectinload(Opportunity.source_records),
        ],
    )


def _dump(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def eligibility_fingerprint(
    profile: ProfileInput, opportunity: OpportunityInput, requirements: list[RequirementInput]
) -> str:
    """SHA-256 of everything that determines an evaluation (ADR-008 §9): the rules version, the
    canonical profile inputs, the opportunity's reference dates and assessment status, and its
    requirements without their row IDs, sorted. Canonical JSON: sorted keys, no whitespace,
    ISO dates. A change detector, not a security control."""
    rows = sorted(_dump(r.model_dump(mode="json", exclude={"id"})) for r in requirements)
    document = {
        "rules_version": RULES_VERSION,
        "profile": profile.model_dump(mode="json"),
        "opportunity": opportunity.model_dump(mode="json"),
        "requirements": rows,
    }
    return hashlib.sha256(_dump(document).encode()).hexdigest()


FIT_FACT_CATEGORIES = (
    FactCategory.SKILL,
    FactCategory.COURSE,
    FactCategory.PROJECT,
    FactCategory.RESEARCH,
)


def fit_profile_input(session: Session, profile: Profile) -> FitProfileInput:
    """What fit v1 reads about the owner (ADR-010 §5): the preference columns plus accepted
    facts (ADR-011 §5: manual facts are accepted; imported ones once the owner accepts them).
    A fact whose value doesn't have the expected shape is left out and logged, never coerced
    into a guess."""
    facts = session.scalars(
        select(ProfileFact)
        .where(
            ProfileFact.profile_id == profile.id,
            ProfileFact.category.in_(FIT_FACT_CATEGORIES),
            ProfileFact.review_state == FactReviewState.ACCEPTED,
        )
        .order_by(ProfileFact.created_at, ProfileFact.fact_key, ProfileFact.id)
    ).all()
    found: dict[FactCategory, list[NamedItem]] = {c: [] for c in FIT_FACT_CATEGORIES}
    for fact in facts:
        try:
            found[fact.category].append(NamedItem.model_validate(fact.value))
        except ValidationError:
            logger.warning("profile fact %s has an unexpected value; not scored", fact.id)
    return FitProfileInput(
        skills=tuple(item.name for item in found[FactCategory.SKILL]),
        courses=tuple(item.name for item in found[FactCategory.COURSE]),
        projects=tuple(found[FactCategory.PROJECT]),
        research=tuple(found[FactCategory.RESEARCH]),
        interests=tuple(profile.interests or ()),
        preferred_locations=tuple(profile.preferred_locations or ()),
        remote_preference=profile.remote_preference,
        availability_start=profile.availability_start,
        availability_end=profile.availability_end,
    )


def fit_fingerprint(profile: FitProfileInput, opportunity: FitOpportunityInput) -> str:
    """SHA-256 of everything fit depends on (ADR-010 §8): the scoring version, the fit profile
    input, and the posting's fit fields. Never updated_at, last_seen_at, or IDs."""
    document = {
        "scoring_version": SCORING_VERSION,
        "profile": profile.model_dump(mode="json"),
        "opportunity": opportunity.model_dump(mode="json"),
    }
    return hashlib.sha256(_dump(document).encode()).hexdigest()


@dataclass(frozen=True)
class EvaluationContext:
    """A profile's evaluation inputs, read once and reused for many opportunities."""

    profile: Profile
    eligibility: ProfileInput
    fit: FitProfileInput


def evaluation_context(
    session: Session, profile: Profile | None = None
) -> EvaluationContext | None:
    """For the given profile (default: the owner's), or None when there's no profile."""
    profile = profile or get_profile(session)
    if profile is None:
        return None
    return EvaluationContext(
        profile, ProfileInput.model_validate(profile), fit_profile_input(session, profile)
    )


@dataclass(frozen=True)
class _Inputs:
    opportunity: OpportunityInput
    requirements: list[RequirementInput]
    fit: FitOpportunityInput
    fingerprints: tuple[str, str]  # (eligibility, fit)


def _inputs(context: EvaluationContext, opportunity: Opportunity) -> _Inputs:
    opportunity_input = OpportunityInput.model_validate(opportunity)
    requirements = [RequirementInput.model_validate(r) for r in opportunity.requirements]
    fit = FitOpportunityInput.model_validate(opportunity)
    return _Inputs(
        opportunity_input,
        requirements,
        fit,
        (
            eligibility_fingerprint(context.eligibility, opportunity_input, requirements),
            fit_fingerprint(context.fit, fit),
        ),
    )


def _save(
    session: Session, context: EvaluationContext, opportunity: Opportunity, inputs: _Inputs
) -> OpportunityEvaluation:
    """Evaluate eligibility and fit, and append the row (history is kept; nothing is
    overwritten). Doesn't flush."""
    evaluation = evaluate_eligibility(context.eligibility, inputs.opportunity, inputs.requirements)
    breakdown = score_fit(context.fit, inputs.fit)
    row = OpportunityEvaluation(
        profile_id=context.profile.id,
        opportunity_id=opportunity.id,
        eligibility_status=evaluation.status,
        eligibility_rules_version=evaluation.rules_version,
        depends_on_projected_status=evaluation.depends_on_projected_status,
        evaluated_at=datetime.now(UTC),
        input_fingerprint=inputs.fingerprints[0],
        fit_score=breakdown.score,
        score_breakdown=breakdown.model_dump(mode="json"),
        scoring_version=breakdown.scoring_version,
        fit_input_fingerprint=inputs.fingerprints[1],
        rule_results=[
            EligibilityRuleResult(
                position=position,
                rule_id=result.rule_id,
                requirement_id=result.requirement_id,
                status=result.status,
                reason=result.reason,
                reference_date=result.reference_date,
                depends_on_projected_status=result.depends_on_projected_status,
                details=result.details,
            )
            for position, result in enumerate(evaluation.rule_results)
        ],
    )
    session.add(row)
    return row


def _context(
    session: Session, profile: Profile, context: EvaluationContext | None
) -> EvaluationContext:
    if context is not None:
        return context
    return EvaluationContext(
        profile, ProfileInput.model_validate(profile), fit_profile_input(session, profile)
    )


def evaluate_and_save(
    session: Session,
    profile: Profile,
    opportunity: Opportunity,
    context: EvaluationContext | None = None,
) -> OpportunityEvaluation:
    """A forced evaluation (eligibility and fit): always appends a row. Pass `context` when
    evaluating many opportunities, so the profile inputs are read once."""
    context = _context(session, profile, context)
    row = _save(session, context, opportunity, _inputs(context, opportunity))
    session.flush()
    return row


def evaluate_if_changed(
    session: Session,
    profile: Profile,
    opportunity: Opportunity,
    context: EvaluationContext | None = None,
) -> OpportunityEvaluation | None:
    """Automatic evaluation: append a row only when the eligibility or fit inputs (rules and
    scoring versions included) differ from the latest evaluation's. None when nothing changed."""
    context = _context(session, profile, context)
    inputs = _inputs(context, opportunity)
    latest = latest_evaluation(session, profile.id, opportunity.id)
    if latest is not None and (
        (latest.input_fingerprint, latest.fit_input_fingerprint) == inputs.fingerprints
    ):
        return None
    row = _save(session, context, opportunity, inputs)
    session.flush()
    return row


@dataclass(frozen=True)
class CatalogEvaluation:
    evaluated: int  # new evaluation rows
    unchanged: int  # skipped: the latest evaluation already has these inputs


CATALOG_BATCH_SIZE = 200


def evaluate_catalog(
    session: Session,
    context: EvaluationContext,
    batch_size: int = CATALOG_BATCH_SIZE,
    dry_run: bool = False,
) -> CatalogEvaluation:
    """Automatic evaluation of every opportunity in one pass (ADR-010 §9). The latest
    fingerprints come from one query; opportunities are read in keyset batches (bounded memory);
    unchanged pairs are skipped; new rows are flushed once per batch. The caller commits. With
    `dry_run`, counts what would be evaluated and writes nothing."""
    latest = {
        opportunity_id: (eligibility, fit)
        for opportunity_id, eligibility, fit in session.execute(
            select(
                OpportunityEvaluation.opportunity_id,
                OpportunityEvaluation.input_fingerprint,
                OpportunityEvaluation.fit_input_fingerprint,
            )
            .where(OpportunityEvaluation.profile_id == context.profile.id)
            .ext(distinct_on(OpportunityEvaluation.opportunity_id))
            .order_by(
                OpportunityEvaluation.opportunity_id,
                OpportunityEvaluation.evaluated_at.desc(),
                OpportunityEvaluation.id.desc(),
            )
        )
    }
    evaluated = unchanged = 0
    after: uuid.UUID | None = None
    while True:
        query = (
            select(Opportunity)
            .options(selectinload(Opportunity.requirements))
            .order_by(Opportunity.id)
            .limit(batch_size)
        )
        if after is not None:
            query = query.where(Opportunity.id > after)
        batch = session.scalars(query).all()
        if not batch:
            break
        for opportunity in batch:
            inputs = _inputs(context, opportunity)
            if latest.get(opportunity.id) == inputs.fingerprints:
                unchanged += 1
            else:
                if not dry_run:
                    _save(session, context, opportunity, inputs)
                evaluated += 1
        session.flush()
        after = batch[-1].id
    return CatalogEvaluation(evaluated, unchanged)


def latest_evaluation(
    session: Session, profile_id: uuid.UUID, opportunity_id: uuid.UUID
) -> OpportunityEvaluation | None:
    return session.scalars(
        select(OpportunityEvaluation)
        .where(
            OpportunityEvaluation.profile_id == profile_id,
            OpportunityEvaluation.opportunity_id == opportunity_id,
        )
        # id breaks evaluated_at ties: arbitrary among equal timestamps, but stable.
        .order_by(OpportunityEvaluation.evaluated_at.desc(), OpportunityEvaluation.id.desc())
        .limit(1)
    ).first()
