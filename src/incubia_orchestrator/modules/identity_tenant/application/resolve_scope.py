from incubia_orchestrator.foundation.contracts.execution import ExecutionScope
from incubia_orchestrator.modules.identity_tenant.domain.principal import Membership, Principal
from incubia_orchestrator.modules.identity_tenant.ports.identity import (
    BindingPort,
    MembershipPort,
    TrustedBinding,
)


class ScopeResolutionDenied(PermissionError):
    """A binding or membership cannot establish a trusted execution scope."""


def resolve_scope(
    principal: Principal,
    binding: TrustedBinding,
    *,
    membership: Membership | None = None,
    membership_active: bool | None = None,
) -> ExecutionScope:
    """Build a scope only when identity, binding and current membership agree.

    ``membership_active`` is retained as a narrow compatibility seam for the
    E3-02 contract tests. Production paths pass the complete ``Membership`` so
    deployment, tenant, subject and role are all checked from server state.
    """
    if membership is not None:
        usable_membership = (
            membership.active
            and membership.deployment_id == binding.deployment_id
            and membership.tenant_id == binding.tenant_id
            and membership.subject_id == principal.subject_id
        )
    else:
        usable_membership = membership_active is True
    if (not usable_membership or principal.deployment_id != binding.deployment_id
            or principal.subject_id != binding.actor_id):
        raise ScopeResolutionDenied("Binding is not usable by this principal")
    return ExecutionScope(binding.deployment_id, binding.tenant_id,
                          binding.conversation_id, binding.actor_id)


class BoundScopeResolver:
    """Resolve a channel identity through the two trusted identity ports."""

    def __init__(self, bindings: BindingPort, memberships: MembershipPort):
        self._bindings = bindings
        self._memberships = memberships

    @staticmethod
    def _binding(value) -> TrustedBinding | None:
        if value is None:
            return None
        if isinstance(value, TrustedBinding):
            return value
        # Transitional adapters may still return the old four-value tuple.
        return TrustedBinding(*value)

    def resolve_binding(self, *, channel: str, account: str, chat: str,
                        sender: str) -> TrustedBinding | None:
        return self._binding(self._bindings.resolve(
            channel=channel, account=account, chat=chat, sender=sender
        ))

    def resolve_scope(self, *, channel: str, account: str, chat: str,
                      sender: str) -> ExecutionScope:
        binding = self.resolve_binding(
            channel=channel, account=account, chat=chat, sender=sender
        )
        if binding is None:
            raise ScopeResolutionDenied("No trusted binding exists")
        # Telegram's binding is the authenticated server-side subject mapping;
        # the membership lookup still decides whether that subject is active.
        principal = Principal(binding.deployment_id, binding.actor_id)
        membership = self._memberships.get(
            binding.deployment_id, binding.tenant_id, binding.actor_id
        )
        return resolve_scope(principal, binding, membership=membership)
