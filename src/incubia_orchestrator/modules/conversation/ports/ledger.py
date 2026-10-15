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


class ClaimConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class ClaimToken:
    deployment_id: str
    tenant_id: str
    resource_type: str
    resource_key: str
    owner_id: str
    generation: int


def conversation_claim_key(scope: ExecutionScope) -> str:
    return f"{len(scope.conversation_id)}:{scope.conversation_id}{scope.actor_id}"


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
    claim_tokens: tuple[ClaimToken, ...] = ()


class ConversationLedgerPort(Protocol):
    def reserve_inbox(self, deployment_id: str, tenant_id: str, account: str,
                      event_id: str, payload: dict, *, channel: str = "telegram") -> InboxReservation: ...
    def pending_inbox_events(self, account: str) -> tuple[PendingInboxEvent, ...]: ...
    def claim(self, execution_id: str, *, scope: ExecutionScope, owner_id: str,
              lease_seconds: float = 60) -> ClaimToken | None: ...
    def acquire_claim(self, scope: ExecutionScope, *, resource_type: str, resource_key: str,
                      owner_id: str, lease_seconds: float = 60) -> ClaimToken | None: ...
    def acquire_dispatcher_claim(self, *, channel: str, account_ref: str, owner_id: str,
                                 lease_seconds: float = 60) -> ClaimToken | None: ...
    def renew_dispatcher_claim(self, token: ClaimToken, *, lease_seconds: float = 60) -> bool: ...
    def release_dispatcher_claim(self, token: ClaimToken) -> bool: ...
    def commit_conversation(self, commit: ConversationCommit) -> int: ...
