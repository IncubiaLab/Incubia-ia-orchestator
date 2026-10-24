"""G7: durable Postgres audit adapter, correlated events and secrets canary (offline)."""
import hashlib
import json
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest

from incubia_orchestrator.bootstrap.e3_grounded import compose_grounded_workflow
from incubia_orchestrator.foundation.contracts.execution import ExecutionScope
from incubia_orchestrator.modules.audit.adapters.memory import InMemoryAuditLog
from incubia_orchestrator.modules.audit.adapters.postgres import PostgresAuditLog
from incubia_orchestrator.modules.audit.adapters.sqlite import SqliteAuditLog
from incubia_orchestrator.modules.audit.domain.audit import AuditEvent, AuditEventType
from incubia_orchestrator.modules.governance.adapters.policy.in_process.engine import Authority, InProcessPolicyEngine
from incubia_orchestrator.modules.knowledge.adapters.fake import FakeRetrieval
from incubia_orchestrator.modules.knowledge.domain import EvidenceItem
from incubia_orchestrator.modules.orchestration.adapters.tools.fake import FakeCatalogAdapter
from incubia_orchestrator.modules.orchestration.application.grounded_workflow import ReadRequest
from incubia_orchestrator.modules.orchestration.domain.tools import ToolDescriptor
from incubia_orchestrator.modules.orchestration.ports.tool_executor import ResolvedCredential

ROOT = Path(__file__).resolve().parents[2]
SCOPE = ExecutionScope("dep", "ten", "conv", "actor")
CAP = "business.catalog.lookup"
CANARY_INPUT = "CANARY-INPUT-9f3a7c1e"
CANARY_CRED = "CANARY-CRED-5b2d8e4a"
CANARY_RESOURCE = "CANARY-RES-77aa01cc"


class FakeCursor:
    def __init__(self, log):
        self.log = log

    def execute(self, sql, params=()):
        self.log.append((sql, tuple(params)))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConnection:
    def __init__(self, log, fail=False):
        self.log, self.fail, self.closed, self.committed = log, fail, False, False

    @contextmanager
    def transaction(self):
        yield
        if self.fail:
            raise RuntimeError("db down")
        self.committed = True

    def cursor(self):
        return FakeCursor(self.log)

    def close(self):
        self.closed = True


def _event(**kw):
    base = dict(event_id="e1", event_type=AuditEventType.OUTCOME, tool_call_id="c1", execution_id="x1",
                scope=SCOPE, tool_id="t", resource="tenant:ten:catalog")
    base.update(kw)
    return AuditEvent.now(**base)


def test_postgres_append_sets_rls_scope_then_inserts_redacted_row():
    log, holder = [], []

    def connect(dsn):
        holder.append(FakeConnection(log))
        return holder[-1]

    PostgresAuditLog("postgresql://x", connect=connect).append(
        _event(resource=CANARY_RESOURCE, metadata={"attempts": 2, "note": CANARY_INPUT, "evidence_count": 3}))
    assert "set_config('app.deployment_id'" in log[0][0] and log[0][1] == ("dep", "ten")
    params = log[1][1]
    assert hashlib.sha256(CANARY_RESOURCE.encode()).hexdigest() in params
    assert json.loads(params[-1]) == {"attempts": 2, "evidence_count": 3}
    assert CANARY_RESOURCE not in repr(log) and CANARY_INPUT not in repr(log)
    assert holder[0].committed and holder[0].closed


def test_postgres_append_fails_closed_and_closes_connection():
    conn = FakeConnection([], fail=True)
    with pytest.raises(RuntimeError):
        PostgresAuditLog("postgresql://x", connect=lambda dsn: conn).append(_event())
    assert conn.closed


def test_postgres_requires_dsn_and_scope():
    with pytest.raises(ValueError):
        PostgresAuditLog("")
    audit = PostgresAuditLog("postgresql://x", connect=lambda dsn: FakeConnection([]))
    with pytest.raises(ValueError):
        audit.append(_event(scope=ExecutionScope("dep", "", "c", "a")))


def test_audit_migration_is_scoped_append_only():
    sql = (ROOT / "migrations/postgres/008_e3_g7_audit.sql").read_text()
    assert "ENABLE ROW LEVEL SECURITY" in sql and "audit_events_tenant_scope" in sql
    assert "GRANT SELECT, INSERT ON audit_events TO incubia_runtime" in sql
    assert "UPDATE" not in sql.replace("-- ", "").split("GRANT")[1].split(";")[0]
    assert "GRANT" not in sql.split("d0_runtime", 1)[1].split("REVOKE ALL")[0]


class _Resolver:
    def resolve(self, profile_ref, scope):
        return ResolvedCredential(profile_ref, CANARY_CRED)


