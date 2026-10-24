"""E3-5: fallos de proveedores, pool agotado y fencing bajo workers concurrentes.

Todo es offline: los proveedores son ``httpx.MockTransport``, el ledger es
SQLite y el pool usa una clase de conexión sustituta. Cada caso comprueba
tiempo acotado, abstención o error controlado, ausencia de efectos duplicados
y un estado de ledger recuperable.
"""
import json
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack

import httpx
import psycopg
import psycopg_pool
import pytest

from incubia_orchestrator.bootstrap.d0 import D0Deployment, D0Runtime, D0Settings, ExecutionInProgress, ExecutionUnavailable
from incubia_orchestrator.bootstrap.e3_grounded import compose_grounded_workflow
from incubia_orchestrator.foundation.contracts.execution import (
    CompletedExecution, ConversationTurn, ExecutionOutput, ExecutionScope,
)
from incubia_orchestrator.modules.audit.adapters.sqlite import SqliteAuditLog
from incubia_orchestrator.modules.conversation.adapters.channels.telegram.client import TelegramClient
from incubia_orchestrator.modules.conversation.adapters.channels.telegram.runner import (
    DispatcherAlreadyActive, TelegramRunner,
)
from incubia_orchestrator.modules.conversation.adapters.persistence.sqlite_ledger import SqliteLedger
from incubia_orchestrator.modules.conversation.ports.ledger import (
    ClaimConflict, ConversationCommit, conversation_claim_key,
)
from incubia_orchestrator.modules.governance.adapters.policy.in_process.engine import Authority, InProcessPolicyEngine
from incubia_orchestrator.modules.knowledge.adapters import pool as pool_module
from incubia_orchestrator.modules.knowledge.adapters.fake import FakeRetrieval
from incubia_orchestrator.modules.knowledge.adapters.openai_embedding import EmbeddingBudget, OpenAIEmbedding
from incubia_orchestrator.modules.knowledge.adapters.pool import KnowledgePools
from incubia_orchestrator.modules.knowledge.adapters.postgres import PostgresKnowledge
from incubia_orchestrator.modules.knowledge.domain import EvidenceItem
from incubia_orchestrator.modules.orchestration.adapters.llm.openai_adapter import OpenAILLM
from incubia_orchestrator.modules.orchestration.adapters.runtime.langgraph.adapter import LangGraphRuntimeAdapter
from incubia_orchestrator.modules.orchestration.adapters.runtime.langgraph.graph import build_graph
from incubia_orchestrator.modules.orchestration.adapters.runtime.langgraph.nodes.generate_response import make_node
from incubia_orchestrator.modules.orchestration.adapters.runtime.langgraph.nodes.select_specialty import select_specialty
from incubia_orchestrator.modules.orchestration.adapters.tools.catalog_http import CatalogHttpAdapter, CatalogHttpConfig
from incubia_orchestrator.modules.orchestration.application.grounded_workflow import ReadRequest
from incubia_orchestrator.modules.orchestration.domain.specialty import profiles_for
from incubia_orchestrator.modules.orchestration.domain.tools import ToolDescriptor

SETTINGS = D0Settings("sqlite://unused", "dep-f", "tenant-f", "actor-f")
SCOPE = ExecutionScope("dep-f", "tenant-f", "conv-f", "actor-f")
BOUND_SECONDS = 5.0


# --------------------------------------------------------------------------- helpers
class _Ledger:
    """Ledger D0 sobre SQLite con una conexión por hilo."""

    def __init__(self, path):
        self.path, self._local, self._all, self._lock = path, threading.local(), [], threading.Lock()

    def _ledger(self):
        ledger = getattr(self._local, "ledger", None)
        if ledger is None:
            ledger = self._local.ledger = SqliteLedger(self.path)
            with self._lock:
                self._all.append(ledger)
        return ledger

    def __getattr__(self, name):
        return getattr(self._ledger(), name)

    def ready(self):
        return True

    def outcome(self, execution_id, *, scope):
        row = self._ledger()._connection.execute(
            "SELECT outcome_json FROM outcomes WHERE execution_id=?", (execution_id,)).fetchone()
        return None if row is None else json.loads(row[0])

    def close(self):
        with self._lock:
            for ledger in self._all:
                try:  # conexiones por hilo: las de otros hilos las libera el GC
                    ledger.close()
                except sqlite3.ProgrammingError:
                    pass
            self._all.clear()


