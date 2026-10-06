from incubia_orchestrator.foundation.contracts.execution import (
    CompletedExecution, ExecutionError, ExecutionOutput, FailedExecution, StartExecutionRequest,
)
from incubia_orchestrator.modules.orchestration.adapters.runtime.langgraph.state import GraphState


def to_state(request: StartExecutionRequest) -> GraphState:
    state = {"text": request.input.content, "history": request.input.history,
             "scope": request.scope, "execution_id": request.execution_id}
    if request.selection is not None:
        state["specialty"] = request.selection
    return state


def to_outcome(request: StartExecutionRequest, state: GraphState):
    if code := state.get("error_code"):
        return FailedExecution(request.request_id, request.execution_id,
                               ExecutionError(code, "Generation unavailable", state.get("specialty")))
    return CompletedExecution(request.request_id, request.execution_id,
                              ExecutionOutput(state["reply"], "policy_denied" if state.get("denied") else "message",
                                              state.get("specialty"), state.get("usage")))
