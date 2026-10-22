"""Product-owned, versioned Knowledge values."""
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from incubia_orchestrator.foundation.contracts.execution import ExecutionScope


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


class AclState(StrEnum):
    UNKNOWN = "UNKNOWN"
    PENDING_REVIEW = "PENDING_REVIEW"
    VERIFIED = "VERIFIED"
    DENIED = "DENIED"


@dataclass(frozen=True)
class SourceRef:
    source_id: str
    name: str
    mime_type: str
    parents: tuple[str, ...]
    observed_version: str
    modified_time: datetime
    size_bytes: int | None = None
    trashed: bool = False
    shortcut_target_id: str | None = None

    def __post_init__(self):
        if not all((self.source_id.strip(), self.name.strip(), self.mime_type.strip(),
                    self.observed_version.strip())):
            raise ValueError("SourceRef requires id, name, mime type and version")
        if not self.parents:
            raise ValueError("SourceRef requires at least one parent")
        if self.size_bytes is not None and self.size_bytes < 0:
            raise ValueError("SourceRef size must be non-negative")


@dataclass(frozen=True)
class InventoryPage:
    items: tuple[SourceRef, ...]
    next_page_token: str | None = None


@dataclass(frozen=True)
class InventoryEntry:
    ref: SourceRef
    root_id: str
    depth: int
    classification: str
    acl_state: AclState = AclState.UNKNOWN

    def __post_init__(self):
        if not self.root_id.strip():
            raise ValueError("InventoryEntry requires a root id")
        if self.depth < 0:
            raise ValueError("InventoryEntry depth must be non-negative")
        if not self.classification.strip():
            raise ValueError("InventoryEntry requires a classification")


@dataclass(frozen=True)
class ExportRequest:
    source_id: str
    mime_type: str
    target_mime_type: str
    max_bytes: int

    def __post_init__(self):
        if not all((self.source_id.strip(), self.mime_type.strip(), self.target_mime_type.strip())):
            raise ValueError("ExportRequest requires source id and mime types")
        if self.max_bytes <= 0:
            raise ValueError("ExportRequest max_bytes must be positive")


@dataclass(frozen=True)
class ExportResult:
    source_id: str
    target_mime_type: str
    content: bytes
    sha256: str
    truncated: bool = False

    def __post_init__(self):
        if not all((self.source_id.strip(), self.target_mime_type.strip(), self.sha256.strip())):
            raise ValueError("ExportResult requires source id, mime type and checksum")
        if self.truncated:
            raise ValueError("Export V1 never accepts a truncated export")


class SourceCatalogError(Exception):
    """Base error for the Drive source catalog; messages must stay sanitized."""


class RootContainmentError(SourceCatalogError):
    """An item's parent chain does not terminate at the requested root."""


class IdentityNotVerifiedError(SourceCatalogError):
    """Drive identity was absent, unverified, or unrecognised."""


class InventoryLimitError(SourceCatalogError):
    """A configured inventory limit (depth, documents, or pages) was exceeded."""


class ExportTooLargeError(SourceCatalogError):
    """An export exceeded the configured size bound."""


class UnsupportedExportError(SourceCatalogError):
    """The requested export target MIME type is not supported."""
