from incubia_orchestrator.foundation.contracts.execution import ExecutionScope
from incubia_orchestrator.modules.identity_tenant.domain.principal import Principal
from incubia_orchestrator.modules.identity_tenant.ports.identity import TrustedBinding


class ScopeResolutionDenied(PermissionError):
    """A binding or membership cannot establish a trusted execution scope."""


def resolve_scope(principal: Principal, binding: TrustedBinding, *, membership_active: bool) -> ExecutionScope:
    """Build scope only when authenticated identity and binding agree exactly."""
    if (not membership_active or principal.deployment_id != binding.deployment_id
            or principal.subject_id != binding.actor_id):
        raise ScopeResolutionDenied("Binding is not usable by this principal")
    return ExecutionScope(binding.deployment_id, binding.tenant_id,
                          binding.conversation_id, binding.actor_id)
