import pytest

from incubia_orchestrator.foundation.contracts.execution import ConversationTurn, ExecutionScope
from incubia_orchestrator.modules.conversation.adapters.persistence.sqlite_ledger import SqliteLedger
from incubia_orchestrator.modules.conversation.ports.ledger import (
    ConversationCommit, RevisionConflict, ScopeConflict,
)
from incubia_orchestrator.modules.identity_tenant.application.resolve_scope import (
    ScopeResolutionDenied, resolve_scope,
)
from incubia_orchestrator.modules.identity_tenant.domain.principal import Principal
from incubia_orchestrator.modules.identity_tenant.ports.identity import TrustedBinding


def test_scope_requires_authenticated_subject_to_match_trusted_binding():
    binding = TrustedBinding("deployment", "tenant", "conversation", "actor")
    scope = resolve_scope(Principal("deployment", "actor"), binding, membership_active=True)
    assert scope == ExecutionScope("deployment", "tenant", "conversation", "actor")
    with pytest.raises(ScopeResolutionDenied):
        resolve_scope(Principal("deployment", "other"), binding, membership_active=True)
    with pytest.raises(ScopeResolutionDenied):
        resolve_scope(Principal("deployment", "actor"), binding, membership_active=False)


def test_sqlite_uow_commits_turn_outcome_and_delivery_with_one_revision(tmp_path):
    ledger = SqliteLedger(tmp_path / "ledger.sqlite")
    event = ledger.reserve_inbox("d", "t", "bot", "1", {"text": "hola"})
    scope = ExecutionScope("d", "t", "conversation", "actor")
    owner = "owner-1"
    event_claim = ledger.claim(event.execution_id, scope=scope, owner_id=owner)
    conversation_claim = ledger.acquire_claim(
        scope, resource_type="conversation", resource_key="conversation", owner_id=owner
    )
    assert event_claim and conversation_claim
    revision = ledger.commit_conversation(ConversationCommit(
        event.execution_id, scope, 0, "response", "telegram:chat:actor", {"text": "ok"},
        {"status": "completed"}, ConversationTurn("hola", "ok"),
        (event_claim, conversation_claim)))
    assert revision == 1
    assert ledger.conversation_revision(scope) == 1
    assert ledger.delivery_state(event.execution_id, "response", "telegram:chat:actor") == "PENDING"
    turn = ledger._connection.execute(
        "SELECT conversation_id,actor_id,user_text,assistant_text FROM turns WHERE execution_id=?",
        (event.execution_id,),
    ).fetchone()
    assert turn == ("conversation", "actor", "hola", "ok")
    assert ledger._connection.execute("SELECT state FROM inbox_events WHERE execution_id=?", (event.execution_id,)).fetchone() == ("COMPLETED",)
    ledger.close()


def test_sqlite_uow_rejects_stale_revision_and_scope_without_partial_commit(tmp_path):
    ledger = SqliteLedger(tmp_path / "ledger.sqlite")
    event = ledger.reserve_inbox("d", "t", "bot", "1", {"text": "hola"})
    scope = ExecutionScope("d", "t", "conversation", "actor")
    assert ledger.claim(event.execution_id, scope=scope, owner_id="owner-1")
    wrong_scope = ExecutionScope("d", "other", "conversation", "actor")
    with pytest.raises(ScopeConflict):
        ledger.commit_conversation(ConversationCommit(event.execution_id, wrong_scope, 0, "r", "dest", {}, {}, ConversationTurn("u", "a")))
    with pytest.raises(RevisionConflict):
        ledger.commit_conversation(ConversationCommit(event.execution_id, scope, 1, "r", "dest", {}, {}, ConversationTurn("u", "a")))
    assert ledger._connection.execute("SELECT state FROM inbox_events WHERE execution_id=?", (event.execution_id,)).fetchone() == ("PROCESSING",)
    assert ledger._connection.execute("SELECT count(*) FROM outcomes").fetchone() == (0,)
    assert ledger._connection.execute("SELECT count(*) FROM deliveries").fetchone() == (0,)
    ledger.close()
