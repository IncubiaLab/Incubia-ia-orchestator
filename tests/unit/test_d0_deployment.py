import pytest

from incubia_orchestrator.bootstrap.d0 import (
    D0Deployment,
    D0Runtime,
    D0RuntimeResult,
    D0Settings,
    ExecutionUnavailable,
    InputRejected,
)
from incubia_orchestrator.foundation.contracts.execution import (
    CompletedExecution,
    ConversationTurn,
    ExecutionOutput,
)
from incubia_orchestrator.foundation.contracts.specialty import Specialty
from incubia_orchestrator.interfaces.http.main import validate_bind_host, validate_execution_payload
from incubia_orchestrator.modules.conversation.ports.ledger import (
    ClaimToken, ConversationCommit, InboxReservation,
)


class Ledger:
    def __init__(self):
        self.events = {}
        self.histories = {}
        self.outcomes = {}
        self.revisions = {}
        self.commits = []

    def ready(self):
        return True

    def recover_interrupted(self, *, deployment_id, tenant_id):
        return 0

    def reserve_inbox(self, deployment_id, tenant_id, account, event_id, payload, *, channel):
        key = (deployment_id, tenant_id, account, event_id)
        event = self.events.get(key)
        if event:
            assert event["payload"] == payload
            return InboxReservation(event["request_id"], event["execution_id"], event["state"], False)
        sequence = len(self.events) + 1
        event = {
            "request_id": f"request-{sequence}",
            "execution_id": f"execution-{sequence}",
            "payload": payload,
            "state": "RECEIVED",
        }
        self.events[key] = event
        return InboxReservation(event["request_id"], event["execution_id"], event["state"], True)

    def claim(self, execution_id, *, scope, owner_id, lease_seconds):
        for event in self.events.values():
            if event["execution_id"] == execution_id and event["state"] == "RECEIVED":
                event["state"] = "PROCESSING"
                return ClaimToken(scope.deployment_id, scope.tenant_id, "execution",
                                  execution_id, owner_id, 1)
        return None

    def acquire_claim(self, scope, *, resource_type, resource_key, owner_id, lease_seconds):
        return ClaimToken(scope.deployment_id, scope.tenant_id, resource_type,
                          resource_key, owner_id, 1)

    def release_claim(self, token):
        return True

    def return_to_received(self, execution_id, *, scope, claim_token):
        for event in self.events.values():
            if event["execution_id"] == execution_id:
                event["state"] = "RECEIVED"
                return True
        return False

    def conversation_history(self, scope, *, limit):
        return tuple(self.histories.get(scope, ())[-limit:])

    def conversation_revision(self, scope):
        return self.revisions.get(scope, 0)

    def commit_conversation(self, commit: ConversationCommit):
        assert len(commit.claim_tokens) == 2
        assert self.conversation_revision(commit.scope) == commit.expected_revision
        revision = commit.expected_revision + 1
        self.revisions[commit.scope] = revision
        self.histories.setdefault(commit.scope, []).append(commit.turn)
        self.outcomes[commit.execution_id] = commit.outcome
        self.commits.append(commit)
        for event in self.events.values():
            if event["execution_id"] == commit.execution_id:
                event["state"] = "COMPLETED"
        return revision

    def outcome(self, execution_id, *, scope):
        return self.outcomes.get(execution_id)


class Runtime:
    def execute(self, *, request_id, execution_id, scope, message, history):
        specialty = Specialty.VENTAS if "venta" in message else Specialty.MARKETING
        return D0RuntimeResult(
            CompletedExecution(
                request_id,
                execution_id,
                ExecutionOutput(f"{specialty.value}: {message}", specialty=specialty),
            ),
            {"tool": {"network": False}, "retrieval": {"network": False}},
        )


def deployment():
    return D0Deployment(
        D0Settings("postgresql://ignored", "d0", "tenant", "actor"), Ledger(), Runtime()
    )


def test_d0_chain_persists_conversation_but_issues_a_new_execution_per_turn():
    service = deployment()
    first = service.execute(message="necesito una venta", conversation_id="conversation-1", idempotency_key="key-1")
    second = service.execute(message="campana de marketing", conversation_id="conversation-1", idempotency_key="key-2")

    assert first["execution_id"] != second["execution_id"]
    assert first["conversation_id"] == second["conversation_id"] == "conversation-1"
    assert first["revision"] == 1
    assert second["revision"] == 2
    assert first["specialty"] == "ventas"
    assert second["specialty"] == "marketing"


def test_d0_replay_returns_the_durable_result_without_another_turn():
    service = deployment()
    first = service.execute(message="necesito una venta", conversation_id="conversation-1", idempotency_key="key-1")
    replay = service.execute(message="necesito una venta", conversation_id="conversation-1", idempotency_key="key-1")

    assert replay["execution_id"] == first["execution_id"]
    assert replay["replayed"] is True
    assert len(service._ledger.commits) == 1


def test_d0_does_not_reserve_or_commit_when_readiness_is_false():
    service = deployment()
    service._ledger.ready = lambda: False

    with pytest.raises(ExecutionUnavailable):
        service.execute(message="necesito una venta", conversation_id="conversation-1", idempotency_key="key-1")

    assert service._ledger.events == {}


