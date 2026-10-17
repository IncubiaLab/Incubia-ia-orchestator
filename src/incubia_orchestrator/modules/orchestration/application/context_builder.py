"""Build bounded inference context without exposing one conversation to another."""
from dataclasses import dataclass
from math import ceil

from incubia_orchestrator.foundation.contracts.execution import ConversationTurn, ExecutionScope
from incubia_orchestrator.modules.conversation.ports.repository import ConversationFact, ConversationRepositoryPort
from incubia_orchestrator.modules.orchestration.domain.profile import SpecialtyProfile
from incubia_orchestrator.modules.knowledge.domain import EvidenceItem


class ContextOverflow(ValueError):
    pass


@dataclass(frozen=True)
class SpecialtyContext:
    profile_id: str
    profile_version: int
    instructions: str
    facts: tuple[ConversationFact, ...]
    missing_required_fields: tuple[str, ...]
    history: tuple[ConversationTurn, ...]
    user_text: str
    estimated_input_tokens: int
    evidence: tuple[EvidenceItem, ...] = ()


def estimate_tokens(text: str) -> int:
    return ceil(len(text.encode("utf-8")) / 3)


class ContextBuilder:
    def __init__(self, repository: ConversationRepositoryPort):
        self._repository = repository

    def build(self, scope: ExecutionScope, profile: SpecialtyProfile, user_text: str,
              evidence: tuple[EvidenceItem, ...] = ()) -> SpecialtyContext:
        snapshot = self._repository.load(scope)
        # Facts are always scoped by the repository; retain the extra guard for adapters.
        facts = tuple(fact for fact in snapshot.facts if fact.scope == scope)
        available = {fact.name for fact in facts}
        missing = tuple(field for field in profile.required_fields if field not in available)
        selected_facts = facts[-profile.budget.max_context_items:]
        history = snapshot.turns[-profile.budget.max_history_pairs:]
        selected_evidence = tuple(item for item in evidence if item.deployment_id == scope.deployment_id)[:5]
        required_text = profile.instructions + user_text
        if estimate_tokens(required_text) > profile.budget.max_input_tokens:
            raise ContextOverflow("Required instructions and current message exceed the context budget")
        # Drop oldest optional context first, retaining complete user/assistant pairs.
        while estimate_tokens(self._render(profile.instructions, selected_facts, history, user_text,
                                           selected_evidence)) > profile.budget.max_input_tokens:
            if selected_evidence:
                selected_evidence = selected_evidence[:-1]
            elif selected_facts:
                selected_facts = selected_facts[1:]
            elif history:
                history = history[1:]
            else:
                raise ContextOverflow("Context does not fit the configured budget")
        rendered = self._render(profile.instructions, selected_facts, history, user_text, selected_evidence)
        return SpecialtyContext(profile.profile_id, profile.profile_version, profile.instructions, selected_facts,
                                missing, history, user_text, estimate_tokens(rendered), selected_evidence)

    @staticmethod
    def _render(instructions: str, facts: tuple[ConversationFact, ...], history: tuple[ConversationTurn, ...],
                text: str, evidence: tuple[EvidenceItem, ...] = ()) -> str:
        return "\n".join((instructions, *(f"{fact.name}: {fact.value}" for fact in facts),
                          *(f"Evidence (untrusted): {item.text}" for item in evidence),
                          *(f"U:{turn.user}\nA:{turn.assistant}" for turn in history), text))
