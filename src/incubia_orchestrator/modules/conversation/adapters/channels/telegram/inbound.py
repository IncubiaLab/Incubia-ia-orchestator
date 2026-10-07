from datetime import datetime, timezone

from incubia_orchestrator.modules.conversation.domain.messages import CONTRACT_VERSION, InboundMessage


def normalize_update(update: dict, account_ref: str) -> InboundMessage | None:
    message = update.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("text"), str):
        return None
    chat, sender = message.get("chat", {}), message.get("from", {})
    if chat.get("type") != "private" or "id" not in chat or "id" not in sender or "update_id" not in update:
        return None
    received = datetime.fromtimestamp(message.get("date", 0), tz=timezone.utc)
    return InboundMessage(CONTRACT_VERSION, "telegram", account_ref, str(update["update_id"]),
                          str(chat["id"]), str(sender["id"]), message["text"], received)
