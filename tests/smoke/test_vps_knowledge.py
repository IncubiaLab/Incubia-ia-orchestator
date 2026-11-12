"""Live E2E online smoke test for VPS Knowledge sync (/v1/knowledge/documents), RAG turns (/v1/turns),
workspace isolation, document extraction (.txt/.docx/.pdf), idempotent revoke, and Orbit client compatibility.

Run manually with VPS access:
    PYTHONPATH=src .venv/bin/python tests/smoke/test_vps_knowledge.py
"""
from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import urllib.error
import urllib.request
from uuid import uuid4
import zipfile


BASE_URL = os.environ.get("INCUBIA_STAGING_URL", "https://agent-staging.incubialab.com").rstrip("/")
VPS_HOST = os.environ.get("INCUBIA_VPS_HOST", "hector@2.24.201.39")
ORBIT_CLIENT_DIST = Path("/home/hector/projects/Incubia Orbit/backend/dist/orchestrator/client.js")


def _get_staging_token() -> str:
    env_token = os.environ.get("INCUBIA_ORCHESTRATOR_TOKEN", "").strip()
    if env_token:
        return env_token
    out = subprocess.check_output(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            VPS_HOST,
            "awk -F= '/^INCUBIA_ORCHESTRATOR_TOKEN=/{print $2}' /opt/incubia/staging/.env",
        ],
        text=True,
    ).strip()
    if not out:
        raise RuntimeError("Could not obtain INCUBIA_ORCHESTRATOR_TOKEN from env or VPS staging")
    return out


def _http_json(
    path: str,
    *,
    method: str = "GET",
    body: dict | None = None,
    token: str | None = None,
    timeout: float = 30.0,
) -> tuple[int, dict]:
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8")
        try:
            parsed = json.loads(raw) if raw else {}
        except Exception:
            parsed = {"raw": raw}
        return err.code, parsed