def _rows(path, sql):
    with sqlite3.connect(path) as connection:
        return connection.execute(sql).fetchall()


def _expire(path):
    with sqlite3.connect(path) as connection:
        for table in ("resource_claims", "dispatcher_claims"):
            connection.execute(f"UPDATE {table} SET lease_until='1970-01-01T00:00:00+00:00'")


def _llm_runtime(llm):
    """Runtime D0 con el adaptador LLM real (transporte simulado) en vez de FakeLLM."""
    runtime = D0Runtime(SETTINGS)
    policy = InProcessPolicyEngine(Authority(SETTINGS.deployment_id, SETTINGS.tenant_id,
                                             frozenset({SETTINGS.actor_id}), enabled_actions=frozenset({"llm.generate"})))
    runtime._runtime = LangGraphRuntimeAdapter(
        build_graph(make_node(llm, policy, 128, profiles_for("e3-d0-deterministic")), select_specialty))
    return runtime


class _Provider:
    """Proveedor HTTP simulado que cuenta llamadas y falla según un guion."""

    def __init__(self, *script):
        self.script, self.calls = list(script), 0

    def __call__(self, request):
        self.calls += 1
        step = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(step, Exception):
            raise step
        return step

    def client(self):
        return httpx.Client(transport=httpx.MockTransport(self))


def _ok_llm():
    return httpx.Response(200, json={"status": "completed", "output": [
        {"type": "message", "content": [{"type": "output_text", "text": "respuesta"}]}]})


# --------------------------------------------------------------------------- LLM
@pytest.mark.parametrize("failure,code", [
    (httpx.ReadTimeout("t"), "PROVIDER_TIMEOUT"),
    (httpx.ConnectError("c"), "PROVIDER_UNAVAILABLE"),
    (httpx.Response(503), "PROVIDER_ERROR"),
    (httpx.Response(500), "PROVIDER_ERROR"),
])
def test_llm_failure_is_bounded_controlled_and_leaves_recoverable_ledger(tmp_path, failure, code):
    path = tmp_path / "d0.sqlite"
    provider = _Provider(failure)
    ledger = _Ledger(path)
    service = D0Deployment(SETTINGS, ledger, _llm_runtime(
        OpenAILLM(model="m", api_key="k", retries=1, client=provider.client())))
    started = time.monotonic()
    with pytest.raises(ExecutionUnavailable):
        service.execute(message="hola", conversation_id="conv-1", idempotency_key="k-1")
    assert time.monotonic() - started < BOUND_SECONDS
    # Intentos físicos acotados: 1 + retries; sin efecto durable visible.
    assert provider.calls == 2
    assert _rows(path, "SELECT state FROM inbox_events") == [("RECEIVED",)]
    assert _rows(path, "SELECT count(*) FROM outcomes") == [(0,)]
    assert _rows(path, "SELECT count(*) FROM deliveries") == [(0,)]
    assert _rows(path, "SELECT count(*) FROM turns") == [(0,)]

    # Recuperación: con el proveedor sano la misma clave completa exactamente una vez.
    recovered = D0Deployment(SETTINGS, ledger, _llm_runtime(
        OpenAILLM(model="m", api_key="k", client=_Provider(_ok_llm()).client())))
    first = recovered.execute(message="hola", conversation_id="conv-1", idempotency_key="k-1")
    again = recovered.execute(message="hola", conversation_id="conv-1", idempotency_key="k-1")
    assert first["revision"] == 1 and again["replayed"] is True
    assert again["execution_id"] == first["execution_id"]
    assert _rows(path, "SELECT count(*) FROM deliveries") == [(1,)]
    assert _rows(path, "SELECT state FROM inbox_events") == [("COMPLETED",)]
    ledger.close()


