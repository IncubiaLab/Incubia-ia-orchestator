"""In-process tool registry, scoped discovery and adapter dispatch."""

from collections.abc import Iterable, Mapping
from typing import Any

from incubia_orchestrator.foundation.contracts.execution import ExecutionScope
from incubia_orchestrator.modules.audit.ports.sink import AuditSinkPort
from incubia_orchestrator.modules.orchestration.domain.tools import (
    ToolAvailability,
    ToolCandidateSet,
    ToolDescriptor,
    ToolError,
    ToolExecutionResult,
    ToolInvocation,
    ToolStatus,
)
from incubia_orchestrator.modules.orchestration.ports.tool_discovery import ToolRegistryPort
from incubia_orchestrator.modules.orchestration.ports.tool_executor import (
    CredentialError,
    CredentialResolverPort,
    ResolvedCredential,
    ToolAdapterPort,
    ToolExecutorPort,
)


class DuplicateToolError(ValueError):
    pass


class InProcessToolRegistry(ToolRegistryPort):
    def __init__(self, descriptors: Iterable[ToolDescriptor] = ()):
        self._descriptors: dict[tuple[str, str], ToolDescriptor] = {}
        for descriptor in descriptors:
            self.register(descriptor)

    def register(self, descriptor: ToolDescriptor) -> None:
        key = (descriptor.tool_id, descriptor.tool_version)
        if key in self._descriptors:
            raise DuplicateToolError(f"Tool descriptor already registered: {descriptor.tool_id}")
        self._descriptors[key] = descriptor

    def get(self, tool_id: str, version: str | None = None) -> ToolDescriptor | None:
        matches = [
            item for (registered_id, registered_version), item in self._descriptors.items()
            if registered_id == tool_id and (version is None or registered_version == version)
        ]
        if not matches:
            return None
        return sorted(matches, key=_descriptor_sort_key)[0]

    def all(self) -> tuple[ToolDescriptor, ...]:
        return tuple(sorted(self._descriptors.values(), key=_descriptor_sort_key))


class InProcessToolDiscovery:
    """Return only technically eligible descriptors; it never evaluates policy."""

    def __init__(self, registry: ToolRegistryPort):
        self._registry = registry

    def find(
        self,
        capability: str,
        scope: ExecutionScope,
        *,
        input_data: Mapping[str, Any] | None = None,
    ) -> ToolCandidateSet:
        candidates = []
        for descriptor in self._registry.all():
            if descriptor.availability is not ToolAvailability.ENABLED:
                continue
            if capability not in descriptor.capabilities:
                continue
            if not descriptor.allows_scope(scope):
                continue
            if input_data is not None and descriptor.validate_input(input_data):
                continue
            candidates.append(descriptor)
        candidates.sort(key=_descriptor_sort_key)
        return ToolCandidateSet(capability, tuple(candidates))


class InProcessToolAdapterRegistry:
    def __init__(self, adapters: Mapping[str, ToolAdapterPort] | None = None):
        self._adapters = dict(adapters or {})

    def register(self, adapter_key: str, adapter: ToolAdapterPort) -> None:
        if not adapter_key.strip():
            raise ValueError("adapter_key is required")
        if adapter_key in self._adapters:
            raise ValueError(f"Tool adapter already registered: {adapter_key}")
        self._adapters[adapter_key] = adapter

    def get(self, adapter_key: str) -> ToolAdapterPort | None:
        return self._adapters.get(adapter_key)


class InProcessToolExecutor(ToolExecutorPort):
    """Resolve an opaque credential and delegate to the selected adapter."""

    def __init__(
        self,
        adapters: InProcessToolAdapterRegistry,
        credentials: CredentialResolverPort | None = None,
    ):
        self._adapters = adapters
        self._credentials = credentials

    def execute(
        self,
        invocation: ToolInvocation,
        descriptor: ToolDescriptor,
        *,
        audit: AuditSinkPort | None = None,
    ) -> ToolExecutionResult:
        adapter = self._adapters.get(descriptor.adapter_key)
        if adapter is None:
            return _failure(invocation, "TOOL_ADAPTER_UNAVAILABLE", "Tool adapter is unavailable")

        credential: ResolvedCredential | None = None
        if descriptor.credential_profile_ref:
            if self._credentials is None:
                return _failure(invocation, "CREDENTIAL_UNAVAILABLE", "Credential is unavailable")
            try:
                credential = self._credentials.resolve(descriptor.credential_profile_ref, invocation.scope)
            except CredentialError as error:
                return _failure(invocation, error.code, "Credential cannot be used")
            except Exception:
                return _failure(invocation, "CREDENTIAL_UNAVAILABLE", "Credential is unavailable")
            if credential is None:
                return _failure(invocation, "CREDENTIAL_UNAVAILABLE", "Credential is unavailable")

        try:
            return adapter.execute(invocation, descriptor, credential=credential, audit=audit)
        except CredentialError as error:
            return _failure(invocation, error.code, "Credential cannot be used")
        except Exception:
            # Adapter details are deliberately not exposed to the product contract.
            return _failure(invocation, "TOOL_ADAPTER_ERROR", "Tool adapter failed")


def _version_key(version: str) -> tuple:
    parts = []
    for piece in version.replace("-", ".").split("."):
        parts.append((0, int(piece)) if piece.isdigit() else (1, piece))
    return tuple(parts)


def _descriptor_sort_key(descriptor: ToolDescriptor) -> tuple:
    # Highest priority and highest version win; identifiers remain stable ties.
    return (-descriptor.priority, descriptor.tool_id, _version_key_desc(descriptor.tool_version))


def _version_key_desc(version: str) -> tuple:
    return tuple(
        (0, -part[1]) if part[0] == 0 else (1, part[1])
        for part in _version_key(version)
    )


def _failure(invocation: ToolInvocation, code: str, message: str) -> ToolExecutionResult:
    return ToolExecutionResult(
        invocation.tool_call_id,
        invocation.tool_id,
        ToolStatus.FAILED,
        error=ToolError(code, message),
    )
