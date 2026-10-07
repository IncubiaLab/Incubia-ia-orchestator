from datetime import UTC, datetime, timedelta
from threading import Barrier, Thread

import pytest

from incubia_orchestrator.modules.conversation.adapters.persistence.sqlite_ledger import IdempotencyConflict, RunnerAlreadyActive, SqliteLedger


def test_durable_deduplication_recovery_and_unknown_effect(tmp_path):
    path = tmp_path / "e2.sqlite"
    first = SqliteLedger(path)
    reserved = first.reserve_inbox("d", "t", "bot", "1", {"text": "hola"})
    assert reserved.is_new and first.claim(reserved.execution_id)
    first.complete(reserved.execution_id, "r", "telegram:b", {"text": "ok"})
    assert first.reserve_delivery(reserved.execution_id, "r", "telegram:b")
    first.close()
    second = SqliteLedger(path)
    assert not second.reserve_inbox("d", "t", "bot", "1", {"text": "hola"}).is_new
    second.recover()
    assert second.delivery_state(reserved.execution_id, "r", "telegram:b") == "UNKNOWN_EFFECT"
    with pytest.raises(IdempotencyConflict):
        second.reserve_inbox("d", "t", "bot", "1", {"text": "otro"})
    second.close()


def test_two_connections_have_one_reservation_and_one_runner(tmp_path):
    path = tmp_path / "e2.sqlite"
    owner = SqliteLedger(path, acquire_runner_lock=True)
    with pytest.raises(RunnerAlreadyActive):
        SqliteLedger(path, acquire_runner_lock=True)
    owner.close()
    barrier, reservations = Barrier(2), []
    def reserve():
        ledger = SqliteLedger(path)
        barrier.wait()
        reservations.append(ledger.reserve_inbox("d", "t", "bot", "2", {"text": "same"}))
        ledger.close()
    workers = [Thread(target=reserve), Thread(target=reserve)]
    for worker in workers: worker.start()
    for worker in workers: worker.join()
    assert sum(item.is_new for item in reservations) == 1
    assert len({item.execution_id for item in reservations}) == 1


def test_purge_removes_payload_then_tombstone(tmp_path):
    ledger = SqliteLedger(tmp_path / "e2.sqlite")
    event = ledger.reserve_inbox("d", "t", "bot", "3", {"text": "old"})
    assert ledger.claim(event.execution_id)
    ledger.complete(event.execution_id, "r", "telegram:b", {"text": "old"})
    old = datetime.now(UTC) + timedelta(days=1)
    payloads, tombstones = ledger.purge(payload_before=old, tombstone_before=old)
    assert (payloads, tombstones) == (1, 1)
    assert ledger.reserve_inbox("d", "t", "bot", "3", {"text": "old"}).is_new
    ledger.close()


def test_binding_and_offset_are_durable(tmp_path):
    path = tmp_path / "e2.sqlite"
    ledger = SqliteLedger(path)
    ledger.add_binding(channel="telegram", account="bot", chat="chat-a", sender="actor-a",
                       deployment_id="d", tenant_id="tenant-a", conversation_id="conv-a", actor_id="a")
    ledger.advance_offset("bot", 12)
    ledger.close()
    reopened = SqliteLedger(path)
    assert reopened.resolve_binding(channel="telegram", account="bot", chat="chat-a", sender="actor-a") == ("d", "tenant-a", "conv-a", "a")
    assert reopened.resolve_binding(channel="telegram", account="bot", chat="chat-b", sender="actor-a") is None
    assert reopened.last_offset("bot") == 12
    reopened.close()


def test_online_backup_reopens_with_durable_event(tmp_path):
    source, backup = tmp_path / "e2.sqlite", tmp_path / "backup.sqlite"
    ledger = SqliteLedger(source)
    event = ledger.reserve_inbox("d", "t", "bot", "4", {"text": "backup"})
    ledger.backup_to(backup)
    ledger.close()
    restored = SqliteLedger(backup)
    assert not restored.reserve_inbox("d", "t", "bot", "4", {"text": "backup"}).is_new
    restored.close()
