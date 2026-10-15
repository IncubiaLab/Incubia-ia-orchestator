"""Live connection and least-privilege checks for the isolated Neon branch."""
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import time
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
import pytest

from incubia_orchestrator.foundation.contracts.execution import ExecutionScope
from incubia_orchestrator.modules.conversation.adapters.persistence.postgres import PostgresLedger
from incubia_orchestrator.modules.conversation.ports.ledger import (
    ClaimConflict,
    ConversationCommit,
    IdempotencyConflict,
    RevisionConflict,
    conversation_claim_key,
)
from incubia_orchestrator.foundation.contracts.execution import ConversationTurn


pytestmark = pytest.mark.neon
ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module", autouse=True)
def apply_h1_migrations():
    if (os.getenv("INCUBIA_E3_NEON_TESTS") != "1"
            or os.getenv("INCUBIA_E3_NEON_BRANCH") != "e3-h1-synthetic"):
        pytest.skip("Neon campaign requires explicit branch opt-in")
    ledger = PostgresLedger(os.environ["INCUBIA_MIGRATION_DATABASE_URL"])
    try:
        for migration in sorted((ROOT / "migrations/postgres").glob("[0-9][0-9][0-9]_*.sql")):
            ledger.migrate(migration)
    except Exception as exc:
        pytest.fail(f"Neon H1 migrations failed ({type(exc).__name__})", pytrace=False)


def _connect(variable: str):
    try:
        return psycopg.connect(os.environ[variable], connect_timeout=10, sslmode="require")
    except Exception as exc:  # keep driver diagnostics (and URLs) out of pytest output
        pytest.fail(f"{variable} connection failed ({type(exc).__name__})", pytrace=False)


def test_runtime_is_pooled_tls_and_cannot_create_objects():
    parts = urlsplit(os.environ["DATABASE_URL"])
    assert "-pooler." in parts.hostname
    with _connect("DATABASE_URL") as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_user, current_database(), "
                "has_schema_privilege(current_user, 'public', 'CREATE'), "
                "(SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolbypassrls "
                " FROM pg_roles WHERE rolname=current_user), "
                "pg_has_role(current_user, 'neondb_owner', 'MEMBER')"
            )
            role, database, can_create, privileged, owner_member = cursor.fetchone()
        # Inspect TLS on the client→Neon connection. pg_stat_ssl describes the
        # proxy→PostgreSQL backend hop and may be false even when Neon enforces
        # TLS at its public endpoint.
        tls = connection.pgconn.ssl_in_use
    assert role == "incubia_runtime"
    assert database == "neondb"
    assert tls is True
    assert can_create is False
    assert privileged is False
    assert owner_member is False
    assert PostgresLedger(os.environ["DATABASE_URL"]).ready() is True


def test_migrator_is_direct_tls_and_has_schema_ddl():
    parts = urlsplit(os.environ["INCUBIA_MIGRATION_DATABASE_URL"])
    assert "-pooler." not in parts.hostname
    with _connect("INCUBIA_MIGRATION_DATABASE_URL") as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_user, current_database(), "
                "has_schema_privilege(current_user, 'public', 'CREATE'), "
                "(SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolbypassrls "
                " FROM pg_roles WHERE rolname=current_user)"
            )
            role, database, can_create, privileged = cursor.fetchone()
        tls = connection.pgconn.ssl_in_use
    assert role == "incubia_migrator"
    assert database == "neondb"
    assert tls is True
    assert can_create is True
    assert privileged is False


