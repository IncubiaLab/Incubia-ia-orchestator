"""Neutral routing result; it deliberately names no agent or model."""
from dataclasses import dataclass
from enum import StrEnum


class RouteStatus(StrEnum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class RouteDecision:
    status: RouteStatus
    capability: str | None
    confidence: float
    signals: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (self.status is RouteStatus.RESOLVED) != (self.capability is not None):
            raise ValueError("A capability is present if and only if routing is resolved")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")

    def to_dict(self) -> dict:
        return {"status": self.status.value, "capability": self.capability,
                "confidence": self.confidence, "signals": list(self.signals)}

    @classmethod
    def from_dict(cls, data: dict) -> "RouteDecision":
        return cls(RouteStatus(data["status"]), data.get("capability"), data["confidence"],
                   tuple(data.get("signals", ())))
