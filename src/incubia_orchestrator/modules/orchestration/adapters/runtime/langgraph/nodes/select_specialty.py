import logging
from incubia_orchestrator.modules.orchestration.application.router import route
from incubia_orchestrator.modules.orchestration.adapters.runtime.langgraph.state import GraphState

LOG = logging.getLogger(__name__)


def select_specialty(state: GraphState) -> GraphState:
    selection = route(state["text"])
    LOG.info("specialty=%s reason=%s", selection.specialty, selection.reason)
    return {"specialty": selection.specialty, "route_reason": selection.reason}
