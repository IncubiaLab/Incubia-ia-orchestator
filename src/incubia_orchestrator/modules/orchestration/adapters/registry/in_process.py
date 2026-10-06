from incubia_orchestrator.foundation.contracts.execution import ExecutionScope
from incubia_orchestrator.modules.orchestration.domain.descriptor import AgentDescriptor, AgentState


class InProcessAgentRegistry:
    def __init__(self, descriptors: tuple[AgentDescriptor, ...]):
        self._descriptors = descriptors

    def find(self, capability: str, scope: ExecutionScope) -> tuple[AgentDescriptor, ...]:
        return tuple(descriptor for descriptor in self._descriptors
                     if descriptor.state is AgentState.ENABLED and capability in descriptor.capabilities
                     and scope.deployment_id in descriptor.deployment_ids
                     and scope.tenant_id in descriptor.tenant_ids)
