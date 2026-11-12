from pathlib import Path
import pytest

from incubia_orchestrator.interfaces.http.migrate_all import (
    postgres_migrations,
    run_postgres_migrations,
    validate_migration_role,
)


def test_postgres_migrations_lists_all_in_order():
    root = Path(__file__).resolve().parents[2]
    migrations = postgres_migrations(root)
    names = [m.name for m in migrations]
    assert len(names) == 8
    assert names[0] == "001_e3_d0_ledger.sql"
    assert names[1] == "002_e3_h1_rls.sql"
    assert names[6] == "007_e3_h2_identity.sql"
    assert names[7] == "008_e3_g7_audit.sql"


def test_validate_migration_role_rejects_runtime_roles():
    with pytest.raises(ValueError, match="Migration refused"):
        validate_migration_role("postgresql://incubia_runtime:secret@host/db")
    with pytest.raises(ValueError, match="Migration refused"):
        validate_migration_role("postgresql://d0_runtime:secret@host/db")


def test_run_postgres_migrations_applies_with_fake_ledger(monkeypatch, tmp_path):
    root = Path(__file__).resolve().parents[2]
    applied_files = []

    class MockLedger:
        def __init__(self, dsn):
            self.dsn = dsn

        def migrate(self, path):
            applied_files.append(path.name)

    monkeypatch.setattr("incubia_orchestrator.interfaces.http.migrate_all.PostgresLedger", MockLedger)
    applied = run_postgres_migrations("postgresql://incubia_migrator:secret@host/db", root)
    assert len(applied) == 8
    assert applied == applied_files

