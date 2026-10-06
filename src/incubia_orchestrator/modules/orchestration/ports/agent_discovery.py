from typing import Protocol

from incubia_orchestrator.foundation.contracts.execution import ExecutionScope
from incubia_orchestrator.modules.orchestration.domain.descriptor import AgentDescriptor


class AgentDiscoveryPort(Protocol):
    def find(self, capability: str, scope: ExecutionScope) -> tuple[AgentDescriptor, ...]: ...
