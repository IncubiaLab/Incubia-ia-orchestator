"""Durable PostgreSQL audit sink (E3 G7).

Same port and redaction contract as ``SqliteAuditLog``: identifiers, a resource
hash and whitelisted bounded metadata only. Each append is its own short
transaction scoped via ``set_config`` so RLS applies; failures propagate so the
caller fails closed before external I/O.
"""

import hashlib
import json
import re
from collections.abc import Callable
from typing import Any

from incubia_orchestrator.modules.audit.domain.audit import AuditEvent, safe_metadata

_INSERT = """INSERT INTO audit_events (
    event_id, event_type, occurred_at, tool_call_id, execution_id, deployment_id,
    tenant_id, conversation_id, actor_id, tool_id, resource_sha256, decision,
    attempt, status, error_code, metadata
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)"""


# Columnas libres sólo aceptan identificadores acotados: nunca texto libre ni secretos.
_IDENTIFIER = re.compile(r"[A-Za-z0-9._:@/-]{1,128}")


def _bounded(name: str, value: str | None, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"Audit field {name} must be a bounded identifier")
    return value


def _default_connect(dsn: str) -> Any:
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Install psycopg to use PostgreSQL audit") from exc
    return psycopg.connect(dsn, connect_timeout=3)


class PostgresAuditLog:
    def __init__(self, database_url: str, *, connect: Callable[[str], Any] = _default_connect,
                 pool: Any = None):
        """``pool`` (foundation.pg_pool.PooledConnections) is opt-in; scope stays
        transaction-local (set_config ... true) so pooled reuse cannot leak it."""
        if not database_url:
            raise ValueError("DATABASE_URL is required")
        self._dsn = database_url
        self._connect = connect
        self._pool = pool

    def append(self, event: AuditEvent) -> None:
        self.append_many((event,))

    def append_many(self, events: tuple[AuditEvent, ...] | list[AuditEvent]) -> None:
        """All events of one scope in ONE connection/transaction (atomic, one round trip)."""
        if not events:
            return
        scope = events[0].scope
        if not scope.deployment_id or not scope.tenant_id:
            raise ValueError("A trusted deployment and tenant scope is required")
        if any(e.scope != scope for e in events):
            raise ValueError("append_many requires a single scope")
        rows = [self._row(e) for e in events]
        if self._pool is not None:
            with self._pool.connection() as connection:
                self._write(connection, scope, rows)
            return
        connection = self._connect(self._dsn)
        try:
            self._write(connection, scope, rows)
        finally:
            connection.close()

    @staticmethod
    def _write(connection, scope, rows) -> None:
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('app.deployment_id', %s, true), "
                    "set_config('app.tenant_id', %s, true)",
                    (scope.deployment_id, scope.tenant_id),
                )
                for row in rows:
                    cursor.execute(_INSERT, row)

    @staticmethod
    def _row(event: AuditEvent) -> tuple:
        scope = event.scope
        fields = {name: _bounded(name, getattr(event, name)) for name in
                  ("event_id", "tool_call_id", "execution_id", "tool_id")}
        fields.update({name: _bounded(name, getattr(scope, name)) for name in
                       ("conversation_id", "actor_id")})
        for name in ("status", "error_code", "decision"):
            fields[name] = _bounded(name, getattr(event, name), optional=True)
        return (
            fields["event_id"], event.event_type.value, event.occurred_at,
            fields["tool_call_id"], fields["execution_id"], scope.deployment_id,
            scope.tenant_id, fields["conversation_id"], fields["actor_id"],
            fields["tool_id"], hashlib.sha256(event.resource.encode()).hexdigest(),
            fields["decision"], event.attempt, fields["status"], fields["error_code"],
            json.dumps(safe_metadata(event.metadata), sort_keys=True),
        )
