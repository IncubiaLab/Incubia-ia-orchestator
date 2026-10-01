from typing import TypedDict
from incubia_orchestrator.foundation.contracts.execution import ConversationTurn, ExecutionScope


class GraphState(TypedDict, total=False):
    text: str
    history: tuple[ConversationTurn, ...]
    scope: ExecutionScope
    execution_id: str
    reply: str
    denied: bool
    error_code: str
