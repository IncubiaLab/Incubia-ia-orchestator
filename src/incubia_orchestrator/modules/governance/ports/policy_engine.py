from typing import Protocol
from incubia_orchestrator.modules.governance.domain.policy import PolicyDecision, PolicyQuery


class PolicyEnginePort(Protocol):
    def evaluate(self, query: PolicyQuery) -> PolicyDecision: ...
