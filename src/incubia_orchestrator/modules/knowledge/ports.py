"""Knowledge application ports; SQL and provider SDKs live in adapters."""
from typing import Protocol, Sequence

from incubia_orchestrator.modules.knowledge.domain import EvidenceItem, RetrievalQuery, Source


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
