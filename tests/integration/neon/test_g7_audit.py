"""Opt-in Neon campaign for G7: durable, RLS-scoped, append-only audit."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
import pytest

from incubia_orchestrator.foundation.contracts.execution import ExecutionScope
from incubia_orchestrator.modules.audit.adapters.postgres import PostgresAuditLog
from incubia_orchestrator.modules.audit.domain.audit import AuditEvent, AuditEventType
from incubia_orchestrator.modules.conversation.adapters.persistence.postgres import PostgresLedger

pytestmark = pytest.mark.neon
ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = sorted((ROOT / "migrations/postgres").glob("[0-9][0-9][0-9]_*.sql"))


def _guard() -> None:
    if os.getenv("INCUBIA_E3_NEON_TESTS") != "1":
        pytest.skip("G7 Neon campaign requires explicit opt-in")
    if os.getenv("INCUBIA_E3_NEON_BRANCH") != "e3-h1-synthetic":
        pytest.skip("G7 Neon campaign requires the synthetic H1 branch")
    for var in ("DATABASE_URL", "INCUBIA_MIGRATION_DATABASE_URL"):
        host = urlsplit(os.getenv(var, "")).hostname or ""
        if not host.endswith(".neon.tech"):
            pytest.skip(f"{var} is not a Neon host")


@pytest.fixture(scope="module", autouse=True)
def schema():
    _guard()
    ledger = PostgresLedger(os.environ["INCUBIA_MIGRATION_DATABASE_URL"])
    for migration in MIGRATIONS:
        ledger.migrate(migration)


def _event(scope: ExecutionScope, execution_id: str, kind: AuditEventType) -> AuditEvent:
    return AuditEvent.now(event_id=str(uuid4()), event_type=kind, tool_call_id=f"{execution_id}:{kind.value}",
                          execution_id=execution_id, scope=scope, tool_id="g7.test", resource="tenant:x:y",
                          status="ok", metadata={"evidence_count": 1})


def test_audit_rls_isolation_and_append_only():
    _guard()
    dep = "e3-g7-" + uuid4().hex[:10]
    scope_a = ExecutionScope(dep, "tenant-a", "c", "actor")
    scope_b = ExecutionScope(dep, "tenant-b", "c", "actor")
    execution = "exec-" + uuid4().hex[:8]
    audit = PostgresAuditLog(os.environ["DATABASE_URL"])
    for kind in (AuditEventType.POLICY_DECISION, AuditEventType.RETRIEVAL, AuditEventType.OUTCOME):
        audit.append(_event(scope_a, execution, kind))
    audit.append(_event(scope_b, execution, AuditEventType.OUTCOME))

    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10, sslmode="require") as conn:
        with conn.transaction():
            cur = conn.cursor()
            cur.execute("SELECT set_config('app.deployment_id', %s, true), set_config('app.tenant_id', %s, true)",
                        (dep, "tenant-a"))
            cur.execute("SELECT count(*) FROM audit_events WHERE execution_id = %s", (execution,))
            assert cur.fetchone()[0] == 3  # tenant-b row is invisible
        for statement in ("UPDATE audit_events SET status = 'x'", "DELETE FROM audit_events"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with conn.transaction():
                    conn.execute(statement)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        # RLS WITH CHECK / scope mismatch must not allow writing another tenant's row.
        with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10, sslmode="require") as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.deployment_id', %s, true), set_config('app.tenant_id', %s, true)",
                             (dep, "tenant-a"))
                conn.execute(
                    "INSERT INTO audit_events (event_id,event_type,occurred_at,tool_call_id,execution_id,"
                    "deployment_id,tenant_id,conversation_id,actor_id,tool_id,resource_sha256) "
                    "VALUES (%s,'t',now(),'c',%s,%s,'tenant-b','c','a','t','h')", (str(uuid4()), execution, dep))
