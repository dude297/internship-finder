"""Source adapters: build the request URL from a hard-coded host + validated identifier, validate
the response's top level, and normalize items. No database access (ADR-002, ADR-008 §2)."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from pydantic import BaseModel, ValidationError

from app.enums import IngestionSourceKind, OpportunitySourceType, SourceRegion
from app.ingestion.normalize import ItemError, NormalizedOpportunity, Snapshot, SnapshotError


@dataclass(frozen=True)
class SourceConfig:
    """The safe, read-only view of a registry row an adapter needs."""

    kind: IngestionSourceKind
    identifier: str
    region: SourceRegion | None
    display_name: str


@dataclass(frozen=True)
class Adapter:
    source_type: OpportunitySourceType
    url: Callable[[SourceConfig], str]
    # Raises SnapshotError when the response as a whole is unusable.
    parse: Callable[[Any, SourceConfig], Snapshot]
    # One stored raw item → its normalized form (ADR-013 §5: re-deriving a fallback owner's
    # canonical fields without a fetch). Raises ItemError/ValidationError like `parse` items.
    normalize: Callable[[dict[str, Any], SourceConfig], NormalizedOpportunity]


def top_level[M: BaseModel](model: type[M], payload: Any, what: str) -> M:
    """Validate the response's outer shape; any mismatch fails the whole snapshot."""
    try:
        return model.model_validate(payload)
    except ValidationError as error:
        raise SnapshotError("schema_mismatch", f"Unexpected {what} format.") from error


def normalize_each(
    items: list[Any],
    normalize: Callable[[dict[str, Any]], NormalizedOpportunity],
    item_id: Callable[[dict[str, Any]], object],
) -> list[NormalizedOpportunity | ItemError]:
    """Normalize every item; a bad item becomes an ItemError instead of failing the snapshot."""
    results: list[NormalizedOpportunity | ItemError] = []
    for item in items:
        if not isinstance(item, dict):
            results.append(ItemError("invalid_item", "Item isn't a JSON object."))
            continue
        raw = cast(dict[str, Any], item)
        raw_id = item_id(raw)
        external_id = str(raw_id)[:255] if raw_id is not None else None
        try:
            results.append(normalize(raw))
        except ItemError as error:
            error.external_id = error.external_id or external_id
            results.append(error)
        except ValidationError as error:
            first = error.errors()[0]
            where = ".".join(str(part) for part in first["loc"]) or "item"
            results.append(ItemError("invalid_item", f"{where}: {first['msg']}"[:500], external_id))
    return results


def adapter_for(kind: IngestionSourceKind) -> Adapter:
    from app.ingestion.adapters import ashby, community_feed, greenhouse, lever

    return {
        IngestionSourceKind.COMMUNITY_FEED: community_feed.ADAPTER,
        IngestionSourceKind.GREENHOUSE: greenhouse.ADAPTER,
        IngestionSourceKind.LEVER: lever.ADAPTER,
        IngestionSourceKind.ASHBY: ashby.ADAPTER,
    }[kind]
