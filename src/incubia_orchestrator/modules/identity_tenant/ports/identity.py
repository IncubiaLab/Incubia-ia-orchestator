from dataclasses import dataclass
from typing import Protocol

from incubia_orchestrator.modules.identity_tenant.domain.principal import Membership


@dataclass(frozen=True)
class TrustedBinding:
    deployment_id: str
    tenant_id: str
    conversation_id: str
    actor_id: str


class MembershipPort(Protocol):
    def get(self, deployment_id: str, tenant_id: str, subject_id: str) -> Membership | None: ...


class BindingPort(Protocol):
    def resolve(self, *, channel: str, account: str, chat: str, sender: str) -> TrustedBinding | None: ...