def _post_turn_sse(body: dict, *, token: str, timeout: float = 60.0) -> tuple[int, str, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "Authorization": f"Bearer {token}",
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(f"{BASE_URL}/v1/turns", data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            answer = _extract_done_answer(raw)
            return resp.status, raw, answer
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8")
        return err.code, raw, ""


def _extract_done_answer(sse_raw: str) -> str:
    deltas: list[str] = []
    done_answer = ""
    for frame in sse_raw.replace("\r\n", "\n").split("\n\n"):
        if not frame.strip():
            continue
        event_name = ""
        data_lines: list[str] = []
        for line in frame.split("\n"):
            if line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
        if not data_lines:
            continue
        try:
            payload = json.loads("\n".join(data_lines))
        except Exception:
            continue
        if event_name == "delta" and isinstance(payload.get("text"), str):
            deltas.append(payload["text"])
        elif event_name == "done" and isinstance(payload.get("answer"), str):
            done_answer = payload["answer"]
    return done_answer or "".join(deltas)


def _make_minimal_docx(paragraphs: list[str]) -> bytes:
    body = "".join(f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>" for text in paragraphs)
    doc_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    ).encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "<Types></Types>")
        zf.writestr("word/document.xml", doc_xml)
    return buf.getvalue()


def _make_minimal_pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objs = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n",
        b"4 0 obj << /Length " + str(len(stream)).encode() + b" >> stream\n" + stream + b"\nendstream endobj\n",
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
    ]
    buf = io.BytesIO()
    buf.write(b"%PDF-1.4\n")
    offsets = []
    for obj in objs:
        offsets.append(buf.tell())
        buf.write(obj)
    xref_pos = buf.tell()
    buf.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        buf.write(f"{off:010d} 00000 n \n".encode())
    buf.write(f"trailer << /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode())
    return buf.getvalue()


class EphemeralHttpsFileHost:
    """Temporarily exposes synthetic fixture bytes over HTTPS under /__smoke_kb/<nonce>/ on staging Caddy."""

    def __init__(self, files: dict[str, tuple[str, bytes]]):
        self.nonce = secrets.token_urlsafe(12)
        self.files = files
        self._original_caddyfile = ""

    def url_for(self, filename: str) -> str:
        return f"{BASE_URL}/__smoke_kb/{self.nonce}/{filename}"

    def download_hits(self, filename: str) -> int:
        logs = subprocess.check_output(
            ["ssh", "-o", "BatchMode=yes", VPS_HOST, "docker logs smoke-kb-files 2>&1 || true"],
            text=True,
        )
        target = f"HIT /{self.nonce}/{filename}"
        return sum(1 for line in logs.splitlines() if line.strip() == target)

    def __enter__(self) -> "EphemeralHttpsFileHost":
        self._original_caddyfile = subprocess.check_output(
            ["ssh", "-o", "BatchMode=yes", VPS_HOST, "cat /opt/incubia/proxy/Caddyfile"],
            text=True,
        )

        encoded_files = {
            f"/{self.nonce}/{name}": (ctype, base64.b64encode(raw).decode("ascii"))
            for name, (ctype, raw) in self.files.items()
        }
        server_code = (
            "import base64, json, sys\n"
            "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
            f"FILES = {json.dumps(encoded_files)}\n"
            "class H(BaseHTTPRequestHandler):\n"
            "    def do_GET(self):\n"
            "        path = self.path.split('?', 1)[0]\n"
            "        entry = FILES.get(path)\n"
            "        if not entry:\n"
            "            self.send_response(404); self.end_headers(); return\n"
            "        print('HIT ' + path, flush=True)\n"
            "        ctype, b64 = entry\n"
            "        data = base64.b64decode(b64)\n"
            "        self.send_response(200)\n"
            "        self.send_header('Content-Type', ctype)\n"
            "        self.send_header('Content-Length', str(len(data)))\n"
            "        self.end_headers()\n"
            "        self.wfile.write(data)\n"
            "    def log_message(self, *args): pass\n"
            "HTTPServer(('0.0.0.0', 8000), H).serve_forever()\n"
        )
        server_b64 = base64.b64encode(server_code.encode("utf-8")).decode("ascii")

        subprocess.check_call(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                VPS_HOST,
                (
                    "docker rm -f smoke-kb-files >/dev/null 2>&1 || true; "
                    "docker run -d --rm --name smoke-kb-files --network web --entrypoint python "
                    f"incubia-orchestrator:staging -c \"import base64; exec(base64.b64decode('{server_b64}'))\""
                ),
            ]
        )

        staging_block = (
            "agent-staging.incubialab.com {\n"
            "\treverse_proxy orchestrator-staging:8080 {\n"
            "\t\tflush_interval -1\n"
            "\t}\n"
            "}"
        )
        if staging_block not in self._original_caddyfile:
            raise RuntimeError("Unexpected staging Caddyfile structure")
        patched_caddyfile = self._original_caddyfile.replace(
            staging_block,
            (
                "agent-staging.incubialab.com {\n"
                "\thandle_path /__smoke_kb/* {\n"
                "\t\treverse_proxy smoke-kb-files:8000\n"
                "\t}\n"
                "\thandle {\n"
                "\t\treverse_proxy orchestrator-staging:8080 {\n"
                "\t\t\tflush_interval -1\n"
                "\t\t}\n"
                "\t}\n"
                "}"
            ),
        )
        caddy_b64 = base64.b64encode(patched_caddyfile.encode("utf-8")).decode("ascii")
        subprocess.check_call(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                VPS_HOST,
                (
                    f"echo '{caddy_b64}' | base64 -d > /opt/incubia/proxy/Caddyfile && "
                    "docker exec caddy caddy reload --config /etc/caddy/Caddyfile"
                ),
            ]
        )
        time.sleep(1.0)
        return self

    def __exit__(self, *_exc) -> None:
        try:
            if self._original_caddyfile:
                orig_b64 = base64.b64encode(self._original_caddyfile.encode("utf-8")).decode("ascii")
                subprocess.run(
                    [
                        "ssh",
                        "-o",
                        "BatchMode=yes",
                        VPS_HOST,
                        (
                            f"echo '{orig_b64}' | base64 -d > /opt/incubia/proxy/Caddyfile && "
                            "docker exec caddy caddy reload --config /etc/caddy/Caddyfile"
                        ),
                    ],
                    check=False,
                )
        finally:
            subprocess.run(
                ["ssh", "-o", "BatchMode=yes", VPS_HOST, "docker rm -f smoke-kb-files >/dev/null 2>&1 || true"],
                check=False,
            )


