from dataclasses import dataclass
from typing import Protocol
from incubia_orchestrator.foundation.contracts.execution import ConversationTurn


@dataclass(frozen=True)
class GenerationRequest:
    text: str
    history: tuple[ConversationTurn, ...]
    instructions: str
    max_output_tokens: int


@dataclass(frozen=True)
class GenerationResponse:
    text: str


class GenerationFailure(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class LLMPort(Protocol):
    def generate(self, request: GenerationRequest) -> GenerationResponse: ...
