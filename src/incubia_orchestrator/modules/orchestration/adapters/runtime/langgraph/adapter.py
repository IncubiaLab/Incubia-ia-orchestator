"""Adaptación entre contratos de ejecución del producto y el grafo LangGraph."""

from incubia_orchestrator.foundation.contracts.execution import ExecutionError, FailedExecution
from incubia_orchestrator.modules.orchestration.adapters.runtime.langgraph.mapper import to_outcome, to_state


class LangGraphRuntimeAdapter:
    """Mapea requests/resultados y convierte fallos del grafo en errores estables."""

    def __init__(self, graph):
        self._graph = graph

    def start(self, request):
        """Ejecuta el grafo compilado y devuelve un outcome del producto."""
        try:
            return to_outcome(request, self._graph.invoke(to_state(request)))
        except Exception:
            return FailedExecution(request.request_id, request.execution_id,
                                   ExecutionError("RUNTIME_ERROR", "Execution unavailable"))

    def resume(self, request):
        """Devuelve el resultado explícito de reanudación aún no implementada."""
        return FailedExecution(request.request_id, request.execution_id,
                               ExecutionError("RESUME_UNSUPPORTED", "Resume is not supported"))