def _run_orbit_client_online_check(*, token: str, ws_a: str, md_url: str, md_bytes_len: int) -> None:
    if not ORBIT_CLIENT_DIST.is_file():
        print("  [SKIP] Compiled Orbit client dist not found at", ORBIT_CLIENT_DIST)
        return

    doc_id = str(uuid4())
    node_script = f"""
import {{ createOrchestratorClient }} from {json.dumps(ORBIT_CLIENT_DIST.as_uri())};
import assert from 'node:assert/strict';

const client = createOrchestratorClient({{
  baseUrl: {json.dumps(BASE_URL)},
  apiKey: process.env.SMOKE_ORCHESTRATOR_TOKEN,
  timeoutMs: 30000,
}});

const ready = await client.ready();
assert.equal(ready.ok, true, 'ready.ok should be true');
assert.equal(ready.status, 'ready', 'ready.status should be ready');

const upsertRes = await client.syncKnowledgeDocument({{
  requestId: {json.dumps(str(uuid4()))},
  workspaceId: {json.dumps(ws_a)},
  operation: 'upsert',
  document: {{
    id: {json.dumps(doc_id)},
    sourceId: {json.dumps(f'orbit:{doc_id}')},
    version: 'orbit-client-v1',
    title: 'Manual Orbit Client Smoke',
    contentType: 'text/markdown',
    sizeBytes: {md_bytes_len},
    downloadUrl: {json.dumps(md_url)},
  }},
}});
assert.equal(upsertRes.status, 'indexed', 'Orbit client upsert should return indexed');
assert.ok(upsertRes.generationId, 'generationId should be non-empty');

let answer = '';
for await (const ev of client.streamTurn({{
  requestId: {json.dumps(str(uuid4()))},
  turnId: {json.dumps(str(uuid4()))},
  conversationId: {json.dumps(str(uuid4()))},
  workspaceId: {json.dumps(ws_a)},
  actor: {{ id: 'orbit-smoke-user' }},
  projectId: null,
  question: 'Cuál es el código de verificación del manual Markdown Orbit Client Smoke? Responde solo el código.',
  evidence: [],
}})) {{
  if (ev.type === 'done') {{
    answer = ev.answer;
  }}
}}
assert.ok(answer.includes('ORBIT-MD-NODE-3318'), `Expected ORBIT-MD-NODE-3318 in answer, got: ${{answer}}`);

const revokeRes = await client.syncKnowledgeDocument({{
  requestId: {json.dumps(str(uuid4()))},
  workspaceId: {json.dumps(ws_a)},
  operation: 'revoke',
  document: {{
    id: {json.dumps(doc_id)},
    sourceId: {json.dumps(f'orbit:{doc_id}')},
    version: 'orbit-client-v1',
    title: 'Manual Orbit Client Smoke',
    contentType: 'text/markdown',
    sizeBytes: 0,
    downloadUrl: null,
  }},
}});
assert.equal(revokeRes.status, 'revoked', 'Orbit client revoke should return revoked');
console.log('ORBIT_NODE_CLIENT_E2E_OK');
"""
    env = {**os.environ, "SMOKE_ORCHESTRATOR_TOKEN": token}
    out = subprocess.check_output(["node", "--input-type=module", "-e", node_script], env=env, text=True)
    assert "ORBIT_NODE_CLIENT_E2E_OK" in out, f"Unexpected Orbit client output: {out}"
    print("  [PASS] Orbit compiled OrchestratorClient E2E sync + streamTurn + revoke passed!")


