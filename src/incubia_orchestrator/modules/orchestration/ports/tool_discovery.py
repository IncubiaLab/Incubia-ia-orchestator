from collections.abc import Mapping
from typing import Protocol

from incubia_orchestrator.foundation.contracts.execution import ExecutionScope
from incubia_orchestrator.modules.orchestration.domain.tools import (
    ToolCandidateSet,
    ToolDescriptor,
)


class ToolRegistryPort(Protocol):
    def get(self, tool_id: str, version: str | None = None) -> ToolDescriptor | None: ...

    def all(self) -> tuple[ToolDescriptor, ...]: ...


class ToolDiscoveryPort(Protocol):
    def find(
        self,
        capability: str,
        scope: ExecutionScope,
        *,
        input_data: Mapping | None = None,
    ) -> ToolCandidateSet: ...
