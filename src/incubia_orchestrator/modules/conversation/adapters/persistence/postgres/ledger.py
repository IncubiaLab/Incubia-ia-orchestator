"""PostgreSQL adapter for the E3-D0 local deployment ledger.

The adapter is deliberately synchronous and opens only short transactions; no
provider call may run while a transaction is held.
"""
import json
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from incubia_orchestrator.foundation.contracts.execution import ConversationTurn, ExecutionScope
from incubia_orchestrator.modules.conversation.ports.ledger import (
    ConversationCommit, IdempotencyConflict, InboxReservation, RevisionConflict,
    ScopeConflict,
)


class PostgresLedger:
    CONNECT_TIMEOUT_SECONDS = 3

    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("DATABASE_URL is required")
        self.database_url = database_url

    @staticmethod
    def _driver():
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - exercised by container build
            raise RuntimeError("Install psycopg to use PostgreSQL persistence") from exc
        return psycopg

    @contextmanager
    def _transaction(self):
        connection = self._driver().connect(
            self.database_url, connect_timeout=self.CONNECT_TIMEOUT_SECONDS
        )
        try:
            with connection.transaction():
                yield connection
        finally:
            connection.close()

    def migrate(self, migration_path: Path) -> None:
        sql = migration_path.read_text(encoding="utf-8")
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql)
                cursor.execute(
                    "INSERT INTO schema_migrations(version) VALUES (%s) ON CONFLICT DO NOTHING",
                    (migration_path.name,),
                )

    def ready(self) -> bool:
        try:
            with self._transaction() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1 FROM schema_migrations WHERE version=%s", ("001_e3_d0_ledger.sql",))
                    return cursor.fetchone() is not None
        except Exception:
            return False

    @staticmethod
    def _hash(payload: dict) -> str:
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def reserve_inbox(self, deployment_id: str, tenant_id: str, account: str,
                      event_id: str, payload: dict, *, channel: str = "http") -> InboxReservation:
        digest = self._hash(payload)
        key = (deployment_id, tenant_id, channel, account, event_id)
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT payload_hash, request_id, execution_id, state "
                    "FROM inbox_events WHERE deployment_id=%s AND tenant_id=%s "
                    "AND channel=%s AND channel_account_ref=%s AND external_event_id=%s FOR UPDATE",
                    key,
                )
                row = cursor.fetchone()
                if row:
                    if row[0] != digest:
                        raise IdempotencyConflict("Same event key has a different payload")
                    return InboxReservation(str(row[1]), str(row[2]), row[3], False)
                request_id, execution_id = str(uuid4()), str(uuid4())
                cursor.execute(
                    "INSERT INTO inbox_events (deployment_id, tenant_id, channel, channel_account_ref, "
                    "external_event_id, payload_hash, payload_json, request_id, execution_id, state) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::uuid, %s::uuid, 'RECEIVED')",
                    (*key, digest, json.dumps(payload), request_id, execution_id),
                )
                return InboxReservation(request_id, execution_id, "RECEIVED", True)

    def claim(self, execution_id: str) -> bool:
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE inbox_events SET state='PROCESSING' WHERE execution_id=%s::uuid AND state='RECEIVED'", (execution_id,))
                return cursor.rowcount == 1

    def recover_interrupted(self) -> int:
        """Return unfinished local work to RECEIVED after an app restart.

        E3-D0 has a single runtime process and no external side effect.  A
        PROCESSING record therefore has not been delivered yet and is safe to
        replay through the deterministic runtime.  Later multi-replica/
        external-tool work must use fencing instead of this recovery rule.
        """
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE inbox_events SET state='RECEIVED' WHERE state='PROCESSING'")
                return cursor.rowcount

    def return_to_received(self, execution_id: str) -> bool:
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE inbox_events SET state='RECEIVED' "
                    "WHERE execution_id=%s::uuid AND state='PROCESSING'",
                    (execution_id,),
                )
                return cursor.rowcount == 1

    def conversation_revision(self, scope: ExecutionScope) -> int:
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT revision FROM conversations WHERE deployment_id=%s AND tenant_id=%s "
                    "AND conversation_id=%s AND actor_id=%s",
                    (scope.deployment_id, scope.tenant_id, scope.conversation_id, scope.actor_id),
                )
                row = cursor.fetchone()
                return row[0] if row else 0

    def conversation_history(self, scope: ExecutionScope, *, limit: int = 20) -> tuple[ConversationTurn, ...]:
        if limit < 1:
            raise ValueError("History limit must be positive")
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT user_text, assistant_text FROM ("
                    "SELECT user_text, assistant_text, created_at, execution_id FROM turns "
                    "WHERE deployment_id=%s AND tenant_id=%s AND conversation_id=%s AND actor_id=%s "
                    "ORDER BY created_at DESC, execution_id DESC LIMIT %s"
                    ") recent ORDER BY created_at, execution_id",
                    (scope.deployment_id, scope.tenant_id, scope.conversation_id, scope.actor_id, limit),
                )
                return tuple(ConversationTurn(*row) for row in cursor.fetchall())

    def commit_conversation(self, commit: ConversationCommit) -> int:
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT deployment_id, tenant_id FROM inbox_events "
                    "WHERE execution_id=%s::uuid AND state='PROCESSING' FOR UPDATE",
                    (commit.execution_id,),
                )
                event = cursor.fetchone()
                if event is None:
                    raise RuntimeError("Only a claimed event can complete")
                if tuple(event) != (commit.scope.deployment_id, commit.scope.tenant_id):
                    raise ScopeConflict("Execution scope does not match accepted event")
                cursor.execute(
                    "INSERT INTO conversations (deployment_id, tenant_id, conversation_id, actor_id) "
                    "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                    (commit.scope.deployment_id, commit.scope.tenant_id,
                     commit.scope.conversation_id, commit.scope.actor_id),
                )
                cursor.execute(
                    "UPDATE conversations SET revision=revision+1 WHERE deployment_id=%s AND tenant_id=%s "
                    "AND conversation_id=%s AND actor_id=%s AND revision=%s",
                    (commit.scope.deployment_id, commit.scope.tenant_id,
                     commit.scope.conversation_id, commit.scope.actor_id, commit.expected_revision),
                )
                if cursor.rowcount != 1:
                    raise RevisionConflict("Conversation revision changed")
                cursor.execute(
                    "INSERT INTO outcomes (execution_id, outcome_json) VALUES (%s::uuid, %s::jsonb)",
                    (commit.execution_id, json.dumps(commit.outcome)),
                )
                cursor.execute(
                    "INSERT INTO turns (execution_id, deployment_id, tenant_id, conversation_id, actor_id, "
                    "user_text, assistant_text) VALUES (%s::uuid, %s, %s, %s, %s, %s, %s)",
                    (commit.execution_id, commit.scope.deployment_id, commit.scope.tenant_id,
                     commit.scope.conversation_id, commit.scope.actor_id,
                     commit.turn.user, commit.turn.assistant),
                )
                cursor.execute(
                    "INSERT INTO deliveries (execution_id, response_id, destination_ref, payload_json, state) "
                    "VALUES (%s::uuid, %s, %s, %s::jsonb, 'PENDING')",
                    (commit.execution_id, commit.response_id, commit.destination_ref,
                     json.dumps(commit.public_payload)),
                )
                cursor.execute(
                    "UPDATE inbox_events SET state='COMPLETED', terminal_at=now() "
                    "WHERE execution_id=%s::uuid",
                    (commit.execution_id,),
                )
                return commit.expected_revision + 1

    def outcome(self, execution_id: str) -> dict | None:
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT outcome_json FROM outcomes WHERE execution_id=%s::uuid", (execution_id,))
                row = cursor.fetchone()
                if row is None:
                    return None
                return json.loads(row[0]) if isinstance(row[0], str) else row[0]
