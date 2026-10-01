from incubia_orchestrator.foundation.contracts.execution import (
    CompletedExecution, ExecutionError, ExecutionOutput, FailedExecution, StartExecutionRequest,
)
from incubia_orchestrator.modules.orchestration.adapters.runtime.langgraph.state import GraphState


def to_state(request: StartExecutionRequest) -> GraphState:
    return {"text": request.input.content, "history": request.input.history,
            "scope": request.scope, "execution_id": request.execution_id}


def to_outcome(request: StartExecutionRequest, state: GraphState):
    if code := state.get("error_code"):
        return FailedExecution(request.request_id, request.execution_id,
                               ExecutionError(code, "Generation unavailable"))
    return CompletedExecution(request.request_id, request.execution_id,
                              ExecutionOutput(state["reply"], "policy_denied" if state.get("denied") else "message"))
