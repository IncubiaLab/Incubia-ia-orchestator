"""Product-owned, versioned Knowledge values."""
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from incubia_orchestrator.foundation.contracts.execution import ExecutionScope


class EmbeddingUnavailable(RuntimeError):
    """A bounded, secret-free signal that retrieval could not embed its query."""


class GenerationStatus(StrEnum):
    BUILDING = "BUILDING"
    VALIDATING = "VALIDATING"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class Source:
    deployment_id: str
    source_id: str
    version: str
    content: str
    public_ref: str | None = None
    revoked: bool = False

    def __post_init__(self):
        if not all((self.deployment_id, self.source_id, self.version, self.content.strip())):
            raise ValueError("Source requires deployment, id, version and content")
        if len(self.content.encode("utf-8")) > 4096:
            raise ValueError("One-chunk source exceeds the current limit")


@dataclass(frozen=True)
class EvidenceItem:
    deployment_id: str
    source_id: str
    source_version: str
    chunk_id: str
    generation_id: str
    text: str
    score: float | None = None
    public_ref: str | None = None

    def __post_init__(self):
        if not all((self.deployment_id, self.source_id, self.source_version,
                    self.chunk_id, self.generation_id, self.text.strip())):
            raise ValueError("Evidence provenance and text are required")
        if len(self.text.encode("utf-8")) > 4096:
            raise ValueError("Evidence text is too large")
        if self.score is not None and not 0 <= self.score <= 1:
            raise ValueError("Evidence score must be in [0, 1]")


@dataclass(frozen=True)
class RetrievalQuery:
    scope: ExecutionScope
    text: str
    capability: str
    top_k: int = 5
    deadline: datetime | None = None

    def __post_init__(self):
        if not all((self.scope.deployment_id, self.scope.tenant_id, self.scope.actor_id,
                    self.text.strip(), self.capability.strip())):
            raise ValueError("Scoped query and capability are required")
        if not 1 <= self.top_k <= 5 or len(self.text.encode("utf-8")) > 2048:
            raise ValueError("Query exceeds retrieval limits")
