"""PEP for tool execution.

Discovery and descriptors identify a candidate.  This use case is the final
enforcement point: it validates the invocation and asks policy immediately
before delegating to an adapter.
"""

from uuid import uuid4

from incubia_orchestrator.modules.audit.domain.audit import AuditEvent, AuditEventType
from incubia_orchestrator.modules.audit.ports.sink import AuditSinkPort
from incubia_orchestrator.modules.governance.domain.policy import Effect, PolicyQuery
from incubia_orchestrator.modules.governance.ports.policy_engine import PolicyEnginePort
from incubia_orchestrator.modules.orchestration.domain.tools import (
    ToolDescriptor,
    ToolError,
    ToolExecutionResult,
    ToolInvocation,
    ToolOperationType,
    ToolStatus,
    ToolAvailability,
)
from incubia_orchestrator.modules.orchestration.ports.tool_discovery import ToolRegistryPort
from incubia_orchestrator.modules.orchestration.ports.tool_executor import ToolExecutorPort


class ExecuteTool:
    def __init__(
        self,
        registry: ToolRegistryPort,
        executor: ToolExecutorPort,
        policy: PolicyEnginePort,
        audit: AuditSinkPort | None = None,
    ):
        self._registry = registry
        self._executor = executor
        self._policy = policy
        self._audit = audit

    def __call__(self, invocation: ToolInvocation) -> ToolExecutionResult:
        descriptor = self._registry.get(invocation.tool_id, invocation.tool_version)
        self._record(
            AuditEventType.TOOL_REQUESTED,
            invocation,
            tool_id=invocation.tool_id,
            metadata={"descriptor_found": descriptor is not None},
        )
        if descriptor is None:
            return self._finish(invocation, _failure(invocation, "TOOL_NOT_FOUND", "Tool is not registered"))

        validation_error = self._validate(invocation, descriptor)
        if validation_error is not None:
            return self._finish(invocation, validation_error)

        try:
            decision = self._policy.evaluate(PolicyQuery(
                principal=invocation.scope.actor_id,
                action=descriptor.action(),
                resource=invocation.resource,
                scope=invocation.scope,
                execution_id=invocation.execution_id,
            ))
        except Exception:
            self._record(
                AuditEventType.POLICY_DECISION,
                invocation,
                tool_id=descriptor.tool_id,
                decision=Effect.INDETERMINATE.value,
                error_code="POLICY_UNAVAILABLE",
            )
            return self._finish(invocation, _failure(invocation, "POLICY_UNAVAILABLE", "Policy is unavailable"))

        self._record(
            AuditEventType.POLICY_DECISION,
            invocation,
            tool_id=descriptor.tool_id,
            decision=decision.effect.value,
            metadata={"policy_revision": decision.policy_revision},
        )
        if decision.effect is not Effect.ALLOW:
            code, message = {
                Effect.DENY: ("POLICY_DENIED", "Tool execution was denied"),
                Effect.REQUIRE_APPROVAL: ("APPROVAL_REQUIRED", "Tool execution requires approval"),
                Effect.INDETERMINATE: ("POLICY_UNAVAILABLE", "Policy could not be evaluated"),
            }[decision.effect]
            status = ToolStatus.DENIED if decision.effect is not Effect.INDETERMINATE else ToolStatus.FAILED
            return self._finish(invocation, ToolExecutionResult(
                invocation.tool_call_id,
                invocation.tool_id,
                status,
                error=ToolError(code, message),
            ))

        try:
            result = self._executor.execute(invocation, descriptor, audit=self._audit)
        except Exception:
            result = _failure(invocation, "TOOL_EXECUTION_ERROR", "Tool execution failed")
        return self._finish(invocation, result)

    @staticmethod
    def _validate(invocation: ToolInvocation, descriptor: ToolDescriptor) -> ToolExecutionResult | None:
        if descriptor.availability is not ToolAvailability.ENABLED:
            return _denied(invocation, "TOOL_UNAVAILABLE", "Tool is not available")
        if not descriptor.allows_scope(invocation.scope):
            return _denied(invocation, "TOOL_SCOPE_DENIED", "Tool is outside the execution scope")
        if invocation.input_schema_version != descriptor.input_schema_version:
            return _denied(invocation, "INVALID_INPUT_VERSION", "Tool input version is unsupported")
        if descriptor.operation_type is not ToolOperationType.READ:
            return _denied(invocation, "TOOL_OPERATION_DISABLED", "Only READ tools are enabled")
        if not invocation.resource.strip():
            return _denied(invocation, "RESOURCE_REQUIRED", "A tool resource is required")
        problems = descriptor.validate_input(invocation.input_data)
        if problems:
            return _denied(invocation, "INVALID_INPUT", "Tool input is invalid")
        return None

    def _finish(self, invocation: ToolInvocation, result: ToolExecutionResult) -> ToolExecutionResult:
        self._record(
            AuditEventType.TOOL_COMPLETED,
            invocation,
            tool_id=result.tool_id,
            status=result.status.value,
            error_code=result.error.code if result.error else None,
            metadata={"attempts": result.attempts, "source": result.source},
        )
        return result

    def _record(self, event_type: AuditEventType, invocation: ToolInvocation, *, tool_id: str,
                decision: str | None = None, attempt: int | None = None,
                status: str | None = None, error_code: str | None = None,
                metadata: dict | None = None) -> None:
        if self._audit is None:
            return
        self._audit.append(AuditEvent.now(
            event_id=str(uuid4()),
            event_type=event_type,
            tool_call_id=invocation.tool_call_id,
            execution_id=invocation.execution_id,
            scope=invocation.scope,
            tool_id=tool_id,
            resource=invocation.resource[:256],
            decision=decision,
            attempt=attempt,
            status=status,
            error_code=error_code,
            metadata=metadata or {},
        ))


def _failure(invocation: ToolInvocation, code: str, message: str) -> ToolExecutionResult:
    return ToolExecutionResult(
        invocation.tool_call_id,
        invocation.tool_id,
        ToolStatus.FAILED,
        error=ToolError(code, message),
    )


def _denied(invocation: ToolInvocation, code: str, message: str) -> ToolExecutionResult:
    return ToolExecutionResult(
        invocation.tool_call_id,
        invocation.tool_id,
        ToolStatus.DENIED,
        error=ToolError(code, message),
    )