def test_llm_provider_error_codes_do_not_retry_non_transient_status():
    for status, code in ((401, "PROVIDER_AUTH"), (400, "PROVIDER_ERROR")):
        provider = _Provider(httpx.Response(status))
        llm = OpenAILLM(model="m", api_key="k", retries=3, client=provider.client())
        from incubia_orchestrator.modules.orchestration.ports.llm import GenerationFailure, GenerationRequest
        with pytest.raises(GenerationFailure) as error:
            llm.generate(GenerationRequest("hola", (), "i", 16))
        assert error.value.code == code and provider.calls == 1


# --------------------------------------------------------------------------- READ tool
def _workflow(tmp_path, client, *, retrieval_items=(), max_attempts=2, clock=None, deadline_seconds=10):
    capability = "sales.advice"
    descriptor = ToolDescriptor("business.catalog.lookup", capabilities=frozenset({capability}),
                                deployment_ids=frozenset({"dep-f"}), tenant_ids=frozenset({"tenant-f"}),
                                adapter_key="catalog.http",
                                input_schema={"type": "object", "required": ["query"],
                                              "properties": {"query": {"type": "string", "maxLength": 256}},
                                              "additionalProperties": False})
    config = CatalogHttpConfig("http://127.0.0.1:9", allow_loopback_for_fixture=True,
                               max_attempts=max_attempts, timeout_seconds=1.0)
    kwargs = {"clock": clock} if clock else {}
    adapter = CatalogHttpAdapter(config, client=client, **kwargs)
    audit = SqliteAuditLog(tmp_path / "audit.sqlite3")
    policy = InProcessPolicyEngine(Authority("dep-f", "tenant-f", frozenset({"actor-f"}),
                                             enabled_actions=frozenset({descriptor.tool_id})))
    retrieval = FakeRetrieval(retrieval_items)
    workflow = compose_grounded_workflow(
        retrieval=retrieval, descriptors=(descriptor,), adapters={"catalog.http": adapter},
        policy=policy, audit=audit, deadline_seconds=deadline_seconds,
        read_request=lambda q, c, s: ReadRequest({"query": "zapatos"}, f"tenant:{s.tenant_id}:catalog"))
    return workflow, retrieval, tmp_path / "audit.sqlite3"


KNOWLEDGE = (EvidenceItem("dep-f", "manual", "v1", "chunk", "gen", "zapatos tienen garantía", 0.9,
                          "https://docs.incubia.org/garantia"),)


@pytest.mark.parametrize("failure", [httpx.ReadTimeout("t"), httpx.ConnectError("c"),
                                     httpx.Response(500), httpx.Response(503), httpx.Response(429)])
def test_read_tool_failure_abstains_or_degrades_without_hanging(tmp_path, failure):
    provider = _Provider(failure)
    workflow, _, audit = _workflow(tmp_path, provider.client())
    started = time.monotonic()
    answer = workflow.answer(SCOPE, "zapatos", "sales.advice", execution_id="exec-1")
    assert time.monotonic() - started < BOUND_SECONDS
    assert answer.abstained is True and "No tengo evidencia" in answer.text
    assert provider.calls == 2  # max_attempts, nunca más
    types = [row[0] for row in _rows(audit, "SELECT event_type FROM audit_events WHERE execution_id='exec-1' ORDER BY occurred_at")]
    assert types[:2] == ["tool.requested", "tool.policy_decision"]
    assert len(types) >= 3  # al menos un intento/resultado registrado
    assert len(_rows(audit, "SELECT DISTINCT execution_id FROM audit_events")) == 1


