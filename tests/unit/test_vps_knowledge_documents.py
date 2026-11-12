"""Offline unit tests for POST /v1/knowledge/documents, extraction, SSRF guards, and RAG turns."""
from __future__ import annotations

import io
import json
import math
import socket
import urllib.error
import urllib.request
import zipfile
from uuid import uuid4

import httpx
import pytest

from incubia_orchestrator.bootstrap.vps import VPSService, VPSSettings
from incubia_orchestrator.foundation.contracts.execution import CompletedExecution, ExecutionOutput
from incubia_orchestrator.foundation.contracts.specialty import Specialty
from incubia_orchestrator.foundation.limits import load_runtime_limits
from incubia_orchestrator.interfaces.http.service import (
    VPSHTTPServer,
    validate_knowledge_document_payload,
)
from incubia_orchestrator.modules.knowledge.adapters.document_extract import DocumentTextExtractor
from incubia_orchestrator.modules.knowledge.adapters.document_http import (
    HttpxDocumentDownloader,
    validate_download_url,
)
from incubia_orchestrator.modules.knowledge.adapters.embedding import HashEmbedding
from incubia_orchestrator.modules.knowledge.application.document_sync import (
    RetrieveWorkspaceKnowledge,
    SyncDocumentKnowledge,
)
from incubia_orchestrator.modules.knowledge.domain import (
    DocumentDownloadError,
    DocumentExtractionError,
    DocumentRejectedError,
    WorkspaceKnowledgeHit,
)
from tests.unit.test_vps_bootstrap import FakeLedger, loopback


def _build_minimal_docx(paragraphs: list[str]) -> bytes:
    body = "".join(
        f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>" for text in paragraphs
    )
    doc_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", doc_xml)
    return buf.getvalue()


def _build_minimal_pdf(text: str) -> bytes:
    safe_text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({safe_text}) Tj ET".encode("latin-1")
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /MediaBox [0 0 612 792] /Contents 5 0 R >>\nendobj\n",
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        f"5 0 obj\n<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream\nendobj\n",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for obj in objects:
        offsets.append(len(out))
        out.extend(obj)
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for off in offsets:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("ascii")
    )
    return bytes(out)


class InMemoryDocumentStore:
    def __init__(self):
        self.active_gen: str | None = None
        self.model_version: str | None = None
        self.docs: dict[tuple[str, str], dict] = {}
        self.chunks: list[dict] = []

    def ready(self, deployment_id: str) -> bool:
        return True

    def is_document_active(self, deployment_id, workspace_id, document_id, version, model_version):
        record = self.docs.get((workspace_id, document_id))
        if (
            record
            and not record["revoked"]
            and record["version"] == version
            and self.model_version == model_version
            and self.active_gen
        ):
            return self.active_gen
        return None

    def upsert_document(self, deployment_id, workspace_id, document_id, source_id, version, title, chunks, embeddings, model_version):
        if self.is_document_active(deployment_id, workspace_id, document_id, version, model_version):
            return "already_indexed", self.active_gen
        self.chunks = [
            c for c in self.chunks if not (c["workspace_id"] == workspace_id and c["document_id"] == document_id)
        ]
        gen_id = f"gen-{uuid4().hex[:12]}"
        self.active_gen = gen_id
        self.model_version = model_version
        self.docs[(workspace_id, document_id)] = {
            "source_id": source_id,
            "version": version,
            "title": title,
            "revoked": False,
        }
        for idx, (text, vec) in enumerate(zip(chunks, embeddings, strict=True)):
            self.chunks.append(
                {
                    "workspace_id": workspace_id,
                    "document_id": document_id,
                    "source_id": source_id,
                    "chunk_id": f"orbit:{workspace_id}:{document_id}:{idx}",
                    "generation_id": gen_id,
                    "title": title,
                    "text": text,
                    "vector": vec,
                }
            )
        return "indexed", gen_id

    def revoke_document(self, deployment_id, workspace_id, document_id, source_id):
        record = self.docs.get((workspace_id, document_id))
        if not record or record["revoked"]:
            return "already_revoked", self.active_gen
        record["revoked"] = True
        self.chunks = [
            c for c in self.chunks if not (c["workspace_id"] == workspace_id and c["document_id"] == document_id)
        ]
        self.active_gen = f"gen-{uuid4().hex[:12]}" if self.chunks else None
        return "revoked", self.active_gen

    def retrieve_workspace(self, deployment_id, workspace_id, query_vector, model_version, *, top_k=5, query_text=""):
        hits = []
        for chunk in self.chunks:
            if chunk["workspace_id"] != workspace_id:
                continue
            dot = sum(a * b for a, b in zip(query_vector, chunk["vector"], strict=True))
            hits.append(
                WorkspaceKnowledgeHit(
                    deployment_id=deployment_id,
                    workspace_id=workspace_id,
                    document_id=chunk["document_id"],
                    source_id=chunk["source_id"],
                    chunk_id=chunk["chunk_id"],
                    generation_id=chunk["generation_id"],
                    title=chunk["title"],
                    text=chunk["text"],
                    score=max(0.0, min(1.0, float(dot))),
                )
            )
        hits.sort(key=lambda h: (-h.score, h.chunk_id))
        return tuple(hits[:top_k])


