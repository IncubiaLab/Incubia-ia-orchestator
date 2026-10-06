"""Discovery metadata; profiles retain the behavioural instructions."""
from dataclasses import dataclass
from enum import StrEnum


class AgentState(StrEnum):
    ENABLED = "enabled"
    DISABLED = "disabled"


@dataclass(frozen=True)
class AgentDescriptor:
    agent_id: str
    agent_version: int
    capabilities: frozenset[str]
    deployment_ids: frozenset[str]
    tenant_ids: frozenset[str]
    profile_id: str
    profile_version: int
    priority: int = 0
    state: AgentState = AgentState.ENABLED
    execution_mode: str = "sync"
    policy_tags: frozenset[str] = frozenset()

