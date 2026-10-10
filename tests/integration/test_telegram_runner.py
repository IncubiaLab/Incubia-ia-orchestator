import httpx

from incubia_orchestrator.foundation.contracts.execution import CompletedExecution, ExecutionOutput
from incubia_orchestrator.foundation.contracts.specialty import Specialty
from incubia_orchestrator.modules.conversation.adapters.channels.telegram.client import TelegramClient
from incubia_orchestrator.modules.conversation.adapters.channels.telegram.runner import TelegramRunner
from incubia_orchestrator.modules.conversation.adapters.persistence.sqlite_ledger import SqliteLedger


def _update(number, chat, text):
    return {"update_id": number, "message": {"chat": {"id": chat, "type": "private"},
            "from": {"id": chat}, "date": 1, "text": text}}


def test_two_bound_chats_and_unknown_sender_with_replay(tmp_path):
    ledger = SqliteLedger(tmp_path / "e2.sqlite")
    for suffix in ("1", "2"):
        ledger.add_binding(channel="telegram", account="42", chat=suffix, sender=suffix,
                           deployment_id="pilot", tenant_id="t" + suffix,
                           conversation_id="c" + suffix, actor_id="a" + suffix)
    sent, generated = [], []
    updates = [_update(1, 1, "ventas"), _update(2, 2, "marketing"), _update(3, 999, "unknown")]
    def handler(request):
        if request.url.path.endswith("getUpdates"):
            return httpx.Response(200, json={"ok": True, "result": updates})
        if request.url.path.endswith("sendMessage"):
            sent.append(request.read())
            return httpx.Response(200, json={"ok": True, "result": {"message_id": len(sent)}})
        raise AssertionError("Unexpected endpoint")
    client = TelegramClient("secret", httpx.Client(transport=httpx.MockTransport(handler)))
    def generate(text, scope):
        generated.append((text, scope.tenant_id))
        return type("Result", (), {"text": "reply " + text, "specialty": Specialty.GENERAL})()
    runner = TelegramRunner(ledger, client, account="42", generate=generate)
    runner.cycle()
    runner.cycle()
    assert generated == [("ventas", "t1"), ("marketing", "t2")]
    assert len(sent) == 2
    assert ledger.last_offset("42") == 3
    ledger.close()


def test_multi_session_binding_isolated_by_private_chat(tmp_path):
    ledger = SqliteLedger(tmp_path / "multi.sqlite3")
    updates = [_update(1, 101, "ventas"), _update(2, 202, "marketing"), _update(3, 101, "hola")]
    sent, generated = [], []

    def handler(request):
        if request.url.path.endswith("getUpdates"):
            return httpx.Response(200, json={"ok": True, "result": updates})
        if request.url.path.endswith("sendMessage"):
            sent.append(request.read())
            return httpx.Response(200, json={"ok": True, "result": {"message_id": len(sent)}})
        raise AssertionError("Unexpected endpoint")

    def bind(inbound):
        binding = ("deployment", "tenant", "conversation-" + inbound.external_chat_ref,
                   "actor-" + inbound.external_sender_ref)
        ledger.add_binding(channel="telegram", account="42", chat=inbound.external_chat_ref,
                           sender=inbound.external_sender_ref, deployment_id=binding[0],
                           tenant_id=binding[1], conversation_id=binding[2], actor_id=binding[3])
        return binding

    def generate(text, scope, history, request_id, execution_id):
        generated.append((text, scope.conversation_id, tuple(turn.user for turn in history)))
        return CompletedExecution(request_id, execution_id,
                                  ExecutionOutput("respuesta " + text, Specialty.GENERAL))

    client = TelegramClient("secret", httpx.Client(transport=httpx.MockTransport(handler)))
    runner = TelegramRunner(ledger, client, account="42", generate=generate, bind_unknown=bind)
    runner.cycle()

    assert generated == [
        ("ventas", "conversation-101", ()),
        ("marketing", "conversation-202", ()),
        ("hola", "conversation-101", ("ventas",)),
    ]
    assert len(sent) == 3
    assert ledger.resolve_binding(channel="telegram", account="42", chat="101", sender="101")
    assert ledger.resolve_binding(channel="telegram", account="42", chat="202", sender="202")
    ledger.close()


def test_unknown_update_is_durably_discarded_before_offset_advances(tmp_path):
    ledger = SqliteLedger(tmp_path / "e2.sqlite")
    client = TelegramClient("secret", httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"ok": True, "result": [_update(9, 999, "unknown")]})
        if request.url.path.endswith("getUpdates") else httpx.Response(200, json={"ok": True, "result": {"message_id": 1}}))))
    runner = TelegramRunner(ledger, client, account="42", generate=lambda text, scope: None)
    runner.cycle()
    assert ledger.last_offset("42") == 9
    assert ledger._connection.execute("SELECT reason FROM discarded_updates").fetchone() == ("UNBOUND_OR_UNSUPPORTED",)
    ledger.close()
