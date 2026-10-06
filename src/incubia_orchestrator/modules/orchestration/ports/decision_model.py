from typing import Protocol

from incubia_orchestrator.modules.orchestration.domain.routing import RouteDecision


class DecisionModelPort(Protocol):
    def decide(self, text: str, eligible_capabilities: frozenset[str]) -> RouteDecision: ...