class CapturingRuntime:
    def __init__(self):
        self.last_message = ""

    def execute(self, *, request_id, execution_id, scope, message, history):
        self.last_message = message
        return CompletedExecution(
            request_id,
            execution_id,
            ExecutionOutput(f"Echo: {message[:120]}", specialty=Specialty.GENERAL),
        )


def _valid_payload(operation: str = "upsert", **overrides):
    doc_id = str(uuid4())
    payload = {
        "requestId": str(uuid4()),
        "workspaceId": str(uuid4()),
        "operation": operation,
        "document": {
            "id": doc_id,
            "sourceId": f"orbit:{doc_id}",
            "version": "etag-v1",
            "title": "Manual Orbit",
            "contentType": "text/plain",
            "sizeBytes": 128 if operation == "upsert" else 0,
            "downloadUrl": "https://storage.example.com/signed-obj" if operation == "upsert" else None,
        },
    }
    for k, v in overrides.items():
        if k.startswith("document."):
            payload["document"][k.split(".", 1)[1]] = v
        else:
            payload[k] = v
    return payload


def _http_post(url: str, body: dict, *, token: str | None = None):
    data = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8")


def test_validate_knowledge_document_payload_strict_contract():
    valid_upsert = _valid_payload("upsert")
    parsed = validate_knowledge_document_payload(valid_upsert, deployment_id="incubia-test")
    assert parsed.operation == "upsert"
    assert parsed.source_id == f"orbit:{parsed.document_id}"

    valid_revoke = _valid_payload("revoke")
    parsed_revoke = validate_knowledge_document_payload(valid_revoke, deployment_id="incubia-test")
    assert parsed_revoke.operation == "revoke"
    assert parsed_revoke.download_url is None

    for bad in (
        {**valid_upsert, "extra": 1},
        {k: v for k, v in valid_upsert.items() if k != "workspaceId"},
        _valid_payload("upsert", **{"document.contentType": "application/x-msdownload"}),
        _valid_payload("upsert", **{"document.sourceId": f"orbit:{uuid4()}"}),
        _valid_payload("upsert", **{"document.sizeBytes": True}),
        _valid_payload("upsert", **{"document.sizeBytes": 0}),
        _valid_payload("revoke", **{"document.downloadUrl": "https://storage.example.com/x"}),
    ):
        with pytest.raises(Exception):
            validate_knowledge_document_payload(bad, deployment_id="incubia-test")


def test_download_ssrf_and_size_bounds(monkeypatch):
    with pytest.raises(DocumentRejectedError):
        validate_download_url("http://storage.example.com/doc.txt")
    with pytest.raises(DocumentRejectedError):
        validate_download_url("https://127.0.0.1/secret")
    with pytest.raises(DocumentRejectedError):
        validate_download_url("https://169.254.169.254/latest/meta-data/")
    with pytest.raises(DocumentRejectedError):
        validate_download_url("https://user:pass@storage.example.com/doc.txt")

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, type=0: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )

    secret_signed_url = "https://storage.example.com/object?X-Amz-Signature=supersecret"
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"A" * 200)
    )
    client = httpx.Client(transport=transport)
    downloader = HttpxDocumentDownloader(client=client)

    with pytest.raises(DocumentRejectedError) as exc_info:
        downloader.download(secret_signed_url, declared_size_bytes=100, max_bytes=1024)
    assert "supersecret" not in str(exc_info.value)

    error_transport = httpx.MockTransport(
        lambda request: httpx.Response(403, content=b"forbidden")
    )
    failing = HttpxDocumentDownloader(client=httpx.Client(transport=error_transport))
    with pytest.raises(DocumentDownloadError) as dl_err:
        failing.download(secret_signed_url, declared_size_bytes=100, max_bytes=1024)
    assert "supersecret" not in str(dl_err.value)


