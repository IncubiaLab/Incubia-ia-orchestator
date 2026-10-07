from incubia_orchestrator.modules.conversation.domain.messages import ContextualizedResponse


def public_text(response: ContextualizedResponse) -> str:
    text = response.text
    return text if len(text) <= 4096 else text[:4090] + " […]"
