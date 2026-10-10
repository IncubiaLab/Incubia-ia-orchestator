"""Composition root for the deliberately local E3-D0 deployment baseline.

E3-D0 is intentionally narrow: one process, one configured synthetic scope,
PostgreSQL durability, and deterministic in-process adapters.  It is not a
production identity boundary or a substitute for the H1--H5 gates.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from incubia_orchestrator.foundation.contracts.execution import (
    CompletedExecution,
    ConversationTurn,
    ExecutionScope,
    FailedExecution,
    StartExecutionRequest,
    ExecutionInput,
    to_dict,
)
from incubia_orchestrator.modules.conversation.ports.ledger import (
    ClaimToken,
    ConversationCommit,
    RevisionConflict,
    conversation_claim_key,
)
from incubia_orchestrator.modules.governance.adapters.policy.in_process.engine import (
    Authority,
    InProcessPolicyEngine,
)
from incubia_orchestrator.modules.orchestration.adapters.llm.fake import FakeLLM
from incubia_orchestrator.modules.orchestration.adapters.runtime.langgraph.adapter import (
    LangGraphRuntimeAdapter,
)
from incubia_orchestrator.modules.orchestration.adapters.runtime.langgraph.graph import build_graph
from incubia_orchestrator.modules.orchestration.adapters.runtime.langgraph.nodes.generate_response import (
    make_node,
)
from incubia_orchestrator.modules.orchestration.adapters.runtime.langgraph.nodes.select_specialty import (
    select_specialty,
)
from incubia_orchestrator.modules.orchestration.domain.specialty import profiles_for


class InputRejected(ValueError):
    """The public D0 HTTP contract was not respected."""


class ExecutionInProgress(RuntimeError):
    """The idempotency key is currently owned by another request."""


class ExecutionUnavailable(RuntimeError):
    """The deterministic runtime did not return a completed outcome."""


class D0DeterministicToolAdapter:
    """No-op READ seam: E3-D0 must not reach a tool provider or the network."""

    def read(self, *, scope: ExecutionScope, message: str) -> dict:
        del scope, message
        return {"adapter": "d0-deterministic-tool", "network": False, "items": 0}


class D0DeterministicRetrievalAdapter:
    """No-op retrieval seam: E3-D0 carries no knowledge-provider dependency."""

    def retrieve(self, *, scope: ExecutionScope, message: str) -> dict:
        del scope, message
        return {"adapter": "d0-deterministic-retrieval", "network": False, "items": 0}


@dataclass(frozen=True)
class D0RuntimeResult:
    completed: CompletedExecution
    deterministic_adapters: dict


@dataclass(frozen=True)
class D0Settings:
    database_url: str
    deployment_id: str
    tenant_id: str
    actor_id: str
    account: str = "d0-http"
    history_limit: int = 20

    @classmethod
    def from_env(cls) -> "D0Settings":
        mode = os.getenv("INCUBIA_D0_MODE", "local")
        if mode != "local":
            raise ValueError("E3-D0 only supports INCUBIA_D0_MODE=local")
        values = {
            "database_url": os.getenv("DATABASE_URL", ""),
            "deployment_id": os.getenv("INCUBIA_D0_DEPLOYMENT_ID", ""),
            "tenant_id": os.getenv("INCUBIA_D0_TENANT_ID", ""),
            "actor_id": os.getenv("INCUBIA_D0_ACTOR_ID", ""),
            "account": os.getenv("INCUBIA_D0_ACCOUNT", "d0-http"),
        }
        missing = tuple(name for name, value in values.items() if not value)
        if missing:
            raise ValueError("Missing E3-D0 configuration: " + ", ".join(missing))
        try:
            history_limit = int(os.getenv("INCUBIA_D0_HISTORY_LIMIT", "20"))
        except ValueError as exc:
            raise ValueError("INCUBIA_D0_HISTORY_LIMIT must be an integer") from exc
        if not 1 <= history_limit <= 100:
            raise ValueError("INCUBIA_D0_HISTORY_LIMIT must be between 1 and 100")
        return cls(**values, history_limit=history_limit)

    def scope_for(self, conversation_id: str) -> ExecutionScope:
        return ExecutionScope(self.deployment_id, self.tenant_id, conversation_id, self.actor_id)


class D0Ledger(Protocol):
    def ready(self) -> bool: ...
    def recover_interrupted(self, *, deployment_id: str, tenant_id: str) -> int: ...
    def reserve_inbox(self, deployment_id: str, tenant_id: str, account: str,
                      event_id: str, payload: dict, *, channel: str): ...
    def claim(self, execution_id: str, *, scope: ExecutionScope,
              owner_id: str, lease_seconds: float) -> ClaimToken | None: ...
    def acquire_claim(self, scope: ExecutionScope, *, resource_type: str, resource_key: str,
                      owner_id: str, lease_seconds: float) -> ClaimToken | None: ...
    def return_to_received(self, execution_id: str, *, scope: ExecutionScope,
                           claim_token: ClaimToken) -> bool: ...
    def release_claim(self, token: ClaimToken) -> bool: ...
    def conversation_history(self, scope: ExecutionScope, *, limit: int) -> tuple[ConversationTurn, ...]: ...
    def conversation_revision(self, scope: ExecutionScope) -> int: ...
    def commit_conversation(self, commit: ConversationCommit) -> int: ...
    def outcome(self, execution_id: str, *, scope: ExecutionScope) -> dict | None: ...


class D0RuntimePort(Protocol):
    def execute(self, *, request_id: str, execution_id: str, scope: ExecutionScope,
                message: str, history: tuple[ConversationTurn, ...]) -> D0RuntimeResult: ...


class D0Runtime:
    """Existing routing/policy/runtime ports with local deterministic seams."""

    def __init__(self, settings: D0Settings,
                 tool: D0DeterministicToolAdapter | None = None,
                 retrieval: D0DeterministicRetrievalAdapter | None = None):
        policy = InProcessPolicyEngine(
            Authority(settings.deployment_id, settings.tenant_id, frozenset({settings.actor_id}))
        )
        profiles = profiles_for("e3-d0-deterministic")
        self._runtime = LangGraphRuntimeAdapter(
            build_graph(make_node(FakeLLM(), policy, 128, profiles), select_specialty)
        )
        self._tool = tool or D0DeterministicToolAdapter()
        self._retrieval = retrieval or D0DeterministicRetrievalAdapter()

    def execute(self, *, request_id: str, execution_id: str, scope: ExecutionScope,
                message: str, history: tuple[ConversationTurn, ...]) -> D0RuntimeResult:
        outcome = self._runtime.start(
            StartExecutionRequest(request_id, execution_id, scope, ExecutionInput(message, history=history))
        )
        if isinstance(outcome, FailedExecution):
            raise ExecutionUnavailable("Deterministic runtime unavailable")
        if not isinstance(outcome, CompletedExecution):  # Defensive against future resumable runtimes.
            raise ExecutionUnavailable("Deterministic runtime did not complete")
        # These seams deliberately return no evidence and make no I/O. They
        # are exercised in the same request path but do not claim the H3/H4
        # Tool/Knowledge contracts or their real providers.
        return D0RuntimeResult(
            outcome,
            {
                "tool": self._tool.read(scope=scope, message=message),
                "retrieval": self._retrieval.retrieve(scope=scope, message=message),
            },
        )


_CONVERSATION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


class D0Deployment:
    """HTTP-facing application service with an inbox-to-outbox durable commit."""

    def __init__(self, settings: D0Settings, ledger: D0Ledger, runtime: D0RuntimePort):
        self.settings = settings
        self._ledger = ledger
        self._runtime = runtime
        self._claim_lease_seconds = 120

    def ready(self) -> bool:
        return self._ledger.ready()

    def recover_interrupted(self) -> int:
        return self._ledger.recover_interrupted(
            deployment_id=self.settings.deployment_id,
            tenant_id=self.settings.tenant_id,
        )

    def _return_to_received_safely(
        self, execution_id: str, scope: ExecutionScope,
        event_claim: ClaimToken, conversation_claim: ClaimToken | None,
    ) -> None:
        """Release local-only work after a recoverable failure when possible.

        A successful durable commit has already changed the row to COMPLETED,
        making this conditional transition a no-op. If PostgreSQL is down,
        startup recovery will revisit unfinished local work after it returns.
        """
        try:
            self._ledger.return_to_received(execution_id, scope=scope, claim_token=event_claim)
        except Exception:
            pass
        if conversation_claim is not None:
            try:
                self._ledger.release_claim(conversation_claim)
            except Exception:
                pass

    @staticmethod
    def _validate(message: object, conversation_id: object, idempotency_key: object) -> tuple[str, str, str]:
        if not isinstance(message, str) or not message.strip() or len(message) > 4_000:
            raise InputRejected("message must be non-empty text up to 4000 characters")
        if not isinstance(conversation_id, str) or not _CONVERSATION_ID.fullmatch(conversation_id):
            raise InputRejected("conversation_id has an invalid format")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip() or len(idempotency_key) > 128:
            raise InputRejected("Idempotency-Key must be non-empty and at most 128 characters")
        return message, conversation_id, idempotency_key

    @staticmethod
    def _replayed(response: dict) -> dict:
        replay = dict(response)
        replay["replayed"] = True
        return replay

    def execute(self, *, message: object, conversation_id: object, idempotency_key: object) -> dict:
        message, conversation_id, idempotency_key = self._validate(
            message, conversation_id, idempotency_key
        )
        if not self.ready():
            raise ExecutionUnavailable("E3-D0 is not ready to accept executions")
        scope = self.settings.scope_for(conversation_id)
        payload = {"conversation_id": conversation_id, "message": message}
        reservation = self._ledger.reserve_inbox(
            scope.deployment_id,
            scope.tenant_id,
            self.settings.account,
            idempotency_key,
            payload,
            channel="http",
        )
        if not reservation.is_new and reservation.state == "COMPLETED":
            stored = self._ledger.outcome(reservation.execution_id, scope=scope)
            if stored is None or not isinstance(stored.get("http_response"), dict):
                raise ExecutionUnavailable("Completed request has no recoverable response")
            return self._replayed(stored["http_response"])
        if reservation.state not in {"RECEIVED", "PROCESSING"}:
            raise ExecutionInProgress("The idempotency key is being processed")
        owner_id = str(uuid4())
        event_claim = self._ledger.claim(
            reservation.execution_id, scope=scope, owner_id=owner_id,
            lease_seconds=self._claim_lease_seconds,
        )
        if event_claim is None:
            raise ExecutionInProgress("The idempotency key is being processed")
        conversation_claim = self._ledger.acquire_claim(
            scope, resource_type="conversation", resource_key=conversation_claim_key(scope),
            owner_id=owner_id, lease_seconds=self._claim_lease_seconds,
        )
        if conversation_claim is None:
            self._return_to_received_safely(
                reservation.execution_id, scope, event_claim, None
            )
            raise ExecutionInProgress("The conversation is being processed")

        try:
            history = self._ledger.conversation_history(scope, limit=self.settings.history_limit)
            runtime_result = self._runtime.execute(
                request_id=reservation.request_id,
                execution_id=reservation.execution_id,
                scope=scope,
                message=message,
                history=history,
            )
        except Exception:
            self._return_to_received_safely(
                reservation.execution_id, scope, event_claim, conversation_claim
            )
            raise

        completed = runtime_result.completed
        specialty = completed.output.specialty.value if completed.output.specialty else "general"
        try:
            for _ in range(3):
                revision = self._ledger.conversation_revision(scope)
                response = {
                    "status": "completed",
                    "request_id": reservation.request_id,
                    "execution_id": reservation.execution_id,
                    "conversation_id": conversation_id,
                    "revision": revision + 1,
                    "specialty": specialty,
                    "message": completed.output.text,
                    "replayed": False,
                }
                try:
                    committed_revision = self._ledger.commit_conversation(
                        ConversationCommit(
                            execution_id=reservation.execution_id,
                            scope=scope,
                            expected_revision=revision,
                            response_id=f"execution:{reservation.execution_id}",
                            destination_ref=f"http:{conversation_id}",
                            public_payload=response,
                            outcome={
                                "http_response": response,
                                "runtime": to_dict(completed),
                                "deterministic_adapters": runtime_result.deterministic_adapters,
                            },
                            turn=ConversationTurn(message, completed.output.text),
                            claim_tokens=(event_claim, conversation_claim),
                        )
                    )
                    if committed_revision != response["revision"]:
                        raise ExecutionUnavailable("Unexpected durable revision")
                    return response
                except RevisionConflict:
                    continue
        except Exception:
            self._return_to_received_safely(
                reservation.execution_id, scope, event_claim, conversation_claim
            )
            raise
        self._return_to_received_safely(
            reservation.execution_id, scope, event_claim, conversation_claim
        )
        raise ExecutionInProgress("Conversation changed while this request was committing")
