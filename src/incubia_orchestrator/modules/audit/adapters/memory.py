from threading import Lock

from incubia_orchestrator.modules.audit.domain.audit import AuditEvent


class InMemoryAuditLog:
    """Deterministic audit sink for local runs and contract tests."""

    def __init__(self):
        self._events: list[AuditEvent] = []
        self._lock = Lock()

    def append(self, event: AuditEvent) -> None:
        with self._lock:
            self._events.append(event)

    @property
    def events(self) -> tuple[AuditEvent, ...]:
        with self._lock:
            return tuple(self._events)
