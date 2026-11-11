"""Knowledge application ports; SQL and provider SDKs live in adapters."""
from dataclasses import dataclass
from typing import Protocol, Sequence

from incubia_orchestrator.modules.knowledge.domain import (
    EvidenceItem,
    ExportRequest,
    ExportResult,
    InventoryEntry,
    InventoryPage,
    RetrievalQuery,
    Source,
    SourceRef,
)


class EmbeddingPort(Protocol):
    model_version: str
    dimension: int

    def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]: ...


class KnowledgeRepository(Protocol):
    def publish(self, deployment_id: str, sources: Sequence[Source], embeddings: Sequence[tuple[float, ...]],
                model_version: str) -> str: ...

    def revoke(self, deployment_id: str, source_id: str) -> None: ...

    def activate_generation(self, deployment_id: str, generation_id: str) -> None: ...


class RetrievalPort(Protocol):
    def retrieve(self, query: RetrievalQuery) -> tuple[EvidenceItem, ...]: ...


@dataclass(frozen=True)
class VerifiedIdentity:
    """An opaque, verified Drive identity. Never carries an email or raw subject."""
    principal_digest: str
    granted_scopes: tuple[str, ...]

    def __post_init__(self):
        if not self.principal_digest.strip():
            raise ValueError("VerifiedIdentity requires an opaque principal digest")


class DriveTransportPort(Protocol):
    """The seam a fake implements today and a real SDK-backed adapter later."""

    def list_children(self, folder_id: str, page_token: str | None) -> InventoryPage: ...

    def get_metadata(self, source_id: str) -> SourceRef: ...

    def export(self, request: ExportRequest) -> ExportResult: ...


class DriveIdentityPort(Protocol):
    """Raising or returning anything unverified must be treated as a deny."""

    def assert_verified(self) -> VerifiedIdentity: ...


class SourceCatalogPort(Protocol):
    def inventory(self, root_id: str) -> tuple[InventoryEntry, ...]: ...

    def export_document(self, entry: InventoryEntry) -> ExportResult: ...
