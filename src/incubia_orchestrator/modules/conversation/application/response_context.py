from incubia_orchestrator.modules.conversation.domain.messages import CONTRACT_VERSION, ContextualizedResponse
from incubia_orchestrator.modules.conversation.ports.response_context import ResponseContextRequest


class InProcessResponseContext:
    """The public mapper intentionally receives no inference prompt or policy decision."""
    def contextualize(self, request: ResponseContextRequest) -> ContextualizedResponse:
        return ContextualizedResponse(CONTRACT_VERSION, request.response_id, request.request_id,
                                      request.execution_id, request.scope, request.destination_ref,
                                      request.text, request.specialty, request.language, (), request.reply_to)
