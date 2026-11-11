"""Small local credential resolver used by fixtures and development."""

from collections.abc import Mapping

from incubia_orchestrator.foundation.contracts.execution import ExecutionScope
from incubia_orchestrator.modules.orchestration.ports.tool_executor import (
    CredentialError,
    ResolvedCredential,
)


class InMemoryCredentialResolver:
    """Resolve opaque profile references without putting secrets in descriptors."""

    def __init__(self, credentials: Mapping[str, str | None] | None = None):
        self._credentials = dict(credentials or {})

    def resolve(self, profile_ref: str, scope: ExecutionScope) -> ResolvedCredential | None:
        del scope  # Scope-specific stores can implement the same port later.
        if profile_ref not in self._credentials:
            raise CredentialError("CREDENTIAL_UNAVAILABLE")
        token = self._credentials[profile_ref]
        if not token:
            raise CredentialError("CREDENTIAL_REVOKED")
        return ResolvedCredential(profile_ref, token)
