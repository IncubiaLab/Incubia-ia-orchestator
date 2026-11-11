from typing import Protocol

from incubia_orchestrator.modules.conversation.domain.messages import ContextualizedResponse


class ResponseContextPort(Protocol):
    def contextualize(self, request: "ResponseContextRequest") -> ContextualizedResponse: ...


class ResponseContextRequest:
    def __init__(self, response_id: str, request_id: str, execution_id: str, scope, destination_ref: str,
                 text: str, specialty, language: str = "es", reply_to: str | None = None,
                 public_references: tuple[str, ...] = ()):
        self.response_id, self.request_id, self.execution_id, self.scope = response_id, request_id, execution_id, scope
        self.destination_ref, self.text, self.specialty, self.language, self.reply_to = destination_ref, text, specialty, language, reply_to
        self.public_references = public_references
