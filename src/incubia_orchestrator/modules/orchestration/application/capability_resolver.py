from incubia_orchestrator.modules.orchestration.domain.routing import RouteDecision, RouteStatus
from incubia_orchestrator.modules.orchestration.ports.decision_model import DecisionModelPort

_COMMANDS = {"/general": "conversation.assistance", "/ventas": "sales.advice", "/marketing": "marketing.planning"}


class CapabilityResolver:
    def __init__(self, decision_model: DecisionModelPort):
        self._decision_model = decision_model

    def resolve(self, text: str, eligible_capabilities: frozenset[str]) -> RouteDecision:
        command = text.split(maxsplit=1)[0].casefold() if text.strip() else ""
        if (capability := _COMMANDS.get(command)) is not None:
            if capability in eligible_capabilities:
                return RouteDecision(RouteStatus.RESOLVED, capability, 1, ("explicit_command",))
            return RouteDecision(RouteStatus.UNSUPPORTED, None, 1, ("command_not_eligible",))
        decision = self._decision_model.decide(text, eligible_capabilities)
        if decision.status is RouteStatus.RESOLVED and decision.capability not in eligible_capabilities:
            return RouteDecision(RouteStatus.AMBIGUOUS, None, 0, ("ineligible_capability",))
        return decision
