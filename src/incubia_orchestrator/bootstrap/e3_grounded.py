"""Explicit composition for a scoped E3 Tool READ + Knowledge workflow."""

from collections.abc import Callable, Mapping

from incubia_orchestrator.foundation.contracts.execution import ExecutionScope
from incubia_orchestrator.modules.audit.ports.sink import AuditSinkPort
from incubia_orchestrator.modules.knowledge.ports import RetrievalPort
from incubia_orchestrator.modules.governance.ports.policy_engine import PolicyEnginePort
from incubia_orchestrator.modules.orchestration.adapters.tools.registry import (
    InProcessToolAdapterRegistry, InProcessToolDiscovery, InProcessToolExecutor, InProcessToolRegistry,
)
from incubia_orchestrator.modules.orchestration.application.execute_tool import ExecuteTool
from incubia_orchestrator.modules.orchestration.application.grounded_response import GroundedResponse
from incubia_orchestrator.modules.orchestration.application.grounded_workflow import GroundedWorkflow, ReadRequest
from incubia_orchestrator.modules.orchestration.domain.tools import ToolDescriptor
from incubia_orchestrator.modules.orchestration.ports.tool_executor import ToolAdapterPort, CredentialResolverPort


def compose_grounded_workflow(
    *, retrieval: RetrievalPort,
    descriptors: tuple[ToolDescriptor, ...],
    adapters: Mapping[str, ToolAdapterPort],
    policy: PolicyEnginePort,
    audit: AuditSinkPort,
    read_request: Callable[[str, str, ExecutionScope], ReadRequest | None],
    credentials: CredentialResolverPort | None = None,
    deadline_seconds: float = 10,
    metrics=None,
) -> GroundedWorkflow:
    """Build an opt-in workflow; caller supplies trusted scope and adapters.

    Audit is mandatory because policy/tool decisions must be durable before an
    external READ. Deployment-specific resource and input mapping stays in the
    caller's controlled ``read_request`` implementation.
    """
    if audit is None:
        raise ValueError("A durable audit sink is required")
    registry = InProcessToolRegistry(descriptors)
    executor = InProcessToolExecutor(InProcessToolAdapterRegistry(adapters), credentials)
    tool = ExecuteTool(registry, executor, policy, audit)
    return GroundedWorkflow(GroundedResponse(retrieval, metrics=metrics), InProcessToolDiscovery(registry),
                            tool, read_request, deadline_seconds=deadline_seconds,
                            audit=audit)
