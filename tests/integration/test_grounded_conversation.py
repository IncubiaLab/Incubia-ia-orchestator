import sqlite3

from incubia_orchestrator.foundation.contracts.execution import ExecutionScope
from incubia_orchestrator.foundation.contracts.specialty import Specialty
from incubia_orchestrator.bootstrap.e3_grounded import compose_grounded_workflow
from incubia_orchestrator.modules.audit.adapters.sqlite import SqliteAuditLog
from incubia_orchestrator.modules.conversation.adapters.persistence.memory import InMemoryConversationRepository
from incubia_orchestrator.modules.governance.adapters.policy.in_process.engine import Authority, InProcessPolicyEngine
from incubia_orchestrator.modules.knowledge.adapters.fake import FakeRetrieval
from incubia_orchestrator.modules.knowledge.domain import EvidenceItem
from incubia_orchestrator.modules.orchestration.adapters.decision.fake import FakeDecisionModel
from incubia_orchestrator.modules.orchestration.adapters.registry.in_process import InProcessAgentRegistry
from incubia_orchestrator.modules.orchestration.adapters.tools.fake import FakeCatalogAdapter
from incubia_orchestrator.modules.orchestration.application.capability_resolver import CapabilityResolver
from incubia_orchestrator.modules.orchestration.application.context_builder import ContextBuilder
from incubia_orchestrator.modules.orchestration.application.grounded_workflow import ReadRequest
from incubia_orchestrator.modules.orchestration.application.use_cases.handle_inbound import HandleInbound
from incubia_orchestrator.modules.orchestration.domain.descriptor import AgentDescriptor
from incubia_orchestrator.modules.orchestration.domain.profile import ContextBudget, SpecialtyProfile
from incubia_orchestrator.modules.orchestration.domain.routing import RouteDecision, RouteStatus
from incubia_orchestrator.modules.orchestration.domain.tools import ToolDescriptor


SCOPE = ExecutionScope("deployment", "tenant", "conversation", "actor")


def _compose(path, *, allow_tool=True):
    capability = "sales.advice"
    profile = SpecialtyProfile("sales", 1, Specialty.VENTAS, "sales", "Responde con evidencia",
                               "simple", frozenset({capability}), frozenset(), (), (), "text",
                               ContextBudget(2000, 256, 2, 5))
    agent = AgentDescriptor("sales", 1, frozenset({capability}), frozenset({"deployment"}),
                            frozenset({"tenant"}), "sales", 1)
    descriptor = ToolDescriptor("business.catalog.lookup", capabilities=frozenset({capability}),
                                deployment_ids=frozenset({"deployment"}), tenant_ids=frozenset({"tenant"}),
                                adapter_key="catalog.fake", input_schema={"type": "object", "required": ["query"],
                                "properties": {"query": {"type": "string", "maxLength": 256}},
                                "additionalProperties": False})
    adapter = FakeCatalogAdapter({"zapatos": [{"name": "Zapato sintético"}]})
    audit = SqliteAuditLog(path)
    policy = InProcessPolicyEngine(Authority("deployment", "tenant", frozenset({"actor"}),
                                             enabled_actions=frozenset({descriptor.tool_id}) if allow_tool else frozenset()))
    retrieval = FakeRetrieval((EvidenceItem("deployment", "manual", "v1", "chunk", "gen",
                                            "Los zapatos tienen garantía.", 0.9,
                                            "https://docs.incubia.org/garantia"),))
    workflow = compose_grounded_workflow(
        retrieval=retrieval, descriptors=(descriptor,), adapters={"catalog.fake": adapter},
        policy=policy, audit=audit,
        read_request=lambda query, capability, scope: ReadRequest(
            {"query": "zapatos"}, f"tenant:{scope.tenant_id}:catalog"),
    )
    inbound = HandleInbound(
        CapabilityResolver(FakeDecisionModel({"zapatos": RouteDecision(RouteStatus.RESOLVED, capability, 1)})),
        InProcessAgentRegistry((agent,)), ContextBuilder(InMemoryConversationRepository()),
        {("sales", 1): profile}, None, new_id=iter(("request-1", "execution-1")).__next__,
        grounded=workflow,
    )
    return inbound, adapter, retrieval


def test_inbound_combines_governed_read_retrieval_and_correlated_audit(tmp_path):
    path = tmp_path / "audit.sqlite3"
    inbound, adapter, retrieval = _compose(path)
    result = inbound("zapatos", SCOPE)
    assert result.execution_id == "execution-1"
    assert "Zapato sintético" in result.output.text
    assert "Los zapatos tienen garantía." in result.output.text
    assert result.output.public_references == ("https://docs.incubia.org/garantia",)
    assert len(adapter.calls) == 1
    assert retrieval.calls[0].scope == SCOPE
    with sqlite3.connect(path) as connection:
        rows = connection.execute("SELECT DISTINCT execution_id FROM audit_events").fetchall()
    assert rows == [(result.execution_id,)]


def test_denied_read_still_uses_scoped_retrieval_without_adapter_io(tmp_path):
    inbound, adapter, retrieval = _compose(tmp_path / "audit.sqlite3", allow_tool=False)
    result = inbound("zapatos", SCOPE)
    assert "Zapato sintético" not in result.output.text
    assert "Los zapatos tienen garantía." in result.output.text
    assert adapter.calls == []
    assert len(retrieval.calls) == 1
