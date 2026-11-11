"""Caso de uso del chat local: convertir un turno en una ejecución del runtime."""

from uuid import uuid4
from typing import Callable
from incubia_orchestrator.foundation.contracts.execution import (
    ConversationTurn, ExecutionInput, ExecutionOutcome, ExecutionScope, StartExecutionRequest,
)
from incubia_orchestrator.modules.orchestration.ports.workflow_runtime import WorkflowRuntimePort


class HandleMessage:
    """Inicia una ejecución con el scope local y un historial proporcionado por la interfaz."""

    def __init__(self, runtime: WorkflowRuntimePort, scope: ExecutionScope,
                 new_id: Callable[[], str] = lambda: str(uuid4())):
        """Recibe el runtime y un generador de IDs reemplazable en pruebas."""
        self.runtime, self.scope, self.new_id = runtime, scope, new_id

    def __call__(self, text: str, history: tuple[ConversationTurn, ...] = ()) -> ExecutionOutcome:
        """Crea IDs de request y ejecución independientes y devuelve su resultado."""
        request = StartExecutionRequest(self.new_id(), self.new_id(), self.scope,
                                        ExecutionInput(text, history=history))
        return self.runtime.start(request)
