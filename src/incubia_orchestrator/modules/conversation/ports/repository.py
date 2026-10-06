"""Canonical conversation state is accessed only through this port."""
from dataclasses import dataclass
from typing import Protocol

from incubia_orchestrator.foundation.contracts.execution import ConversationTurn, ExecutionScope


class RevisionConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class ConversationFact:
    name: str
    value: str
    source: str
    scope: ExecutionScope
    version: str | None = None


@dataclass(frozen=True)
class ConversationSnapshot:
    revision: int
    turns: tuple[ConversationTurn, ...] = ()
    facts: tuple[ConversationFact, ...] = ()


class ConversationRepositoryPort(Protocol):
    def load(self, scope: ExecutionScope) -> ConversationSnapshot: ...
    def append_turn(self, scope: ExecutionScope, turn: ConversationTurn, expected_revision: int) -> int: ...
