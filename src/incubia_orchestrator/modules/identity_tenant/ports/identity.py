from dataclasses import dataclass
from typing import Protocol

from incubia_orchestrator.modules.identity_tenant.domain.principal import Membership


@dataclass(frozen=True)
class TrustedBinding:
    deployment_id: str
    tenant_id: str
    conversation_id: str
    actor_id: str

    def __post_init__(self):
        if not all((self.deployment_id, self.tenant_id, self.conversation_id, self.actor_id)):
            raise ValueError("Trusted binding identifiers are required")


class MembershipPort(Protocol):
    def get(self, deployment_id: str, tenant_id: str, subject_id: str) -> Membership | None: ...


class BindingPort(Protocol):
    def resolve(self, *, channel: str, account: str, chat: str, sender: str) -> TrustedBinding | None: ...
