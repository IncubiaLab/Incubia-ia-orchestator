"""Opt-in Neon restore campaign for the E3-05 H1 gate.

This test deliberately uses a unique synthetic scope. It seeds one complete
Conversation ledger unit, exports it, deletes only that scope through the
migrator role, restores it, and verifies a second import is idempotent. It is
never enabled by the ordinary offline suite; run it only on
``e3-h1-synthetic`` with the explicit Neon guards.
"""
from __future__ import annotations

import os
import json
import time
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from incubia_orchestrator.foundation.contracts.execution import ConversationTurn, ExecutionScope
from incubia_orchestrator.modules.conversation.adapters.persistence.postgres import (
    PostgresLedger,
    PostgresLedgerBackup,
)
from incubia_orchestrator.modules.conversation.ports.ledger import (
    ConversationCommit,
    conversation_claim_key,
)


pytestmark = pytest.mark.neon
ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = sorted((ROOT / "migrations/postgres").glob("[0-9][0-9][0-9]_*.sql"))


def _guard_campaign() -> None:
    if os.getenv("INCUBIA_E3_NEON_TESTS") != "1":
        pytest.skip("Neon campaign requires explicit opt-in")
    if os.getenv("INCUBIA_E3_NEON_BRANCH") != "e3-h1-synthetic":
        pytest.skip("Neon campaign requires the synthetic H1 branch")
    if not (os.getenv("DATABASE_URL", "").endswith("?sslmode=require")
            or ".neon.tech" in os.getenv("DATABASE_URL", "")):
        pytest.skip("Neon runtime URL is not configured")


def _apply_migrations() -> None:
    _guard_campaign()
    ledger = PostgresLedger(os.environ["INCUBIA_MIGRATION_DATABASE_URL"])
    for migration in MIGRATIONS:
        ledger.migrate(migration)


def _cleanup(scope: tuple[str, str]) -> None:
    deployment_id, tenant_id = scope
    with psycopg.connect(os.environ["INCUBIA_MIGRATION_DATABASE_URL"], connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            for table in ("deliveries", "outcomes", "turns", "inbox_events", "conversations", "resource_claims"):
                cursor.execute(
                    f"DELETE FROM {table} WHERE deployment_id=%s AND tenant_id=%s",
                    scope,
                )
            cursor.execute(
                "DELETE FROM ledger_imports WHERE deployment_id=%s AND tenant_id=%s",
                scope,
            )


@pytest.fixture(scope="module", autouse=True)
def h1_schema():
    _apply_migrations()


def test_neon_export_restore_with_rows_is_idempotent_and_preserves_ledger(tmp_path):
    _guard_campaign()
    deployment_id = f"e3-h1-restore-{uuid4().hex[:12]}"
    tenant_id = f"tenant-{uuid4().hex[:12]}"
    scope_values = (deployment_id, tenant_id)
    scope = ExecutionScope(deployment_id, tenant_id, "conversation", "actor")
    event_id = f"event-{uuid4().hex}"
    account = "backup-account"
    package = tmp_path / "ledger-backup.json"
    restored_export = tmp_path / "ledger-restored.json"
    runtime = PostgresLedger(os.environ["DATABASE_URL"])
    backup = PostgresLedgerBackup(os.environ["DATABASE_URL"])
    migrator_backup = PostgresLedgerBackup(os.environ["INCUBIA_MIGRATION_DATABASE_URL"])
    started = time.monotonic()

    try:
        reservation = runtime.reserve_inbox(
            deployment_id,
            tenant_id,
            account,
            event_id,
            {"text": "restore me", "synthetic": True},
            channel="neon-backup",
        )
        event_claim = runtime.claim(
            reservation.execution_id,
            scope=scope,
            owner_id="backup-test-owner",
            lease_seconds=60,
        )
        conversation_claim = runtime.acquire_claim(
            scope,
            resource_type="conversation",
            resource_key=conversation_claim_key(scope),
            owner_id="backup-test-owner",
            lease_seconds=60,
        )
        assert event_claim is not None and conversation_claim is not None
        runtime.commit_conversation(
            ConversationCommit(
                execution_id=reservation.execution_id,
                scope=scope,
                expected_revision=0,
                response_id=f"response-{reservation.execution_id}",
                destination_ref="synthetic:restore",
                public_payload={"text": "restored", "synthetic": True},
                outcome={"status": "completed", "synthetic": True},
                turn=ConversationTurn("restore me", "restored"),
                claim_tokens=(event_claim, conversation_claim),
            )
        )

        exported = backup.export(scope, package)
        assert exported.table_counts == {
            "inbox_events": 1,
            "conversations": 1,
            "turns": 1,
            "outcomes": 1,
            "deliveries": 1,
        }

        _cleanup(scope_values)
        first_restore = migrator_backup.import_package(package, expected_scope=scope_values)
        assert first_restore.status == "COMPLETED"
        assert first_restore.idempotent is False
        assert first_restore.rpo_seconds >= 0
        assert first_restore.rto_seconds >= 0

        restored_reservation = runtime.reserve_inbox(
            deployment_id,
            tenant_id,
            account,
            event_id,
            {"text": "restore me", "synthetic": True},
            channel="neon-backup",
        )
        assert restored_reservation.is_new is False
        assert restored_reservation.execution_id == reservation.execution_id
        assert runtime.conversation_revision(scope) == 1
        assert runtime.conversation_history(scope) == (ConversationTurn("restore me", "restored"),)

        second_restore = migrator_backup.import_package(package, expected_scope=scope_values)
        assert second_restore.status == "COMPLETED"
        assert second_restore.idempotent is True
        round_trip = backup.export(scope, restored_export)
        assert round_trip.manifest["tables"] == exported.manifest["tables"]
        assert round_trip.manifest["revision_range"] == exported.manifest["revision_range"]
        evidence_path = os.getenv("INCUBIA_E3_H1_BACKUP_EVIDENCE")
        if evidence_path:
            Path(evidence_path).write_text(
                json.dumps(
                    {
                        "schema_version": "e3-h1-m2/v1",
                        "milestone": "M2",
                        "status": "passed",
                        "critical_failures": 0,
                        "synthetic": True,
                        "branch": "e3-h1-synthetic",
                        "rows": exported.table_counts,
                        "first_restore": first_restore.as_dict(),
                        "second_restore": second_restore.as_dict(),
                        "test_duration_seconds": round(time.monotonic() - started, 3),
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
    finally:
        _cleanup(scope_values)
