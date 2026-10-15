"""Single-thread Telegram pilot runner with durable receive/send boundaries."""
import json
import inspect
from datetime import UTC, datetime, timedelta
from uuid import uuid4

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
from incubia_orchestrator.modules.conversation.ports.ledger import (
    ConversationCommit, conversation_claim_key,
)
from incubia_orchestrator.modules.identity_tenant.application.resolve_scope import (
    BoundScopeResolver,
    ScopeResolutionDenied,
)


class DispatcherAlreadyActive(RuntimeError):
    """Another owner currently holds the durable channel-account lease."""


class TelegramRunner:
    def __init__(self, ledger, client, *, account: str, generate, history_limit: int = 2,
                 bind_unknown=None, owner_id: str | None = None,
                 dispatcher_lease_seconds: float = 60, identity_resolver=None):
        if history_limit < 0:
            raise ValueError("history_limit must be non-negative")
        self.ledger, self.client, self.account, self.generate = ledger, client, account, generate
        self.history_limit = history_limit
        self.bind_unknown = bind_unknown
        self._identity_resolver = identity_resolver
        if self._identity_resolver is None and hasattr(ledger, "resolve") and hasattr(ledger, "get"):
            self._identity_resolver = BoundScopeResolver(ledger, ledger)
        self._owner_id = owner_id or str(uuid4())
        self._dispatcher_lease_seconds = dispatcher_lease_seconds
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

    @staticmethod
    def _binding_tuple(binding):
        return ((binding.deployment_id, binding.tenant_id, binding.conversation_id, binding.actor_id)
                if binding is not None else None)

    def _resolve_binding(self, inbound):
        if inbound is None:
            return None
        if self._identity_resolver is not None:
            return self._identity_resolver.resolve_binding(
                channel="telegram", account=self.account,
                chat=inbound.external_chat_ref, sender=inbound.external_sender_ref,
            )
        raw = self.ledger.resolve_binding(
            channel="telegram", account=self.account,
            chat=inbound.external_chat_ref, sender=inbound.external_sender_ref,
        )
        if raw is None:
            return None
        return type("LegacyBinding", (), dict(zip(
            ("deployment_id", "tenant_id", "conversation_id", "actor_id"), raw
        )))()

    def _resolve_scope(self, inbound):
        if self._identity_resolver is not None:
            return self._identity_resolver.resolve_scope(
                channel="telegram", account=self.account,
                chat=inbound.external_chat_ref, sender=inbound.external_sender_ref,
            )
        binding = self._resolve_binding(inbound)
        if binding is None:
            raise ScopeResolutionDenied("No trusted binding exists")
        return ExecutionScope(*self._binding_tuple(binding))

    def cycle(self):
        acquire = getattr(self.ledger, "acquire_dispatcher_claim", None)
        dispatcher_claim = None
        if acquire is not None:
            dispatcher_claim = acquire(
                channel="telegram", account_ref=self.account, owner_id=self._owner_id,
                lease_seconds=self._dispatcher_lease_seconds,
            )
            if dispatcher_claim is None:
                raise DispatcherAlreadyActive(
                    f"Telegram account {self.account} is owned by another dispatcher"
                )
        updates = self.client.get_updates(offset=self.ledger.last_offset(self.account) + 1)
        for update in updates:
            update_id = update.get("update_id")
            if not isinstance(update_id, int):
                continue
            inbound = normalize_update(update, self.account)
            binding = self._resolve_binding(inbound)
            if inbound and len(inbound.text) > 2000:
                binding = None
            if inbound and binding is None and len(inbound.text) <= 2000 and self.bind_unknown is not None:
                candidate = self.bind_unknown(inbound)
                # A binding returned by an administrative callback must also
                # be durable and resolvable through the identity ports. This
                # prevents a callback from smuggling an arbitrary scope into
                # the inbox.
                binding = self._resolve_binding(inbound)
                if self._identity_resolver is None and binding is None and candidate is not None:
                    binding = type("LegacyBinding", (), dict(zip(
                        ("deployment_id", "tenant_id", "conversation_id", "actor_id"),
                        candidate,
                    )))()
            self.ledger.accept_update(
                self.account, update_id, update,
                binding=self._binding_tuple(binding),
            )
        for event in self.ledger.pending_inbox_events(self.account):
            inbound = normalize_update(json.loads(event.payload_json), self.account)
            if inbound is None:
                continue
            try:
                scope = self._resolve_scope(inbound)
            except ScopeResolutionDenied:
                continue
            event_claim = self.ledger.claim(
                event.execution_id, scope=scope, owner_id=event.execution_id, lease_seconds=60
            )
            if event_claim is None:
                continue
            conversation_claim = self.ledger.acquire_claim(
                scope, resource_type="conversation", resource_key=conversation_claim_key(scope),
                owner_id=event.execution_id, lease_seconds=60,
            )
            if conversation_claim is None:
                self.ledger.return_to_received(
                    event.execution_id, scope=scope, claim_token=event_claim
                )
                continue
            try:
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
                    ConversationTurn(inbound.text, response.text),
                    claim_tokens=(event_claim, conversation_claim),
                ))
            except Exception:
                # A failed local generation/commit has no external effect yet.
                # Return the inbox row so a later cycle can retry it; a send
                # failure is handled separately by dispatch() as UNKNOWN_EFFECT.
                self.ledger.return_to_received(
                    event.execution_id, scope=scope, claim_token=event_claim
                )
                self.ledger.release_claim(conversation_claim)
                raise
        if dispatcher_claim is not None:
            renew = getattr(self.ledger, "renew_dispatcher_claim", None)
            if renew is not None and not renew(
                dispatcher_claim, lease_seconds=self._dispatcher_lease_seconds
            ):
                raise DispatcherAlreadyActive(
                    f"Telegram account {self.account} lost dispatcher ownership"
                )
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
            try:
                current_scope = self._resolve_scope(type(
                    "InboundRef", (), {
                        "external_chat_ref": chat,
                        "external_sender_ref": sender,
                    }
                )())
            except ScopeResolutionDenied:
                continue
            if current_scope != response.scope:
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
