from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
import json
import urllib.error
import urllib.request
from uuid import uuid4

import pytest

from incubia_orchestrator.bootstrap.vps import (
    ExecutionInProgress,
    InputRejected,
    LangGraphOrchestrationRuntime,
    VPSService,
    VPSSettings,
)
from incubia_orchestrator.foundation.contracts.execution import (
    CompletedExecution,
    ConversationTurn,
    ExecutionOutput,
    ExecutionScope,
)
from incubia_orchestrator.foundation.contracts.specialty import Specialty
from incubia_orchestrator.foundation.limits import load_runtime_limits
from incubia_orchestrator.interfaces.http.service import (
    VPSHTTPServer,
    validate_executions_payload,
    validate_orbit_turn,
)
from incubia_orchestrator.modules.conversation.ports.ledger import (
    ClaimToken,
    ConversationCommit,
    InboxReservation,
)


class FakeLedger:
    def __init__(self):
        self.events = {}
        self.histories = {}
        self.outcomes = {}
        self.revisions = {}
        self.commits = []
        self.is_ready = True

    def ready(self):
        return self.is_ready

    def recover_interrupted(self, *, deployment_id, tenant_id):
        return 0

    def reserve_inbox(self, deployment_id, tenant_id, account, event_id, payload, *, channel):
        key = (deployment_id, tenant_id, account, event_id)
        event = self.events.get(key)
        if event:
            return InboxReservation(event["request_id"], event["execution_id"], event["state"], False)
        seq = len(self.events) + 1
        event = {
            "request_id": f"req-{seq}",
            "execution_id": f"exec-{seq}",
            "payload": payload,
            "state": "RECEIVED",
        }
        self.events[key] = event
        return InboxReservation(event["request_id"], event["execution_id"], event["state"], True)

    def claim_execution(self, execution_id, *, scope, owner_id, lease_seconds):
        for event in self.events.values():
            if event["execution_id"] == execution_id and event["state"] == "RECEIVED":
                event["state"] = "PROCESSING"
                claim_ev = ClaimToken(scope.deployment_id, scope.tenant_id, "execution", execution_id, owner_id, 1)
                claim_conv = ClaimToken(scope.deployment_id, scope.tenant_id, "conversation", scope.conversation_id, owner_id, 1)
                return claim_ev, claim_conv, None
        return None, None, "event"

    def release_claim(self, token):
        return True

    def return_to_received(self, execution_id, *, scope, claim_token):
        for event in self.events.values():
            if event["execution_id"] == execution_id:
                event["state"] = "RECEIVED"
                return True
        return False

    def conversation_snapshot(self, scope, *, limit):
        return tuple(self.histories.get(scope, ())[-limit:]), self.revisions.get(scope, 0)

    def commit_conversation(self, commit: ConversationCommit):
        rev = commit.expected_revision + 1
        self.revisions[commit.scope] = rev
        self.histories.setdefault(commit.scope, []).append(commit.turn)
        self.outcomes[commit.execution_id] = commit.outcome
        self.commits.append(commit)
        for event in self.events.values():
            if event["execution_id"] == commit.execution_id:
                event["state"] = "COMPLETED"
        return rev

    def outcome(self, execution_id, *, scope):
        return self.outcomes.get(execution_id)


class FakeRuntime:
    def execute(self, *, request_id, execution_id, scope, message, history):
        specialty = Specialty.VENTAS if "venta" in message.lower() else Specialty.GENERAL
        return CompletedExecution(
            request_id,
            execution_id,
            ExecutionOutput(f"Respuesta a: {message}", specialty=specialty),
        )


@pytest.fixture
def vps_service():
    settings = VPSSettings(
        database_url="postgresql://fake",
        token="0123456789abcdef0123456789abcdef",
        deployment_id="test-deployment",
        fake_mode=True,
        model="gpt-4o-mini",
    )
    limits = load_runtime_limits()
    ledger = FakeLedger()
    runtime = FakeRuntime()
    return VPSService(settings, ledger, runtime, limits)


