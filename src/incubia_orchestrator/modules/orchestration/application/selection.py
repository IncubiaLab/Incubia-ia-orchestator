from incubia_orchestrator.modules.orchestration.domain.descriptor import AgentDescriptor


class NoEligibleAgent(ValueError):
    pass


def select(candidates: tuple[AgentDescriptor, ...]) -> AgentDescriptor:
    if not candidates:
        raise NoEligibleAgent("No eligible agent")
    return sorted(candidates, key=lambda item: (-item.priority, item.agent_id, -item.agent_version))[0]
