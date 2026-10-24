"""PostgreSQL adapter for the shared E3 Conversation ledger.

The adapter is deliberately synchronous and opens only short transactions; no
provider call may run while a transaction is held.
"""
import json
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from incubia_orchestrator.foundation.contracts.execution import ConversationTurn, ExecutionScope
from incubia_orchestrator.modules.identity_tenant.domain.principal import Membership, Role
from incubia_orchestrator.modules.identity_tenant.ports.identity import TrustedBinding
from incubia_orchestrator.modules.conversation.ports.ledger import (
    ClaimConflict, ClaimToken, ConversationCommit, IdempotencyConflict,
    InboxReservation, RevisionConflict, ScopeConflict, conversation_claim_key,
)


class PostgresLedger:
    CONNECT_TIMEOUT_SECONDS = 3
    _HISTORY_SQL = (
        "SELECT user_text, assistant_text FROM ("
        "SELECT user_text, assistant_text, created_at, execution_id FROM turns "
        "WHERE deployment_id=%s AND tenant_id=%s AND conversation_id=%s AND actor_id=%s "
        "ORDER BY created_at DESC, execution_id DESC LIMIT %s"
        ") recent ORDER BY created_at, execution_id"
    )
    _READY_VERSIONS = {
        "d0_runtime": "006_e3_d0_runtime_claims.sql",
        "incubia_runtime": "004_e3_h1_dispatcher_claims.sql",
    }

    def __init__(self, database_url: str, *, pool=None):
        """``pool`` (foundation.pg_pool.PooledConnections) is opt-in for the hot
        path; without it every transaction opens its own connection (migrator,
        backup and probes keep that behaviour)."""
        if not database_url:
            raise ValueError("DATABASE_URL is required")
        self.database_url = database_url
        self._pool = pool

    @staticmethod
    def _driver():
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - exercised by container build
            raise RuntimeError("Install psycopg to use PostgreSQL persistence") from exc
        return psycopg

    @contextmanager
    def _transaction(self, scope: ExecutionScope | tuple[str, str] | str | None = None):
        if self._pool is not None:
            with self._pool.connection() as connection:
                with self._scoped(connection, scope):
                    yield connection
            return
        connection = self._driver().connect(
            self.database_url, connect_timeout=self.CONNECT_TIMEOUT_SECONDS
        )
        try:
            with self._scoped(connection, scope):
                yield connection
        finally:
            connection.close()

    @contextmanager
    def _scoped(self, connection, scope):
        # Scope is set with transaction-local set_config inside THIS transaction,
        # so it never survives on a pooled connection after COMMIT/ROLLBACK.
        with connection.transaction():
            if scope is not None:
                if isinstance(scope, str):
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT set_config('app.deployment_id', %s, true)", (scope,),
                        )
                else:
                    deployment_id, tenant_id = self._scope_values(scope)
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT set_config('app.deployment_id', %s, true), "
                            "set_config('app.tenant_id', %s, true)",
                            (deployment_id, tenant_id),
                        )
            yield

    @staticmethod
    def _scope_values(scope: ExecutionScope | tuple[str, str]) -> tuple[str, str]:
        if isinstance(scope, tuple):
            deployment_id, tenant_id = scope
        else:
            deployment_id, tenant_id = scope.deployment_id, scope.tenant_id
        if not deployment_id or not tenant_id:
            raise ValueError("A trusted deployment and tenant scope is required")
        return deployment_id, tenant_id

    def migrate(self, migration_path: Path) -> None:
        sql = migration_path.read_text(encoding="utf-8")
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT to_regclass('public.schema_migrations')")
                if cursor.fetchone()[0] is not None:
                    cursor.execute(
                        "SELECT 1 FROM schema_migrations WHERE version=%s",
                        (migration_path.name,),
                    )
                    if cursor.fetchone() is not None:
                        return
                cursor.execute(sql)
                cursor.execute(
                    "INSERT INTO schema_migrations(version) VALUES (%s)",
                    (migration_path.name,),
                )

    def ready(self) -> bool:
        try:
            with self._transaction() as connection:
                with connection.cursor() as cursor:
                    # One round trip: role plus the migration versions it may require.
                    cursor.execute(
                        "SELECT current_user, ARRAY(SELECT version FROM schema_migrations "
                        "WHERE version = ANY(%s))",
                        (list(self._READY_VERSIONS.values()),),
                    )
                    role, versions = cursor.fetchone()
                    required_version = self._READY_VERSIONS.get(role)
                    return required_version is not None and required_version in versions
        except Exception:
            return False

    @staticmethod
    def _hash(payload: dict) -> str:
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def get(self, deployment_id: str, tenant_id: str, subject_id: str) -> Membership | None:
        """Read the current membership through the tenant-scoped runtime role."""
        with self._transaction((deployment_id, tenant_id)) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT deployment_id, tenant_id, subject_id, role, active "
                    "FROM memberships WHERE deployment_id=%s AND tenant_id=%s AND subject_id=%s",
                    (deployment_id, tenant_id, subject_id),
                )
                row = cursor.fetchone()
        return Membership(row[0], row[1], row[2], Role(row[3]), bool(row[4])) if row else None

    def resolve(self, *, channel: str, account: str, chat: str,
                sender: str) -> TrustedBinding | None:
        """Resolve one binding using the trusted channel-account boundary."""
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('app.binding_channel', %s, true), "
                    "set_config('app.binding_account', %s, true)",
                    (channel, account),
                )
                cursor.execute(
                    "SELECT deployment_id, tenant_id, conversation_id, actor_id FROM bindings "
                    "WHERE channel=%s AND channel_account_ref=%s AND external_chat_ref=%s "
                    "AND external_sender_ref=%s AND enabled",
                    (channel, account, chat, sender),
                )
                row = cursor.fetchone()
        return TrustedBinding(*row) if row else None

    def reserve_inbox(self, deployment_id: str, tenant_id: str, account: str,
                      event_id: str, payload: dict, *, channel: str = "http") -> InboxReservation:
        digest = self._hash(payload)
        key = (deployment_id, tenant_id, channel, account, event_id)
        with self._transaction((deployment_id, tenant_id)) as connection:
            with connection.cursor() as cursor:
                request_id, execution_id = str(uuid4()), str(uuid4())
                cursor.execute(
                    "INSERT INTO inbox_events (deployment_id, tenant_id, channel, channel_account_ref, "
                    "external_event_id, payload_hash, payload_json, request_id, execution_id, state) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::uuid, %s::uuid, 'RECEIVED') "
                    "ON CONFLICT (deployment_id, tenant_id, channel, channel_account_ref, external_event_id) "
                    "DO NOTHING RETURNING request_id, execution_id, state",
                    (*key, digest, json.dumps(payload), request_id, execution_id),
                )
                row = cursor.fetchone()
                if row is not None:
                    return InboxReservation(str(row[0]), str(row[1]), row[2], True)
                cursor.execute(
                    "SELECT payload_hash, request_id, execution_id, state FROM inbox_events "
                    "WHERE deployment_id=%s AND tenant_id=%s AND channel=%s "
                    "AND channel_account_ref=%s AND external_event_id=%s FOR UPDATE",
                    key,
                )
                existing = cursor.fetchone()
                if existing is None:
                    raise RuntimeError("Inbox conflict could not be reconciled")
                if existing[0] != digest:
                    raise IdempotencyConflict("Same event key has a different payload")
                return InboxReservation(str(existing[1]), str(existing[2]), existing[3], False)

    @staticmethod
    def _lease_seconds(value: float) -> float:
        if not 0 < value <= 300:
            raise ValueError("Claim lease must be between 0 and 300 seconds")
        return float(value)

    @classmethod
    def _dispatcher_key(cls, channel: str, account_ref: str) -> tuple[str, str]:
        if not channel or not account_ref:
            raise ValueError("Dispatcher channel and account are required")
        return channel, account_ref

    def acquire_dispatcher_claim(
        self, *, channel: str, account_ref: str, owner_id: str,
        lease_seconds: float = 60,
    ) -> ClaimToken | None:
        """Acquire durable ownership for one channel account.

        The claim is deliberately not tenant-scoped: one Telegram bot can
        serve several bindings. RLS scopes the row to the channel/account
        values set transaction-locally by this method.
        """
        seconds = self._lease_seconds(lease_seconds)
        channel, account_ref = self._dispatcher_key(channel, account_ref)
        if not owner_id:
            raise ValueError("Dispatcher owner is required")
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('app.dispatch_channel', %s, true), "
                    "set_config('app.dispatch_account', %s, true)",
                    (channel, account_ref),
                )
                cursor.execute(
                    "INSERT INTO dispatcher_claims "
                    "(channel, account_ref, owner_id, generation, lease_until) "
                    "VALUES (%s, %s, %s, 1, clock_timestamp() + (%s * interval '1 second')) "
                    "ON CONFLICT (channel, account_ref) DO UPDATE SET "
                    "owner_id=EXCLUDED.owner_id, "
                    "generation=CASE WHEN dispatcher_claims.owner_id=EXCLUDED.owner_id "
                    "THEN dispatcher_claims.generation "
                    "ELSE dispatcher_claims.generation + 1 END, "
                    "lease_until=EXCLUDED.lease_until, updated_at=clock_timestamp() "
                    "WHERE dispatcher_claims.lease_until <= clock_timestamp() "
                    "OR dispatcher_claims.owner_id=EXCLUDED.owner_id "
                    "RETURNING generation",
                    (channel, account_ref, owner_id, seconds),
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                return ClaimToken(
                    "", "", "dispatcher", f"{channel}:{account_ref}", owner_id, row[0]
                )

    def renew_dispatcher_claim(
        self, token: ClaimToken, *, lease_seconds: float = 60,
    ) -> bool:
        seconds = self._lease_seconds(lease_seconds)
        channel, account_ref = self._dispatcher_key(
            *token.resource_key.split(":", 1)
        ) if token.resource_type == "dispatcher" and ":" in token.resource_key else ("", "")
        if token.resource_type != "dispatcher" or not channel or not account_ref:
            return False
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('app.dispatch_channel', %s, true), "
                    "set_config('app.dispatch_account', %s, true)",
                    (channel, account_ref),
                )
                cursor.execute(
                    "UPDATE dispatcher_claims SET lease_until=clock_timestamp() + "
                    "(%s * interval '1 second'), updated_at=clock_timestamp() "
                    "WHERE channel=%s AND account_ref=%s AND owner_id=%s "
                    "AND generation=%s AND lease_until > clock_timestamp()",
                    (seconds, channel, account_ref, token.owner_id, token.generation),
                )
                return cursor.rowcount == 1

    def release_dispatcher_claim(self, token: ClaimToken) -> bool:
        if token.resource_type != "dispatcher" or ":" not in token.resource_key:
            return False
        channel, account_ref = token.resource_key.split(":", 1)
        channel, account_ref = self._dispatcher_key(channel, account_ref)
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('app.dispatch_channel', %s, true), "
                    "set_config('app.dispatch_account', %s, true)",
                    (channel, account_ref),
                )
                cursor.execute(
                    "UPDATE dispatcher_claims SET lease_until=clock_timestamp(), "
                    "updated_at=clock_timestamp() WHERE channel=%s AND account_ref=%s "
                    "AND owner_id=%s AND generation=%s",
                    (channel, account_ref, token.owner_id, token.generation),
                )
                return cursor.rowcount == 1

    @classmethod
    def _acquire_claim_in_transaction(
        cls, cursor, scope: ExecutionScope, resource_type: str,
        resource_key: str, owner_id: str, lease_seconds: float,
    ) -> ClaimToken | None:
        seconds = cls._lease_seconds(lease_seconds)
        if not resource_type or not resource_key or not owner_id:
            raise ValueError("Claim resource and owner are required")
        cursor.execute(
            "INSERT INTO resource_claims AS current_claim "
            "(deployment_id, tenant_id, resource_type, resource_key, owner_id, generation, lease_until) "
            "VALUES (%s, %s, %s, %s, %s, 1, clock_timestamp() + (%s * interval '1 second')) "
            "ON CONFLICT (deployment_id, tenant_id, resource_type, resource_key) DO UPDATE SET "
            "owner_id=EXCLUDED.owner_id, generation=current_claim.generation + 1, "
            "lease_until=EXCLUDED.lease_until, updated_at=clock_timestamp() "
            "WHERE current_claim.lease_until <= clock_timestamp() "
            "RETURNING generation",
            (scope.deployment_id, scope.tenant_id, resource_type, resource_key,
             owner_id, seconds),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return ClaimToken(
            scope.deployment_id, scope.tenant_id, resource_type,
            resource_key, owner_id, row[0],
        )

    def acquire_claim(
        self, scope: ExecutionScope, *, resource_type: str, resource_key: str,
        owner_id: str, lease_seconds: float = 60,
    ) -> ClaimToken | None:
        if resource_type == "execution":
            raise ValueError("Execution claims must be acquired through claim()")
        if resource_type == "conversation":
            resource_key = conversation_claim_key(scope)
        with self._transaction(scope) as connection:
            with connection.cursor() as cursor:
                return self._acquire_claim_in_transaction(
                    cursor, scope, resource_type, resource_key, owner_id, lease_seconds
                )

    def claim(
        self, execution_id: str, *, scope: ExecutionScope | None = None,
        owner_id: str, lease_seconds: float = 60,
    ) -> ClaimToken | None:
        if scope is None:
            raise ValueError("A trusted scope is required to claim an event")
        with self._transaction(scope) as connection:
            with connection.cursor() as cursor:
                return self._claim_event_in_transaction(
                    cursor, execution_id, scope, owner_id, lease_seconds)

    @classmethod
    def _claim_event_in_transaction(cls, cursor, execution_id, scope, owner_id, lease_seconds):
        token = cls._acquire_claim_in_transaction(
            cursor, scope, "execution", execution_id, owner_id, lease_seconds
        )
        if token is None:
            return None
        cursor.execute(
            "UPDATE inbox_events SET state='PROCESSING' WHERE execution_id=%s::uuid "
            "AND deployment_id=%s AND tenant_id=%s AND state IN ('RECEIVED', 'PROCESSING')",
            (execution_id, scope.deployment_id, scope.tenant_id),
        )
        if cursor.rowcount != 1:
            cursor.execute(
                "UPDATE resource_claims SET lease_until=clock_timestamp(), "
                "updated_at=clock_timestamp() WHERE deployment_id=%s AND tenant_id=%s "
                "AND resource_type=%s AND resource_key=%s AND owner_id=%s AND generation=%s",
                (token.deployment_id, token.tenant_id, token.resource_type,
                 token.resource_key, token.owner_id, token.generation),
            )
            return None
        return token

    def claim_execution(
        self, execution_id: str, *, scope: ExecutionScope, owner_id: str,
        lease_seconds: float = 60,
    ) -> tuple[ClaimToken | None, ClaimToken | None, str | None]:
        """Event claim + conversation claim in ONE transaction (saves round trips).

        Returns (event_token, conversation_token, busy) with busy in
        {None, "event", "conversation"}. If the conversation is busy the whole
        transaction rolls back, so no event claim or PROCESSING state is left.
        """
        class _Busy(Exception):
            pass

        try:
            with self._transaction(scope) as connection:
                with connection.cursor() as cursor:
                    event = self._claim_event_in_transaction(
                        cursor, execution_id, scope, owner_id, lease_seconds)
                    if event is None:
                        return None, None, "event"
                    conversation = self._acquire_claim_in_transaction(
                        cursor, scope, "conversation", conversation_claim_key(scope),
                        owner_id, lease_seconds)
                    if conversation is None:
                        raise _Busy
                    return event, conversation, None
        except _Busy:
            return None, None, "conversation"

    def conversation_snapshot(
        self, scope: ExecutionScope, *, limit: int = 20,
    ) -> tuple[tuple[ConversationTurn, ...], int]:
        """History and current revision in one transaction."""
        if limit < 1:
            raise ValueError("History limit must be positive")
        with self._transaction(scope) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COALESCE((SELECT revision FROM conversations WHERE deployment_id=%s "
                    "AND tenant_id=%s AND conversation_id=%s AND actor_id=%s), 0)",
                    (scope.deployment_id, scope.tenant_id, scope.conversation_id, scope.actor_id),
                )
                revision = cursor.fetchone()[0]
                cursor.execute(self._HISTORY_SQL, (
                    scope.deployment_id, scope.tenant_id, scope.conversation_id,
                    scope.actor_id, limit))
                return tuple(ConversationTurn(*row) for row in cursor.fetchall()), revision

    def renew_claim(self, token: ClaimToken, *, lease_seconds: float = 60) -> bool:
        seconds = self._lease_seconds(lease_seconds)
        scope = (token.deployment_id, token.tenant_id)
        with self._transaction(scope) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE resource_claims SET lease_until=clock_timestamp() + (%s * interval '1 second'), "
                    "updated_at=clock_timestamp() WHERE deployment_id=%s AND tenant_id=%s "
                    "AND resource_type=%s AND resource_key=%s AND owner_id=%s AND generation=%s "
                    "AND lease_until > clock_timestamp()",
                    (seconds, token.deployment_id, token.tenant_id, token.resource_type,
                     token.resource_key, token.owner_id, token.generation),
                )
                return cursor.rowcount == 1

    def release_claim(self, token: ClaimToken) -> bool:
        with self._transaction((token.deployment_id, token.tenant_id)) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE resource_claims SET lease_until=clock_timestamp(), "
                    "updated_at=clock_timestamp() WHERE deployment_id=%s AND tenant_id=%s "
                    "AND resource_type=%s AND resource_key=%s AND owner_id=%s AND generation=%s",
                    (token.deployment_id, token.tenant_id, token.resource_type,
                     token.resource_key, token.owner_id, token.generation),
                )
                return cursor.rowcount == 1

    def recover_interrupted(self, *, deployment_id: str, tenant_id: str) -> int:
        """Return this tenant's unfinished local-only work after an app restart.

        E3-D0 has a single runtime process and no external side effect.  A
        PROCESSING record therefore has not been delivered yet and is safe to
        replay through the deterministic runtime.  Later multi-replica/
        external-tool work must use fencing instead of this recovery rule.
        """
        scope = (deployment_id, tenant_id)
        with self._transaction(scope) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE inbox_events AS event SET state='RECEIVED' WHERE event.deployment_id=%s "
                    "AND event.tenant_id=%s AND event.state='PROCESSING' AND ("
                    "NOT EXISTS (SELECT 1 FROM resource_claims AS missing_claim "
                    "WHERE missing_claim.deployment_id=event.deployment_id "
                    "AND missing_claim.tenant_id=event.tenant_id "
                    "AND missing_claim.resource_type='execution' "
                    "AND missing_claim.resource_key=event.execution_id::text) "
                    "OR EXISTS (SELECT 1 FROM resource_claims AS expired_claim "
                    "WHERE expired_claim.deployment_id=event.deployment_id "
                    "AND expired_claim.tenant_id=event.tenant_id "
                    "AND expired_claim.resource_type='execution' "
                    "AND expired_claim.resource_key=event.execution_id::text "
                    "AND expired_claim.lease_until<=clock_timestamp()))",
                    scope,
                )
                return cursor.rowcount

    def return_to_received(
        self, execution_id: str, *, scope: ExecutionScope, claim_token: ClaimToken,
    ) -> bool:
        with self._transaction(scope) as connection:
            with connection.cursor() as cursor:
                if not self._claim_is_current(
                    cursor, claim_token, scope, "execution", execution_id
                ):
                    return False
                cursor.execute(
                    "UPDATE inbox_events SET state='RECEIVED' "
                    "WHERE execution_id=%s::uuid AND deployment_id=%s AND tenant_id=%s "
                    "AND state='PROCESSING'",
                    (execution_id, scope.deployment_id, scope.tenant_id),
                )
                changed = cursor.rowcount == 1
                if changed:
                    self._expire_claim(cursor, claim_token)
                return changed

    @staticmethod
    def _claim_is_current(cursor, token: ClaimToken, scope: ExecutionScope,
                          resource_type: str, resource_key: str) -> bool:
        if (token.deployment_id != scope.deployment_id or token.tenant_id != scope.tenant_id
                or token.resource_type != resource_type or token.resource_key != resource_key):
            return False
        cursor.execute(
            "SELECT 1 FROM resource_claims WHERE deployment_id=%s AND tenant_id=%s "
            "AND resource_type=%s AND resource_key=%s AND owner_id=%s AND generation=%s "
            "AND lease_until > clock_timestamp() FOR UPDATE",
            (token.deployment_id, token.tenant_id, token.resource_type, token.resource_key,
             token.owner_id, token.generation),
        )
        return cursor.fetchone() is not None

    @staticmethod
    def _expire_claim(cursor, token: ClaimToken) -> None:
        cursor.execute(
            "UPDATE resource_claims SET lease_until=clock_timestamp(), updated_at=clock_timestamp() "
            "WHERE deployment_id=%s AND tenant_id=%s AND resource_type=%s AND resource_key=%s "
            "AND owner_id=%s AND generation=%s",
            (token.deployment_id, token.tenant_id, token.resource_type, token.resource_key,
             token.owner_id, token.generation),
        )

    def conversation_revision(self, scope: ExecutionScope) -> int:
        with self._transaction(scope) as connection:
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
        with self._transaction(scope) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    self._HISTORY_SQL,
                    (scope.deployment_id, scope.tenant_id, scope.conversation_id, scope.actor_id, limit),
                )
                return tuple(ConversationTurn(*row) for row in cursor.fetchall())

    def commit_conversation(self, commit: ConversationCommit) -> int:
        with self._transaction(commit.scope) as connection:
            with connection.cursor() as cursor:
                execution_claims = [
                    claim for claim in commit.claim_tokens
                    if claim.resource_type == "execution"
                ]
                conversation_claims = [
                    claim for claim in commit.claim_tokens
                    if claim.resource_type == "conversation"
                ]
                conversation_key = conversation_claim_key(commit.scope)
                if (len(execution_claims) != 1 or len(conversation_claims) != 1
                        or len(commit.claim_tokens) != 2
                        or not self._claim_is_current(
                            cursor, execution_claims[0], commit.scope,
                            "execution", commit.execution_id,
                        )
                        or not self._claim_is_current(
                            cursor, conversation_claims[0], commit.scope,
                            "conversation", conversation_key,
                        )):
                    raise ClaimConflict("Conversation commit has no current fencing claims")
                cursor.execute(
                    "SELECT deployment_id, tenant_id FROM inbox_events "
                    "WHERE execution_id=%s::uuid AND deployment_id=%s AND tenant_id=%s "
                    "AND state='PROCESSING' FOR UPDATE",
                    (commit.execution_id, commit.scope.deployment_id, commit.scope.tenant_id),
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
                    "INSERT INTO outcomes (execution_id, deployment_id, tenant_id, outcome_json) "
                    "VALUES (%s::uuid, %s, %s, %s::jsonb)",
                    (commit.execution_id, commit.scope.deployment_id, commit.scope.tenant_id,
                     json.dumps(commit.outcome)),
                )
                cursor.execute(
                    "INSERT INTO turns (execution_id, deployment_id, tenant_id, conversation_id, actor_id, "
                    "user_text, assistant_text) VALUES (%s::uuid, %s, %s, %s, %s, %s, %s)",
                    (commit.execution_id, commit.scope.deployment_id, commit.scope.tenant_id,
                     commit.scope.conversation_id, commit.scope.actor_id,
                     commit.turn.user, commit.turn.assistant),
                )
                cursor.execute(
                    "INSERT INTO deliveries (execution_id, deployment_id, tenant_id, response_id, "
                    "destination_ref, payload_json, state) "
                    "VALUES (%s::uuid, %s, %s, %s, %s, %s::jsonb, 'PENDING')",
                    (commit.execution_id, commit.scope.deployment_id, commit.scope.tenant_id,
                     commit.response_id, commit.destination_ref, json.dumps(commit.public_payload)),
                )
                cursor.execute(
                    "UPDATE inbox_events SET state='COMPLETED', terminal_at=now() "
                    "WHERE execution_id=%s::uuid AND deployment_id=%s AND tenant_id=%s",
                    (commit.execution_id, commit.scope.deployment_id, commit.scope.tenant_id),
                )
                self._expire_claim(cursor, execution_claims[0])
                self._expire_claim(cursor, conversation_claims[0])
                return commit.expected_revision + 1

    def outcome(self, execution_id: str, *, scope: ExecutionScope) -> dict | None:
        with self._transaction(scope) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT outcome_json FROM outcomes WHERE execution_id=%s::uuid "
                    "AND deployment_id=%s AND tenant_id=%s",
                    (execution_id, scope.deployment_id, scope.tenant_id),
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                return json.loads(row[0]) if isinstance(row[0], str) else row[0]
