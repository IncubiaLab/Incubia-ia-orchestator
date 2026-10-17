from typing import Protocol

from incubia_orchestrator.modules.audit.domain.audit import AuditEvent


class AuditSinkPort(Protocol):
    def append(self, event: AuditEvent) -> None: ...
