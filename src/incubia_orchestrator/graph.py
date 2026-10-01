"""Grafo mínimo: START -> select -> (general | arquitectura | programacion) -> END.

Todo es placeholder: el selector solo lee `profile` del estado de entrada
(sin reglas ni modelo) y cada perfil devuelve un texto fijo.
"""
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph

PROFILES = ("general", "arquitectura", "programacion")


class State(TypedDict, total=False):
    message: str
    profile: str
    reply: str


def select(state: State) -> Literal["general", "arquitectura", "programacion"]:
    profile = state.get("profile", "general")
    return profile if profile in PROFILES else "general"


def make_profile_node(name: str):
    def node(state: State) -> State:
        return {"profile": name, "reply": f"[placeholder {name}] recibí: {state['message']}"}

    return node


def build_graph():
    builder = StateGraph(State)
    for name in PROFILES:
        builder.add_node(name, make_profile_node(name))
        builder.add_edge(name, END)
    builder.add_conditional_edges(START, select)
    return builder.compile()


if __name__ == "__main__":
    graph = build_graph()
    for profile in (*PROFILES, "inexistente"):
        result = graph.invoke({"message": "hola", "profile": profile})
        print(f"pedido={profile!r:16} -> perfil={result['profile']!r:16} {result['reply']}")
