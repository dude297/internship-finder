"""Deterministic identities for requirement extraction (ADR-012 §3, §4). Pure; no database.

- `semantic_key`: what a requirement *means* (type, normalized value, applies_at, reference
  date). The identity of a candidate across re-extractions; source text, IDs, positions, and
  timestamps never take part.
- `extraction_input_fingerprint`: the posting text extraction reads. A change means the
  requirement-relevant content changed (ADR-012 §6).
- `extraction_fingerprint`: the inputs plus the extractor name and version: what an extraction
  ran on. Stored on the opportunity so the catalog scan can skip current rows.
"""

import hashlib
import json
from datetime import date
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from app.enums import RequirementAppliesAt, RequirementType

if TYPE_CHECKING:
    from app.models import OpportunityRequirement, OpportunityRequirementCandidate
    from app.schemas.opportunity import RequirementBody


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(document: Any) -> str:
    return hashlib.sha256(_canonical_json(document).encode()).hexdigest()


def _text(value: object) -> str:
    return " ".join(value.split()).casefold() if isinstance(value, str) else ""


def normalized_value(requirement_type: RequirementType, value: dict[str, Any]) -> dict[str, Any]:
    """The value as identity sees it: list order and free-text case/whitespace don't matter.
    Unknown keys are kept (sorted by canonical JSON), so distinct values stay distinct."""
    result = dict(value)
    if requirement_type is RequirementType.EDUCATION and isinstance(result.get("levels"), list):
        result["levels"] = sorted({str(v) for v in result["levels"]})
        result["accepts_incoming"] = bool(result.get("accepts_incoming", False))
    elif requirement_type is RequirementType.CITIZENSHIP and isinstance(
        result.get("countries"), list
    ):
        result["countries"] = sorted({str(v).upper() for v in result["countries"]})
    elif "description" in result:
        result["description"] = _text(result["description"])
    return result


def semantic_key(
    requirement_type: RequirementType,
    value: dict[str, Any],
    applies_at: RequirementAppliesAt,
    reference_date: date | None,
) -> str:
    """SHA-256 hex of the requirement's meaning. Equal for equal requirements however phrased."""
    return _sha256(
        {
            "requirement_type": requirement_type.value,
            "value": normalized_value(requirement_type, value),
            "applies_at": applies_at.value,
            "reference_date": reference_date.isoformat() if reference_date else None,
        }
    )


def requirement_key(
    requirement: "OpportunityRequirement | OpportunityRequirementCandidate | RequirementBody",
) -> str:
    """`semantic_key` of a canonical requirement or a candidate row."""
    return semantic_key(
        requirement.requirement_type,
        requirement.value,
        requirement.applies_at,
        requirement.reference_date,
    )


class ExtractionInput(BaseModel):
    """The canonical, source-derived posting fields extraction reads. Never IDs or timestamps."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    title: str
    description: str | None = None
    application_deadline: date | None = None
    start_date: date | None = None


def extraction_input_fingerprint(inputs: ExtractionInput) -> str:
    """Whitespace is collapsed first, so a provider reformatting the same words isn't a material
    change (ADR-012 §6)."""
    document = inputs.model_dump(mode="json")
    for name in ("title", "description"):
        if isinstance(document[name], str):
            document[name] = " ".join(document[name].split())
    return _sha256(document)


def extraction_fingerprint(inputs: ExtractionInput, extractor_name: str, version: str) -> str:
    return _sha256(
        {
            "extractor": extractor_name,
            "version": version,
            "inputs": extraction_input_fingerprint(inputs),
        }
    )
