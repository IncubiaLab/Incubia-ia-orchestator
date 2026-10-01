from langgraph.graph import START, END, StateGraph
from incubia_orchestrator.modules.orchestration.adapters.runtime.langgraph.state import GraphState


def build_graph(node):
    builder = StateGraph(GraphState)
    builder.add_node("generate_response", node)
    builder.add_edge(START, "generate_response")
    builder.add_edge("generate_response", END)
    return builder.compile()
