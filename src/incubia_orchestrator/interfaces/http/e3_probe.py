"""Loopback, authenticated E3 probe for synthetic real-provider tests only."""

import argparse
import hmac
import json
import logging
import os
import re
import signal
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import uuid4

from incubia_orchestrator.bootstrap.e3_grounded import compose_grounded_workflow
from incubia_orchestrator.foundation.contracts.execution import ExecutionScope
from incubia_orchestrator.interfaces.http.draining import DrainingHTTPServer
from incubia_orchestrator.modules.audit.adapters.sqlite import SqliteAuditLog
from incubia_orchestrator.modules.audit.adapters.postgres import PostgresAuditLog
from incubia_orchestrator.modules.governance.adapters.policy.in_process.engine import Authority, InProcessPolicyEngine
from incubia_orchestrator.modules.knowledge.adapters.openai_embedding import EmbeddingBudget, OpenAIEmbedding
from incubia_orchestrator.modules.knowledge.adapters.postgres import PostgresKnowledge
from incubia_orchestrator.modules.orchestration.adapters.tools.openfoodfacts import OpenFoodFactsAdapter
from incubia_orchestrator.modules.orchestration.application.grounded_workflow import ReadRequest
from incubia_orchestrator.modules.orchestration.domain.tools import ToolDescriptor

LOG = logging.getLogger(__name__)
_BARCODE = re.compile(r"[0-9]{7,18}\Z")
_FIELDS = frozenset({"query", "product_ref"})


def _required(name: str) -> str:
    value = os.getenv(name, "")
    if not value:
        raise ValueError(f"{name} is required")
    return value


class ProbeService:
    def __init__(self, *, token: str, scope: ExecutionScope, workflow, ready):
        if len(token) < 32:
            raise ValueError("Probe token must have at least 32 characters")
        self._token, self.scope, self._workflow, self._ready = token, scope, workflow, ready

    def authorized(self, header: str | None) -> bool:
        return bool(header and header.startswith("Bearer ") and
                    hmac.compare_digest(header[7:], self._token))

    def ready(self) -> bool:
        return self._ready()

    def execute(self, body: object) -> dict:
        if not isinstance(body, dict) or not set(body).issubset(_FIELDS) or "query" not in body:
            raise ValueError("Only query and product_ref are accepted")
        query, product_ref = body["query"], body.get("product_ref")
        if not isinstance(query, str) or not query.strip() or len(query) > 256:
            raise ValueError("query must be non-empty text up to 256 characters")
        if product_ref is not None and (not isinstance(product_ref, str) or
                                        not _BARCODE.fullmatch(product_ref)):
            raise ValueError("product_ref must be a numeric product code")
        scope = ExecutionScope(self.scope.deployment_id, self.scope.tenant_id,
                               str(uuid4()), self.scope.actor_id)
        execution_id = str(uuid4())
        answer = self._workflow(query, product_ref, scope, execution_id)
        return {"execution_id": execution_id, "conversation_id": scope.conversation_id,
                "status": "abstained" if answer.abstained else "completed",
                "message": answer.text, "public_references": list(answer.public_references),
                "evidence_count": len(answer.evidence)}


class ProbeHttpServer(DrainingHTTPServer):
    def __init__(self, address, service: ProbeService):
        super().__init__(address, ProbeHandler)
        self.service = service


