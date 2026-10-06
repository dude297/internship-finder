"""Work-authorization rules (ADR-026). Each rule reads only the owner-provided facts named in
its docstring; nothing is inferred from another fact (citizen does not mean authorized, and no
fact implies a U.S. person). Unknown, and anything not explicit, is `needs_verification`."""

from enum import StrEnum

from app.enums import EligibilityStatus
from app.opportunities.eligibility.schemas import ProfileInput, RequirementInput, RuleResult

ELIGIBLE = EligibilityStatus.ELIGIBLE
INELIGIBLE = EligibilityStatus.INELIGIBLE
NEEDS_VERIFICATION = EligibilityStatus.NEEDS_VERIFICATION


class WorkAuthKind(StrEnum):
    AUTHORIZED = "authorized"
    NO_SPONSORSHIP = "no_sponsorship"
    CITIZEN_OR_PR = "citizen_or_pr"
    US_PERSON = "us_person"
    CLEARANCE = "clearance"


# The extractor's fixed labels (requirements/extractor.py) are the explicit kinds: an accepted
# requirement whose description is exactly one of them has that meaning. Any other wording,
# including an edited one, has no kind and stays needs_verification (ELIG-REQ-001).
# tests/test_work_authorization.py asserts these equal the extractor's constants.
LABEL_KINDS: dict[str, WorkAuthKind] = {
    "Authorized to work in the United States": WorkAuthKind.AUTHORIZED,
    "Authorized to work in the United States without sponsorship": WorkAuthKind.NO_SPONSORSHIP,
    "U.S. citizen or permanent resident": WorkAuthKind.CITIZEN_OR_PR,
    "U.S. person (export control)": WorkAuthKind.US_PERSON,
    "Security clearance required": WorkAuthKind.CLEARANCE,
}


def work_auth_kind(requirement: RequirementInput) -> WorkAuthKind | None:
    description = requirement.value.get("description")
    return LABEL_KINDS.get(description) if isinstance(description, str) else None


def _result(
    rule_id: str, status: EligibilityStatus, reason: str, requirement: RequirementInput
) -> RuleResult:
    return RuleResult(rule_id=rule_id, status=status, reason=reason, requirement_id=requirement.id)


def check_authorized(profile: ProfileInput, requirement: RequirementInput) -> RuleResult:
    """ELIG-WA-001. Reads `work_authorized_us` only. A "no" is not ineligible: the answer
    describes today and the requirement applies on a later date."""
    rid, fact = "ELIG-WA-001", profile.work_authorized_us
    if fact is True:
        return _result(
            rid, ELIGIBLE, "You recorded that you are authorized to work in the U.S.", requirement
        )
    reason = (
        "You recorded that you are not currently authorized to work in the U.S.; that may change"
        " before the requirement applies, so verify it."
        if fact is False
        else "Work authorization is required; you haven't said whether you are authorized to"
        " work in the U.S."
    )
    return _result(rid, NEEDS_VERIFICATION, reason, requirement)


def check_no_sponsorship(profile: ProfileInput, requirement: RequirementInput) -> RuleResult:
    """ELIG-WA-002. Reads `work_authorized_us`, `needs_sponsorship_now`, and
    `needs_sponsorship_future`. Needing sponsorship now fails every reading of the posting;
    eligible only when authorization is stated and no sponsorship is needed now or later."""
    rid = "ELIG-WA-002"
    now, future, authorized = (
        profile.needs_sponsorship_now,
        profile.needs_sponsorship_future,
        profile.work_authorized_us,
    )
    if now is True:
        return _result(
            rid,
            INELIGIBLE,
            "The posting offers no sponsorship and you recorded that you need sponsorship now.",
            requirement,
        )
    if now is False and future is False and authorized is True:
        return _result(
            rid,
            ELIGIBLE,
            "You recorded that you are authorized and need no sponsorship now or in the future.",
            requirement,
        )
    missing = [
        label
        for label, value in (
            ("whether you need sponsorship now", now),
            ("whether you may need sponsorship in the future", future),
            ("whether you are authorized to work in the U.S.", authorized),
        )
        if value is None
    ]
    reason = (
        "The posting offers no sponsorship; you haven't said " + " or ".join(missing) + "."
        if missing
        else "The posting offers no sponsorship; you recorded that you are not authorized or may"
        " need sponsorship later, and the posting's wording can't settle it. Verify it."
    )
    return _result(rid, NEEDS_VERIFICATION, reason, requirement)


def check_citizen_or_pr(profile: ProfileInput, requirement: RequirementInput) -> RuleResult:
    """ELIG-WA-003. Reads `us_citizen` and `us_permanent_resident` (each its own fact)."""
    rid = "ELIG-WA-003"
    citizen, resident = profile.us_citizen, profile.us_permanent_resident
    if citizen is True or resident is True:
        return _result(
            rid, ELIGIBLE, "You recorded U.S. citizenship or permanent residency.", requirement
        )
    if citizen is False and resident is False:
        return _result(
            rid,
            INELIGIBLE,
            "You recorded that you are neither a U.S. citizen nor a permanent resident.",
            requirement,
        )
    return _result(
        rid,
        NEEDS_VERIFICATION,
        "U.S. citizenship or permanent residency is required; you haven't answered both questions.",
        requirement,
    )


def check_us_person(profile: ProfileInput, requirement: RequirementInput) -> RuleResult:
    """ELIG-WA-004. Reads `us_person_export_control` only, never citizenship or residency."""
    rid, fact = "ELIG-WA-004", profile.us_person_export_control
    if fact is None:
        return _result(
            rid,
            NEEDS_VERIFICATION,
            "A U.S. person (export control) is required; you haven't answered that question.",
            requirement,
        )
    return _result(
        rid,
        ELIGIBLE if fact else INELIGIBLE,
        "You recorded that you are a U.S. person for export control."
        if fact
        else "You recorded that you are not a U.S. person for export control.",
        requirement,
    )


def check_clearance(profile: ProfileInput, requirement: RequirementInput) -> RuleResult:
    """ELIG-WA-005. Reads `active_security_clearance` only. "Clearance required" may mean held
    or obtainable, so holding one is eligible and anything else is never ineligible."""
    rid, fact = "ELIG-WA-005", profile.active_security_clearance
    if fact is True:
        return _result(
            rid, ELIGIBLE, "You recorded that you hold an active security clearance.", requirement
        )
    reason = (
        "A security clearance is required; you recorded none, and the posting may allow"
        " obtaining one. Verify it."
        if fact is False
        else "A security clearance is required; you haven't answered whether you hold one."
    )
    return _result(rid, NEEDS_VERIFICATION, reason, requirement)


RULES = {
    WorkAuthKind.AUTHORIZED: check_authorized,
    WorkAuthKind.NO_SPONSORSHIP: check_no_sponsorship,
    WorkAuthKind.CITIZEN_OR_PR: check_citizen_or_pr,
    WorkAuthKind.US_PERSON: check_us_person,
    WorkAuthKind.CLEARANCE: check_clearance,
}
