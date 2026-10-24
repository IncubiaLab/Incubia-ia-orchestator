"""Minimal loopback-only HTTP boundary for the E3-D0 local baseline."""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import threading
from time import monotonic
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from typing import Any

from incubia_orchestrator.bootstrap.d0 import (
    D0Deployment,
    D0Runtime,
    D0Settings,
    ExecutionInProgress,
    ExecutionUnavailable,
    InputRejected,
)
from incubia_orchestrator.modules.conversation.adapters.persistence.postgres import PostgresLedger
from incubia_orchestrator.modules.conversation.ports.ledger import IdempotencyConflict
from incubia_orchestrator.foundation.limits import AdmissionLimiter, Limits, load_runtime_limits
from incubia_orchestrator.foundation.telemetry import HttpMetrics
from incubia_orchestrator.interfaces.http.draining import DrainingHTTPServer

LOG = logging.getLogger(__name__)
MAX_BODY_BYTES = 8_192
_ALLOWED_EXECUTION_FIELDS = frozenset({"message", "conversation_id"})


def validate_execution_payload(body: object) -> dict:
    """Keep identity fields out of the public local ingress contract."""
    if not isinstance(body, dict) or set(body) != _ALLOWED_EXECUTION_FIELDS:
        raise InputRejected("Only message and conversation_id are accepted")
    return body


class E3D0HttpServer(DrainingHTTPServer):
    def __init__(self, address: tuple[str, int], service: D0Deployment,
                 limits: Limits | None = None):
        super().__init__(address, E3D0RequestHandler)
        self.service = service
        self.limits = limits
        self.admission = (AdmissionLimiter(limits.tenant.admission_rate_per_minute)
                          if limits is not None else None)
        self.metrics = HttpMetrics(service.settings.deployment_id, service.settings.tenant_id)


class E3D0RequestHandler(BaseHTTPRequestHandler):
    server: E3D0HttpServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        # Do not log request bodies, headers, queries, credentials, or errors.
        route = self.path.split("?", 1)[0]
        safe_route = route if route in {"/healthz", "/readyz", "/metrics", "/v1/executions"} else "other"
        LOG.info("http method=%s route=%s status=%s", self.command, safe_route,
                 args[1] if len(args) > 1 else "-")

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(10)

    def _send_json(self, status: HTTPStatus, body: dict, headers: dict[str, str] | None = None) -> None:
        try:
            encoded = json.dumps(body, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(encoded)
            started = getattr(self, "_metric_started", None)
            if started is not None and status == HTTPStatus.OK:
                self.server.metrics.stage_latency("reception_to_delivery", (monotonic() - started) * 1000)
        finally:
            started = getattr(self, "_metric_started", None)
            if started is not None:
                self.server.metrics.finished(int(status), (monotonic() - started) * 1000)
                self._metric_started = None

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError as exc:
            raise InputRejected("Content-Length is required") from exc
        if length < 1 or length > MAX_BODY_BYTES:
            raise InputRejected("Request body has an invalid size")
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise InputRejected("Content-Type must be application/json")
        try:
            body = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InputRejected("Request body must be valid JSON") from exc
        return validate_execution_payload(body)

    def do_GET(self) -> None:
        if self.path == "/metrics":
            self._send_json(HTTPStatus.OK, self.server.metrics.snapshot())
            return
        if self.path == "/healthz":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
            return
        if self.path == "/readyz":
            try:
                ready = self.server.service.ready()
            except Exception:
                ready = False
            status = HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE
            self._send_json(status, {"status": "ready" if status == HTTPStatus.OK else "not_ready"})
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:
        if self.path != "/v1/executions":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        self._metric_started = monotonic()
        self.server.metrics.started()
        admission = self.server.admission
        if admission is not None and not admission.try_acquire(self.server.service.settings.tenant_id):
            self.server.metrics.rejection("limit", "TENANT_RATE")
            self.close_connection = True  # request body is left unread
            self._send_json(HTTPStatus.TOO_MANY_REQUESTS, {"error": "rate_limited"},
                            {"Retry-After": str(admission.retry_after_seconds),
                             "Connection": "close"})
            return
        try:
            body = self._body()
            result = self.server.service.execute(
                message=body["message"],
                conversation_id=body["conversation_id"],
                idempotency_key=self.headers.get("Idempotency-Key"),
            )
        except InputRejected as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_request", "message": str(exc)})
        except IdempotencyConflict:
            self._send_json(HTTPStatus.CONFLICT, {"error": "idempotency_conflict"})
        except ExecutionInProgress:
            self._send_json(HTTPStatus.CONFLICT, {"error": "execution_in_progress"})
        except (ExecutionUnavailable, RuntimeError):
            LOG.warning("execution_unavailable")
            self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "execution_unavailable"})
        except Exception as exc:  # Keep persistence internals out of HTTP and stderr.
            LOG.error("execution_failed type=%s", type(exc).__name__)
            self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "execution_unavailable"})
        else:
            self.server.metrics.stage_latency("reception_to_outcome", (monotonic() - self._metric_started) * 1000)
            self._send_json(HTTPStatus.OK, result)

    def do_PUT(self) -> None:
        self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method_not_allowed"})

    do_DELETE = do_PUT
    do_PATCH = do_PUT


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the E3-D0 local HTTP baseline")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8080, type=int)
    return parser.parse_args()


def validate_bind_host(host: str) -> None:
    """Prevent accidental exposure of the unauthenticated D0 endpoint.

    Compose uses 0.0.0.0 only inside its isolated container network. The host
    mapping in compose.yaml is still explicitly bound to 127.0.0.1.
    """
    if host in {"127.0.0.1", "::1"}:
        return
    if host == "0.0.0.0" and os.getenv("INCUBIA_D0_CONTAINER_BIND") == "1":
        return
    raise ValueError("E3-D0 HTTP must bind loopback outside approved Compose")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        args = parse_args()
        validate_bind_host(args.host)
        limits = load_runtime_limits()  # fail closed: invalid/unratified -> exit 1
        settings = D0Settings.from_env()
        service = D0Deployment(settings, PostgresLedger(settings.database_url), D0Runtime(settings))
    except Exception as exc:
        LOG.error("e3_d0_startup_failed type=%s", type(exc).__name__)
        return 1
    try:
        if service.ready():
            recovered = service.recover_interrupted()
            if recovered:
                LOG.warning("e3_d0_recovered_interrupted=%s", recovered)
    except Exception as exc:
        LOG.warning("e3_d0_recovery_deferred type=%s", type(exc).__name__)
    try:
        server = E3D0HttpServer((args.host, args.port), service, limits)
    except Exception as exc:
        LOG.error("e3_d0_server_start_failed type=%s", type(exc).__name__)
        return 1

    def shutdown(signum: int, _frame: object) -> None:
        LOG.info("shutdown_signal=%s", signum)
        # shutdown() waits for serve_forever(), so it must not run in the
        # signal-handling (serve_forever) thread.
        threading.Thread(target=server.shutdown, name="e3-d0-shutdown", daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    LOG.info("e3_d0_http_started host=%s port=%s", args.host, args.port)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        LOG.info("e3_d0_http_stopped")
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