def test_read_tool_failure_still_answers_from_knowledge_without_tool_evidence(tmp_path):
    provider = _Provider(httpx.Response(503))
    workflow, retrieval, _ = _workflow(tmp_path, provider.client(), retrieval_items=KNOWLEDGE)
    answer = workflow.answer(SCOPE, "zapatos", "sales.advice")
    assert answer.abstained is False and "garantía" in answer.text
    assert len(retrieval.calls) == 1


def test_read_tool_deadline_already_spent_makes_no_more_than_one_attempt(tmp_path):
    ticks = iter(range(0, 1000, 20))  # reloj simulado: cada lectura avanza 20 s (no hay espera real)

    provider = _Provider(httpx.ReadTimeout("t"))
    workflow, _, _ = _workflow(tmp_path, provider.client(), clock=lambda: next(ticks), deadline_seconds=1)
    answer = workflow.answer(SCOPE, "zapatos", "sales.advice")
    # El reloj del adaptador ya superó el deadline: a lo sumo un intento físico.
    assert provider.calls <= 1
    assert answer.abstained is True


# --------------------------------------------------------------------------- embeddings
def _knowledge(tmp_path, provider):
    budget = EmbeddingBudget(tmp_path / "budget.sqlite", max_calls=10, max_input_tokens=100_000, usd_cap=1.0)
    embedding = OpenAIEmbedding("sk-secret-value", budget, client=provider.client())
    return PostgresKnowledge(lambda _d: pytest.fail("la base no debe abrirse"), embedding), budget


@pytest.mark.parametrize("failure", [httpx.ReadTimeout("t"), httpx.ConnectError("c"),
                                     httpx.Response(503), httpx.Response(429)])
def test_embeddings_down_fails_fast_with_controlled_error_and_no_leak(tmp_path, failure):
    from incubia_orchestrator.modules.knowledge.domain import RetrievalQuery
    provider = _Provider(failure)
    store, budget = _knowledge(tmp_path, provider)
    started = time.monotonic()
    with pytest.raises(RuntimeError) as error:
        store.retrieve(RetrievalQuery(SCOPE, "zapatos", "sales.advice"))
    assert time.monotonic() - started < BOUND_SECONDS
    assert str(error.value) == "Embedding request failed"
    assert "sk-secret-value" not in repr(error.value.__cause__) + str(error.value)
    assert error.value.__context__ is None
    assert store.embedding_ready is False
    assert provider.calls == 1  # sin reintentos ocultos
    assert budget.snapshot()["calls"] == 1  # la reserva fail-closed se conserva


def test_embeddings_down_degrades_to_abstention_instead_of_exception(tmp_path):
    from incubia_orchestrator.modules.orchestration.application.grounded_response import GroundedResponse
    from incubia_orchestrator.foundation.telemetry import HttpMetrics
    store, _ = _knowledge(tmp_path, _Provider(httpx.Response(503)))
    metrics = HttpMetrics(SCOPE.deployment_id, SCOPE.tenant_id)
    answer = GroundedResponse(store, metrics=metrics).answer(SCOPE, "zapatos", "sales.advice")
    assert answer.abstained is True
    assert answer.retrieval_ran and answer.retrieval_hit_count == 0
    assert answer.retrieval_error_code == "EMBEDDING_UNAVAILABLE"
    assert metrics.snapshot()["rejections"] == [
        {"category": "knowledge", "reason": "EMBEDDING_UNAVAILABLE", "count": 1}]

    tool = EvidenceItem(SCOPE.deployment_id, "catalog", "1", "call:0", "call",
                        "Zapato sintético", public_ref="https://world.openfoodfacts.org/product/1")
    answer = GroundedResponse(store).answer(SCOPE, "zapatos", "sales.advice", tool_evidence=(tool,))
    assert not answer.abstained
    assert answer.evidence == (tool,)
    assert answer.text == tool.text
    assert answer.retrieval_error_code == "EMBEDDING_UNAVAILABLE"

    class BrokenMetrics:
        def rejection(self, *args):
            raise RuntimeError("metrics down")

    answer = GroundedResponse(store, metrics=BrokenMetrics()).answer(
        SCOPE, "zapatos", "sales.advice", tool_evidence=(tool,))
    assert answer.evidence == (tool,)


