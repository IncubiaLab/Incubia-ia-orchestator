from dataclasses import dataclass, field
from collections.abc import Mapping
from uuid import uuid4
from incubia_orchestrator.modules.governance.domain.policy import Effect, PolicyDecision, PolicyQuery
from incubia_orchestrator.modules.identity_tenant.domain.principal import (
    Role,
    role_at_least,
)
from incubia_orchestrator.modules.identity_tenant.ports.identity import MembershipPort


DEFAULT_MINIMUM_ROLES: Mapping[str, Role] = {
    "tenant.bind": Role.OPERATOR,
    "tenant.manage": Role.ADMIN,
}


@dataclass(frozen=True)
class Authority:
    deployment_id: str
    tenant_id: str
    allowed_actors: frozenset[str]
    enabled_actions: frozenset[str] = frozenset({"llm.generate"})
    revision: str = "local-1"
    actor_roles: Mapping[str, Role] = field(default_factory=dict)
    minimum_roles: Mapping[str, Role] = field(default_factory=lambda: dict(DEFAULT_MINIMUM_ROLES))


class InProcessPolicyEngine:
    def __init__(self, authority: Authority, membership_port: MembershipPort | None = None):
        self.authority = authority
        self.membership_port = membership_port

    @staticmethod
    def _decision(effect: Effect, reason: str, revision: str) -> PolicyDecision:
        return PolicyDecision(
            str(uuid4()), effect, (reason,), (), ("local-envelope",), revision
        )

    def evaluate(self, query: PolicyQuery) -> PolicyDecision:
        a = self.authority
        if query.scope.deployment_id != a.deployment_id or query.scope.tenant_id != a.tenant_id:
            return self._decision(Effect.DENY, "OUTSIDE_AUTHORITY", a.revision)
        if query.principal != query.scope.actor_id or query.principal not in a.allowed_actors:
            return self._decision(Effect.DENY, "SUBJECT_NOT_AUTHORIZED", a.revision)
        if query.action not in a.enabled_actions:
            return self._decision(Effect.DENY, "ACTION_DISABLED", a.revision)
        if not query.resource:
            return self._decision(Effect.DENY, "RESOURCE_REQUIRED", a.revision)

        role = query.role or a.actor_roles.get(query.principal, Role.ACTOR)
        if self.membership_port is not None:
            try:
                membership = self.membership_port.get(
                    a.deployment_id, a.tenant_id, query.principal
                )
            except Exception:
                return self._decision(Effect.INDETERMINATE, "MEMBERSHIP_UNAVAILABLE", a.revision)
            if membership is None or not membership.active:
                return self._decision(Effect.DENY, "MEMBERSHIP_INACTIVE", a.revision)
            if (membership.deployment_id != query.scope.deployment_id
                    or membership.tenant_id != query.scope.tenant_id):
                return self._decision(Effect.DENY, "MEMBERSHIP_SCOPE_MISMATCH", a.revision)
            role = membership.role

        minimum_role = a.minimum_roles.get(query.action, Role.ACTOR)
        if not role_at_least(role, minimum_role):
            return self._decision(Effect.DENY, "ROLE_INSUFFICIENT", a.revision)

        return self._decision(Effect.ALLOW, "LOCAL_ALLOW", a.revision)
