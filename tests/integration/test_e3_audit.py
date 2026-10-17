import sqlite3

import httpx
import pytest

from incubia_orchestrator.modules.audit.adapters.sqlite import SqliteAuditLog
from tests.integration.test_read_tool import compose, invocation


def test_tool_audit_is_durable_and_omits_resource_and_secret(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        raise AssertionError("No network call expected")

    use_case, adapter, _ = compose(handler)
    audit_path = tmp_path / "audit.sqlite3"
    use_case._audit = SqliteAuditLog(audit_path)
    try:
        result = use_case(invocation(resource="tenant:tenant-b:canary-secret"))
    finally:
        adapter.close()
    assert result.error.code == "POLICY_DENIED"
    assert calls == []
    with sqlite3.connect(audit_path) as connection:
        events = connection.execute(
            "SELECT event_type, tool_call_id, execution_id FROM audit_events ORDER BY occurred_at"
        ).fetchall()
    assert len(events) == 3
    assert {row[0] for row in events} == {
        "tool.requested", "tool.policy_decision", "tool.completed"
    }
    assert all(row[1:] == ("tool-call-1", "execution-1") for row in events)
    assert b"canary-secret" not in audit_path.read_bytes()


def test_audit_failure_prevents_external_call(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        raise AssertionError("External I/O must be blocked")

    use_case, adapter, _ = compose(handler)
    audit = SqliteAuditLog(tmp_path / "audit.sqlite3")
    use_case._audit = audit
    audit.path.unlink()
    audit.path.mkdir()
    try:
        with pytest.raises(sqlite3.OperationalError):
            use_case(invocation())
    finally:
        adapter.close()
    assert calls == []


def test_allowed_read_persists_policy_attempt_and_outcome(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"items": [{"sku": "S-1", "name": "shoe"}]})

    use_case, adapter, _ = compose(handler)
    path = tmp_path / "audit.sqlite3"
    use_case._audit = SqliteAuditLog(path)
    try:
        result = use_case(invocation())
    finally:
        adapter.close()
    assert result.status.value == "SUCCESS"
    assert len(calls) == 1
    with sqlite3.connect(path) as connection:
        events = connection.execute(
            "SELECT event_type FROM audit_events WHERE execution_id = ? ORDER BY occurred_at, rowid",
            ("execution-1",),
        ).fetchall()
    assert [event[0] for event in events] == [
        "tool.requested", "tool.policy_decision", "tool.attempt", "tool.completed"
    ]
