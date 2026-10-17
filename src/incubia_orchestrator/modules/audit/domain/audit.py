"""Minimal structured audit events for governed tool execution."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from incubia_orchestrator.foundation.contracts.execution import ExecutionScope


class AuditEventType(StrEnum):
    TOOL_REQUESTED = "tool.requested"
    POLICY_DECISION = "tool.policy_decision"
    TOOL_ATTEMPT = "tool.attempt"
    TOOL_COMPLETED = "tool.completed"


@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    event_type: AuditEventType
    occurred_at: datetime
    tool_call_id: str
    execution_id: str
    scope: ExecutionScope
    tool_id: str
    resource: str = ""
    decision: str | None = None
    attempt: int | None = None
    status: str | None = None
    error_code: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.event_id or not self.tool_call_id or not self.execution_id or not self.tool_id:
            raise ValueError("audit event identifiers are required")
        if self.occurred_at.tzinfo is None:
            raise ValueError("audit event time must be timezone-aware")
        if self.attempt is not None and self.attempt < 1:
            raise ValueError("audit attempt must be positive")

    @classmethod
    def now(cls, **kwargs) -> "AuditEvent":
        return cls(occurred_at=datetime.now(UTC), **kwargs)