def test_runtime_rls_denies_missing_scope_and_isolates_tenants_on_reused_connection():
    deployment_id = "e3-h1-rls-test"
    tenant_a, tenant_b = "tenant-a-" + uuid4().hex, "tenant-b-" + uuid4().hex
    actor_id = "actor-test"
    conversation_a, conversation_b = "conversation-a-" + uuid4().hex, "conversation-b-" + uuid4().hex
    execution_a, execution_b = str(uuid4()), str(uuid4())
    account_ref = "e3-h1-" + uuid4().hex
    seeded = False
    admin = psycopg.connect(os.environ["INCUBIA_MIGRATION_DATABASE_URL"], connect_timeout=10)
    try:
        with admin.transaction():
            with admin.cursor() as cursor:
                for tenant, conversation, execution, event_id in (
                    (tenant_a, conversation_a, execution_a, "event-a"),
                    (tenant_b, conversation_b, execution_b, "event-b"),
                ):
                    cursor.execute(
                        "INSERT INTO inbox_events (deployment_id, tenant_id, channel, "
                        "channel_account_ref, external_event_id, payload_hash, payload_json, "
                        "request_id, execution_id, state, terminal_at) "
                        "VALUES (%s, %s, 'test', %s, %s, 'synthetic', '{}'::jsonb, %s::uuid, "
                        "%s::uuid, 'COMPLETED', now())",
                        (deployment_id, tenant, account_ref, event_id, str(uuid4()), execution),
                    )
                    cursor.execute(
                        "INSERT INTO conversations (deployment_id, tenant_id, conversation_id, actor_id, revision) "
                        "VALUES (%s, %s, %s, %s, 1)",
                        (deployment_id, tenant, conversation, actor_id),
                    )
                    cursor.execute(
                        "INSERT INTO turns (execution_id, deployment_id, tenant_id, conversation_id, actor_id, "
                        "user_text, assistant_text) VALUES (%s::uuid, %s, %s, %s, %s, 'synthetic', 'synthetic')",
                        (execution, deployment_id, tenant, conversation, actor_id),
                    )
                    cursor.execute(
                        "INSERT INTO outcomes (execution_id, deployment_id, tenant_id, outcome_json) "
                        "VALUES (%s::uuid, %s, %s, '{}'::jsonb)",
                        (execution, deployment_id, tenant),
                    )
                    cursor.execute(
                        "INSERT INTO deliveries (execution_id, deployment_id, tenant_id, response_id, "
                        "destination_ref, payload_json, state) VALUES (%s::uuid, %s, %s, %s, 'synthetic', "
                        "'{}'::jsonb, 'PENDING')",
                        (execution, deployment_id, tenant, "response-" + execution),
                    )
        seeded = True

        runtime = psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10, sslmode="require")
        try:
            scoped_tables = ("inbox_events", "conversations", "turns", "outcomes", "deliveries")
            with runtime.transaction():
                with runtime.cursor() as cursor:
                    for table in scoped_tables:
                        cursor.execute(f"SELECT count(*) FROM {table}")
                        assert cursor.fetchone()[0] == 0, f"unscoped read leaked rows from {table}"
                    with pytest.raises(psycopg.errors.InsufficientPrivilege):
                        with runtime.transaction():
                            with runtime.cursor() as cursor:
                                cursor.execute(
                                    "INSERT INTO schema_migrations(version) VALUES ('runtime-must-not-write')"
                                )
                    with pytest.raises(psycopg.errors.InsufficientPrivilege):
                        with runtime.transaction():  # savepoint keeps the connection usable after RLS denial
                            with runtime.cursor() as cursor:
                                cursor.execute(
                                    "INSERT INTO conversations (deployment_id, tenant_id, conversation_id, actor_id) "
                                    "VALUES (%s, %s, %s, %s)",
                                    (deployment_id, tenant_a, "must-be-denied", actor_id),
                                )

            scope = ExecutionScope(deployment_id, tenant_a, conversation_a, actor_id)
            history = PostgresLedger(os.environ["DATABASE_URL"]).conversation_history(scope)
            assert len(history) == 1
            assert history[0].user == "synthetic"

            # A transaction-local tenant value must not survive pool/connection reuse.
            with runtime.transaction():
                with runtime.cursor() as cursor:
                    cursor.execute(
                        "SELECT set_config('app.deployment_id', %s, true), "
                        "set_config('app.tenant_id', %s, true)",
                        (deployment_id, tenant_a),
                    )
                    cursor.execute("SELECT count(*) FROM turns")
                    assert cursor.fetchone()[0] == 1
            with runtime.transaction():
                with runtime.cursor() as cursor:
                    cursor.execute("SELECT count(*) FROM turns")
                    assert cursor.fetchone()[0] == 0
        finally:
            runtime.close()
    finally:
        if seeded:
            with admin.transaction():
                with admin.cursor() as cursor:
                    for execution in (execution_a, execution_b):
                        cursor.execute("DELETE FROM deliveries WHERE execution_id=%s::uuid", (execution,))
                        cursor.execute("DELETE FROM outcomes WHERE execution_id=%s::uuid", (execution,))
                        cursor.execute("DELETE FROM turns WHERE execution_id=%s::uuid", (execution,))
                    cursor.execute(
                        "DELETE FROM conversations WHERE deployment_id=%s AND tenant_id IN (%s, %s)",
                        (deployment_id, tenant_a, tenant_b),
                    )
                    cursor.execute(
                        "DELETE FROM inbox_events WHERE deployment_id=%s AND tenant_id IN (%s, %s)",
                        (deployment_id, tenant_a, tenant_b),
                    )
        admin.close()


