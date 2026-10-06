"""Versioned, channel-neutral messages owned by the product."""
from dataclasses import asdict, dataclass
from datetime import datetime

from incubia_orchestrator.foundation.contracts.execution import ExecutionScope
from incubia_orchestrator.foundation.contracts.specialty import Specialty

CONTRACT_VERSION = 1


class UnsupportedContractVersion(ValueError):
    """Raised before an unknown wire contract enters the application."""


def _require_version(version: int) -> None:
    if version != CONTRACT_VERSION:
        raise UnsupportedContractVersion(f"Unsupported contract version: {version}")


@dataclass(frozen=True)
class InboundMessage:
    contract_version: int
    channel: str
    channel_account_ref: str
    external_event_id: str
    external_chat_ref: str
    external_sender_ref: str
    text: str
    received_at: datetime

    def __post_init__(self) -> None:
        _require_version(self.contract_version)
        if not all((self.channel, self.channel_account_ref, self.external_event_id,
                    self.external_chat_ref, self.external_sender_ref)):
            raise ValueError("Inbound references must be non-empty")

    def to_dict(self) -> dict:
        data = asdict(self)
        data["received_at"] = self.received_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "InboundMessage":
        return cls(**{**data, "received_at": datetime.fromisoformat(data["received_at"])})


@dataclass(frozen=True)
class ContextualizedResponse:
    contract_version: int
    response_id: str
    request_id: str
    execution_id: str
    scope: ExecutionScope
    destination_ref: str
    text: str
    specialty: Specialty
    language: str = "es"
    public_blocks: tuple[str, ...] = ()
    reply_to: str | None = None

    def __post_init__(self) -> None:
        _require_version(self.contract_version)
        if not all((self.response_id, self.request_id, self.execution_id, self.destination_ref)):
            raise ValueError("Response identifiers and destination must be non-empty")

    def to_dict(self) -> dict:
        data = asdict(self)
        data["specialty"] = self.specialty.value
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "ContextualizedResponse":
        raw = dict(data)
        raw["scope"] = ExecutionScope(**raw["scope"])
        raw["specialty"] = Specialty(raw["specialty"])
        raw["public_blocks"] = tuple(raw.get("public_blocks", ()))
        return cls(**raw)
