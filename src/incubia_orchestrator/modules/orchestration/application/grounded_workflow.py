"""One bounded, scoped Tool READ plus retrieval before an extractive answer."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from incubia_orchestrator.foundation.contracts.execution import ExecutionScope
from incubia_orchestrator.modules.orchestration.application.grounded_response import GroundedResponse, GroundedAnswer
from incubia_orchestrator.modules.orchestration.application.tool_selection import NoEligibleTool, select_tool
from incubia_orchestrator.modules.orchestration.domain.tools import ToolInvocation
from incubia_orchestrator.modules.orchestration.ports.tool_discovery import ToolDiscoveryPort


@dataclass(frozen=True)
class ReadRequest:
    input_data: Mapping[str, Any]
    resource: str


class GroundedWorkflow:
    """The caller supplies trusted scope and a controlled READ input builder."""

    def __init__(self, grounded: GroundedResponse, discovery: ToolDiscoveryPort,
                 execute_tool: Callable[[ToolInvocation], Any],
                 read_request: Callable[[str, str, ExecutionScope], ReadRequest | None],
                 *, deadline_seconds: float = 10):
        if deadline_seconds <= 0:
            raise ValueError("deadline_seconds must be positive")
        self._grounded = grounded
        self._discovery = discovery
        self._execute_tool = execute_tool
        self._read_request = read_request
        self._deadline_seconds = deadline_seconds

    def answer(self, scope: ExecutionScope, query: str, capability: str,
               *, execution_id: str | None = None) -> GroundedAnswer:
        execution_id = execution_id or str(uuid4())
        deadline = datetime.now(UTC) + timedelta(seconds=self._deadline_seconds)
        tool_evidence = ()
        request = self._read_request(query, capability, scope)
        if request is not None:
            try:
                descriptor = select_tool(self._discovery.find(
                    capability, scope, input_data=request.input_data
                ))
            except NoEligibleTool:
                descriptor = None
            if descriptor is not None and datetime.now(UTC) < deadline:
                invocation = ToolInvocation(
                    str(uuid4()), execution_id, scope, descriptor.tool_id,
                    request.input_data, request.resource,
                    deadline_seconds=max(0.001, (deadline - datetime.now(UTC)).total_seconds()),
                    input_schema_version=descriptor.input_schema_version,
                    tool_version=descriptor.tool_version,
                )
                # ExecuteTool is the PEP. Audit failures propagate before adapter I/O.
                tool_evidence = GroundedResponse.read_evidence(self._execute_tool, invocation)
        return self._grounded.answer(scope, query, capability,
                                     deadline=deadline, tool_evidence=tool_evidence)
