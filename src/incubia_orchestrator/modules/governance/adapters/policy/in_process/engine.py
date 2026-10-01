from dataclasses import dataclass
from uuid import uuid4
from incubia_orchestrator.modules.governance.domain.policy import Effect, PolicyDecision, PolicyQuery


@dataclass(frozen=True)
class Authority:
    deployment_id: str
    tenant_id: str
    allowed_actors: frozenset[str]
    enabled_actions: frozenset[str] = frozenset({"llm.generate"})
    revision: str = "local-1"


class InProcessPolicyEngine:
    def __init__(self, authority: Authority):
        self.authority = authority

    def evaluate(self, query: PolicyQuery) -> PolicyDecision:
        a = self.authority
        allowed = (query.scope.deployment_id == a.deployment_id
                   and query.scope.tenant_id == a.tenant_id
                   and query.principal == query.scope.actor_id
                   and query.principal in a.allowed_actors
                   and query.action in a.enabled_actions
                   and query.resource == "configured-llm")
        return PolicyDecision(str(uuid4()), Effect.ALLOW if allowed else Effect.DENY,
                              ("LOCAL_ALLOW",) if allowed else ("OUTSIDE_AUTHORITY",),
                              (), ("local-envelope",), a.revision)
