"""Product-owned durable inbox/outbox and conversation commit contract."""
from dataclasses import dataclass
from typing import Protocol

from incubia_orchestrator.foundation.contracts.execution import ConversationTurn, ExecutionScope


class IdempotencyConflict(RuntimeError):
    pass


class ScopeConflict(RuntimeError):
    pass


class RevisionConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class InboxReservation:
    request_id: str
    execution_id: str
    state: str
    is_new: bool


@dataclass(frozen=True)
class PendingInboxEvent:
    request_id: str
    execution_id: str
    payload_json: str


@dataclass(frozen=True)
class ConversationCommit:
    execution_id: str
    scope: ExecutionScope
    expected_revision: int
    response_id: str
    destination_ref: str
    public_payload: dict
    outcome: dict
    turn: ConversationTurn


class ConversationLedgerPort(Protocol):
    def reserve_inbox(self, deployment_id: str, tenant_id: str, account: str,
                      event_id: str, payload: dict, *, channel: str = "telegram") -> InboxReservation: ...
    def pending_inbox_events(self, account: str) -> tuple[PendingInboxEvent, ...]: ...
    def claim(self, execution_id: str) -> bool: ...
    def commit_conversation(self, commit: ConversationCommit) -> int: ...
