"""Use cases for workspace-scoped Orbit document sync and retrieval."""
from __future__ import annotations

import base64
import binascii
from collections.abc import Sequence

from incubia_orchestrator.modules.knowledge.application.drive_ingest import MAX_SOURCE_BYTES, chunk_markdown
from incubia_orchestrator.modules.knowledge.domain import (
    MAX_DOCUMENT_BYTES,
    MAX_DOCUMENT_CHUNKS,
    DocumentExtractionError,
    DocumentRejectedError,
    DocumentSyncRequest,
    DocumentSyncResult,
    EmbeddingUnavailable,
    KnowledgeStoreUnavailable,
    WorkspaceKnowledgeHit,
)
from incubia_orchestrator.modules.knowledge.ports import (
    DocumentDownloadPort,
    DocumentExtractorPort,
    DocumentKnowledgeStorePort,
    EmbeddingPort,
)

DEFAULT_CHUNK_BYTES = 3500
DEFAULT_BATCH_SIZE = 32
MAX_RETURNED_EXTRACTED_CHARS = 100_000


class SyncDocumentKnowledge:
    """Download, extract, chunk, embed, and atomically publish or revoke an Orbit document."""

    def __init__(
        self,
        store: DocumentKnowledgeStorePort,
        downloader: DocumentDownloadPort,
        extractor: DocumentExtractorPort,
        embedding: EmbeddingPort,
        *,
        max_bytes: int = MAX_DOCUMENT_BYTES,
        max_chunk_bytes: int = DEFAULT_CHUNK_BYTES,
        max_chunks: int = MAX_DOCUMENT_CHUNKS,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ):
        if max_chunk_bytes > MAX_SOURCE_BYTES or max_chunk_bytes < 512:
            raise ValueError("Invalid chunk size bound")
        if batch_size < 1:
            raise ValueError("Positive embedding batch size is required")
        self._store = store
        self._downloader = downloader
        self._extractor = extractor
        self._embedding = embedding
        self._max_bytes = max_bytes
        self._max_chunk_bytes = max_chunk_bytes
        self._max_chunks = max_chunks
        self._batch_size = batch_size

    def _resolve_raw_bytes(self, request: DocumentSyncRequest) -> bytes:
        if request.content is not None:
            raw = request.content.encode("utf-8")
            if len(raw) > self._max_bytes:
                raise DocumentRejectedError("Inline content exceeds maximum allowed byte size")
            return raw
        if request.content_base64 is not None:
            try:
                raw = base64.b64decode(request.content_base64.strip(), validate=True)
            except (binascii.Error, ValueError) as exc:
                raise DocumentRejectedError("Invalid base64 document payload") from exc
            if not raw or len(raw) > self._max_bytes:
                raise DocumentRejectedError("Decoded binary content exceeds allowed byte bounds")
            return raw
        assert request.download_url is not None
        return self._downloader.download(
            request.download_url,
            declared_size_bytes=request.size_bytes,
            max_bytes=self._max_bytes,
        )

    def __call__(self, request: DocumentSyncRequest) -> DocumentSyncResult:
        if request.operation == "revoke":
            status, generation_id = self._store.revoke_document(
                request.deployment_id,
                request.workspace_id,
                request.document_id,
                request.source_id,
            )
            return DocumentSyncResult(
                status=status,
                source_id=request.source_id,
                generation_id=generation_id,
            )

        existing_generation = self._store.is_document_active(
            request.deployment_id,
            request.workspace_id,
            request.document_id,
            request.version,
            self._embedding.model_version,
        )
        if existing_generation is not None:
            extracted_preview: str | None = None
            if request.content_base64 is not None:
                raw_bytes = self._resolve_raw_bytes(request)
                extracted_preview = self._extractor.extract_text(
                    raw_bytes, content_type=request.content_type
                )[:MAX_RETURNED_EXTRACTED_CHARS]
            elif request.content is not None:
                extracted_preview = request.content.strip()[:MAX_RETURNED_EXTRACTED_CHARS]
            return DocumentSyncResult(
                status="already_indexed",
                source_id=request.source_id,
                generation_id=existing_generation,
                extracted_text=extracted_preview,
            )

        raw_bytes = self._resolve_raw_bytes(request)
        text = self._extractor.extract_text(raw_bytes, content_type=request.content_type)
        if not text.strip():
            raise DocumentExtractionError("Extracted document text is empty")

        header = _truncate_utf8(request.title.strip() or request.source_id, 240)
        prefix = f"{header}\n\n"
        body_limit = self._max_chunk_bytes - len(prefix.encode("utf-8"))
        chunks_body = chunk_markdown(text.strip(), max_bytes=body_limit)
        if not chunks_body:
            raise DocumentExtractionError("Document yielded no usable text chunks")
        if len(chunks_body) > self._max_chunks:
            raise DocumentRejectedError("Document exceeds maximum allowed chunks")

        chunks = [f"{prefix}{piece}" for piece in chunks_body]
        if any(len(chunk.encode("utf-8")) > MAX_SOURCE_BYTES for chunk in chunks):
            raise DocumentRejectedError("Document chunk exceeds UTF-8 size limit")

        vectors: list[tuple[float, ...]] = []
        try:
            for start in range(0, len(chunks), self._batch_size):
                batch = chunks[start : start + self._batch_size]
                batch_vectors = self._embedding.embed(batch)
                if len(batch_vectors) != len(batch) or any(
                    len(vector) != self._embedding.dimension for vector in batch_vectors
                ):
                    raise EmbeddingUnavailable("Embedding response shape mismatch")
                vectors.extend(batch_vectors)
        except EmbeddingUnavailable:
            raise
        except Exception as exc:
            raise KnowledgeStoreUnavailable("Embedding generation failed") from exc

        status, generation_id = self._store.upsert_document(
            request.deployment_id,
            request.workspace_id,
            request.document_id,
            request.source_id,
            request.version,
            header,
            chunks,
            vectors,
            self._embedding.model_version,
        )
        return DocumentSyncResult(
            status=status,
            source_id=request.source_id,
            generation_id=generation_id,
            extracted_text=text.strip()[:MAX_RETURNED_EXTRACTED_CHARS],
        )


class RetrieveWorkspaceKnowledge:
    """Retrieve relevant workspace-scoped Knowledge chunks for conversational grounding."""

    def __init__(self, store: DocumentKnowledgeStorePort, embedding: EmbeddingPort):
        self._store = store
        self._embedding = embedding

    def __call__(
        self,
        *,
        deployment_id: str,
        workspace_id: str,
        query: str,
        top_k: int = 5,
    ) -> tuple[WorkspaceKnowledgeHit, ...]:
        cleaned = query.strip()
        if not cleaned:
            return ()
        bounded_query = _truncate_utf8(cleaned, 2048)
        try:
            vectors = self._embedding.embed((bounded_query,))
        except Exception as exc:
            raise KnowledgeStoreUnavailable("Query embedding failed") from exc
        if len(vectors) != 1 or len(vectors[0]) != self._embedding.dimension:
            raise KnowledgeStoreUnavailable("Query embedding had unexpected dimensions")
        return self._store.retrieve_workspace(
            deployment_id,
            workspace_id,
            vectors[0],
            self._embedding.model_version,
            top_k=max(1, min(top_k, 10)),
            query_text=bounded_query,
        )


def _truncate_utf8(text: str, max_bytes: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore").strip()

