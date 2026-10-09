"""Single-thread Telegram pilot runner with durable receive/send boundaries."""
import json
from datetime import UTC, datetime, timedelta

from incubia_orchestrator.foundation.contracts.execution import ConversationTurn, ExecutionScope
from incubia_orchestrator.foundation.contracts.specialty import Specialty
from incubia_orchestrator.modules.conversation.adapters.channels.telegram.client import TelegramTransportError
from incubia_orchestrator.modules.conversation.adapters.channels.telegram.inbound import normalize_update
from incubia_orchestrator.modules.conversation.adapters.channels.telegram.outbound import public_text
from incubia_orchestrator.modules.conversation.application.response_context import InProcessResponseContext
from incubia_orchestrator.modules.conversation.domain.messages import ContextualizedResponse
from incubia_orchestrator.modules.conversation.ports.response_context import ResponseContextRequest
from incubia_orchestrator.modules.conversation.ports.ledger import ConversationCommit


class TelegramRunner:
    def __init__(self, ledger, client, *, account: str, generate):
        self.ledger, self.client, self.account, self.generate = ledger, client, account, generate

    def preflight(self):
        bot = self.client.get_me()
        if not bot.get("is_bot"):
            raise RuntimeError("Configured Telegram account is not a bot")
        if self.client.get_webhook_info().get("url"):
            raise RuntimeError("Telegram webhook is active")
        if str(bot.get("id")) != self.account:
            raise RuntimeError("Telegram bot account mismatch")

    def cycle(self):
        updates = self.client.get_updates(offset=self.ledger.last_offset(self.account) + 1)
        for update in updates:
            update_id = update.get("update_id")
            if not isinstance(update_id, int):
                continue
            inbound = normalize_update(update, self.account)
            binding = (self.ledger.resolve_binding(channel="telegram", account=self.account,
                       chat=inbound.external_chat_ref, sender=inbound.external_sender_ref) if inbound else None)
            if inbound and len(inbound.text) > 2000:
                binding = None
            self.ledger.accept_update(self.account, update_id, update, binding=binding)
        for event in self.ledger.pending_inbox_events(self.account):
            inbound = normalize_update(json.loads(event.payload_json), self.account)
            if inbound is None:
                continue
            binding = self.ledger.resolve_binding(channel="telegram", account=self.account,
                       chat=inbound.external_chat_ref, sender=inbound.external_sender_ref)
            if binding is None or not self.ledger.claim(event.execution_id):
                continue
            scope = ExecutionScope(*binding)
            result = self.generate(inbound.text, scope)
            response = InProcessResponseContext().contextualize(ResponseContextRequest(
                "response-" + event.execution_id, event.request_id, event.execution_id, scope,
                "telegram:" + inbound.external_chat_ref + ":" + inbound.external_sender_ref,
                result.text, result.specialty))
            self.ledger.commit_conversation(ConversationCommit(
                event.execution_id, scope, self.ledger.conversation_revision(scope), response.response_id,
                response.destination_ref, response.to_dict(), {"status": "completed"},
                ConversationTurn(inbound.text, response.text)))
        self.dispatch()

    def dispatch(self):
        for execution_id, response_id, destination, payload in self.ledger.pending_deliveries():
            response = ContextualizedResponse.from_dict(json.loads(payload))
            if response.destination_ref != destination or not destination.startswith("telegram:"):
                continue
            _, chat, sender = destination.split(":", 2)
            binding = self.ledger.resolve_binding(channel="telegram", account=self.account, chat=chat, sender=sender)
            if binding is None or tuple(response.scope.__dict__.values()) != binding:
                continue
            if not self.ledger.reserve_delivery(execution_id, response_id, destination):
                continue
            try:
                message_id = self.client.send_message(chat, public_text(response))
            except TelegramTransportError as error:
                if error.code == "UNKNOWN_EFFECT":
                    self.ledger.mark_delivery_unknown(execution_id, response_id, destination)
                else:
                    retry_at = ((datetime.now(UTC) + timedelta(seconds=error.retry_after)).isoformat()
                                if error.code == "RATE_LIMIT" and error.retry_after else None)
                    self.ledger.mark_delivery_failed(execution_id, response_id, destination, next_attempt_at=retry_at)
            else:
                self.ledger.mark_delivery_sent(execution_id, response_id, destination, message_id)
