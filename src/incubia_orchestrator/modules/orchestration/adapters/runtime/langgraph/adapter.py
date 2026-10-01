from incubia_orchestrator.foundation.contracts.execution import ExecutionError, FailedExecution
from incubia_orchestrator.modules.orchestration.adapters.runtime.langgraph.mapper import to_outcome, to_state


class LangGraphRuntimeAdapter:
    def __init__(self, graph):
        self._graph = graph

    def start(self, request):
        try:
            return to_outcome(request, self._graph.invoke(to_state(request)))
        except Exception:
            return FailedExecution(request.request_id, request.execution_id,
                                   ExecutionError("RUNTIME_ERROR", "Execution unavailable"))

    def resume(self, request):
        return FailedExecution(request.request_id, request.execution_id,
                               ExecutionError("RESUME_UNSUPPORTED", "Resume is not supported"))
