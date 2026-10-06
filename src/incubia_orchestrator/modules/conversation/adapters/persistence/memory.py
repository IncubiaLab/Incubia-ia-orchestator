"""In-memory adapter used by local CLI and tests, never shared across scopes."""
from incubia_orchestrator.foundation.contracts.execution import ConversationTurn, ExecutionScope
from incubia_orchestrator.modules.conversation.ports.repository import ConversationSnapshot, RevisionConflict


class InMemoryConversationRepository:
    def __init__(self):
        self._conversations: dict[ExecutionScope, ConversationSnapshot] = {}

    def load(self, scope: ExecutionScope) -> ConversationSnapshot:
        return self._conversations.get(scope, ConversationSnapshot(0))

    def append_turn(self, scope: ExecutionScope, turn: ConversationTurn, expected_revision: int) -> int:
        snapshot = self.load(scope)
        if snapshot.revision != expected_revision:
            raise RevisionConflict("Conversation revision changed")
        revision = snapshot.revision + 1
        self._conversations[scope] = ConversationSnapshot(revision, snapshot.turns + (turn,), snapshot.facts)
        return revision