class ProbeHandler(BaseHTTPRequestHandler):
    server: ProbeHttpServer
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        LOG.info("probe method=%s status=%s", self.command, args[1] if len(args) > 1 else "-")

    def _reply(self, status: HTTPStatus, body: dict) -> None:
        payload = json.dumps(body, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == "/healthz":
            self._reply(HTTPStatus.OK, {"status": "ok"})
            return
        if not self.server.service.authorized(self.headers.get("Authorization")):
            self._reply(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        if self.path == "/readyz":
            ready = self.server.service.ready()
            self._reply(HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE,
                        {"status": "ready" if ready else "not_ready"})
            return
        self._reply(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self):
        if not self.server.service.authorized(self.headers.get("Authorization")):
            self._reply(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        if self.path != "/v1/probe":
            self._reply(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 1 <= length <= 2048 or self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
                raise ValueError("Invalid request envelope")
            body = json.loads(self.rfile.read(length))
            result = self.server.service.execute(body)
        except (ValueError, json.JSONDecodeError):
            self._reply(HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
        except Exception as exc:
            LOG.error("probe_failed type=%s", type(exc).__name__)
            self._reply(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "probe_unavailable"})
        else:
            self._reply(HTTPStatus.OK, result)


def compose_from_env() -> tuple[ProbeService, tuple[object, ...]]:
    if os.getenv("INCUBIA_E3_PROBE_REAL") != "1":
        raise ValueError("Explicit real-probe opt-in is required")
    deployment = _required("INCUBIA_E3_PROBE_DEPLOYMENT_ID")
    tenant = _required("INCUBIA_E3_PROBE_TENANT_ID")
    actor = _required("INCUBIA_E3_PROBE_ACTOR_ID")
    token = _required("INCUBIA_E3_PROBE_TOKEN")
    dsn = _required("INCUBIA_E3_PROBE_KNOWLEDGE_DSN")
    api_key = _required("OPENAI_API_KEY")
    parsed = urlsplit(dsn)
    if (_required("INCUBIA_E3_PROBE_BRANCH") != "e3-h1-synthetic"
            or parsed.scheme not in {"postgres", "postgresql"}
            or not (parsed.hostname or "").endswith(".neon.tech")
            or parsed.username in {None, "neondb_owner", "incubia_migrator"}
            or parse_qs(parsed.query).get("sslmode") != ["require"]
            or "REPLACE" in token or "REPLACE" in dsn or "REPLACE" in api_key):
        raise ValueError("A synthetic Neon runtime DSN and configured credentials are required")
    budget = EmbeddingBudget(Path(_required("INCUBIA_E3_PROBE_BUDGET_FILE")),
                             max_calls=int(_required("INCUBIA_E3_PROBE_MAX_CALLS")),
                             max_input_tokens=int(_required("INCUBIA_E3_PROBE_MAX_INPUT_TOKENS")),
                             usd_cap=float(_required("INCUBIA_E3_PROBE_USD_CAP")))
    embedding = OpenAIEmbedding(api_key, budget)
    knowledge = PostgresKnowledge(lambda requested: dsn if requested == deployment else "", embedding)
    # Durable Postgres audit (G7) when a runtime audit DSN is given; sqlite file otherwise.
    audit_dsn = os.getenv("INCUBIA_E3_PROBE_AUDIT_DSN", "")
    # G7: el sink durable sólo usa el rol runtime (INSERT/SELECT); nunca owner/migrator.
    if audit_dsn and unquote(urlsplit(audit_dsn).username or "") != "incubia_runtime":
        raise ValueError("INCUBIA_E3_PROBE_AUDIT_DSN must use the incubia_runtime role")
    audit = (PostgresAuditLog(audit_dsn) if audit_dsn
             else SqliteAuditLog(Path(_required("INCUBIA_E3_PROBE_AUDIT_FILE"))))
    adapter = OpenFoodFactsAdapter()
    descriptor = ToolDescriptor("business.catalog.lookup", capabilities=frozenset({"business.catalog.lookup"}),
                                deployment_ids=frozenset({deployment}), tenant_ids=frozenset({tenant}),
                                adapter_key="openfoodfacts", input_schema={"type": "object",
                                "required": ["product_ref"], "additionalProperties": False,
                                "properties": {"product_ref": {"type": "string", "maxLength": 18}}})
    policy = InProcessPolicyEngine(Authority(deployment, tenant, frozenset({actor}),
                                             enabled_actions=frozenset({"business.catalog.lookup"})))

    def execute(query, product_ref, scope, execution_id):
        workflow = compose_grounded_workflow(
            retrieval=knowledge, descriptors=(descriptor,), adapters={"openfoodfacts": adapter},
            policy=policy, audit=audit,
            read_request=lambda _query, _capability, _scope: (
                ReadRequest({"product_ref": product_ref}, f"tenant:{tenant}:catalog")
                if product_ref is not None else None),
        )
        return workflow.answer(scope, query, "business.catalog.lookup", execution_id=execution_id)

    def ready():
        import psycopg
        try:
            with psycopg.connect(dsn, connect_timeout=3) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT to_regclass('knowledge_chunks')")
                    return cursor.fetchone()[0] is not None
        except Exception:
            return False

    return ProbeService(token=token, scope=ExecutionScope(deployment, tenant, "", actor),
                        workflow=execute, ready=ready), (embedding, adapter)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18081)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "::1"}:
        parser.error("The real probe must bind loopback")
    logging.basicConfig(level=logging.INFO)
    try:
        service, resources = compose_from_env()
        server = ProbeHttpServer((args.host, args.port), service)
    except Exception as exc:
        LOG.error("probe_start_failed type=%s", type(exc).__name__)
        return 1
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown, daemon=True).start())
    try:
        server.serve_forever()
    finally:
        server.server_close()
        for resource in resources:
            resource.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