# --------------------------------------------------------------------------- pool
class _StubConnection:
    """Conexión mínima para psycopg_pool: sin red ni libpq."""

    class _Pg:
        transaction_status = psycopg.pq.TransactionStatus.IDLE
        status = psycopg.pq.ConnStatus.OK

    def __init__(self):
        self.pgconn, self.closed, self.broken = self._Pg(), False, False
        self.info = None

    @classmethod
    def connect(cls, conninfo="", **kwargs):
        return cls()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def close(self):
        self.closed = True

    def execute(self, *args, **kwargs):
        return None

    def rollback(self):
        pass

    def commit(self):
        pass


def test_pool_exhaustion_rejects_fast_and_recovers(tmp_path, monkeypatch):
    from incubia_orchestrator.foundation.telemetry import HttpMetrics
    real = psycopg_pool.ConnectionPool
    monkeypatch.setattr(pool_module, "ConnectionPool",
                        lambda *a, **k: real(*a, connection_class=_StubConnection, **k))
    metrics = HttpMetrics("dep-f", "tenant-f")
    pools = KnowledgePools(lambda _d: "postgresql://unused/x", max_size=2, metrics=metrics)
    try:
        with ExitStack() as held:
            for _ in range(2):  # agota max_size reteniendo las conexiones
                held.enter_context(pools.connection("dep-f"))
            started = time.monotonic()
            with pytest.raises(psycopg_pool.PoolTimeout):
                with pools.connection("dep-f"):
                    pytest.fail("no debe haber conexión disponible")
            elapsed = time.monotonic() - started
            # Rechazo acotado por el timeout=3 del pool, no una espera indefinida.
            assert elapsed < 4.5
        with pools.connection("dep-f"):  # liberadas las retenidas, vuelve a servir
            pass
        snapshot = metrics.snapshot()["db_pool"]
        assert snapshot["max"] == 2
        assert snapshot["wait_count"] == 4
        assert snapshot["timeouts"] == 1
    finally:
        pools.close()


def test_pool_recovers_after_release(monkeypatch):
    class BrokenMetrics:
        def pool_stats(self, **kwargs):
            raise RuntimeError("metrics down")

        def pool_wait(self, *args, **kwargs):
            raise RuntimeError("metrics down")

    real = psycopg_pool.ConnectionPool
    monkeypatch.setattr(pool_module, "ConnectionPool",
                        lambda *a, **k: real(*a, connection_class=_StubConnection, **k))
    pools = KnowledgePools(lambda _d: "postgresql://unused/x", max_size=1,
                           metrics=BrokenMetrics())
    try:
        with pools.connection("dep-f"):
            pass
        with pools.connection("dep-f"):  # la conexión devuelta es reutilizable
            pass
    finally:
        pools.close()


# --------------------------------------------------------------------------- fencing
class _Gated:
    """Runtime que retiene un worker en PROCESSING hasta liberarlo."""

    def __init__(self):
        self._inner = D0Runtime(SETTINGS)
        self.entered, self.release = threading.Event(), threading.Event()

    def execute(self, **kwargs):
        self.entered.set()
        assert self.release.wait(10)
        return self._inner.execute(**kwargs)