def test_document_text_extractor_all_supported_formats():
    extractor = DocumentTextExtractor()

    txt = extractor.extract_text(b"\xef\xbb\xbfHola\x00\r\nmundo", content_type="text/plain; charset=utf-8")
    assert txt == "Hola\nmundo"

    md = extractor.extract_text(b"# Titulo\n\nContenido markdown", content_type="text/markdown")
    assert "Titulo" in md and "Contenido markdown" in md

    csv_text = extractor.extract_text(b"nombre,codigo\nOrbit,KB-42\n", content_type="text/csv")
    assert "Orbit | KB-42" in csv_text

    docx_bytes = _build_minimal_docx(["Primer parrafo", "Codigo secreto DOCX-99"])
    assert "DOCX-99" in extractor.extract_text(
        docx_bytes,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    pdf_bytes = _build_minimal_pdf("Contrato PDF-77 autorizado")
    assert "PDF-77" in extractor.extract_text(pdf_bytes, content_type="application/pdf")

    with pytest.raises(DocumentExtractionError):
        extractor.extract_text(b"   \x00  ", content_type="text/plain")
    with pytest.raises(DocumentExtractionError):
        extractor.extract_text(b"not-a-zip", content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


def test_vps_settings_rejects_partial_knowledge_env():
    base_env = {
        "INCUBIA_ORCHESTRATOR_TOKEN": "0123456789abcdef0123456789abcdef",
        "DATABASE_URL": "postgresql://incubia_runtime:pw@ep-ex-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require",
        "INCUBIA_FAKE_MODE": "1",
        "INCUBIA_KNOWLEDGE_RUNTIME_DATABASE_URL": "postgresql://incubia_kb_runtime:pw@ep-ex-pooler.us-east-2.aws.neon.tech/kb?sslmode=require",
    }
    with pytest.raises(ValueError):
        VPSSettings.from_env(base_env)


def test_http_knowledge_endpoint_and_workspace_scoped_rag_turn(loopback):
    token = "0123456789abcdef0123456789abcdef"
    settings = VPSSettings(
        database_url="postgresql://fake",
        token=token,
        deployment_id="incubia-test",
        fake_mode=True,
        model="fake",
    )
    limits = load_runtime_limits()
    runtime = CapturingRuntime()
    store = InMemoryDocumentStore()
    embedding = HashEmbedding()
    extractor = DocumentTextExtractor()

    download_calls = 0
    files = {
        "https://cdn.example.com/ws-a-secret.txt": b"La clave confidencial del workspace A es ALPHA-101.",
    }

    def _mock_fetch(request: httpx.Request) -> httpx.Response:
        nonlocal download_calls
        download_calls += 1
        content = files.get(str(request.url))
        if content is None:
            return httpx.Response(404)
        return httpx.Response(200, content=content)

    downloader = HttpxDocumentDownloader(
        client=httpx.Client(transport=httpx.MockTransport(_mock_fetch)),
        allow_private_network=True,
    )
    sync_uc = SyncDocumentKnowledge(store, downloader, extractor, embedding)
    retrieve_uc = RetrieveWorkspaceKnowledge(store, embedding)

    service = VPSService(
        settings,
        FakeLedger(),
        runtime,
        limits,
        knowledge_sync=sync_uc,
        knowledge_retrieve=retrieve_uc,
        knowledge_ready=lambda: True,
        knowledge_deployment_id="incubia-test",
    )
    server = VPSHTTPServer(("127.0.0.1", 0), service)
    port = server.server_address[1]
    import threading
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        ws_a = str(uuid4())
        ws_b = str(uuid4())
        doc_id = str(uuid4())
        upsert_body = {
            "requestId": str(uuid4()),
            "workspaceId": ws_a,
            "operation": "upsert",
            "document": {
                "id": doc_id,
                "sourceId": f"orbit:{doc_id}",
                "version": "etag-1",
                "title": "Secreto WS-A",
                "contentType": "text/plain",
                "sizeBytes": len(files["https://cdn.example.com/ws-a-secret.txt"]),
                "downloadUrl": "https://cdn.example.com/ws-a-secret.txt",
            },
        }

        status, _ = _http_post(f"{base}/v1/knowledge/documents", upsert_body)
        assert status == 401

        status, raw = _http_post(f"{base}/v1/knowledge/documents", upsert_body, token=token)
        assert status == 200
        res = json.loads(raw)
        assert res["status"] == "indexed"
        assert res["sourceId"] == f"orbit:{doc_id}"
        assert res["generationId"]
        assert download_calls == 1

        # Idempotent retry does not re-download
        status, raw2 = _http_post(f"{base}/v1/knowledge/documents", upsert_body, token=token)
        assert status == 200
        assert json.loads(raw2)["status"] == "already_indexed"
        assert download_calls == 1

        # Turn in workspace A retrieves the indexed RAG content even with empty Orbit evidence
        turn_ws_a = {
            "requestId": str(uuid4()),
            "turnId": str(uuid4()),
            "conversationId": str(uuid4()),
            "workspaceId": ws_a,
            "actor": {"id": "user-a"},
            "projectId": None,
            "question": "¿Cuál es la clave confidencial?",
            "evidence": [],
        }
        status, _ = _http_post(f"{base}/v1/turns", turn_ws_a, token=token)
        assert status == 200
        assert "ALPHA-101" in runtime.last_message

        # Turn in workspace B never receives chunks from workspace A
        turn_ws_b = {
            "requestId": str(uuid4()),
            "turnId": str(uuid4()),
            "conversationId": str(uuid4()),
            "workspaceId": ws_b,
            "actor": {"id": "user-b"},
            "projectId": None,
            "question": "¿Cuál es la clave confidencial?",
            "evidence": [],
        }
        status, _ = _http_post(f"{base}/v1/turns", turn_ws_b, token=token)
        assert status == 200
        assert "ALPHA-101" not in runtime.last_message

        # Revoke removes it immediately and is idempotent
        revoke_body = {
            "requestId": str(uuid4()),
            "workspaceId": ws_a,
            "operation": "revoke",
            "document": {
                "id": doc_id,
                "sourceId": f"orbit:{doc_id}",
                "version": "etag-1",
                "title": "Secreto WS-A",
                "contentType": "text/plain",
                "sizeBytes": 0,
                "downloadUrl": None,
            },
        }
        status, raw_rev = _http_post(f"{base}/v1/knowledge/documents", revoke_body, token=token)
        assert status == 200
        assert json.loads(raw_rev)["status"] == "revoked"

        status, raw_rev2 = _http_post(f"{base}/v1/knowledge/documents", revoke_body, token=token)
        assert status == 200
        assert json.loads(raw_rev2)["status"] == "already_revoked"

        turn_ws_a_after = {**turn_ws_a, "requestId": str(uuid4()), "turnId": str(uuid4())}
        status, _ = _http_post(f"{base}/v1/turns", turn_ws_a_after, token=token)
        assert status == 200
        assert "ALPHA-101" not in runtime.last_message

        # Inline content (Linear ADR / Google Doc) and contentBase64 (Drive PDF)
        import base64
        linear_doc_id = str(uuid4())
        inline_text = "# ADR-ORCH-999\n\nDecisión arquitectónica clave LINEAR-ADR-777."
        inline_body = {
            "requestId": str(uuid4()),
            "workspaceId": ws_a,
            "operation": "upsert",
            "document": {
                "id": linear_doc_id,
                "sourceId": f"orbit:{linear_doc_id}",
                "version": "2026-11-12T00:00:00Z",
                "title": "[LINEAR · ADR] ADR-ORCH-999",
                "contentType": "text/markdown",
                "sizeBytes": len(inline_text.encode("utf-8")),
                "downloadUrl": None,
                "content": inline_text,
            },
        }
        status, raw_inline = _http_post(f"{base}/v1/knowledge/documents", inline_body, token=token)
        assert status == 200
        res_inline = json.loads(raw_inline)
        assert res_inline["status"] == "indexed"
        assert "LINEAR-ADR-777" in res_inline["extractedText"]
        assert download_calls == 1  # No external HTTP fetch made for inline content

        pdf_doc_id = str(uuid4())
        pdf_bytes = _build_minimal_pdf("Acta de reunion DRIVE-PDF-555 aprobada")
        pdf_body = {
            "requestId": str(uuid4()),
            "workspaceId": ws_a,
            "operation": "upsert",
            "document": {
                "id": pdf_doc_id,
                "sourceId": f"orbit:{pdf_doc_id}",
                "version": "2026-11-12T01:00:00Z",
                "title": "[DRIVE · PDF] ACT-001.pdf",
                "contentType": "application/pdf",
                "sizeBytes": len(pdf_bytes),
                "downloadUrl": None,
                "contentBase64": base64.b64encode(pdf_bytes).decode("ascii"),
            },
        }
        status, raw_pdf = _http_post(f"{base}/v1/knowledge/documents", pdf_body, token=token)
        assert status == 200
        res_pdf = json.loads(raw_pdf)
        assert res_pdf["status"] == "indexed"
        assert "DRIVE-PDF-555" in res_pdf["extractedText"]
    finally:
        server.shutdown()
        server.server_close()
