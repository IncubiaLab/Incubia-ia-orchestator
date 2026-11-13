"""Unified production composition root for the complete VPS orchestrator deployment.

Integrates:
- PostgresLedger (conversation turns, claims, fencing, inbox-to-outbox)
- PostgresAuditLog (G7 durable audit under RLS, fail-closed)
- Bounded connection pooling (PooledConnections)
- LangGraphRuntimeAdapter with specialty routing and policy enforcement
- OpenAI LLM or FakeLLM
- Strict, fail-closed limits and admission control
"""
from __future__ import annotations

import os
from pathlib import Path
import re
from dataclasses import dataclass
from time import monotonic
from typing import Any, Callable, Protocol
from uuid import uuid4

from incubia_orchestrator.foundation.contracts.execution import (
    CompletedExecution,
    ConversationTurn,
    ExecutionInput,
    ExecutionOutput,
    ExecutionScope,
    StartExecutionRequest,
    to_dict,
)
from incubia_orchestrator.foundation.contracts.specialty import Specialty
from incubia_orchestrator.foundation.limits import Limits, load_runtime_limits
from incubia_orchestrator.foundation.pg_pool import PooledConnections
from incubia_orchestrator.foundation.telemetry import HttpMetrics
from incubia_orchestrator.modules.audit.domain.audit import AuditEvent, AuditEventType
from incubia_orchestrator.modules.audit.ports.sink import AuditSinkPort
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
from incubia_orchestrator.modules.governance.domain.guardrails import (
    sanitize_capa1_output,
)
from incubia_orchestrator.modules.identity_tenant.domain.principal import Role
from incubia_orchestrator.modules.knowledge.domain import (
    DocumentSyncRequest,
    DocumentSyncResult,
    KnowledgeNotConfigured,
    WorkspaceKnowledgeHit,
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
    """The request payload or arguments violated validation invariants."""


class ExecutionInProgress(RuntimeError):
    """The idempotency key or conversation is currently leased by another active worker."""


class ExecutionUnavailable(RuntimeError):
    """The runtime or persistence layer is unavailable to complete the execution."""


_CONVERSATION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


@dataclass(frozen=True)
class VPSSettings:
    database_url: str
    token: str
    deployment_id: str
    fake_mode: bool
    model: str
    history_limit: int = 20
    claim_lease_seconds: int = 120
    knowledge_runtime_database_url: str = ""
    knowledge_ingest_database_url: str = ""
    knowledge_deployment_id: str = ""
    knowledge_budget_file: str = ""
    allow_insecure_download_urls: bool = False

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "VPSSettings":
        e = os.environ if env is None else env
        token = e.get("INCUBIA_ORCHESTRATOR_TOKEN") or e.get("INCUBIA_ORBIT_GATEWAY_TOKEN") or ""
        if len(token) < 32:
            raise ValueError("INCUBIA_ORCHESTRATOR_TOKEN must be at least 32 characters")
        db_url = e.get("DATABASE_URL", "")
        if not db_url:
            raise ValueError("DATABASE_URL is required")
        deployment_id = e.get("INCUBIA_DEPLOYMENT_ID") or e.get("INCUBIA_ORBIT_GATEWAY_DEPLOYMENT_ID") or "incubia-vps"
        fake_mode = e.get("INCUBIA_FAKE_MODE", "0") == "1" or e.get("INCUBIA_ORBIT_GATEWAY_FAKE", "0") == "1"
        model = e.get("INCUBIA_MODEL", "gpt-4o-mini")
        if not fake_mode and not e.get("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY is required when not in fake mode")
        kb_runtime = e.get("INCUBIA_KNOWLEDGE_RUNTIME_DATABASE_URL", "").strip()
        kb_ingest = e.get("INCUBIA_KNOWLEDGE_INGEST_DATABASE_URL", "").strip()
        if bool(kb_runtime) != bool(kb_ingest):
            raise ValueError(
                "Both INCUBIA_KNOWLEDGE_RUNTIME_DATABASE_URL and "
                "INCUBIA_KNOWLEDGE_INGEST_DATABASE_URL must be configured together"
            )
        kb_deployment = e.get("INCUBIA_KNOWLEDGE_DEPLOYMENT_ID", "").strip() or deployment_id
        kb_budget_file = e.get("INCUBIA_KNOWLEDGE_EMBEDDING_BUDGET_FILE", "").strip()
        allow_insecure = e.get("INCUBIA_ALLOW_INSECURE_DOWNLOAD_URLS", "0") == "1"
        return cls(
            database_url=db_url,
            token=token,
            deployment_id=deployment_id,
            fake_mode=fake_mode,
            model=model,
            history_limit=int(e.get("INCUBIA_HISTORY_LIMIT", "20")),
            claim_lease_seconds=int(e.get("INCUBIA_CLAIM_LEASE_SECONDS", "120")),
            knowledge_runtime_database_url=kb_runtime,
            knowledge_ingest_database_url=kb_ingest,
            knowledge_deployment_id=kb_deployment,
            knowledge_budget_file=kb_budget_file,
            allow_insecure_download_urls=allow_insecure,
        )


class OrchestrationRuntimePort(Protocol):
    def execute(self, *, request_id: str, execution_id: str, scope: ExecutionScope,
                message: str, history: tuple[ConversationTurn, ...],
                actor_role: Role = Role.ACTOR) -> CompletedExecution:
        ...


class LangGraphOrchestrationRuntime:
    """LangGraph execution engine configured with policy engine and specialist profiles."""

    def __init__(self, llm: Any, model: str, limits: Limits, metrics: HttpMetrics | None = None):
        self._llm = llm
        self._profiles = profiles_for(model)
        self._limits = limits
        self._metrics = metrics
        self._max_output_tokens = max(limits.eval_e3.max_output_tokens, 2000)

    def execute(self, *, request_id: str, execution_id: str, scope: ExecutionScope,
                message: str, history: tuple[ConversationTurn, ...],
                actor_role: Role = Role.ACTOR) -> CompletedExecution:
        policy = InProcessPolicyEngine(
            Authority(
                scope.deployment_id,
                scope.tenant_id,
                frozenset({scope.actor_id}),
                actor_roles={scope.actor_id: actor_role},
            )
        )
        runtime = LangGraphRuntimeAdapter(build_graph(
            make_node(self._llm, policy, self._max_output_tokens, self._profiles),
            select_specialty,
        ))
        outcome = runtime.start(StartExecutionRequest(
            request_id=request_id,
            execution_id=execution_id,
            scope=scope,
            input=ExecutionInput(message, history=history),
        ))
        if not isinstance(outcome, CompletedExecution) or outcome.output.kind != "message":
            reason = getattr(outcome, "error", None) or getattr(outcome, "reason", None) or "unknown"
            raise ExecutionUnavailable(f"Orchestration runtime failed: {reason}")
        return outcome


class VPSService:
    """Core domain service for the VPS orchestrator with durable transactional boundaries."""

    def __init__(
        self,
        settings: VPSSettings,
        ledger: Any,
        runtime: OrchestrationRuntimePort,
        limits: Limits,
        audit: AuditSinkPort | None = None,
        metrics: HttpMetrics | None = None,
        *,
        knowledge_sync: Callable[[DocumentSyncRequest], DocumentSyncResult] | None = None,
        knowledge_retrieve: Callable[..., tuple[WorkspaceKnowledgeHit, ...]] | None = None,
        knowledge_ready: Callable[[], bool] | None = None,
        knowledge_deployment_id: str | None = None,
        on_close: Callable[[], None] | None = None,
    ):
        self.settings = settings
        self._ledger = ledger
        self._runtime = runtime
        self._limits = limits
        self._audit = audit
        self._metrics = metrics
        self._knowledge_sync = knowledge_sync
        self._knowledge_retrieve = knowledge_retrieve
        self._knowledge_ready = knowledge_ready
        self._knowledge_deployment_id = knowledge_deployment_id or settings.knowledge_deployment_id or settings.deployment_id
        self._on_close = on_close
        self._ready_until = 0.0

    READY_CACHE_SECONDS = 3.0

    @property
    def knowledge_deployment_id(self) -> str:
        return self._knowledge_deployment_id

    @property
    def has_knowledge(self) -> bool:
        return self._knowledge_sync is not None

    def ready(self) -> bool:
        try:
            if not bool(self._ledger.ready()):
                return False
            if self._knowledge_ready is not None and not bool(self._knowledge_ready()):
                return False
            return True
        except Exception:
            return False

    def close(self) -> None:
        if self._on_close is not None:
            self._on_close()

    def sync_knowledge_document(self, request: DocumentSyncRequest) -> DocumentSyncResult:
        if self._knowledge_sync is None:
            raise KnowledgeNotConfigured("Knowledge synchronization is not configured")
        if not self._ready_for_execute():
            raise ExecutionUnavailable("Orchestrator persistence is not ready")
        return self._knowledge_sync(request)

    def retrieve_workspace_knowledge(
        self,
        *,
        workspace_id: str,
        query: str,
        top_k: int = 5,
        allowed_tiers: frozenset[str] | None = None,
    ) -> tuple[WorkspaceKnowledgeHit, ...]:
        if self._knowledge_retrieve is None:
            return ()
        return self._knowledge_retrieve(
            deployment_id=self._knowledge_deployment_id,
            workspace_id=workspace_id,
            query=query,
            top_k=top_k,
            allowed_tiers=allowed_tiers,
        )

    def _ready_for_execute(self) -> bool:
        now = monotonic()
        if now < self._ready_until:
            return True
        if not self.ready():
            self._ready_until = 0.0
            return False
        self._ready_until = now + self.READY_CACHE_SECONDS
        return True

    def recover_interrupted(self, tenant_id: str = "default") -> int:
        return self._ledger.recover_interrupted(
            deployment_id=self.settings.deployment_id,
            tenant_id=tenant_id,
        )

    def _return_to_received_safely(
        self, execution_id: str, scope: ExecutionScope,
        event_claim: ClaimToken | None, conversation_claim: ClaimToken | None,
    ) -> None:
        if event_claim is not None:
            try:
                self._ledger.return_to_received(execution_id, scope=scope, claim_token=event_claim)
            except Exception:
                pass
        if conversation_claim is not None:
            try:
                self._ledger.release_claim(conversation_claim)
            except Exception:
                pass

    def _audit_execution(self, *, execution_id: str, scope: ExecutionScope, specialty: str) -> None:
        """G7 fail-closed durable audit logging."""
        if self._audit is None:
            return
        events = [
            AuditEvent.now(
                event_id=str(uuid4()),
                event_type=AuditEventType.OUTCOME,
                tool_call_id=f"{execution_id}:outcome",
                execution_id=execution_id,
                scope=scope,
                tool_id="vps-orchestrator",
                status="completed",
                metadata={"specialty": specialty},
            )
        ]
        batch = getattr(self._audit, "append_many", None)
        if batch is not None:
            batch(events)
        else:
            for event in events:
                self._audit.append(event)

    def audit_policy_denial(
        self,
        *,
        execution_id: str,
        scope: ExecutionScope,
        reason_code: str,
        resource: str = "capa1-guard",
    ) -> None:
        """Record a fail-closed policy/guard denial in the durable audit log."""
        if self._audit is None:
            return
        self._audit.append(
            AuditEvent.now(
                event_id=str(uuid4()),
                event_type=AuditEventType.POLICY_DECISION,
                tool_call_id=f"{execution_id}:policy_denial",
                execution_id=execution_id,
                scope=scope,
                tool_id="capa1-guardrail",
                resource=resource,
                decision="deny",
                status="denied",
                error_code=reason_code,
            )
        )

    def execute_turn(
        self,
        *,
        scope: ExecutionScope,
        message: str,
        idempotency_key: str,
        account: str = "http",
        request_id: str | None = None,
        turn_id: str | None = None,
        max_message_chars: int = 8_000,
        actor_role: Role = Role.ACTOR,
    ) -> dict[str, Any]:
        """Execute a conversational turn through durable reservation, claims, graph run, and commit."""
        if not self._ready_for_execute():
            raise ExecutionUnavailable("Orchestrator persistence is not ready")

        if not isinstance(message, str) or not message.strip() or len(message) > max_message_chars:
            raise InputRejected(f"message must be non-empty text up to {max_message_chars} characters")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip() or len(idempotency_key) > 128:
            raise InputRejected("idempotency_key must be non-empty text up to 128 characters")

        payload = {"conversation_id": scope.conversation_id, "message": message}
        reservation = self._ledger.reserve_inbox(
            scope.deployment_id,
            scope.tenant_id,
            account,
            idempotency_key,
            payload,
            channel="http",
        )

        if not reservation.is_new and reservation.state == "COMPLETED":
            stored = self._ledger.outcome(reservation.execution_id, scope=scope)
            if stored and isinstance(stored.get("http_response"), dict):
                replayed = dict(stored["http_response"])
                replayed["replayed"] = True
                return replayed
            raise ExecutionUnavailable("Completed request has no recoverable outcome")

        if reservation.state not in {"RECEIVED", "PROCESSING"}:
            raise ExecutionInProgress("The idempotency key is currently being processed")

        owner_id = str(uuid4())
        batched = getattr(self._ledger, "claim_execution", None)
        if batched is not None:
            event_claim, conversation_claim, busy = batched(
                reservation.execution_id,
                scope=scope,
                owner_id=owner_id,
                lease_seconds=self.settings.claim_lease_seconds,
            )
            if busy == "event":
                raise ExecutionInProgress("The idempotency key is currently being processed")
            if busy == "conversation":
                raise ExecutionInProgress("The conversation is currently being processed")
        else:
            event_claim = self._ledger.claim(
                reservation.execution_id,
                scope=scope,
                owner_id=owner_id,
                lease_seconds=self.settings.claim_lease_seconds,
            )
            if event_claim is None:
                raise ExecutionInProgress("The idempotency key is currently being processed")
            conversation_claim = self._ledger.acquire_claim(
                scope,
                resource_type="conversation",
                resource_key=conversation_claim_key(scope),
                owner_id=owner_id,
                lease_seconds=self.settings.claim_lease_seconds,
            )
            if conversation_claim is None:
                self._return_to_received_safely(reservation.execution_id, scope, event_claim, None)
                raise ExecutionInProgress("The conversation is currently being processed")

        try:
            snapshot = getattr(self._ledger, "conversation_snapshot", None)
            if snapshot is not None:
                history, first_revision = snapshot(scope, limit=self.settings.history_limit)
            else:
                history = self._ledger.conversation_history(scope, limit=self.settings.history_limit)
                first_revision = None

            req_id = request_id or reservation.request_id
            exec_id = turn_id or reservation.execution_id

            completed = self._runtime.execute(
                request_id=req_id,
                execution_id=exec_id,
                scope=scope,
                message=message,
                history=history,
                actor_role=actor_role,
            )
        except Exception:
            self._return_to_received_safely(reservation.execution_id, scope, event_claim, conversation_claim)
            raise

        specialty = completed.output.specialty.value if completed.output.specialty else "general"
        output_guard = sanitize_capa1_output(completed.output.text)
        safe_output_text = output_guard.redacted_text if output_guard.redacted_text is not None else completed.output.text

        try:
            self._audit_execution(execution_id=exec_id, scope=scope, specialty=specialty)
        except Exception:
            self._return_to_received_safely(reservation.execution_id, scope, event_claim, conversation_claim)
            raise

        try:
            for _ in range(3):
                if first_revision is not None:
                    revision, first_revision = first_revision, None
                else:
                    revision = self._ledger.conversation_revision(scope)

                response = {
                    "status": "completed",
                    "request_id": req_id,
                    "execution_id": exec_id,
                    "conversation_id": scope.conversation_id,
                    "revision": revision + 1,
                    "specialty": specialty,
                    "message": safe_output_text,
                    "replayed": False,
                }

                try:
                    committed_revision = self._ledger.commit_conversation(
                        ConversationCommit(
                            execution_id=reservation.execution_id,
                            scope=scope,
                            expected_revision=revision,
                            response_id=f"execution:{exec_id}",
                            destination_ref=f"http:{scope.conversation_id}",
                            public_payload=response,
                            outcome={
                                "http_response": response,
                                "runtime": to_dict(completed),
                            },
                            turn=ConversationTurn(message, safe_output_text),
                            claim_tokens=(event_claim, conversation_claim),
                        )
                    )
                    if committed_revision != response["revision"]:
                        raise ExecutionUnavailable("Unexpected durable revision committed")
                    return response
                except RevisionConflict:
                    continue
        except Exception:
            self._return_to_received_safely(reservation.execution_id, scope, event_claim, conversation_claim)
            raise

        self._return_to_received_safely(reservation.execution_id, scope, event_claim, conversation_claim)
        raise ExecutionInProgress("Conversation revision conflict during commit")


def _default_knowledge_budget_path(configured: str) -> Path:
    if configured:
        return Path(configured).expanduser()
    data_dir = Path("/data")
    if data_dir.is_dir() and os.access(data_dir, os.W_OK):
        return data_dir / "knowledge-embedding-budget.sqlite"
    return Path.home() / ".local/state/incubia/knowledge-embedding-budget.sqlite"


def create_vps_service(settings: VPSSettings, pool: PooledConnections | None = None) -> tuple[VPSService, PooledConnections]:
    """Factory creating the complete production service graph with shared connection pool."""
    limits = load_runtime_limits()

    from incubia_orchestrator.modules.conversation.adapters.persistence.postgres import PostgresLedger
    from incubia_orchestrator.modules.audit.adapters.postgres import PostgresAuditLog
    from incubia_orchestrator.modules.orchestration.adapters.llm.openai_adapter import OpenAILLM

    effective_pool = pool or PooledConnections(settings.database_url, max_size=limits.pool_max_size)
    ledger = PostgresLedger(settings.database_url, pool=effective_pool)
    audit = PostgresAuditLog(settings.database_url, pool=effective_pool)

    if settings.fake_mode:
        llm = FakeLLM()
    else:
        llm = OpenAILLM(
            model=settings.model,
            api_key=os.getenv("OPENAI_API_KEY", ""),
            timeout=min(float(os.getenv("INCUBIA_TIMEOUT_SECONDS", "30")), 60.0),
            retries=0,
        )

    knowledge_sync = None
    knowledge_retrieve = None
    knowledge_ready = None
    kb_deployment = settings.knowledge_deployment_id or settings.deployment_id
    cleanup_callbacks: list[Callable[[], None]] = []

    if settings.knowledge_runtime_database_url and settings.knowledge_ingest_database_url:
        from incubia_orchestrator.bootstrap.knowledge_incubialab import (
            APPROVED_MAX_CALLS,
            APPROVED_MAX_INPUT_TOKENS,
            APPROVED_USD_CAP,
        )
        from incubia_orchestrator.modules.knowledge.adapters.document_extract import DocumentTextExtractor
        from incubia_orchestrator.modules.knowledge.adapters.document_http import HttpxDocumentDownloader
        from incubia_orchestrator.modules.knowledge.adapters.embedding import HashEmbedding
        from incubia_orchestrator.modules.knowledge.adapters.openai_embedding import EmbeddingBudget, OpenAIEmbedding
        from incubia_orchestrator.modules.knowledge.adapters.pool import KnowledgePools
        from incubia_orchestrator.modules.knowledge.adapters.postgres_documents import PostgresOrbitKnowledgeStore
        from incubia_orchestrator.modules.knowledge.adapters.runtime_dsn import (
            knowledge_ingest_resolver,
            knowledge_runtime_resolver,
        )
        from incubia_orchestrator.modules.knowledge.application.document_sync import (
            RetrieveWorkspaceKnowledge,
            SyncDocumentKnowledge,
        )

        kb_env = {
            "INCUBIA_KNOWLEDGE_RUNTIME_DATABASE_URL": settings.knowledge_runtime_database_url,
            "INCUBIA_KNOWLEDGE_INGEST_DATABASE_URL": settings.knowledge_ingest_database_url,
        }
        runtime_resolve = knowledge_runtime_resolver(kb_env, deployment_id=kb_deployment)
        ingest_resolve = knowledge_ingest_resolver(kb_env, deployment_id=kb_deployment)
        runtime_pools = KnowledgePools(runtime_resolve, max_size=min(4, limits.pool_max_size))
        ingest_pools = KnowledgePools(ingest_resolve, max_size=min(2, limits.pool_max_size))
        store = PostgresOrbitKnowledgeStore(ingest_pools=ingest_pools, runtime_pools=runtime_pools)
        cleanup_callbacks.append(store.close)

        if settings.fake_mode:
            kb_embedding = HashEmbedding()
        else:
            max_calls = int(os.getenv("INCUBIA_KNOWLEDGE_MAX_CALLS") or str(max(APPROVED_MAX_CALLS, 10_000)))
            usd_cap = float(os.getenv("INCUBIA_KNOWLEDGE_USD_CAP") or str(max(APPROVED_USD_CAP, 5.0)))
            budget = EmbeddingBudget(
                _default_knowledge_budget_path(settings.knowledge_budget_file),
                max_calls=max_calls,
                max_input_tokens=APPROVED_MAX_INPUT_TOKENS,
                usd_cap=usd_cap,
            )
            kb_embedding = OpenAIEmbedding(os.getenv("OPENAI_API_KEY", ""), budget)
            cleanup_callbacks.append(kb_embedding.close)

        downloader = HttpxDocumentDownloader(
            allow_insecure_urls=settings.allow_insecure_download_urls,
        )
        extractor = DocumentTextExtractor()
        knowledge_sync = SyncDocumentKnowledge(store, downloader, extractor, kb_embedding)
        knowledge_retrieve = RetrieveWorkspaceKnowledge(store, kb_embedding)
        knowledge_ready = lambda: store.ready(kb_deployment)

    def _close_all() -> None:
        for cb in cleanup_callbacks:
            try:
                cb()
            except Exception:
                pass

    runtime = LangGraphOrchestrationRuntime(llm, settings.model, limits)
    service = VPSService(
        settings,
        ledger,
        runtime,
        limits,
        audit=audit,
        knowledge_sync=knowledge_sync,
        knowledge_retrieve=knowledge_retrieve,
        knowledge_ready=knowledge_ready,
        knowledge_deployment_id=kb_deployment,
        on_close=_close_all,
    )
    return service, effective_pool
