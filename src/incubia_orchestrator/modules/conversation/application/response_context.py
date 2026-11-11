from incubia_orchestrator.modules.conversation.domain.messages import CONTRACT_VERSION, ContextualizedResponse
from incubia_orchestrator.modules.conversation.ports.response_context import ResponseContextRequest
from incubia_orchestrator.foundation.public_references import safe_public_ref


class InProcessResponseContext:
    """The public mapper intentionally receives no inference prompt or policy decision."""
    def contextualize(self, request: ResponseContextRequest) -> ContextualizedResponse:
        return ContextualizedResponse(CONTRACT_VERSION, request.response_id, request.request_id,
                                      request.execution_id, request.scope, request.destination_ref,
                                      request.text, request.specialty, request.language,
                                      tuple(dict.fromkeys(ref for value in request.public_references
                                                          if (ref := safe_public_ref(value)))), request.reply_to)