def test_vps_service_execute_turn_and_replay(vps_service):
    scope = ExecutionScope("test-deployment", "tenant-1", "conv-1", "user-1")
    first = vps_service.execute_turn(
        scope=scope,
        message="Quiero una venta",
        idempotency_key="key-1",
    )
    assert first["status"] == "completed"
    assert first["conversation_id"] == "conv-1"
    assert first["specialty"] == "ventas"
    assert first["revision"] == 1
    assert first["replayed"] is False

    # Second execution with same idempotency key should replay outcome
    replayed = vps_service.execute_turn(
        scope=scope,
        message="Quiero una venta",
        idempotency_key="key-1",
    )
    assert replayed["execution_id"] == first["execution_id"]
    assert replayed["replayed"] is True
    assert len(vps_service._ledger.commits) == 1


def test_vps_service_rejects_empty_inputs(vps_service):
    scope = ExecutionScope("test-deployment", "tenant-1", "conv-1", "user-1")
    with pytest.raises(InputRejected):
        vps_service.execute_turn(scope=scope, message="", idempotency_key="key-1")
    with pytest.raises(InputRejected):
        vps_service.execute_turn(scope=scope, message="hola", idempotency_key="")


import http.client
import socket

_REAL_CONNECT = socket.socket.connect
_REAL_CREATE_CONNECTION = socket.create_connection

@pytest.fixture
def loopback(no_network, monkeypatch):
    def create_connection(address, *args, **kwargs):
        assert address[0] == "127.0.0.1", "Network access is disabled in local tests"
        return _REAL_CREATE_CONNECTION(address, *args, **kwargs)

    def connect(sock, address):
        assert isinstance(address, tuple) and address[0] == "127.0.0.1"
        return _REAL_CONNECT(sock, address)

    monkeypatch.setattr(socket, "create_connection", create_connection)
    monkeypatch.setattr(socket.socket, "connect", connect)


def test_vps_http_server_endpoints(vps_service, loopback):
    server = VPSHTTPServer(("127.0.0.1", 0), vps_service)
    port = server.server_port

    import threading
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base = f"http://127.0.0.1:{port}"

        # /healthz
        with urllib.request.urlopen(f"{base}/healthz") as res:
            assert res.status == 200
            data = json.loads(res.read().decode())
            assert data["status"] == "ok"

        # /readyz
        with urllib.request.urlopen(f"{base}/readyz") as res:
            assert res.status == 200
            data = json.loads(res.read().decode())
            assert data["status"] == "ready"

        # /v1/executions unauthorized without token
        body_exec = json.dumps({"message": "hola", "conversation_id": "c1"}).encode()
        req_unauth = urllib.request.Request(f"{base}/v1/executions", data=body_exec, headers={"Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(req_unauth)
        assert err.value.code == 401

        # /v1/executions authorized
        headers_auth = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {vps_service.settings.token}",
            "Idempotency-Key": "idemp-http-1",
        }
        req_auth = urllib.request.Request(f"{base}/v1/executions", data=body_exec, headers=headers_auth)
        with urllib.request.urlopen(req_auth) as res:
            assert res.status == 200
            data = json.loads(res.read().decode())
            assert data["status"] == "completed"
            assert data["conversation_id"] == "c1"

        # /v1/turns (Orbit turn with SSE format)
        orbit_body = json.dumps({
            "requestId": str(uuid4()),
            "turnId": str(uuid4()),
            "conversationId": str(uuid4()),
            "workspaceId": str(uuid4()),
            "actor": {"id": "orbit-user"},
            "projectId": None,
            "question": "Quiero una venta",
            "evidence": [],
        }).encode()
        req_orbit = urllib.request.Request(f"{base}/v1/turns", data=orbit_body, headers=headers_auth)
        with urllib.request.urlopen(req_orbit) as res:
            assert res.status == 200
            payload = res.read().decode()
            assert "event: delta" in payload
            assert "event: done" in payload

    finally:
        server.shutdown()
        server.server_close()
