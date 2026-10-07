from incubia_orchestrator.modules.conversation.adapters.channels.telegram.inbound import normalize_update
from incubia_orchestrator.modules.conversation.adapters.channels.telegram.outbound import public_text
from incubia_orchestrator.modules.conversation.adapters.channels.telegram.client import TelegramClient, TelegramTransportError
from incubia_orchestrator.modules.conversation.domain.messages import ContextualizedResponse
from incubia_orchestrator.foundation.contracts.execution import ExecutionScope
from incubia_orchestrator.foundation.contracts.specialty import Specialty
import httpx
import pytest


def test_telegram_normalizes_only_private_text_and_truncates_unicode():
    update = {"update_id": 3, "message": {"text": "hola", "date": 1, "chat": {"id": 2, "type": "private"}, "from": {"id": 4}}}
    assert normalize_update(update, "bot").external_event_id == "3"
    assert normalize_update({"update_id": 3, "message": {"chat": {"type": "group"}}}, "bot") is None
    response = ContextualizedResponse(1, "r", "q", "e", ExecutionScope("d", "t", "c", "a"), "telegram:b", "😀" * 5000, Specialty.GENERAL)
    assert len(public_text(response)) == 4094


def test_telegram_transport_classifies_conflict_rate_limit_and_ambiguous_send():
    def handler(request):
        if request.url.path.endswith("getUpdates"):
            return httpx.Response(409)
        return httpx.Response(429, json={"parameters": {"retry_after": 7}})
    client = TelegramClient("secret", httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(TelegramTransportError, match="POLLING_CONFLICT"):
        client.get_updates(1)
    with pytest.raises(TelegramTransportError) as caught:
        client.send_message("1", "hello")
    assert (caught.value.code, caught.value.retry_after) == ("RATE_LIMIT", 7)

    def timeout(request):
        raise httpx.ReadTimeout("timeout")
    client = TelegramClient("secret", httpx.Client(transport=httpx.MockTransport(timeout)))
    with pytest.raises(TelegramTransportError, match="UNKNOWN_EFFECT"):
        client.send_message("1", "hello")
