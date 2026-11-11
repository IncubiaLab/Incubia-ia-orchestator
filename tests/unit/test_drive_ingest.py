from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256

import pytest

from incubia_orchestrator.modules.knowledge.application.drive_ingest import (
    AclNotReviewedError, chunk_markdown, ingest_drive_root)
from incubia_orchestrator.modules.knowledge.domain import (
    ExportResult, InventoryEntry, SourceRef)

DOC = "application/vnd.google-apps.document"


def test_chunks_respect_byte_limit_and_keep_all_text():
    text = "# Título\n\n" + "\n\n".join(f"Párrafo {i} " + "ñ" * 300 for i in range(20))
    chunks = chunk_markdown(text, max_bytes=1000)
    assert len(chunks) > 1
    assert all(len(c.encode()) <= 1000 for c in chunks)
    for i in range(20):
        assert any(f"Párrafo {i} " in c for c in chunks)


def test_oversized_paragraph_is_split_on_utf8_boundaries():
    chunks = chunk_markdown("ñ" * 3000, max_bytes=500)
    assert all(len(c.encode()) <= 500 for c in chunks)
    assert "".join(chunks) == "ñ" * 3000


def test_empty_markdown_yields_no_chunks():
    assert chunk_markdown("  \n\n ", max_bytes=500) == []


def _entry(id_, mime=DOC, name="Doc"):
    ref = SourceRef(id_, name, mime, ("root",), "3", datetime(2026, 10, 1, tzinfo=timezone.utc))
    return InventoryEntry(ref, "root", 1, "document")


class FakeCatalog:
    def __init__(self, entries, bodies):
        self.entries, self.bodies = entries, bodies

    def inventory(self, root_id):
        return tuple(self.entries)

    def export_document(self, entry):
        body = self.bodies[entry.ref.source_id]
        return ExportResult(entry.ref.source_id, "text/markdown", body, sha256(body).hexdigest())


class FakeEmbedding:
    model_version, dimension = "fake:384", 384

    def __init__(self):
        self.batches = []

    def embed(self, texts):
        self.batches.append(len(texts))
        return tuple((1.0,) + (0.0,) * 383 for _ in texts)


class FakeRepository:
    def __init__(self):
        self.calls = []

    def publish(self, deployment_id, sources, embeddings, model_version):
        self.calls.append((deployment_id, list(sources), list(embeddings), model_version))
        return "gen-1"


def test_ingest_publishes_one_generation_with_provenance():
    catalog = FakeCatalog(
        [_entry("d1", name="Guía"), _entry("f1", mime="application/vnd.google-apps.folder"),
         _entry("p1", mime="application/pdf")],
        {"d1": b"\xef\xbb\xbf# Guia\r\n\r\nContenido " + b"x" * 2500 + b"\r\n\r\nMas texto\r\n"})
    embedding, repo = FakeEmbedding(), FakeRepository()
    report = ingest_drive_root(catalog, "root", embedding, repo, "incubialab", acl_reviewed=True,
                               max_chunk_bytes=1500, batch_size=2)
    deployment, sources, vectors, model = repo.calls[0]
    assert deployment == "incubialab" and model == "fake:384" and len(sources) == len(vectors)
    assert [s.source_id for s in sources] == [f"drive:d1:{i}" for i in range(len(sources))]
    assert all(s.version == "3" and s.public_ref == "https://drive.google.com/open?id=d1" for s in sources)
    assert all(s.content.startswith("Guía\n\n") for s in sources)
    assert all("\r" not in s.content and "﻿" not in s.content for s in sources)
    assert max(embedding.batches) <= 2
    assert report.generation_id == "gen-1" and report.documents == 1 and report.chunks == len(sources)
    assert report.skipped == {"application/pdf": 1}


def test_ingest_refuses_without_acl_review():
    repo = FakeRepository()
    with pytest.raises(AclNotReviewedError):
        ingest_drive_root(FakeCatalog([_entry("d1")], {"d1": b"x"}), "root", FakeEmbedding(), repo,
                          "incubialab", acl_reviewed=False)
    assert repo.calls == []


def test_ingest_with_no_documents_does_not_publish():
    repo = FakeRepository()
    report = ingest_drive_root(FakeCatalog([], {}), "root", FakeEmbedding(), repo, "incubialab",
                               acl_reviewed=True)
    assert repo.calls == [] and report.generation_id is None


def test_dry_run_counts_chunks_without_embedding_or_publishing():
    embedding, repo = FakeEmbedding(), FakeRepository()
    report = ingest_drive_root(FakeCatalog([_entry("d1")], {"d1": b"# A\n\nhola"}), "root", embedding,
                               repo, "incubialab", acl_reviewed=True, dry_run=True)
    assert report.chunks == 1 and embedding.batches == [] and repo.calls == []
