"""Contract for scripts/e3/migrate_knowledge.py (offline; fake connection only)."""
from __future__ import annotations

import pytest

from scripts.e3.migrate_knowledge import (
    EXPECTED_BRANCH, MigrationRefused, load_env_file, main, migrate, validate_env)

DSN = ("postgresql://incubia_kb_migrator:s3cretpassword@ep-x.us-east-2.aws.neon.tech/"
       "incubialab_knowledge_dev?sslmode=require")


def _env(**overrides):
    env = {"INCUBIA_KNOWLEDGE_NEON_BRANCH": EXPECTED_BRANCH,
           "INCUBIA_KNOWLEDGE_DATABASE": "incubialab_knowledge_dev",
           "INCUBIA_KNOWLEDGE_MIGRATION_DATABASE_URL": DSN}
    env.update(overrides)
    return env


def test_valid_env_returns_dsn():
    assert validate_env(_env()) == DSN


@pytest.mark.parametrize("overrides", [
    {"INCUBIA_KNOWLEDGE_NEON_BRANCH": "production"},
    {"INCUBIA_KNOWLEDGE_NEON_BRANCH": "e3-h1-synthetic"},
    {"INCUBIA_KNOWLEDGE_NEON_BRANCH": ""},
    {"INCUBIA_KNOWLEDGE_DATABASE": "neondb"},
    {"INCUBIA_KNOWLEDGE_MIGRATION_DATABASE_URL": ""},
    {"INCUBIA_KNOWLEDGE_MIGRATION_DATABASE_URL": DSN.replace("ep-x.", "ep-x-pooler.")},
    {"INCUBIA_KNOWLEDGE_MIGRATION_DATABASE_URL": DSN.replace("incubia_kb_migrator", "incubia_kb_runtime")},
    {"INCUBIA_KNOWLEDGE_MIGRATION_DATABASE_URL": DSN.replace("sslmode=require", "sslmode=disable")},
    {"INCUBIA_KNOWLEDGE_MIGRATION_DATABASE_URL": DSN.replace(".neon.tech", ".example.com")},
    {"INCUBIA_KNOWLEDGE_MIGRATION_DATABASE_URL": DSN.replace("s3cretpassword", "REPLACE_ME")},
])
def test_refuses_unsafe_env_without_echoing_secrets(overrides):
    with pytest.raises(MigrationRefused) as error:
        validate_env(_env(**overrides))
    assert "s3cretpassword" not in str(error.value)
    assert "neon.tech" not in str(error.value)


def test_load_env_file_parses_and_ignores_comments(tmp_path):
    path = tmp_path / "k.env"
    path.write_text("# comment\nA=1\nB='two'\n\nC=\"x=y\"\n")
    assert load_env_file(path) == {"A": "1", "B": "two", "C": "x=y"}


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self._result = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.conn.executed.append(sql)
        self._result = self.conn.answer(sql, params)

    def fetchone(self):
        return self._result


class FakeConnection:
    def __init__(self, *, user="incubia_kb_migrator", runtime_select=True, runtime_write=False,
                 ingest_dml=True):
        self.user, self.executed, self.committed = user, [], False
        self.runtime_select, self.runtime_write, self.ingest_dml = runtime_select, runtime_write, ingest_dml

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.committed = True

    def answer(self, sql, params):
        if sql.startswith("SELECT current_user"):
            return (self.user, "incubialab_knowledge_dev")
        if sql.startswith("SELECT to_regclass"):
            return ("x",)
        if sql.startswith("SELECT tableowner"):
            return ("incubia_kb_migrator",)
        if "has_table_privilege" in sql:
            role = params[0]
            if role == "incubia_kb_runtime":
                return (self.runtime_select, self.runtime_write)
            return (self.ingest_dml,)
        return None


def test_migrate_applies_001_and_verifies_grants():
    conn = FakeConnection()
    report = migrate(conn, "incubialab_knowledge_dev")
    assert conn.committed
    assert any("CREATE TABLE IF NOT EXISTS knowledge_chunks" in sql for sql in conn.executed)
    assert not any("CONCURRENTLY" in sql for sql in conn.executed)  # 002 HNSW stays opt-in
    assert report["tables"] == ["knowledge_generations", "knowledge_sources", "knowledge_chunks"]
    assert report["runtime_read_only"] and report["ingestor_dml"]


def test_migrate_refuses_wrong_session_role_before_ddl():
    conn = FakeConnection(user="neondb_owner")
    with pytest.raises(MigrationRefused):
        migrate(conn, "incubialab_knowledge_dev")
    assert not any("CREATE" in sql for sql in conn.executed)


@pytest.mark.parametrize("kwargs", [{"runtime_select": False}, {"runtime_write": True},
                                    {"ingest_dml": False}])
def test_migrate_fails_when_grants_do_not_converge(kwargs):
    with pytest.raises(MigrationRefused):
        migrate(FakeConnection(**kwargs), "incubialab_knowledge_dev")


def test_main_dry_run_validates_without_connecting(tmp_path, capsys):
    path = tmp_path / "k.env"
    path.write_text("\n".join(f"{k}={v}" for k, v in _env().items()))
    assert main(["--env-file", str(path)], environ={}) == 0
    out = capsys.readouterr().out
    assert "dry-run" in out and "s3cretpassword" not in out


def test_main_refusal_returns_2(tmp_path, capsys):
    path = tmp_path / "k.env"
    path.write_text("INCUBIA_KNOWLEDGE_NEON_BRANCH=production\n")
    assert main(["--env-file", str(path)], environ={}) == 2