def test_expired_claim_with_concurrent_workers_commits_exactly_once(tmp_path):
    path = tmp_path / "d0.sqlite"
    ledger_a, ledger_b = _Ledger(path), _Ledger(path)
    gated = _Gated()
    worker_a = D0Deployment(SETTINGS, ledger_a, gated)
    worker_b = D0Deployment(SETTINGS, ledger_b, D0Runtime(SETTINGS))
    outcome_a = []

    def run_a():
        try:
            outcome_a.append(worker_a.execute(message="hola", conversation_id="conv-1", idempotency_key="k"))
        except Exception as error:  # noqa: BLE001
            outcome_a.append(error)

    thread = threading.Thread(target=run_a, daemon=True)
    thread.start()
    assert gated.entered.wait(5)
    # B no roba mientras el lease de A sigue vigente.
    assert worker_b.recover_interrupted() == 0
    with pytest.raises(ExecutionInProgress):
        worker_b.execute(message="hola", conversation_id="conv-1", idempotency_key="k")
    _expire(path)
    assert worker_b.recover_interrupted() == 1
    first = worker_b.execute(message="hola", conversation_id="conv-1", idempotency_key="k")
    assert first["revision"] == 1 and first["replayed"] is False

    gated.release.set()  # A despierta con claims vencidos y generación obsoleta
    thread.join(10)
    assert not thread.is_alive()
    assert len(outcome_a) == 1 and isinstance(outcome_a[0], Exception)
    assert _rows(path, "SELECT count(*) FROM deliveries") == [(1,)]
    assert _rows(path, "SELECT count(*) FROM turns") == [(1,)]
    assert _rows(path, "SELECT count(*) FROM outcomes") == [(1,)]
    assert _rows(path, "SELECT state FROM inbox_events") == [("COMPLETED",)]
    assert _rows(path, "SELECT revision FROM conversations") == [(1,)]
    replay = worker_b.execute(message="hola", conversation_id="conv-1", idempotency_key="k")
    assert replay["replayed"] is True and replay["execution_id"] == first["execution_id"]
    ledger_a.close()
    ledger_b.close()


def test_stale_worker_cannot_commit_nor_rewind_the_new_owner(tmp_path):
    path = tmp_path / "d0.sqlite"
    ledger = SqliteLedger(path)
    reservation = ledger.reserve_inbox("dep-f", "tenant-f", "acc", "k", {"m": 1}, channel="http")
    stale_event = ledger.claim(reservation.execution_id, scope=SCOPE, owner_id="A", lease_seconds=60)
    stale_conv = ledger.acquire_claim(SCOPE, resource_type="conversation",
                                      resource_key=conversation_claim_key(SCOPE), owner_id="A", lease_seconds=60)
    _expire(path)
    assert ledger.recover_interrupted(deployment_id="dep-f", tenant_id="tenant-f") == 1
    new_event = ledger.claim(reservation.execution_id, scope=SCOPE, owner_id="B", lease_seconds=60)
    new_conv = ledger.acquire_claim(SCOPE, resource_type="conversation",
                                    resource_key=conversation_claim_key(SCOPE), owner_id="B", lease_seconds=60)
    assert new_event.generation > stale_event.generation and new_conv.generation > stale_conv.generation

    def commit(tokens):
        return ConversationCommit(reservation.execution_id, SCOPE, 0, "r", "http:conv-f", {"m": 1}, {"ok": 1},
                                  ConversationTurn("u", "a"), claim_tokens=tokens)

    with pytest.raises(ClaimConflict):
        ledger.commit_conversation(commit((stale_event, stale_conv)))
    # El fallo del worker obsoleto no devuelve a RECEIVED ni libera el trabajo del nuevo dueño.
    assert ledger.return_to_received(reservation.execution_id, scope=SCOPE, claim_token=stale_event) is False
    assert ledger.release_claim(stale_conv) is False
    assert _rows(path, "SELECT state FROM inbox_events") == [("PROCESSING",)]
    assert ledger.commit_conversation(commit((new_event, new_conv))) == 1
    assert _rows(path, "SELECT count(*) FROM deliveries") == [(1,)]
    ledger.close()


def _update(number, chat, text):
    return {"update_id": number, "message": {"chat": {"id": chat, "type": "private"},
            "from": {"id": chat}, "date": 1, "text": text}}


