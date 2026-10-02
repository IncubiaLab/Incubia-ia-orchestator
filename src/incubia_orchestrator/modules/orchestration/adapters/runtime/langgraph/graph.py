from langgraph.graph import START, END, StateGraph
from incubia_orchestrator.modules.orchestration.adapters.runtime.langgraph.state import GraphState


def build_graph(node, select_node=None):
    builder = StateGraph(GraphState)
    if select_node is not None:
        builder.add_node("select_specialty", select_node)
        builder.add_edge(START, "select_specialty")
        builder.add_edge("select_specialty", "generate_response")
    else:
        builder.add_edge(START, "generate_response")
    builder.add_node("generate_response", node)
    builder.add_edge("generate_response", END)
    return builder.compile()
