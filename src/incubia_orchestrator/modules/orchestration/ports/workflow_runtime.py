from typing import Protocol
from incubia_orchestrator.foundation.contracts.execution import (
    StartExecutionRequest, ResumeExecutionRequest, ExecutionOutcome,
)


class WorkflowRuntimePort(Protocol):
    def start(self, request: StartExecutionRequest) -> ExecutionOutcome: ...
    def resume(self, request: ResumeExecutionRequest) -> ExecutionOutcome: ...