def test_d0_runtime_uses_existing_policy_routing_and_fake_llm_without_network():
    settings = D0Settings("postgresql://ignored", "d0", "tenant", "actor")
    runtime = D0Runtime(settings)
    scope = settings.scope_for("conversation-1")

    sales = runtime.execute(
        request_id="request-1", execution_id="execution-1", scope=scope,
        message="necesito una venta", history=(),
    )
    marketing = runtime.execute(
        request_id="request-2", execution_id="execution-2", scope=scope,
        message="necesito una campana de marketing", history=(),
    )

    assert sales.completed.output.specialty is Specialty.VENTAS
    assert marketing.completed.output.specialty is Specialty.MARKETING
    assert sales.deterministic_adapters["tool"]["network"] is False
    assert sales.deterministic_adapters["retrieval"]["network"] is False


@pytest.mark.parametrize("payload", [
    {"message": "hola"},
    {"message": "hola", "conversation_id": "c", "tenant_id": "forged"},
    {"message": "hola", "conversation_id": "c", "actor_id": "forged"},
    {"message": "hola", "conversation_id": "c", "deployment_id": "forged"},
])
def test_d0_http_contract_rejects_identity_fields_and_incomplete_payloads(payload):
    with pytest.raises(InputRejected):
        validate_execution_payload(payload)


def test_d0_non_loopback_bind_requires_the_compose_container_marker(monkeypatch):
    validate_bind_host("127.0.0.1")
    with pytest.raises(ValueError):
        validate_bind_host("0.0.0.0")

    monkeypatch.setenv("INCUBIA_D0_CONTAINER_BIND", "1")
    validate_bind_host("0.0.0.0")
    with pytest.raises(ValueError):
        validate_bind_host("192.0.2.10")


def test_d0_audit_emits_correlated_events_before_commit_and_fails_closed():
    from incubia_orchestrator.modules.audit.adapters.memory import InMemoryAuditLog

    audit = InMemoryAuditLog()
    ledger = Ledger()
    service = D0Deployment(D0Settings("postgresql://ignored", "d0", "tenant", "actor"),
                           ledger, Runtime(), audit)
    result = service.execute(message="hola", conversation_id="c-audit", idempotency_key="k1")
    assert {e.execution_id for e in audit.events} == {result["execution_id"]}
    assert {e.event_type.value for e in audit.events} >= {"workflow.outcome", "retrieval.completed"}

    class Broken:
        def append(self, event):
            raise RuntimeError("audit down")

    ledger2 = Ledger()
    failing = D0Deployment(D0Settings("postgresql://ignored", "d0", "tenant", "actor"),
                           ledger2, Runtime(), Broken())
    with pytest.raises(RuntimeError):
        failing.execute(message="hola", conversation_id="c-audit", idempotency_key="k2")
    assert not ledger2.commits  # nothing delivered when audit cannot be written


class BatchedLedger(Ledger):
    """Ledger exposing the round-trip-saving batched operations."""

    def __init__(self):
        super().__init__()
        self.calls = []
        self.busy = None

    def claim_execution(self, execution_id, *, scope, owner_id, lease_seconds):
        self.calls.append("claim_execution")
        if self.busy:
            return None, None, self.busy
        event = self.claim(execution_id, scope=scope, owner_id=owner_id, lease_seconds=lease_seconds)
        conversation = self.acquire_claim(scope, resource_type="conversation", resource_key="c",
                                          owner_id=owner_id, lease_seconds=lease_seconds)
        return event, conversation, None

    def conversation_snapshot(self, scope, *, limit):
        self.calls.append("snapshot")
        return self.conversation_history(scope, limit=limit), self.conversation_revision(scope)

    def claim(self, *a, **kw):
        self.calls.append("claim")
        return super().claim(*a, **kw)

    def conversation_history(self, scope, *, limit):
        self.calls.append("history")
        return super().conversation_history(scope, limit=limit)

    def conversation_revision(self, scope):
        self.calls.append("revision")
        return super().conversation_revision(scope)


def test_d0_uses_batched_claims_and_snapshot_without_extra_round_trips():
    ledger = BatchedLedger()
    service = D0Deployment(D0Settings("postgresql://ignored", "d0", "tenant", "actor"), ledger, Runtime())
    first = service.execute(message="venta", conversation_id="c1", idempotency_key="k1")
    second = service.execute(message="venta", conversation_id="c1", idempotency_key="k2")
    assert (first["revision"], second["revision"]) == (1, 2)
    # revision is read once, inside the snapshot (history+revision), not separately.
    assert ledger.calls.count("snapshot") == 2
    assert ledger.calls.count("claim_execution") == 2


def test_d0_batched_busy_conversation_maps_to_in_progress():
    from incubia_orchestrator.bootstrap.d0 import ExecutionInProgress
    ledger = BatchedLedger()
    ledger.busy = "conversation"
    service = D0Deployment(D0Settings("postgresql://ignored", "d0", "tenant", "actor"), ledger, Runtime())
    with pytest.raises(ExecutionInProgress):
        service.execute(message="venta", conversation_id="c1", idempotency_key="k1")
    assert ledger.commits == []
