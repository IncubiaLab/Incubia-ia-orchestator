from typing import Protocol

from incubia_orchestrator.foundation.contracts.execution import ExecutionScope
from incubia_orchestrator.modules.audit.domain.audit import AuditEvent
from incubia_orchestrator.modules.audit.ports.sink import AuditSinkPort
from incubia_orchestrator.modules.orchestration.domain.tools import (
    ToolDescriptor,
    ToolExecutionResult,
    ToolInvocation,
)


class CredentialError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class ResolvedCredential:
    """Short-lived credential material; never part of a descriptor."""

    def __init__(self, profile_ref: str, token: str):
        if not profile_ref or not token:
            raise ValueError("credential profile and token are required")
        self.profile_ref = profile_ref
        self.token = token


class CredentialResolverPort(Protocol):
    def resolve(self, profile_ref: str, scope: ExecutionScope) -> ResolvedCredential | None: ...


class ToolAdapterPort(Protocol):
    def execute(
        self,
        invocation: ToolInvocation,
        descriptor: ToolDescriptor,
        *,
        credential: ResolvedCredential | None,
        audit: AuditSinkPort | None = None,
    ) -> ToolExecutionResult: ...


class ToolExecutorPort(Protocol):
    def execute(
        self,
        invocation: ToolInvocation,
        descriptor: ToolDescriptor,
        *,
        audit: AuditSinkPort | None = None,
    ) -> ToolExecutionResult: ...