def test_concurrent_dispatchers_with_expired_claim_send_exactly_once(tmp_path):
    path = tmp_path / "e3.sqlite"
    seed = SqliteLedger(path)
    seed.add_binding(channel="telegram", account="42", chat="7", sender="7", deployment_id="d",
                     tenant_id="t", conversation_id="c", actor_id="a")
    seed.acquire_dispatcher_claim(channel="telegram", account_ref="42", owner_id="dead", lease_seconds=60)
    seed.close()
    _expire(path)
    sent, lock, barrier = [], threading.Lock(), threading.Barrier(4)

    def handler(request):
        if request.url.path.endswith("getUpdates"):
            return httpx.Response(200, json={"ok": True, "result": [_update(1, 7, "hola")]})
        with lock:
            sent.append(request.read())
        return httpx.Response(200, json={"ok": True, "result": {"message_id": len(sent)}})

    def generate(text, scope, history, request_id, execution_id):
        return CompletedExecution(request_id, execution_id, ExecutionOutput("respuesta", None))

    def worker(_):
        ledger = SqliteLedger(path)
        runner = TelegramRunner(ledger, TelegramClient("secret", httpx.Client(transport=httpx.MockTransport(handler))),
                                account="42", generate=generate)
        barrier.wait(5)
        try:
            runner.cycle()
            return "ran"
        except DispatcherAlreadyActive:
            return "rejected"
        finally:
            ledger.close()

    with ThreadPoolExecutor(4) as executor:
        results = list(executor.map(worker, range(4)))
    assert results.count("ran") == 1 and results.count("rejected") == 3
    assert len(sent) == 1
    assert _rows(path, "SELECT state FROM deliveries") == [("SENT",)]
    assert _rows(path, "SELECT count(*) FROM turns") == [(1,)]


def _llm_request():
    from incubia_orchestrator.modules.orchestration.ports.llm import GenerationRequest
    return GenerationRequest("hola", (), "i", 16)


@pytest.mark.parametrize("body", [
    {"error": {"type": "insufficient_quota", "code": "insufficient_quota"}},
    {"error": {"code": "credit_balance_exhausted"}},
])
def test_llm_quota_429_fails_fast_without_retry(body):
    from incubia_orchestrator.modules.orchestration.ports.llm import GenerationFailure
    provider = _Provider(httpx.Response(429, json=body))
    llm = OpenAILLM(model="m", api_key="k", retries=3, client=provider.client(), sleep=lambda s: None)
    with pytest.raises(GenerationFailure) as error:
        llm.generate(_llm_request())
    assert error.value.code == "PROVIDER_QUOTA" and provider.calls == 1


def test_llm_transient_429_retries_with_retry_after_then_succeeds():
    slept = []
    provider = _Provider(httpx.Response(429, headers={"retry-after": "2"}, json={"error": {"type": "rate_limit_exceeded"}}),
                         _ok_llm())
    llm = OpenAILLM(model="m", api_key="k", retries=2, timeout=30, client=provider.client(), sleep=slept.append)
    assert llm.generate(_llm_request()).text
    assert provider.calls == 2 and slept == [2.0]


def test_llm_transient_429_is_bounded_and_respects_deadline():
    from incubia_orchestrator.modules.orchestration.ports.llm import GenerationFailure
    provider = _Provider(httpx.Response(429, headers={"retry-after": "3600"}))
    llm = OpenAILLM(model="m", api_key="k", retries=5, timeout=5, client=provider.client(), sleep=lambda s: None)
    with pytest.raises(GenerationFailure) as error:
        llm.generate(_llm_request())
    assert error.value.code == "PROVIDER_RATE_LIMIT" and provider.calls == 1
    provider = _Provider(httpx.Response(429))
    llm = OpenAILLM(model="m", api_key="k", retries=2, client=provider.client(), sleep=lambda s: None)
    with pytest.raises(GenerationFailure):
        llm.generate(_llm_request())
    assert provider.calls == 3
