from datetime import datetime, timezone
from pathlib import Path

import pytest

from incubia_orchestrator.foundation.config_e2 import InvalidE2Configuration, load_budgets, load_capabilities, load_profiles
from incubia_orchestrator.foundation.contracts.execution import ExecutionScope
from incubia_orchestrator.foundation.contracts.specialty import Specialty
from incubia_orchestrator.modules.conversation.adapters.persistence.memory import InMemoryConversationRepository
from incubia_orchestrator.modules.conversation.domain.messages import ContextualizedResponse, InboundMessage, UnsupportedContractVersion
from incubia_orchestrator.modules.conversation.ports.repository import ConversationFact, RevisionConflict
from incubia_orchestrator.modules.orchestration.application.capability_resolver import CapabilityResolver
from incubia_orchestrator.modules.orchestration.application.context_builder import ContextBuilder, ContextOverflow
from incubia_orchestrator.modules.orchestration.application.selection import select
from incubia_orchestrator.modules.orchestration.domain.descriptor import AgentDescriptor
from incubia_orchestrator.modules.orchestration.domain.routing import RouteDecision, RouteStatus
from incubia_orchestrator.modules.orchestration.adapters.decision.fake import FakeDecisionModel

ROOT = Path(__file__).resolve().parents[2] / "config" / "e2"
SCOPE = ExecutionScope("d", "t", "c", "a")


def test_contracts_round_trip_and_reject_unknown_version():
    inbound = InboundMessage(1, "fake", "account", "event", "chat", "sender", "hola", datetime.now(timezone.utc))
    assert InboundMessage.from_dict(inbound.to_dict()) == inbound
    response = ContextualizedResponse(1, "response", "request", "execution", SCOPE, "fake:binding", "ok", Specialty.GENERAL)
    assert ContextualizedResponse.from_dict(response.to_dict()) == response
    with pytest.raises(UnsupportedContractVersion):
        InboundMessage(2, "fake", "account", "event", "chat", "sender", "hola", datetime.now(timezone.utc))


def test_config_and_context_are_bounded_and_scoped():
    capabilities = load_capabilities(ROOT)
    profiles = load_profiles(ROOT / "profiles", capabilities)
    assert set(profiles) == set(Specialty)
    assert load_budgets(ROOT / "budgets.yaml", mode="eval-e2")["eval-e2"].usd_cap == 5.0
    repo = InMemoryConversationRepository()
    repo._conversations[SCOPE] = repo.load(SCOPE).__class__(0, (), (ConversationFact("product", "x", "user", SCOPE),))
    context = ContextBuilder(repo).build(SCOPE, profiles[Specialty.VENTAS], "ayuda")
    assert context.facts[0].name == "product"
    assert ContextBuilder(repo).build(ExecutionScope("d", "t", "other", "a"), profiles[Specialty.VENTAS], "ayuda").facts == ()
    with pytest.raises(ContextOverflow):
        ContextBuilder(repo).build(SCOPE, profiles[Specialty.VENTAS], "x" * 10000)
    with pytest.raises(RevisionConflict):
        repo.append_turn(SCOPE, None, 9)  # type: ignore[arg-type]


def test_routing_command_bypasses_model_and_selection_is_stable():
    fake = FakeDecisionModel()
    decision = CapabilityResolver(fake).resolve("/ventas oferta", frozenset({"sales.advice"}))
    assert decision.status is RouteStatus.RESOLVED and fake.calls == []
    assert RouteDecision(RouteStatus.AMBIGUOUS, None, 0).capability is None
    low = AgentDescriptor("z", 1, frozenset({"sales.advice"}), frozenset({"d"}), frozenset({"t"}), "ventas", 1)
    high = AgentDescriptor("a", 1, frozenset({"sales.advice"}), frozenset({"d"}), frozenset({"t"}), "ventas", 1, priority=1)
    assert select((low, high)) == high
