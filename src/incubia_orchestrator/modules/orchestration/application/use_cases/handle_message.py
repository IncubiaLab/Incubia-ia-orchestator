from uuid import uuid4
from typing import Callable
from incubia_orchestrator.foundation.contracts.execution import (
    ConversationTurn, ExecutionInput, ExecutionOutcome, ExecutionScope, StartExecutionRequest,
)
from incubia_orchestrator.modules.orchestration.ports.workflow_runtime import WorkflowRuntimePort


class HandleMessage:
    def __init__(self, runtime: WorkflowRuntimePort, scope: ExecutionScope,
                 new_id: Callable[[], str] = lambda: str(uuid4())):
        self.runtime, self.scope, self.new_id = runtime, scope, new_id

    def __call__(self, text: str, history: tuple[ConversationTurn, ...] = ()) -> ExecutionOutcome:
        request = StartExecutionRequest(self.new_id(), self.new_id(), self.scope,
                                        ExecutionInput(text, history=history))
        return self.runtime.start(request)
