from incubia_orchestrator.modules.orchestration.domain.tools import (
    ToolCandidateSet,
    ToolDescriptor,
)


class NoEligibleTool(ValueError):
    pass


def select_tool(candidates: ToolCandidateSet) -> ToolDescriptor:
    """Select the stable first candidate; this function does not authorize."""
    if candidates.empty:
        raise NoEligibleTool(f"No eligible tool for {candidates.capability}")
    return candidates[0]
