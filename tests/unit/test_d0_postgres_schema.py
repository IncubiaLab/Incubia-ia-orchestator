from pathlib import Path

import pytest

from incubia_orchestrator.modules.conversation.adapters.persistence.postgres import PostgresLedger


def test_d0_runtime_role_has_only_the_ledger_permissions_it_needs():
    root = Path(__file__).resolve().parents[2]
    sql = (root / "migrations/postgres/001_e3_d0_ledger.sql").read_text(encoding="utf-8")

    assert "REVOKE CREATE ON SCHEMA public FROM PUBLIC" in sql
    assert "GRANT SELECT ON schema_migrations TO d0_runtime" in sql
    assert "REVOKE CREATE ON SCHEMA public FROM d0_runtime" in sql
    assert "GRANT SELECT, INSERT, UPDATE ON inbox_events, conversations TO d0_runtime" in sql
    assert "GRANT SELECT, INSERT ON turns, outcomes, deliveries TO d0_runtime" in sql
    assert "ON ALL TABLES" not in sql
    assert "No approved runtime role is provisioned" in sql
    assert "d0_runtime" in sql and "incubia_runtime" in sql


def test_d0_postgres_connections_have_a_bounded_connect_timeout(monkeypatch):
    captured = {}

    class Driver:
        @staticmethod
        def connect(url, **kwargs):
            captured["url"] = url
            captured.update(kwargs)
            raise OSError("unreachable")

    monkeypatch.setattr(PostgresLedger, "_driver", staticmethod(lambda: Driver))
    ledger = PostgresLedger("postgresql://local")

    with pytest.raises(OSError):
        with ledger._transaction():
            pass

    assert captured == {
        "url": "postgresql://local",
        "connect_timeout": PostgresLedger.CONNECT_TIMEOUT_SECONDS,
    }


def test_h1_migrations_enable_scoped_rls_and_monotonic_claims():
    root = Path(__file__).resolve().parents[2]
    rls = (root / "migrations/postgres/002_e3_h1_rls.sql").read_text(encoding="utf-8")
    claims = (root / "migrations/postgres/003_e3_h1_claims.sql").read_text(encoding="utf-8")
    dispatch = (root / "migrations/postgres/004_e3_h1_dispatcher_claims.sql").read_text(encoding="utf-8")
    backup = (root / "migrations/postgres/005_e3_h1_backup.sql").read_text(encoding="utf-8")

    for table in ("inbox_events", "conversations", "turns", "outcomes", "deliveries"):
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in rls
    assert "current_setting('app.deployment_id', true)" in rls
    assert "current_setting('app.tenant_id', true)" in rls
    assert "generation BIGINT NOT NULL CHECK (generation > 0)" in claims
    assert "lease_until TIMESTAMPTZ NOT NULL" in claims
    assert "GRANT SELECT, INSERT, UPDATE ON resource_claims TO incubia_runtime" in claims
    assert "CREATE TABLE IF NOT EXISTS dispatcher_claims" in dispatch
    assert "ALTER TABLE dispatcher_claims ENABLE ROW LEVEL SECURITY" in dispatch
    assert "app.dispatch_channel" in dispatch and "app.dispatch_account" in dispatch
    assert "CREATE TABLE IF NOT EXISTS ledger_imports" in backup


def test_h2_identity_migration_scopes_memberships_and_bindings():
    root = Path(__file__).resolve().parents[2]
    identity = (root / "migrations/postgres/007_e3_h2_identity.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS memberships" in identity
    assert "CHECK (role IN ('actor', 'operator', 'admin'))" in identity
    assert "CREATE TABLE IF NOT EXISTS bindings" in identity
    assert "ALTER TABLE memberships ENABLE ROW LEVEL SECURITY" in identity
    assert "ALTER TABLE bindings ENABLE ROW LEVEL SECURITY" in identity
    assert "app.binding_channel" in identity and "app.binding_account" in identity
    assert "GRANT SELECT ON memberships, bindings TO incubia_runtime" in identity
    assert "REVOKE ALL ON memberships, bindings FROM d0_runtime" in identity