class _Recording:
    """Captures everything handed to a Postgres connection."""

    def __init__(self):
        self.log = []
        self.audit = PostgresAuditLog("postgresql://x", connect=lambda dsn: FakeConnection(self.log))


def _workflow(audit, *, retrieval=None, allow=True):
    descriptor = ToolDescriptor(CAP, capabilities=frozenset({CAP}), deployment_ids=frozenset({"dep"}),
                                tenant_ids=frozenset({"ten"}), adapter_key="fake",
                                credential_profile_ref="profile-1",
                                input_schema={"type": "object", "required": ["query"],
                                              "properties": {"query": {"type": "string", "maxLength": 256}},
                                              "additionalProperties": False})
    policy = InProcessPolicyEngine(Authority("dep", "ten", frozenset({"actor"}),
                                             enabled_actions=frozenset({CAP}) if allow else frozenset()))
    retrieval = retrieval or FakeRetrieval((EvidenceItem("dep", "doc", "v1", "chunk", "gen",
                                                         "Texto sintético.", 0.9, None),))
    return compose_grounded_workflow(
        retrieval=retrieval, descriptors=(descriptor,),
        adapters={"fake": FakeCatalogAdapter({CANARY_INPUT: [{"name": "Item"}]})},
        policy=policy, audit=audit, credentials=_Resolver(),
        read_request=lambda q, c, s: ReadRequest({"query": CANARY_INPUT}, f"tenant:ten:{CANARY_RESOURCE}"))


def test_workflow_emits_policy_tool_retrieval_outcome_correlated_by_execution_id():
    audit = InMemoryAuditLog()
    _workflow(audit).answer(SCOPE, "q", CAP, execution_id="exec-1")
    events = audit.events
    kinds = {e.event_type for e in events}
    assert {AuditEventType.POLICY_DECISION, AuditEventType.TOOL_COMPLETED,
            AuditEventType.RETRIEVAL, AuditEventType.OUTCOME} <= kinds
    assert {e.execution_id for e in events} == {"exec-1"}
    assert events[-1].event_type is AuditEventType.OUTCOME and events[-1].status == "completed"
    retrieval = next(e for e in events if e.event_type is AuditEventType.RETRIEVAL)
    assert retrieval.metadata["evidence_count"] >= 1


def test_workflow_audits_failed_outcome_and_reraises():
    class Boom:
        def retrieve(self, query):
            raise TimeoutError("secret-in-message " + CANARY_INPUT)

    audit = InMemoryAuditLog()
    with pytest.raises(TimeoutError):
        _workflow(audit, retrieval=Boom()).answer(SCOPE, "q", CAP, execution_id="exec-2")
    last = audit.events[-1]
    assert last.event_type is AuditEventType.OUTCOME and last.status == "failed"
    assert last.error_code == "TimeoutError" and CANARY_INPUT not in repr(last)


def test_audit_failure_before_tool_io_is_fail_closed():
    class Down:
        def append(self, event):
            raise RuntimeError("audit down")

    wf = _workflow(Down())
    with pytest.raises(RuntimeError):
        wf.answer(SCOPE, "q", CAP, execution_id="exec-3")


def test_secrets_canary_never_in_audit_payloads_or_logs(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    rec = _Recording()
    sqlite_path = tmp_path / "a.sqlite3"
    memory = InMemoryAuditLog()

    class Fanout:
        sinks = (rec.audit, SqliteAuditLog(sqlite_path), memory)

        def append(self, event):
            for sink in self.sinks:
                sink.append(event)

    _workflow(Fanout()).answer(SCOPE, "pregunta " + CANARY_CRED, CAP, execution_id="exec-4")
    assert rec.log, "postgres sink received events"
    with sqlite3.connect(sqlite_path) as c:
        sqlite_dump = repr(c.execute("SELECT * FROM audit_events").fetchall())
    pg_dump = repr(rec.log)
    mem_dump = " ".join(
        repr((e.event_id, e.decision, e.status, e.error_code, e.metadata)) for e in memory.events)
    for canary in (CANARY_INPUT, CANARY_CRED, CANARY_RESOURCE):
        assert canary not in pg_dump, canary
        assert canary not in sqlite_dump, canary
        assert canary not in mem_dump, canary
        assert canary not in caplog.text, canary


@pytest.mark.parametrize("field", ["error_code", "tool_id", "status"])
def test_postgres_rejects_free_text_in_identifier_columns_before_connecting(field):
    connected = []
    log = PostgresAuditLog("postgresql://x", connect=lambda dsn: connected.append(dsn))
    with pytest.raises(ValueError):
        log.append(_event(**{field: f"secret {CANARY_CRED} leaked"}))
    assert connected == []