def test_postgres_uow_revision_failure_rolls_back_every_row():
    scope = ExecutionScope(
        "e3-h1-rollback-test", "tenant-" + uuid4().hex,
        "conversation-" + uuid4().hex, "actor-test",
    )
    account = "e3-h1-" + uuid4().hex
    event = PostgresLedger(os.environ["DATABASE_URL"]).reserve_inbox(
        scope.deployment_id, scope.tenant_id, account, "event-" + uuid4().hex,
        {"message": "synthetic"}, channel="test",
    )
    ledger = PostgresLedger(os.environ["DATABASE_URL"])
    try:
        owner_id = "owner-" + uuid4().hex
        event_claim = ledger.claim(
            event.execution_id, scope=scope, owner_id=owner_id, lease_seconds=60
        )
        conversation_claim = ledger.acquire_claim(
            scope, resource_type="conversation", resource_key=conversation_claim_key(scope),
            owner_id=owner_id, lease_seconds=60,
        )
        assert event_claim is not None and conversation_claim is not None
        with pytest.raises(RevisionConflict):
            ledger.commit_conversation(ConversationCommit(
                execution_id=event.execution_id,
                scope=scope,
                expected_revision=7,
                response_id="response-" + event.execution_id,
                destination_ref="synthetic",
                public_payload={"message": "must roll back"},
                outcome={"status": "must-roll-back"},
                turn=ConversationTurn("synthetic", "must roll back"),
                claim_tokens=(event_claim, conversation_claim),
            ))

        assert ledger.conversation_revision(scope) == 0
        assert ledger.conversation_history(scope) == ()
        assert ledger.outcome(event.execution_id, scope=scope) is None
        admin = psycopg.connect(os.environ["INCUBIA_MIGRATION_DATABASE_URL"], connect_timeout=10)
        try:
            with admin.cursor() as cursor:
                cursor.execute("SELECT state FROM inbox_events WHERE execution_id=%s::uuid", (event.execution_id,))
                assert cursor.fetchone() == ("PROCESSING",)
                for table in ("turns", "outcomes", "deliveries"):
                    cursor.execute(f"SELECT count(*) FROM {table} WHERE execution_id=%s::uuid", (event.execution_id,))
                    assert cursor.fetchone()[0] == 0, f"failed UoW left a row in {table}"
                cursor.execute(
                    "SELECT count(*) FROM conversations WHERE deployment_id=%s AND tenant_id=%s "
                    "AND conversation_id=%s AND actor_id=%s",
                    (scope.deployment_id, scope.tenant_id, scope.conversation_id, scope.actor_id),
                )
                assert cursor.fetchone()[0] == 0
        finally:
            admin.close()
    finally:
        admin = psycopg.connect(os.environ["INCUBIA_MIGRATION_DATABASE_URL"], connect_timeout=10)
        try:
            with admin.transaction():
                with admin.cursor() as cursor:
                    cursor.execute("DELETE FROM inbox_events WHERE execution_id=%s::uuid", (event.execution_id,))
        finally:
            admin.close()


