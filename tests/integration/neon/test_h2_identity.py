"""Opt-in PostgreSQL/RLS campaign for E3-2 identity isolation."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
import pytest

from incubia_orchestrator.modules.conversation.adapters.persistence.postgres import PostgresLedger
from incubia_orchestrator.modules.governance.adapters.policy.in_process.engine import (
    Authority,
    InProcessPolicyEngine,
)
from incubia_orchestrator.modules.governance.domain.policy import Effect, PolicyQuery
from incubia_orchestrator.modules.identity_tenant.application.resolve_scope import (
    BoundScopeResolver,
    ScopeResolutionDenied,
)


pytestmark = pytest.mark.neon
ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = sorted((ROOT / "migrations/postgres").glob("[0-9][0-9][0-9]_*.sql"))


def _guard_campaign() -> None:
    if os.getenv("INCUBIA_E3_NEON_TESTS") != "1":
        pytest.skip("E3-2 Neon campaign requires explicit opt-in")
    if os.getenv("INCUBIA_E3_NEON_BRANCH") != "e3-h1-synthetic":
        pytest.skip("E3-2 Neon campaign requires the synthetic H1 branch")
    runtime = urlsplit(os.getenv("DATABASE_URL", ""))
    migrator = urlsplit(os.getenv("INCUBIA_MIGRATION_DATABASE_URL", ""))
    if not runtime.hostname or not runtime.hostname.endswith(".neon.tech"):
        pytest.skip("E3-2 runtime URL is not a Neon host")
    if not migrator.hostname or not migrator.hostname.endswith(".neon.tech"):
        pytest.skip("E3-2 migrator URL is not a Neon host")


@pytest.fixture(scope="module", autouse=True)
def h2_schema():
    _guard_campaign()
    ledger = PostgresLedger(os.environ["INCUBIA_MIGRATION_DATABASE_URL"])
    try:
        for migration in MIGRATIONS:
            ledger.migrate(migration)
    except Exception as exc:
        pytest.fail(f"E3-2 Neon migrations failed ({type(exc).__name__})", pytrace=False)


def test_two_tenants_two_actors_rls_pool_reuse_and_revocation():
    _guard_campaign()
    deployment = "e3-h2-" + uuid4().hex[:12]
    tenant_a = "tenant-a-" + uuid4().hex[:12]
    tenant_b = "tenant-b-" + uuid4().hex[:12]
    actors = {
        tenant_a: ("actor-a1-" + uuid4().hex[:8], "actor-a2-" + uuid4().hex[:8]),
        tenant_b: ("actor-b1-" + uuid4().hex[:8], "actor-b2-" + uuid4().hex[:8]),
    }
    account = "e3-h2-account-" + uuid4().hex[:12]
    migration_url = os.environ["INCUBIA_MIGRATION_DATABASE_URL"]
    runtime_url = os.environ["DATABASE_URL"]
    admin = psycopg.connect(migration_url, connect_timeout=10, sslmode="require")

    try:
        with admin.transaction():
            with admin.cursor() as cursor:
                for tenant, tenant_actors in actors.items():
                    for actor in tenant_actors:
                        cursor.execute(
                            "INSERT INTO memberships "
                            "(deployment_id, tenant_id, subject_id, role) "
                            "VALUES (%s, %s, %s, %s)",
                            (deployment, tenant, actor, "actor"),
                        )
                        cursor.execute(
                            "INSERT INTO bindings "
                            "(channel, channel_account_ref, external_chat_ref, external_sender_ref, "
                            "deployment_id, tenant_id, conversation_id, actor_id) "
                            "VALUES ('telegram', %s, %s, %s, %s, %s, %s, %s)",
                            (
                                account,
                                f"chat-{actor}",
                                f"sender-{actor}",
                                deployment,
                                tenant,
                                f"conversation-{actor}",
                                actor,
                            ),
                        )

        runtime = PostgresLedger(runtime_url)
        resolver = BoundScopeResolver(runtime, runtime)
        scope_a1 = resolver.resolve_scope(
            channel="telegram", account=account,
            chat=f"chat-{actors[tenant_a][0]}", sender=f"sender-{actors[tenant_a][0]}",
        )
        scope_a2 = resolver.resolve_scope(
            channel="telegram", account=account,
            chat=f"chat-{actors[tenant_a][1]}", sender=f"sender-{actors[tenant_a][1]}",
        )
        scope_b1 = resolver.resolve_scope(
            channel="telegram", account=account,
            chat=f"chat-{actors[tenant_b][0]}", sender=f"sender-{actors[tenant_b][0]}",
        )
        scope_b2 = resolver.resolve_scope(
            channel="telegram", account=account,
            chat=f"chat-{actors[tenant_b][1]}", sender=f"sender-{actors[tenant_b][1]}",
        )
        assert (scope_a1.tenant_id, scope_a1.actor_id) == (tenant_a, actors[tenant_a][0])
        assert (scope_a2.tenant_id, scope_a2.actor_id) == (tenant_a, actors[tenant_a][1])
        assert (scope_b1.tenant_id, scope_b1.actor_id) == (tenant_b, actors[tenant_b][0])
        assert (scope_b2.tenant_id, scope_b2.actor_id) == (tenant_b, actors[tenant_b][1])
        assert resolver.resolve_binding(
            channel="telegram", account=account,
            chat="chat-does-not-exist", sender="sender-does-not-exist",
        ) is None

        assert runtime.get(deployment, tenant_a, actors[tenant_a][0]).active is True
        assert runtime.get(deployment, tenant_a, actors[tenant_b][0]) is None
        policy = InProcessPolicyEngine(
            Authority(
                deployment,
                tenant_a,
                frozenset({actors[tenant_a][0], actors[tenant_a][1]}),
                enabled_actions=frozenset({"tenant.manage", "llm.generate"}),
            ),
            membership_port=runtime,
        )
        assert policy.evaluate(PolicyQuery(
            actors[tenant_a][0], "llm.generate", f"tenant:{tenant_a}:llm",
            scope_a1, "e3-h2-policy",
        )).effect == Effect.ALLOW
        assert policy.evaluate(PolicyQuery(
            actors[tenant_a][0], "llm.generate", f"tenant:{tenant_b}:llm",
            scope_a1, "e3-h2-policy",
        )).reason_codes == ("RESOURCE_OUTSIDE_TENANT",)
        assert policy.evaluate(PolicyQuery(
            actors[tenant_a][0], "tenant.manage", f"tenant:{tenant_a}:settings",
            scope_a1, "e3-h2-policy",
        )).reason_codes == ("ROLE_INSUFFICIENT",)

        # Transaction-local context must not leak when the same pooled backend
        # connection is reused for another request or returned unscoped.
        with psycopg.connect(runtime_url, connect_timeout=10, sslmode="require") as pooled:
            with pooled.transaction():
                with pooled.cursor() as cursor:
                    cursor.execute(
                        "SELECT set_config('app.deployment_id', %s, true), "
                        "set_config('app.tenant_id', %s, true)",
                        (deployment, tenant_a),
                    )
                    cursor.execute("SELECT count(*) FROM memberships")
                    assert cursor.fetchone()[0] == 2
            with pooled.transaction():
                with pooled.cursor() as cursor:
                    cursor.execute("SELECT count(*) FROM memberships")
                    assert cursor.fetchone()[0] == 0
            with pooled.transaction():
                with pooled.cursor() as cursor:
                    cursor.execute(
                        "SELECT set_config('app.deployment_id', %s, true), "
                        "set_config('app.tenant_id', %s, true)",
                        (deployment, tenant_b),
                    )
                    cursor.execute("SELECT count(*) FROM memberships")
                    assert cursor.fetchone()[0] == 2
            with pooled.transaction():
                with pooled.cursor() as cursor:
                    cursor.execute("SELECT count(*) FROM memberships")
                    assert cursor.fetchone()[0] == 0

        with admin.transaction():
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE memberships SET active=false WHERE deployment_id=%s "
                    "AND tenant_id=%s AND subject_id=%s",
                    (deployment, tenant_a, actors[tenant_a][0]),
                )
        with pytest.raises(ScopeResolutionDenied):
            resolver.resolve_scope(
                channel="telegram", account=account,
                chat=f"chat-{actors[tenant_a][0]}",
                sender=f"sender-{actors[tenant_a][0]}",
            )
        assert runtime.get(deployment, tenant_a, actors[tenant_a][0]).active is False
    finally:
        try:
            with admin.transaction():
                with admin.cursor() as cursor:
                    cursor.execute("DELETE FROM bindings WHERE deployment_id=%s", (deployment,))
                    cursor.execute("DELETE FROM memberships WHERE deployment_id=%s", (deployment,))
        finally:
            admin.close()
