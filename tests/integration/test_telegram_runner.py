import httpx

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