def test_shared_claims_compete_expire_and_reject_stale_fencing_tokens():
    deployment_id = "e3-h1-claims-test"
    tenant_id = "tenant-" + uuid4().hex
    scope = ExecutionScope(deployment_id, tenant_id, "conversation-" + uuid4().hex, "actor-test")
    key = conversation_claim_key(scope)
    runtime_url = os.environ["DATABASE_URL"]
    owners = ("owner-a-" + uuid4().hex, "owner-b-" + uuid4().hex)

    def acquire(owner_id):
        return PostgresLedger(runtime_url).acquire_claim(
            scope, resource_type="conversation", resource_key=key,
            owner_id=owner_id, lease_seconds=30,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(acquire, owners))
    winners = [token for token in results if token is not None]
    assert len(winners) == 1
    assert PostgresLedger(runtime_url).release_claim(winners[0])

    ledger = PostgresLedger(runtime_url)
    account = "e3-h1-" + uuid4().hex
    event = ledger.reserve_inbox(
        deployment_id, tenant_id, account, "event-" + uuid4().hex,
        {"message": "synthetic"}, channel="test",
    )
    try:
        event_owner, new_owner = "old-" + uuid4().hex, "new-" + uuid4().hex
        old_event_claim = ledger.claim(
            event.execution_id, scope=scope, owner_id=event_owner, lease_seconds=5
        )
        old_conversation_claim = ledger.acquire_claim(
            scope, resource_type="conversation", resource_key=key,
            owner_id=event_owner, lease_seconds=5,
        )
        assert old_event_claim is not None and old_conversation_claim is not None
        assert ledger.claim(
            event.execution_id, scope=scope, owner_id=new_owner, lease_seconds=30
        ) is None
        assert ledger.acquire_claim(
            scope, resource_type="conversation", resource_key=key,
            owner_id=new_owner, lease_seconds=30,
        ) is None

        time.sleep(5.2)
        new_event_claim = ledger.claim(
            event.execution_id, scope=scope, owner_id=new_owner, lease_seconds=30
        )
        new_conversation_claim = ledger.acquire_claim(
            scope, resource_type="conversation", resource_key=key,
            owner_id=new_owner, lease_seconds=30,
        )
        assert new_event_claim is not None and new_conversation_claim is not None
        assert new_event_claim.generation == old_event_claim.generation + 1
        assert new_conversation_claim.generation == old_conversation_claim.generation + 1
        assert ledger.renew_claim(old_event_claim, lease_seconds=30) is False
        assert ledger.renew_claim(old_conversation_claim, lease_seconds=30) is False

        with pytest.raises(ClaimConflict):
            ledger.commit_conversation(ConversationCommit(
                execution_id=event.execution_id,
                scope=scope,
                expected_revision=0,
                response_id="response-" + event.execution_id,
                destination_ref="synthetic",
                public_payload={"message": "stale owner must not commit"},
                outcome={"status": "stale"},
                turn=ConversationTurn("synthetic", "stale"),
                claim_tokens=(old_event_claim, old_conversation_claim),
            ))
        assert ledger.conversation_revision(scope) == 0
        assert ledger.conversation_history(scope) == ()
        assert ledger.outcome(event.execution_id, scope=scope) is None
    finally:
        admin = psycopg.connect(os.environ["INCUBIA_MIGRATION_DATABASE_URL"], connect_timeout=10)
        try:
            with admin.transaction():
                with admin.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM resource_claims WHERE deployment_id=%s AND tenant_id=%s",
                        (deployment_id, tenant_id),
                    )
                    cursor.execute("DELETE FROM inbox_events WHERE execution_id=%s::uuid", (event.execution_id,))
        finally:
            admin.close()


