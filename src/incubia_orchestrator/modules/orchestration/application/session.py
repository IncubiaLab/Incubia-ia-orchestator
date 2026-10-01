from incubia_orchestrator.foundation.contracts.execution import CompletedExecution, ConversationTurn, ExecutionOutcome
from incubia_orchestrator.modules.orchestration.application.use_cases.handle_message import HandleMessage


class ConversationSession:
    def __init__(self, handle: HandleMessage, max_turns: int = 10, max_message_chars: int = 8000):
        if max_turns < 0 or max_message_chars < 1:
            raise ValueError("Invalid conversation limits")
        self.handle, self.max_turns, self.max_message_chars = handle, max_turns, max_message_chars
        self.history: list[ConversationTurn] = []

    def send(self, text: str) -> ExecutionOutcome:
        if not text.strip() or len(text) > self.max_message_chars:
            raise ValueError("Message is empty or exceeds configured limit")
        outcome = self.handle(text, tuple(self.history[-self.max_turns:]) if self.max_turns else ())
        if isinstance(outcome, CompletedExecution) and outcome.output.kind == "message" and self.max_turns:
            self.history.append(ConversationTurn(text, outcome.output.text))
            del self.history[:-self.max_turns]
        return outcome
