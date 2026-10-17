import pytest

from incubia_orchestrator.foundation.contracts.execution import ExecutionScope
from incubia_orchestrator.modules.conversation.adapters.persistence.sqlite_ledger import SqliteLedger
from incubia_orchestrator.modules.governance.adapters.policy.in_process.engine import (
    Authority,
    InProcessPolicyEngine,
)
from incubia_orchestrator.modules.governance.domain.policy import Effect, PolicyQuery
from incubia_orchestrator.modules.identity_tenant.application.resolve_scope import (
    BoundScopeResolver,
    ScopeResolutionDenied,
    resolve_scope,
)
from incubia_orchestrator.modules.identity_tenant.domain.principal import (
    Membership,
    Principal,
    Role,
)
from incubia_orchestrator.modules.identity_tenant.ports.identity import TrustedBinding
from incubia_orchestrator.modules.orchestration.adapters.registry.in_process import InProcessAgentRegistry
from incubia_orchestrator.modules.orchestration.domain.descriptor import AgentDescriptor


def test_two_tenants_and_two_actors_resolve_only_their_own_scopes(tmp_path):
    ledger = SqliteLedger(tmp_path / "identity.sqlite3")
    for tenant, suffixes in (("tenant-a", ("a1", "a2")), ("tenant-b", ("b1", "b2"))):
        for suffix in suffixes:
            ledger.add_binding(
                channel="telegram", account="bot", chat="chat-" + suffix, sender="sender-" + suffix,
                deployment_id="deployment", tenant_id=tenant,
                conversation_id="conversation-" + suffix, actor_id="actor-" + suffix,
            )
    resolver = BoundScopeResolver(ledger, ledger)

    assert resolver.resolve_scope(
        channel="telegram", account="bot", chat="chat-a1", sender="sender-a1"
    ) == ExecutionScope("deployment", "tenant-a", "conversation-a1", "actor-a1")
    assert resolver.resolve_scope(
        channel="telegram", account="bot", chat="chat-b2", sender="sender-b2"
    ) == ExecutionScope("deployment", "tenant-b", "conversation-b2", "actor-b2")
    with pytest.raises(ScopeResolutionDenied):
        resolve_scope(
            Principal("deployment", "actor-a1"),
            TrustedBinding("deployment", "tenant-b", "conversation-b2", "actor-b2"),
            membership=Membership("deployment", "tenant-b", "actor-b2", Role.ACTOR),
        )
    assert resolver.resolve_binding(
        channel="telegram", account="bot", chat="chat-a1", sender="sender-b2"
    ) is None
    ledger.close()


def test_revocation_is_seen_without_a_stale_membership_cache(tmp_path):
    ledger = SqliteLedger(tmp_path / "revocation.sqlite3")
    ledger.add_binding(
        channel="telegram", account="bot", chat="chat", sender="sender",
        deployment_id="deployment", tenant_id="tenant",
        conversation_id="conversation", actor_id="actor",
    )
    resolver = BoundScopeResolver(ledger, ledger)
    assert resolver.resolve_scope(
        channel="telegram", account="bot", chat="chat", sender="sender"
    ).tenant_id == "tenant"
    assert ledger.revoke_membership(
        deployment_id="deployment", tenant_id="tenant", subject_id="actor"
    )
    with pytest.raises(ScopeResolutionDenied):
        resolver.resolve_scope(
            channel="telegram", account="bot", chat="chat", sender="sender"
        )
    ledger.close()


def test_policy_denies_foreign_resources_and_insufficient_roles(tmp_path):
    ledger = SqliteLedger(tmp_path / "policy.sqlite3")
    ledger.upsert_membership(
        deployment_id="deployment", tenant_id="tenant", subject_id="actor", role=Role.ACTOR
    )
    engine = InProcessPolicyEngine(
        Authority(
            "deployment", "tenant", frozenset({"actor"}),
            enabled_actions=frozenset({"tenant.manage", "llm.generate"}),
        ),
        membership_port=ledger,
    )
    scope = ExecutionScope("deployment", "tenant", "conversation", "actor")
    assert engine.evaluate(PolicyQuery(
        "actor", "tenant.manage", "tenant:tenant:settings", scope, "execution"
    )).effect == Effect.DENY
    assert engine.evaluate(PolicyQuery(
        "actor", "llm.generate", "tenant:other:llm", scope, "execution"
    )).reason_codes == ("RESOURCE_OUTSIDE_TENANT",)

    ledger.upsert_membership(
        deployment_id="deployment", tenant_id="tenant", subject_id="actor", role=Role.ADMIN
    )
    assert engine.evaluate(PolicyQuery(
        "actor", "tenant.manage", "tenant:tenant:settings", scope, "execution"
    )).effect == Effect.ALLOW
    ledger.revoke_membership(
        deployment_id="deployment", tenant_id="tenant", subject_id="actor"
    )
    assert engine.evaluate(PolicyQuery(
        "actor", "tenant.manage", "tenant:tenant:settings", scope, "execution"
    )).reason_codes == ("MEMBERSHIP_INACTIVE",)
    ledger.close()


def test_discovery_fake_is_scoped_by_deployment_and_tenant():
    registry = InProcessAgentRegistry((
        AgentDescriptor("a", 1, frozenset({"sales"}), frozenset({"d"}), frozenset({"tenant-a"}), "sales", 1),
        AgentDescriptor("b", 1, frozenset({"sales"}), frozenset({"d"}), frozenset({"tenant-b"}), "sales", 1),
    ))
    assert tuple(item.agent_id for item in registry.find(
        "sales", ExecutionScope("d", "tenant-a", "conversation", "actor-a")
    )) == ("a",)
    assert tuple(item.agent_id for item in registry.find(
        "sales", ExecutionScope("d", "tenant-b", "conversation", "actor-b")
    )) == ("b",)
