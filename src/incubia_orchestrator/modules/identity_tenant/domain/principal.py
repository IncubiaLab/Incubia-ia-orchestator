from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    ACTOR = "actor"
    OPERATOR = "operator"
    ADMIN = "admin"


@dataclass(frozen=True)
class Principal:
    """Authenticated server-side subject; never constructed from message text."""
    deployment_id: str
    subject_id: str

    def __post_init__(self):
        if not self.deployment_id or not self.subject_id:
            raise ValueError("Principal identifiers are required")


@dataclass(frozen=True)
class Membership:
    deployment_id: str
    tenant_id: str
    subject_id: str
    role: Role
    active: bool = True

    def __post_init__(self):
        if not self.deployment_id or not self.tenant_id or not self.subject_id:
            raise ValueError("Membership identifiers are required")
