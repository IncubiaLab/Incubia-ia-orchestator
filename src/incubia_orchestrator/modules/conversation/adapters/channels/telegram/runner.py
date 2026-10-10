"""Single-thread Telegram pilot runner with durable receive/send boundaries."""
import json
import inspect
from datetime import UTC, datetime, timedelta

from incubia_orchestrator.foundation.contracts.execution import (
    CompletedExecution,
    ConversationTurn,
    ExecutionScope,
    FailedExecution,
    to_dict,
)
from incubia_orchestrator.foundation.contracts.specialty import Specialty
from incubia_orchestrator.modules.conversation.adapters.channels.telegram.client import TelegramTransportError
from incubia_orchestrator.modules.conversation.adapters.channels.telegram.inbound import normalize_update
from incubia_orchestrator.modules.conversation.adapters.channels.telegram.outbound import public_text
from incubia_orchestrator.modules.conversation.application.response_context import InProcessResponseContext
from incubia_orchestrator.modules.conversation.domain.messages import ContextualizedResponse
from incubia_orchestrator.modules.conversation.ports.response_context import ResponseContextRequest
from incubia_orchestrator.modules.conversation.ports.ledger import ConversationCommit


class TelegramRunner:
    def __init__(self, ledger, client, *, account: str, generate, history_limit: int = 2,
                 bind_unknown=None):
        if history_limit < 0:
            raise ValueError("history_limit must be non-negative")
        self.ledger, self.client, self.account, self.generate = ledger, client, account, generate
        self.history_limit = history_limit
        self.bind_unknown = bind_unknown
        try:
            parameters = inspect.signature(generate).parameters.values()
            positional = [parameter for parameter in parameters
                          if parameter.kind in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD)]
            self._generation_arity = 5 if any(parameter.kind is parameter.VAR_POSITIONAL for parameter in parameters) else len(positional)
        except (TypeError, ValueError):
            self._generation_arity = 5

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
            if inbound and binding is None and len(inbound.text) <= 2000 and self.bind_unknown is not None:
                binding = self.bind_unknown(inbound)
            self.ledger.accept_update(self.account, update_id, update, binding=binding)
        for event in self.ledger.pending_inbox_events(self.account):
            inbound = normalize_update(json.loads(event.payload_json), self.account)
            if inbound is None:
                continue
            binding = self.ledger.resolve_binding(channel="telegram", account=self.account,
                       chat=inbound.external_chat_ref, sender=inbound.external_sender_ref)
            if binding is None:
                continue
            scope = ExecutionScope(*binding)
            if not self.ledger.claim(
                event.execution_id, scope=scope, owner_id=event.execution_id, lease_seconds=60
            ):
                continue
            history = (self.ledger.conversation_history(scope, limit=self.history_limit)
                       if self.history_limit else ())
            result = self._generate(inbound, scope, history, event.request_id, event.execution_id)
            text, specialty = self._public_result(result)
            response = InProcessResponseContext().contextualize(ResponseContextRequest(
                "response-" + event.execution_id, event.request_id, event.execution_id, scope,
                "telegram:" + inbound.external_chat_ref + ":" + inbound.external_sender_ref,
                text, specialty))
            self.ledger.commit_conversation(ConversationCommit(
                event.execution_id, scope, self.ledger.conversation_revision(scope), response.response_id,
                response.destination_ref, response.to_dict(), self._outcome_payload(result),
                ConversationTurn(inbound.text, response.text)))
        self.dispatch()

    def _generate(self, inbound, scope, history, request_id, execution_id):
        """Call the durable-ID-aware generator, retaining the E2 two-arg seam."""
        if self._generation_arity >= 5:
            return self.generate(inbound.text, scope, history, request_id, execution_id)
        if self._generation_arity >= 3:
            return self.generate(inbound.text, scope, history)
        return self.generate(inbound.text, scope)

    @staticmethod
    def _outcome_payload(result):
        if isinstance(result, (CompletedExecution, FailedExecution)):
            return to_dict(result)
        return {"status": "completed"}

    @staticmethod
    def _public_result(result):
        if isinstance(result, CompletedExecution):
            return result.output.text, result.output.specialty or Specialty.GENERAL
        if isinstance(result, FailedExecution):
            return ("No pude procesar tu mensaje en este momento. Inténtalo de nuevo más tarde.",
                    result.error.specialty or Specialty.GENERAL)
        if hasattr(result, "text"):
            return result.text, getattr(result, "specialty", None) or Specialty.GENERAL
        return ("No pude completar tu mensaje en este momento. Inténtalo de nuevo más tarde.",
                Specialty.GENERAL)

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
