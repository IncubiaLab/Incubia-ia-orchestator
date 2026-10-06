from incubia_orchestrator.modules.orchestration.domain.routing import RouteDecision


class FakeDecisionModel:
    def __init__(self, decisions: dict[str, RouteDecision] | None = None):
        self.decisions = decisions or {}
        self.calls: list[tuple[str, frozenset[str]]] = []

    def decide(self, text: str, eligible_capabilities: frozenset[str]) -> RouteDecision:
        self.calls.append((text, eligible_capabilities))
        return self.decisions[text]
