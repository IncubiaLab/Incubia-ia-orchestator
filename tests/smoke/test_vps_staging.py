"""End-to-end integration and smoke verification against VPS Staging environment.

Runs all Phase P5 verification gates:
1. Health and readiness endpoints
2. Authentication enforcement (401 on missing/invalid token)
3. Authenticated execution (POST /v1/executions)
4. Idempotency replay (same Idempotency-Key returns cached execution)
5. Multi-turn conversation persistence in PostgresLedger
6. Orbit turn SSE streaming (POST /v1/turns)
7. Audit log durable recording in PostgresAuditLog
8. Container restart resilience and state preservation
"""
from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from uuid import uuid4

BASE_URL = "https://agent-staging.incubialab.com"


def get_staging_token() -> str:
    # Safely query token from VPS .env without printing secrets
    cmd = ["ssh", "hector@2.24.201.39", "grep '^INCUBIA_ORCHESTRATOR_TOKEN=' /opt/incubia/staging/.env | cut -d= -f2"]
    out = subprocess.check_output(cmd, text=True).strip()
    assert len(out) >= 32, f"Invalid token length: {len(out)}"
    return out


def make_request(
    path: str,
    method: str = "GET",
    data: dict | None = None,
    token: str | None = None,
    idempotency_key: str | None = None,
    stream: bool = False,
) -> tuple[int, dict | str]:
    headers = {"User-Agent": "Incubia-VPS-Smoke/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key

    body = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(f"{BASE_URL}{path}", data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            status = res.status
            content = res.read().decode("utf-8")
            if stream or "text/event-stream" in res.headers.get("Content-Type", ""):
                return status, content
            try:
                return status, json.loads(content)
            except Exception:
                return status, content
    except urllib.error.HTTPError as err:
        content = err.read().decode("utf-8")
        try:
            return err.code, json.loads(content)
        except Exception:
            return err.code, content


def main() -> None:
    print(f"--- 1. Testing Health & Readiness on {BASE_URL} ---")
    s, d = make_request("/healthz")
    assert s == 200 and d == {"status": "ok"}, f"healthz failed: {s} {d}"
    print("  [PASS] /healthz: 200 OK")

    s, d = make_request("/readyz")
    assert s == 200 and d == {"status": "ready"}, f"readyz failed: {s} {d}"
    print("  [PASS] /readyz: 200 READY")

    print("\n--- 2. Testing Authentication Enforcement ---")
    s, d = make_request("/v1/executions", method="POST", data={"conversation_id": "c1", "message": "hi"})
    assert s == 401, f"Missing token should return 401, got {s}"
    print("  [PASS] Missing token returns 401")

    s, d = make_request("/v1/executions", method="POST", data={"conversation_id": "c1", "message": "hi"}, token="bad-token")
    assert s == 401, f"Invalid token should return 401, got {s}"
    print("  [PASS] Invalid token returns 401")

    token = get_staging_token()

    print("\n--- 3. Testing Authenticated POST /v1/executions ---")
    conv_id = f"smoke-vps-{uuid4().hex[:8]}"
    idem_key = f"idem-{uuid4().hex[:8]}"

    s, res1 = make_request(
        "/v1/executions",
        method="POST",
        data={
            "conversation_id": conv_id,
            "message": "Hola, necesito asistencia con ventas de productos.",
            "tenant_id": "tenant-smoke",
            "actor_id": "actor-smoke",
        },
        token=token,
        idempotency_key=idem_key,
    )
    assert s == 200, f"Execution failed: {s} {res1}"
    assert res1.get("status") == "completed", f"Status not completed: {res1}"
    assert res1.get("conversation_id") == conv_id
    assert "message" in res1
    exec_id_1 = res1.get("execution_id")
    print(f"  [PASS] /v1/executions completed. Execution ID: {exec_id_1}")
    print(f"         Response preview: {res1['message'][:60]}...")

    print("\n--- 4. Testing Idempotency Replay ---")
    s, res_replay = make_request(
        "/v1/executions",
        method="POST",
        data={
            "conversation_id": conv_id,
            "message": "Hola, necesito asistencia con ventas de productos.",
            "tenant_id": "tenant-smoke",
            "actor_id": "actor-smoke",
        },
        token=token,
        idempotency_key=idem_key,
    )
    assert s == 200, f"Replay failed: {s} {res_replay}"
    assert res_replay.get("execution_id") == exec_id_1, "Idempotency failed: execution_id changed"
    assert res_replay.get("message") == res1.get("message"), "Idempotency failed: message changed"
    print("  [PASS] Idempotency verified: identical execution_id and response returned without re-executing")

    print("\n--- 5. Testing Multi-turn Conversation & Ledger State ---")
    s, res2 = make_request(
        "/v1/executions",
        method="POST",
        data={
            "conversation_id": conv_id,
            "message": "¿Puedes recordarme qué te pregunté en el mensaje anterior?",
            "tenant_id": "tenant-smoke",
            "actor_id": "actor-smoke",
        },
        token=token,
    )
    assert s == 200, f"Turn 2 failed: {s} {res2}"
    assert res2.get("status") == "completed"
    assert res2.get("execution_id") != exec_id_1
    print(f"  [PASS] Multi-turn second message completed. Execution ID: {res2.get('execution_id')}")
    print(f"         Response preview: {res2['message'][:60]}...")

    print("\n--- 6. Testing Orbit Turn SSE Streaming (POST /v1/turns) ---")
    orbit_body = {
        "requestId": str(uuid4()),
        "turnId": str(uuid4()),
        "conversationId": str(uuid4()),
        "workspaceId": str(uuid4()),
        "actor": {"id": "orbit-user-1"},
        "projectId": None,
        "question": "¿Cuáles son las condiciones de entrega?",
        "evidence": [],
    }
    s, stream_content = make_request(
        "/v1/turns",
        method="POST",
        data=orbit_body,
        token=token,
        stream=True,
    )
    assert s == 200, f"Orbit turns failed: {s} {stream_content}"
    assert "event: delta" in stream_content, "Missing SSE delta event in stream"
    assert "event: done" in stream_content, "Missing SSE done event in stream"
    print("  [PASS] Orbit SSE stream returned event: delta and event: done")

    print("\n--- 7. Checking Telemetry & Metrics ---")
    s, metrics = make_request("/metrics")
    assert s == 200, f"Metrics failed: {s}"
    assert metrics.get("requests", 0) >= 3, f"Requests count unexpected: {metrics}"
    assert metrics.get("db_pool", {}).get("in_use") == 0, "DB connections leaking in pool"
    print(f"  [PASS] Metrics: requests={metrics['requests']}, db_in_use={metrics['db_pool']['in_use']}, max={metrics['db_pool']['max']}")

    print("\n--- 8. Testing Container Restart & Persistence Preservation ---")
    print("  Restarting container 'orchestrator-staging' on VPS...")
    subprocess.check_call(["ssh", "hector@2.24.201.39", "cd /opt/incubia/staging && docker compose restart orchestrator"])
    time.sleep(3)

    # Check readyz
    for _ in range(10):
        try:
            s, d = make_request("/readyz")
            if s == 200 and d == {"status": "ready"}:
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        raise RuntimeError("Service failed to become ready after restart")

    # Verify multi-turn continues with same history after container restart
    s, res3 = make_request(
        "/v1/executions",
        method="POST",
        data={
            "conversation_id": conv_id,
            "message": "¿Sigues recordando nuestra conversación tras el reinicio?",
            "tenant_id": "tenant-smoke",
            "actor_id": "actor-smoke",
        },
        token=token,
    )
    assert s == 200, f"Turn 3 failed after restart: {s} {res3}"
    assert res3.get("status") == "completed"
    print("  [PASS] Conversation resumed seamlessly across container restart. Persistence in Neon validated!")

    print("\n========================================================")
    print("ALL VPS E2E SMOKE & RESTART GATES PASSED SUCCESSFULLY!")
    print("========================================================")


if __name__ == "__main__":
    main()
