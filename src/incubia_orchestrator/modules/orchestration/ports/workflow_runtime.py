"""Contrato de ejecución que mantiene Application independiente de LangGraph."""

from typing import Protocol
from incubia_orchestrator.foundation.contracts.execution import (
    StartExecutionRequest, ResumeExecutionRequest, ExecutionOutcome,
)


class WorkflowRuntimePort(Protocol):
    """Inicia o reanuda ejecuciones mediante tipos propios del producto."""

    def start(self, request: StartExecutionRequest) -> ExecutionOutcome: ...
    def resume(self, request: ResumeExecutionRequest) -> ExecutionOutcome: ...