def test_dispatcher_claim_is_global_per_telegram_account_and_fenced():
    account = "e3-h1-dispatcher-" + uuid4().hex
    first = PostgresLedger(os.environ["DATABASE_URL"])
    second = PostgresLedger(os.environ["DATABASE_URL"])
    owner_a = first.acquire_dispatcher_claim(
        channel="telegram", account_ref=account, owner_id="owner-a", lease_seconds=5
    )
    assert owner_a is not None
    assert second.acquire_dispatcher_claim(
        channel="telegram", account_ref=account, owner_id="owner-b", lease_seconds=5
    ) is None
    assert first.renew_dispatcher_claim(owner_a, lease_seconds=5)
    assert first.release_dispatcher_claim(owner_a)
    owner_b = second.acquire_dispatcher_claim(
        channel="telegram", account_ref=account, owner_id="owner-b", lease_seconds=5
    )
    assert owner_b is not None
    assert owner_b.generation == owner_a.generation + 1
    assert first.renew_dispatcher_claim(owner_a, lease_seconds=5) is False
    assert second.release_dispatcher_claim(owner_b)


def test_postgres_ledger_keeps_inbox_uow_and_replay_atomic_under_rls():
    scope = ExecutionScope(
        "e3-h1-uow-test", "tenant-" + uuid4().hex,
        "conversation-" + uuid4().hex, "actor-test",
    )
    account = "e3-h1-" + uuid4().hex
    event_key = "event-" + uuid4().hex
    payload = {"message": "synthetic"}
    ledger = PostgresLedger(os.environ["DATABASE_URL"])
    event = ledger.reserve_inbox(
        scope.deployment_id, scope.tenant_id, account, event_key, payload, channel="test"
    )
    try:
        assert event.is_new
        owner_id = "owner-" + uuid4().hex
        event_claim = ledger.claim(
            event.execution_id, scope=scope, owner_id=owner_id, lease_seconds=60
        )
        conversation_claim = ledger.acquire_claim(
            scope, resource_type="conversation", resource_key=conversation_claim_key(scope),
            owner_id=owner_id, lease_seconds=60,
        )
        assert event_claim is not None and conversation_claim is not None
        next_revision = ledger.commit_conversation(ConversationCommit(
            execution_id=event.execution_id,
            scope=scope,
            expected_revision=0,
            response_id="response-" + event.execution_id,
            destination_ref="synthetic",
            public_payload={"message": "synthetic response"},
            outcome={"status": "completed"},
            turn=ConversationTurn("synthetic", "synthetic response"),
            claim_tokens=(event_claim, conversation_claim),
        ))
        assert next_revision == 1
        assert ledger.conversation_revision(scope) == 1
        assert ledger.conversation_history(scope) == (ConversationTurn("synthetic", "synthetic response"),)
        assert ledger.outcome(event.execution_id, scope=scope) == {"status": "completed"}

        replay = ledger.reserve_inbox(
            scope.deployment_id, scope.tenant_id, account, event_key, payload, channel="test"
        )
        assert replay.is_new is False
        assert replay.request_id == event.request_id
        assert replay.execution_id == event.execution_id
        assert replay.state == "COMPLETED"
        with pytest.raises(IdempotencyConflict):
            ledger.reserve_inbox(
                scope.deployment_id, scope.tenant_id, account, event_key,
                {"message": "different"}, channel="test",
            )
    finally:
        admin = psycopg.connect(os.environ["INCUBIA_MIGRATION_DATABASE_URL"], connect_timeout=10)
        try:
            with admin.transaction():
                with admin.cursor() as cursor:
                    cursor.execute("DELETE FROM deliveries WHERE execution_id=%s::uuid", (event.execution_id,))
                    cursor.execute("DELETE FROM outcomes WHERE execution_id=%s::uuid", (event.execution_id,))
                    cursor.execute("DELETE FROM turns WHERE execution_id=%s::uuid", (event.execution_id,))
                    cursor.execute(
                        "DELETE FROM conversations WHERE deployment_id=%s AND tenant_id=%s "
                        "AND conversation_id=%s AND actor_id=%s",
                        (scope.deployment_id, scope.tenant_id, scope.conversation_id, scope.actor_id),
                    )
                    cursor.execute("DELETE FROM inbox_events WHERE execution_id=%s::uuid", (event.execution_id,))
        finally:
            admin.close()
