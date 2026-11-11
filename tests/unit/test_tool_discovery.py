import pytest

from incubia_orchestrator.foundation.contracts.execution import ExecutionScope
from incubia_orchestrator.modules.orchestration.adapters.registry.in_process import InProcessAgentRegistry
from incubia_orchestrator.modules.orchestration.adapters.tools.registry import (
    InProcessToolDiscovery,
    InProcessToolRegistry,
)
from incubia_orchestrator.modules.orchestration.application.tool_selection import NoEligibleTool, select_tool
from incubia_orchestrator.modules.orchestration.domain.descriptor import AgentDescriptor
from incubia_orchestrator.modules.orchestration.domain.tools import (
    ToolAvailability,
    ToolDescriptor,
)


SCOPE = ExecutionScope("deployment", "tenant-a", "conversation", "actor")


def descriptor(**changes):
    values = {
        "tool_id": "business.catalog.lookup",
        "version": "1.0",
        "capabilities": frozenset({"business.catalog.lookup"}),
        "deployment_ids": frozenset({"deployment"}),
        "tenant_ids": frozenset({"tenant-a"}),
        "adapter_key": "catalog.fake",
        "input_schema": {
            "type": "object",
            "required": ["query"],
            "additionalProperties": False,
            "properties": {"query": {"type": "string", "maxLength": 20}},
        },
    }
    values.update(changes)
    return ToolDescriptor(**values)


def test_discovery_filters_disabled_foreign_and_invalid_candidates_and_is_stable():
    registry = InProcessToolRegistry((
        descriptor(version="1.0", priority=1),
        descriptor(version="1.10", priority=1),
        descriptor(version="2.0", priority=0),
        descriptor(tool_id="other", tenant_ids=frozenset({"tenant-b"})),
        descriptor(tool_id="disabled", availability=ToolAvailability.DISABLED),
    ))
    discovery = InProcessToolDiscovery(registry)

    found = discovery.find("business.catalog.lookup", SCOPE, input_data={"query": "shoe"})
    assert [item.tool_version for item in found] == ["1.10", "1.0", "2.0"]
    assert all(item.tool_id != "other" for item in found)
    assert discovery.find("business.catalog.lookup", SCOPE, input_data={"bad": "x"}).empty


def test_selection_is_not_authorization_and_empty_selection_is_safe():
    registry = InProcessToolRegistry((descriptor(),))
    candidate = select_tool(InProcessToolDiscovery(registry).find(
        "business.catalog.lookup", SCOPE, input_data={"query": "shoe"}
    ))
    assert candidate.tool_id == "business.catalog.lookup"
    # Discovery/selection do not make a policy decision.
    assert candidate.credential_profile_ref is None
    with pytest.raises(NoEligibleTool):
        select_tool(InProcessToolDiscovery(registry).find("missing", SCOPE))


def test_tool_registry_does_not_change_existing_agent_registry_contract():
    agents = InProcessAgentRegistry((AgentDescriptor(
        "agent", 1, frozenset({"sales"}), frozenset({"deployment"}),
        frozenset({"tenant-a"}), "sales", 1,
    ),))
    assert agents.find("sales", SCOPE)[0].agent_id == "agent"
