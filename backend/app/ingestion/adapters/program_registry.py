"""The curated program registry (ADR-014 §5-§8): a repository data file of public program facts,
read from disk (no network) and written through the shared pipeline like any other source."""

from typing import Any

from app.enums import OpportunitySourceType
from app.ingestion.adapters import Adapter, CollectRequest, SourceConfig
from app.ingestion.normalize import NormalizedOpportunity, Snapshot, SnapshotError

BUILTIN_IDENTIFIER = "program-registry"


def _normalize(raw: dict[str, Any], source: SourceConfig) -> NormalizedOpportunity:
    raise NotImplementedError  # Agent B


def parse(payload: Any, source: SourceConfig) -> Snapshot:
    raise SnapshotError("not_implemented", "The program registry isn't implemented yet.")


def collect(request: CollectRequest) -> Any:
    raise SnapshotError("not_implemented", "The program registry isn't implemented yet.")


ADAPTER = Adapter(
    source_type=OpportunitySourceType.CURATED_REGISTRY,
    url=lambda _source: "",
    parse=parse,
    normalize=_normalize,
    collect=collect,
)
