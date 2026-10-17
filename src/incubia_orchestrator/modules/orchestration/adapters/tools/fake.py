from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import uuid4

from incubia_orchestrator.modules.audit.domain.audit import AuditEvent, AuditEventType
from incubia_orchestrator.modules.audit.ports.sink import AuditSinkPort
from incubia_orchestrator.modules.orchestration.domain.tools import (
    ToolDescriptor,
    ToolError,
    ToolExecutionResult,
    ToolInvocation,
    ToolStatus,
)
from incubia_orchestrator.modules.orchestration.ports.tool_executor import (
    ResolvedCredential,
    ToolAdapterPort,
)


class FakeCatalogAdapter(ToolAdapterPort):
    """Deterministic catalog adapter; it performs no I/O."""

    def __init__(self, items: Mapping[str, list[Mapping]] | None = None):
        self._items = {key: [dict(item) for item in value] for key, value in (items or {}).items()}
        self.calls: list[ToolInvocation] = []

    def execute(self, invocation, descriptor, *, credential: ResolvedCredential | None,
                audit: AuditSinkPort | None = None) -> ToolExecutionResult:
        del credential
        self.calls.append(invocation)
        _attempt(audit, invocation, descriptor, 1, "fake")
        query = invocation.input_data.get("query") or invocation.input_data.get("product_ref")
        items = self._items.get(str(query), [])
        return ToolExecutionResult(
            invocation.tool_call_id,
            descriptor.tool_id,
            ToolStatus.SUCCESS,
            output={
                "items": items,
                "source": "fake-catalog",
                "version": descriptor.tool_version,
                "fetched_at": datetime.now(UTC).isoformat(),
            },
            attempts=1,
            source="fake-catalog",
        )


def _attempt(audit, invocation, descriptor, attempt: int, source: str) -> None:
    if audit is None:
        return
    audit.append(AuditEvent.now(
        event_id=str(uuid4()),
        event_type=AuditEventType.TOOL_ATTEMPT,
        tool_call_id=invocation.tool_call_id,
        execution_id=invocation.execution_id,
        scope=invocation.scope,
        tool_id=descriptor.tool_id,
        resource=invocation.resource[:256],
        attempt=attempt,
        metadata={"adapter": source},
    ))
