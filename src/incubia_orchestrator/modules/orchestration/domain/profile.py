"""Versioned specialist configuration, independent from model selection."""
from dataclasses import dataclass

from incubia_orchestrator.foundation.contracts.specialty import Specialty


@dataclass(frozen=True)
class ContextBudget:
    max_input_tokens: int
    max_output_tokens: int
    max_history_pairs: int
    max_context_items: int

    def __post_init__(self) -> None:
        if min(self.max_input_tokens, self.max_output_tokens, self.max_history_pairs,
               self.max_context_items) < 0:
            raise ValueError("Context budget values cannot be negative")


@dataclass(frozen=True)
class SpecialtyProfile:
    profile_id: str
    profile_version: int
    specialty: Specialty
    purpose: str
    instructions: str
    style: str
    capabilities: frozenset[str]
    exclusions: frozenset[str]
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...]
    output_contract: str
    budget: ContextBudget

    def __post_init__(self) -> None:
        if not self.profile_id or self.profile_version < 1 or not self.instructions:
            raise ValueError("A profile needs an id, positive version and instructions")
        if not self.capabilities:
            raise ValueError("A profile needs at least one capability")

