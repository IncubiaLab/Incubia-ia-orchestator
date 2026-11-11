from incubia_orchestrator.modules.knowledge.domain import ExportResult, InventoryPage, SourceRef


class FakeDriveTransport:
    """Deterministic in-memory Drive transport for offline tests.

    Built from a dict of folder_id -> children (SourceRef tuples). Metadata for
    every listed child is indexed automatically; extra items (e.g. items that
    live outside any listed folder, used to model shortcut targets or sibling
    folders) can be supplied via the `metadata` mapping.
    """

    def __init__(self, folders: dict[str, tuple[SourceRef, ...]],
                 metadata: dict[str, SourceRef] | None = None, *, page_size: int = 10):
        self._folders = {folder_id: tuple(children) for folder_id, children in folders.items()}
        self._metadata: dict[str, SourceRef] = {}
        for children in self._folders.values():
            for child in children:
                self._metadata[child.source_id] = child
        if metadata:
            self._metadata.update(metadata)
        self.page_size = page_size
        self.list_calls = 0
        self.metadata_calls = 0
        self.export_calls = 0
        self._export_responses: dict[str, ExportResult] = {}

    def set_export_response(self, source_id: str, result: ExportResult) -> None:
        self._export_responses[source_id] = result

    def list_children(self, folder_id: str, page_token: str | None) -> InventoryPage:
        self.list_calls += 1
        children = self._folders.get(folder_id, ())
        start = int(page_token) if page_token else 0
        end = start + self.page_size
        page_items = children[start:end]
        next_token = str(end) if end < len(children) else None
        return InventoryPage(items=page_items, next_page_token=next_token)

    def get_metadata(self, source_id: str) -> SourceRef:
        self.metadata_calls += 1
        if source_id not in self._metadata:
            raise LookupError("fixture: unknown source id")
        return self._metadata[source_id]

    def export(self, request) -> ExportResult:
        self.export_calls += 1
        if request.source_id not in self._export_responses:
            raise LookupError("fixture: no export response configured")
        return self._export_responses[request.source_id]