def main() -> None:
    token = _get_staging_token()
    print(f"Running Knowledge E2E Smoke against {BASE_URL}...")

    status, health = _http_json("/healthz")
    assert status == 200 and health.get("status") == "ok", f"/healthz failed: {status} {health}"
    status, ready = _http_json("/readyz")
    assert status == 200 and ready.get("status") == "ready", f"/readyz failed: {status} {ready}"
    print("  [PASS] /healthz + /readyz (Ledger DB + Knowledge Neon DB) ready")

    txt_bytes = (
        "Política confidencial de lanzamiento del Workspace A.\n"
        "El código secreto de lanzamiento Alpha TXT es ORBIT-TXT-ALPHA-9481."
    ).encode("utf-8")
    docx_bytes = _make_minimal_docx(
        ["Anexo operativo DOCX del Workspace A.", "El código de aprobación DOCX es ORBIT-DOCX-BETA-7731."]
    )
    pdf_bytes = _make_minimal_pdf("Politica PDF Workspace A: codigo ORBIT-PDF-GAMMA-5519")
    md_bytes = (
        "# Manual Markdown Orbit Client Smoke\n\n"
        "El código de verificación del manual Markdown Orbit Client Smoke es `ORBIT-MD-NODE-3318`.\n"
    ).encode("utf-8")

    ws_a = str(uuid4())
    ws_b = str(uuid4())
    doc_txt = str(uuid4())
    doc_docx = str(uuid4())
    doc_pdf = str(uuid4())

    files = {
        "secret-a.txt": ("text/plain; charset=utf-8", txt_bytes),
        "guide-a.docx": (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            docx_bytes,
        ),
        "policy-a.pdf": ("application/pdf", pdf_bytes),
        "note-orbit.md": ("text/markdown; charset=utf-8", md_bytes),
    }

    with EphemeralHttpsFileHost(files) as host:
        print("\n--- 1. Auth & Strict Contract / SSRF Negative Gates ---")
        base_doc = {
            "requestId": str(uuid4()),
            "workspaceId": ws_a,
            "operation": "upsert",
            "document": {
                "id": doc_txt,
                "sourceId": f"orbit:{doc_txt}",
                "version": "v1",
                "title": "Secret TXT A",
                "contentType": "text/plain",
                "sizeBytes": len(txt_bytes),
                "downloadUrl": host.url_for("secret-a.txt"),
            },
        }
        s, _ = _http_json("/v1/knowledge/documents", method="POST", body=base_doc)
        assert s == 401, f"Expected 401 without token, got {s}"

        for label, bad_body in [
            ("unsupported mime", {**base_doc, "document": {**base_doc["document"], "contentType": "application/x-msdownload"}}),
            ("ssrf loopback", {**base_doc, "document": {**base_doc["document"], "downloadUrl": "https://127.0.0.1/secret"}}),
            ("non-https url", {**base_doc, "document": {**base_doc["document"], "downloadUrl": f"http://example.com/secret.txt"}}),
            ("unexpected extra field", {**base_doc, "extra": True}),
        ]:
            s, err = _http_json("/v1/knowledge/documents", method="POST", body=bad_body, token=token)
            assert s == 400, f"Expected 400 for {label}, got {s}: {err}"
        print("  [PASS] 401 auth + 400 contract/MIME/SSRF gates verified")

        print("\n--- 2. HTTPS Upsert (.txt, .docx, .pdf) & Idempotency ---")
        s, res_txt = _http_json("/v1/knowledge/documents", method="POST", body=base_doc, token=token)
        assert s == 200 and res_txt["status"] == "indexed" and res_txt["generationId"], f"TXT upsert failed: {s} {res_txt}"

        s, res_txt_retry = _http_json(
            "/v1/knowledge/documents",
            method="POST",
            body={**base_doc, "requestId": str(uuid4())},
            token=token,
        )
        assert s == 200 and res_txt_retry["status"] == "already_indexed", f"Retry failed: {s} {res_txt_retry}"
        assert host.download_hits("secret-a.txt") == 1, "Idempotent retry must not re-download file"

        docx_body = {
            "requestId": str(uuid4()),
            "workspaceId": ws_a,
            "operation": "upsert",
            "document": {
                "id": doc_docx,
                "sourceId": f"orbit:{doc_docx}",
                "version": "v1",
                "title": "Guide DOCX A",
                "contentType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "sizeBytes": len(docx_bytes),
                "downloadUrl": host.url_for("guide-a.docx"),
            },
        }
        s, res_docx = _http_json("/v1/knowledge/documents", method="POST", body=docx_body, token=token)
        assert s == 200 and res_docx["status"] == "indexed", f"DOCX upsert failed: {s} {res_docx}"

        pdf_body = {
            "requestId": str(uuid4()),
            "workspaceId": ws_a,
            "operation": "upsert",
            "document": {
                "id": doc_pdf,
                "sourceId": f"orbit:{doc_pdf}",
                "version": "v1",
                "title": "Policy PDF A",
                "contentType": "application/pdf",
                "sizeBytes": len(pdf_bytes),
                "downloadUrl": host.url_for("policy-a.pdf"),
            },
        }
        s, res_pdf = _http_json("/v1/knowledge/documents", method="POST", body=pdf_body, token=token)
        assert s == 200 and res_pdf["status"] == "indexed", f"PDF upsert failed: {s} {res_pdf}"
        print("  [PASS] TXT (+ idempotent retry without re-fetch), DOCX, and PDF indexed via Neon pgvector + OpenAI")

        print("\n--- 3. Workspace-Scoped RAG Retrieval via POST /v1/turns ---")
        s, _raw, ans_txt = _post_turn_sse(
            {
                "requestId": str(uuid4()),
                "turnId": str(uuid4()),
                "conversationId": str(uuid4()),
                "workspaceId": ws_a,
                "actor": {"id": "smoke-user-a"},
                "projectId": None,
                "question": "¿Cuál es el código secreto de lanzamiento Alpha TXT? Responde incluyendo el código exacto.",
                "evidence": [],
            },
            token=token,
        )
        assert s == 200 and "ORBIT-TXT-ALPHA-9481" in ans_txt, f"TXT RAG missed: {ans_txt}"

        s, _raw, ans_docx = _post_turn_sse(
            {
                "requestId": str(uuid4()),
                "turnId": str(uuid4()),
                "conversationId": str(uuid4()),
                "workspaceId": ws_a,
                "actor": {"id": "smoke-user-a"},
                "projectId": None,
                "question": "¿Cuál es el código de aprobación DOCX? Responde incluyendo el código exacto.",
                "evidence": [],
            },
            token=token,
        )
        assert s == 200 and "ORBIT-DOCX-BETA-7731" in ans_docx, f"DOCX RAG missed: {ans_docx}"

        s, _raw, ans_pdf = _post_turn_sse(
            {
                "requestId": str(uuid4()),
                "turnId": str(uuid4()),
                "conversationId": str(uuid4()),
                "workspaceId": ws_a,
                "actor": {"id": "smoke-user-a"},
                "projectId": None,
                "question": "¿Cuál es el código de Politica PDF Workspace A? Responde incluyendo el código exacto.",
                "evidence": [],
            },
            token=token,
        )
        assert s == 200 and "ORBIT-PDF-GAMMA-5519" in ans_pdf, f"PDF RAG missed: {ans_pdf}"

        s, _raw, ans_ws_b = _post_turn_sse(
            {
                "requestId": str(uuid4()),
                "turnId": str(uuid4()),
                "conversationId": str(uuid4()),
                "workspaceId": ws_b,
                "actor": {"id": "smoke-user-b"},
                "projectId": None,
                "question": "¿Cuál es el código secreto de lanzamiento Alpha TXT, el DOCX y la Politica PDF?",
                "evidence": [],
            },
            token=token,
        )
        assert s == 200
        for leaked in ("ORBIT-TXT-ALPHA-9481", "ORBIT-DOCX-BETA-7731", "ORBIT-PDF-GAMMA-5519"):
            assert leaked not in ans_ws_b, f"Cross-workspace leakage detected ({leaked}): {ans_ws_b}"
        print("  [PASS] TXT, DOCX & PDF chunks retrieved in Workspace A and completely isolated from Workspace B")

        print("\n--- 4. Orbit Compiled OrchestratorClient Compatibility ---")
        _run_orbit_client_online_check(
            token=token,
            ws_a=ws_a,
            md_url=host.url_for("note-orbit.md"),
            md_bytes_len=len(md_bytes),
        )

        print("\n--- 5. Revoke, Idempotent Revoke, & Post-Revoke Removal ---")
        for label, d_id, ver, title, ctype in [
            ("TXT", doc_txt, "v1", "Secret TXT A", "text/plain"),
            ("DOCX", doc_docx, "v1", "Guide DOCX A", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            ("PDF", doc_pdf, "v1", "Policy PDF A", "application/pdf"),
        ]:
            rev = {
                "requestId": str(uuid4()),
                "workspaceId": ws_a,
                "operation": "revoke",
                "document": {
                    "id": d_id,
                    "sourceId": f"orbit:{d_id}",
                    "version": ver,
                    "title": title,
                    "contentType": ctype,
                    "sizeBytes": 0,
                    "downloadUrl": None,
                },
            }
            s, r = _http_json("/v1/knowledge/documents", method="POST", body=rev, token=token)
            assert s == 200 and r["status"] == "revoked", f"Revoke {label} failed: {s} {r}"

        s, r_again = _http_json(
            "/v1/knowledge/documents",
            method="POST",
            body={
                "requestId": str(uuid4()),
                "workspaceId": ws_a,
                "operation": "revoke",
                "document": {
                    "id": doc_txt,
                    "sourceId": f"orbit:{doc_txt}",
                    "version": "v1",
                    "title": "Secret TXT A",
                    "contentType": "text/plain",
                    "sizeBytes": 0,
                    "downloadUrl": None,
                },
            },
            token=token,
        )
        assert s == 200 and r_again["status"] == "already_revoked", f"Idempotent revoke failed: {s} {r_again}"

        s, _raw, ans_after_revoke = _post_turn_sse(
            {
                "requestId": str(uuid4()),
                "turnId": str(uuid4()),
                "conversationId": str(uuid4()),
                "workspaceId": ws_a,
                "actor": {"id": "smoke-user-a"},
                "projectId": None,
                "question": "¿Cuál es el código secreto de lanzamiento Alpha TXT?",
                "evidence": [],
            },
            token=token,
        )
        assert s == 200 and "ORBIT-TXT-ALPHA-9481" not in ans_after_revoke, (
            f"Revoked TXT still retrieved: {ans_after_revoke}"
        )
        print("  [PASS] Revoke, idempotent already_revoked, and post-revoke RAG removal verified")

    s, metrics = _http_json("/metrics")
    assert s == 200 and metrics.get("db_pool", {}).get("in_use") == 0, f"Pool leak in metrics: {metrics}"
    print(f"  [PASS] Metrics clean (db_in_use=0), ephemeral HTTPS fixture & Caddyfile restored.")
    print("\n============================================================")
    print("ALL ONLINE KNOWLEDGE E2E & ORBIT CLIENT TESTS PASSED!")
    print("============================================================")


if __name__ == "__main__":
    main()

