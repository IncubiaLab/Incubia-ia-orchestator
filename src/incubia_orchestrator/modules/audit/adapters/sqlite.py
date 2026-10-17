"""Durable local audit sink for governed tool operations.

Stores identifiers and bounded classifications only. Resource names and tool
inputs may contain customer data, so neither is persisted verbatim.
"""

import hashlib
import json
import sqlite3
from pathlib import Path

from incubia_orchestrator.modules.audit.domain.audit import AuditEvent


class SqliteAuditLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS audit_events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                tool_call_id TEXT NOT NULL,
                execution_id TEXT NOT NULL,
                deployment_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                conversation_id TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                tool_id TEXT NOT NULL,
                resource_sha256 TEXT NOT NULL,
                decision TEXT,
                attempt INTEGER,
                status TEXT,
                error_code TEXT,
                metadata_json TEXT NOT NULL
            )""")
            connection.execute("CREATE INDEX IF NOT EXISTS audit_execution_idx ON audit_events (execution_id, occurred_at)")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5)

    def append(self, event: AuditEvent) -> None:
        # The audit write commits before the caller may perform external I/O.
        # An exception propagates and therefore fails the operation closed.
        safe_metadata = {key: event.metadata[key] for key in
                         ("descriptor_found", "attempts")
                         if key in event.metadata and type(event.metadata[key]) in (int, bool)}
        with self._connect() as connection:
            connection.execute("""INSERT INTO audit_events VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )""", (
                event.event_id, event.event_type.value, event.occurred_at.isoformat(),
                event.tool_call_id, event.execution_id, event.scope.deployment_id,
                event.scope.tenant_id, event.scope.conversation_id, event.scope.actor_id,
                event.tool_id, hashlib.sha256(event.resource.encode()).hexdigest(),
                event.decision, event.attempt, event.status, event.error_code,
                json.dumps(safe_metadata, sort_keys=True),
            ))
