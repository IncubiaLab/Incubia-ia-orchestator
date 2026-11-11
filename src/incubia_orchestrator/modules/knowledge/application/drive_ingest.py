"""Ingest a Drive root into one atomic Knowledge generation.

Inventory -> Markdown export -> byte-bounded chunks -> batched embeddings ->
``KnowledgeRepository.publish``. Each chunk is published as its own source row
``drive:<file id>:<n>`` carrying the Drive version and link, because the current
schema is one chunk per source. ACL is still undecided per document, so the
operator must explicitly confirm the folder-level review before anything is
embedded or published. Reports carry counts only, never file names.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from incubia_orchestrator.modules.knowledge.domain import Source, SourceCatalogError
from incubia_orchestrator.modules.knowledge.ports import (
    EmbeddingPort, KnowledgeRepository, SourceCatalogPort)

GOOGLE_DOC = "application/vnd.google-apps.document"
_FOLDER = "application/vnd.google-apps.folder"
MAX_SOURCE_BYTES = 4096  # Source one-chunk limit in the domain


class AclNotReviewedError(SourceCatalogError):
    """Publishing requires an explicit folder-level ACL review."""


@dataclass(frozen=True)
class IngestReport:
    documents: int
    chunks: int
    generation_id: str | None
    skipped: dict[str, int] = field(default_factory=dict)


def chunk_markdown(text: str, *, max_bytes: int) -> list[str]:
    """Pack blank-line separated blocks into chunks of at most ``max_bytes`` UTF-8 bytes."""
    chunks: list[str] = []
    current = ""
    for block in (b.strip("\n") for b in re.split(r"\n\s*\n", text)):
        if not block.strip():
            continue
        for piece in _split_block(block, max_bytes):
            candidate = f"{current}\n\n{piece}" if current else piece
            if len(candidate.encode()) <= max_bytes:
                current = candidate
            else:
                chunks.append(current)
                current = piece
    if current:
        chunks.append(current)
    return chunks


def _split_block(block: str, max_bytes: int) -> list[str]:
    if len(block.encode()) <= max_bytes:
        return [block]
    pieces, current = [], ""
    for char in block:
        if len((current + char).encode()) > max_bytes:
            pieces.append(current)
            current = ""
        current += char
    if current:
        pieces.append(current)
    return pieces


def _normalize(content: bytes) -> str:
    text = content.decode("utf-8")
    if text.startswith("﻿"):
        text = text[1:]
    return text.replace("\r\n", "\n").replace("\r", "\n")


def ingest_drive_root(catalog: SourceCatalogPort, root_id: str, embedding: EmbeddingPort,
                      repository: KnowledgeRepository, deployment_id: str, *, acl_reviewed: bool,
                      max_chunk_bytes: int = 3500, batch_size: int = 64,
                      dry_run: bool = False) -> IngestReport:
    if not acl_reviewed:
        raise AclNotReviewedError("Folder-level ACL review must be confirmed before ingestion")
    if not deployment_id or batch_size < 1:
        raise ValueError("Trusted deployment and a positive batch size are required")
    skipped: Counter[str] = Counter()
    sources: list[Source] = []
    documents = 0
    for entry in catalog.inventory(root_id):
        ref = entry.ref
        if ref.mime_type == _FOLDER:
            continue
        if ref.mime_type != GOOGLE_DOC:
            skipped[ref.mime_type] += 1
            continue
        title = ref.name.strip() or ref.source_id
        body_limit = max_chunk_bytes - len(f"{title}\n\n".encode())
        if body_limit < 256 or max_chunk_bytes > MAX_SOURCE_BYTES:
            raise ValueError("Chunk limit leaves no room for content")
        chunks = chunk_markdown(_normalize(catalog.export_document(entry).content), max_bytes=body_limit)
        if not chunks:
            skipped["empty-document"] += 1
            continue
        documents += 1
        link = f"https://drive.google.com/open?id={ref.source_id}"
        sources.extend(Source(deployment_id, f"drive:{ref.source_id}:{index}", ref.observed_version,
                              f"{title}\n\n{chunk}", link) for index, chunk in enumerate(chunks))
    if dry_run or not sources:
        return IngestReport(documents, len(sources), None, dict(skipped))
    vectors: list[tuple[float, ...]] = []
    for start in range(0, len(sources), batch_size):
        vectors.extend(embedding.embed([s.content for s in sources[start:start + batch_size]]))
    generation = repository.publish(deployment_id, sources, vectors, embedding.model_version)
    return IngestReport(documents, len(sources), generation, dict(skipped))
