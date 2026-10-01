from dataclasses import dataclass
from enum import StrEnum
from incubia_orchestrator.foundation.contracts.execution import ExecutionScope


class Effect(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True)
class PolicyQuery:
    principal: str
    action: str
    resource: str
    scope: ExecutionScope
    execution_id: str


@dataclass(frozen=True)
class PolicyDecision:
    decision_id: str
    effect: Effect
    reason_codes: tuple[str, ...]
    obligations: tuple[str, ...]
    matched_policies: tuple[str, ...]
    policy_revision: str
