from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from incubia_orchestrator.modules.conversation.domain.messages import ContextualizedResponse


class DeliveryStatus(StrEnum):
    CONFIRMED = "confirmed"
    FAILED = "failed"
    UNKNOWN_EFFECT = "unknown_effect"


@dataclass(frozen=True)
class DeliveryResult:
    status: DeliveryStatus
    external_message_id: str | None = None


class ChannelDeliveryPort(Protocol):
    def deliver(self, response: ContextualizedResponse) -> DeliveryResult: ...
