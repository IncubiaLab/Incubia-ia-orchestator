import json
from datetime import UTC, datetime

import pytest

from incubia_orchestrator.modules.conversation.adapters.persistence.postgres.backup import (
    BACKUP_FORMAT,
    BACKUP_VERSION,
    BackupManifestError,
    PostgresLedgerBackup,
)


def _empty_tables():
    return {table: [] for table in ("inbox_events", "conversations", "turns", "outcomes", "deliveries")}


def _package(scope=("deployment-test", "tenant-test")):
    now = datetime.now(UTC)
    manifest = PostgresLedgerBackup._make_manifest(scope, _empty_tables(), now, now)
    return {"manifest": manifest, "tables": _empty_tables()}


def _write_package(tmp_path, package):
    path = tmp_path / "backup.json"
    path.write_text(json.dumps(package), encoding="utf-8")
    return path


def test_backup_package_manifest_is_verified_and_has_no_claims(tmp_path):
    path = _write_package(tmp_path, _package())

    manifest, tables, manifest_hash = PostgresLedgerBackup._load_package(path)

    assert manifest["format"] == BACKUP_FORMAT
    assert manifest["version"] == BACKUP_VERSION
    assert manifest["claims_included"] is False
    assert tables == _empty_tables()
    assert len(manifest_hash) == 64


def test_tampered_table_is_rejected_before_database_access(tmp_path):
    package = _package()
    package["tables"]["conversations"].append({
        "deployment_id": "deployment-test",
        "tenant_id": "tenant-test",
        "conversation_id": "conversation",
        "actor_id": "actor",
        "revision": 1,
    })
    path = _write_package(tmp_path, package)

    with pytest.raises(BackupManifestError, match="count does not match"):
        PostgresLedgerBackup._load_package(path)


def test_validly_hashed_row_outside_scope_is_rejected(tmp_path):
    package = _package()
    package["tables"]["conversations"].append({
        "deployment_id": "other-deployment",
        "tenant_id": "tenant-test",
        "conversation_id": "conversation",
        "actor_id": "actor",
        "revision": 1,
    })
    manifest = package["manifest"]
    rows = package["tables"]
    metadata = dict(manifest["tables"])
    metadata["conversations"] = {
        "count": 1,
        "sha256": PostgresLedgerBackup._table_hash(rows["conversations"]),
    }
    manifest["tables"] = metadata
    manifest["revision_range"] = {"min": 1, "max": 1}
    from incubia_orchestrator.modules.conversation.adapters.persistence.postgres.backup import _digest

    manifest["content_sha256"] = _digest({"tables": rows, "table_meta": metadata})
    unsigned = dict(manifest)
    unsigned.pop("manifest_sha256")
    unsigned.pop("content_sha256")
    manifest["manifest_sha256"] = _digest(unsigned)
    path = _write_package(tmp_path, package)

    with pytest.raises(BackupManifestError, match="outside the manifest scope"):
        PostgresLedgerBackup._load_package(path)


def test_sending_to_unknown_effect_is_the_only_restore_state_transition():
    expected = {"execution_id": "e", "response_id": "r", "destination_ref": "d", "state": "SENDING"}
    actual = dict(expected, state="UNKNOWN_EFFECT")
    assert PostgresLedgerBackup._same_row("deliveries", expected, actual)
    assert not PostgresLedgerBackup._same_row("deliveries", expected, dict(actual, state="SENT"))
