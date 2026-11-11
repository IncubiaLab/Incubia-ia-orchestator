"""Sanitized, read-only Drive source catalog adapter.

Driven by an injected `DriveTransportPort` fake in V1 — no Google SDK, no HTTP
client, no credentials. Authorization (ACL) is a separate, undecided decision:
every entry is produced with `AclState.UNKNOWN` and this adapter never
upgrades it.
"""
from collections import deque
from dataclasses import dataclass
from hashlib import sha256

from incubia_orchestrator.modules.knowledge.domain import (
    AclState,
    ExportRequest,
    ExportResult,
    ExportTooLargeError,
    IdentityNotVerifiedError,
    InventoryEntry,
    InventoryLimitError,
    RootContainmentError,
    SourceCatalogError,
    SourceRef,
    UnsupportedExportError,
)
from incubia_orchestrator.modules.knowledge.ports import (
    DriveIdentityPort,
    DriveTransportPort,
    VerifiedIdentity,
)


_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"

_DEFAULT_ALLOWED_EXPORT_MIME_TYPES = (
    "text/markdown",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
)

# Google-native source mime type -> the single export target it maps to.
# Never text/csv: a CSV export silently loses every sheet but the first.
_EXPORT_TARGETS = {
    "application/vnd.google-apps.document": "text/markdown",
    "application/vnd.google-apps.spreadsheet":
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.google-apps.presentation":
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


@dataclass(frozen=True)
class DriveCatalogConfig:
    max_documents: int = 5_000
    max_depth: int = 20
    max_pages: int = 500
    max_export_bytes: int = 20_000_000
    allowed_export_mime_types: tuple[str, ...] = _DEFAULT_ALLOWED_EXPORT_MIME_TYPES

    def __post_init__(self) -> None:
        if self.max_documents < 1 or self.max_depth < 1 or self.max_pages < 1:
            raise ValueError("Drive catalog limits must be positive")
        if self.max_export_bytes < 1:
            raise ValueError("Drive catalog export limit must be positive")
        if not self.allowed_export_mime_types:
            raise ValueError("Drive catalog requires at least one allowed export mime type")
        if "text/csv" in self.allowed_export_mime_types:
            raise ValueError("Drive catalog must never allow CSV export")


class DriveSourceCatalog:
    """SourceCatalogPort implementation driven by an injected transport."""

    def __init__(self, transport: DriveTransportPort, identity: DriveIdentityPort,
                 config: DriveCatalogConfig | None = None):
        self._transport = transport
        self._identity = identity
        self._config = config or DriveCatalogConfig()

    def inventory(self, root_id: str) -> tuple[InventoryEntry, ...]:
        self._require_identity()

        config = self._config
        visited_folders: set[str] = set()
        contained_folders: set[str] = {root_id}
        emitted_source_ids: set[str] = set()
        entries: list[InventoryEntry] = []
        pages_fetched = 0
        queue: deque[tuple[str, int]] = deque([(root_id, 0)])

        while queue:
            folder_id, depth = queue.popleft()
            if folder_id in visited_folders:
                continue
            visited_folders.add(folder_id)

            page_token = None
            while True:
                if pages_fetched >= config.max_pages:
                    raise InventoryLimitError("Drive inventory exceeded the configured page limit")
                page = self._transport.list_children(folder_id, page_token)
                pages_fetched += 1

                visible_items = tuple(item for item in page.items if not item.trashed)

                # Resolve folder membership for the complete page before
                # evaluating documents. Drive does not promise an order within
                # a page, and multi-parent items may name a sibling folder that
                # appears later in that same page.
                pending_folders = [
                    item for item in visible_items
                    if item.mime_type == _FOLDER_MIME_TYPE and item.shortcut_target_id is None
                ]
                changed = True
                while changed:
                    changed = False
                    for folder in pending_folders:
                        if (folder.source_id not in contained_folders
                                and any(parent in contained_folders for parent in folder.parents)):
                            contained_folders.add(folder.source_id)
                            changed = True

                for item in visible_items:
                    if item.shortcut_target_id is not None:
                        if _containment(item, contained_folders) != "contained":
                            continue
                        target = self._transport.get_metadata(item.shortcut_target_id)
                        if target.trashed or _containment(target, contained_folders) != "contained":
                            continue  # excluded with a cause; a shortcut target is never followed
                        resolved = target
                    else:
                        state = _containment(item, contained_folders)
                        if state == "excluded":
                            continue
                        if state == "escaped":
                            raise RootContainmentError(
                                "An item's parent chain does not stay within the requested root")
                        resolved = item

                    if resolved.source_id in emitted_source_ids:
                        continue

                    classification = "folder" if resolved.mime_type == _FOLDER_MIME_TYPE else "document"
                    entries.append(InventoryEntry(ref=resolved, root_id=root_id, depth=depth + 1,
                                                   classification=classification,
                                                   acl_state=AclState.UNKNOWN))
                    emitted_source_ids.add(resolved.source_id)
                    if len(entries) > config.max_documents:
                        raise InventoryLimitError("Drive inventory exceeded the configured document limit")

                    # Shortcuts are never traversed, even when their target is a folder
                    # inside the root: keeping shortcut targets as leaves bounds the
                    # traversal surface without needing a second cycle-safe visited set.
                    if resolved.mime_type == _FOLDER_MIME_TYPE and item.shortcut_target_id is None:
                        if depth + 1 > config.max_depth:
                            raise InventoryLimitError("Drive inventory exceeded the configured depth limit")
                        contained_folders.add(resolved.source_id)
                        queue.append((resolved.source_id, depth + 1))

                page_token = page.next_page_token
                if page_token is None:
                    break

        return tuple(entries)

    def export_document(self, entry: InventoryEntry) -> ExportResult:
        self._require_identity()

        ref = entry.ref
        target_mime_type = _EXPORT_TARGETS.get(ref.mime_type)
        if target_mime_type is None or target_mime_type not in self._config.allowed_export_mime_types:
            raise UnsupportedExportError("The requested export target is not supported")

        request = ExportRequest(source_id=ref.source_id, mime_type=ref.mime_type,
                                 target_mime_type=target_mime_type, max_bytes=self._config.max_export_bytes)
        result = self._transport.export(request)

        if len(result.content) > self._config.max_export_bytes:
            raise ExportTooLargeError("Export content exceeds the configured size limit")
        if sha256(result.content).hexdigest() != result.sha256:
            raise SourceCatalogError("Export content failed integrity verification")

        return result

    def _require_identity(self) -> VerifiedIdentity:
        try:
            identity = self._identity.assert_verified()
        except Exception:
            raise IdentityNotVerifiedError("Drive identity could not be verified") from None
        if identity is None or not getattr(identity, "principal_digest", "").strip():
            raise IdentityNotVerifiedError("Drive identity could not be verified")
        return identity


def _containment(item: SourceRef, contained_folders: set[str]) -> str:
    present = [parent for parent in item.parents if parent in contained_folders]
    absent = [parent for parent in item.parents if parent not in contained_folders]
    if not present:
        return "excluded"
    if absent:
        return "escaped"
    return "contained"
