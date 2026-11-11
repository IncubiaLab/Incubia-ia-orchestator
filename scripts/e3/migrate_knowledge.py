"""Apply the Knowledge schema to the isolated RAG IncubiaLab Neon branch.

Reads ``deploy/knowledge-neon.env`` (or ``--env-file``), overlaid by the process
environment. Dry-run by default: ``--apply`` is required to connect. Only
``001_knowledge.sql`` runs; HNSW (002) stays opt-in after the exact-search
baseline. See docs/roadmap/etapa-3/NEON-KNOWLEDGE-DEV.md.

Fail-closed: the branch must be the dedicated ``feat-knowledge-base`` branch,
the DSN must be the direct (non-pooled) TLS DSN of ``incubia_kb_migrator``, and
after DDL the runtime/ingestor grants must have converged. Nothing secret is
printed; the DSN is reported only as a sanitized digest.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Mapping
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.e3.neon_branch_guard import (  # noqa: E402
    BranchGuardError, require_isolated_branch, sanitize_dsn_reference)

EXPECTED_BRANCH = "feat-knowledge-base"
MIGRATOR_ROLE = "incubia_kb_migrator"
RUNTIME_ROLE = "incubia_kb_runtime"
INGEST_ROLE = "incubia_kb_ingestor"
MIGRATION = ROOT / "migrations/knowledge/001_knowledge.sql"
TABLES = ("knowledge_generations", "knowledge_sources", "knowledge_chunks")
DEFAULT_ENV_FILE = ROOT / "deploy/knowledge-neon.env"


class MigrationRefused(RuntimeError):
    pass


def load_env_file(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def validate_env(env: Mapping[str, str]) -> str:
    try:
        require_isolated_branch(env.get("INCUBIA_KNOWLEDGE_NEON_BRANCH"), expected=EXPECTED_BRANCH)
    except BranchGuardError as exc:
        raise MigrationRefused(str(exc)) from None
    database = env.get("INCUBIA_KNOWLEDGE_DATABASE", "")
    dsn = env.get("INCUBIA_KNOWLEDGE_MIGRATION_DATABASE_URL", "")
    parts = urlsplit(dsn)
    host = parts.hostname or ""
    if (parts.scheme not in {"postgres", "postgresql"}
            or not host.endswith(".neon.tech") or "-pooler." in host
            or unquote(parts.username or "") != MIGRATOR_ROLE
            or not parts.password or "REPLACE" in dsn
            or not database or unquote(parts.path.lstrip("/")) != database
            or parse_qs(parts.query).get("sslmode") != ["require"]):
        raise MigrationRefused(
            f"INCUBIA_KNOWLEDGE_MIGRATION_DATABASE_URL must be the direct TLS Neon DSN of "
            f"{MIGRATOR_ROLE} for INCUBIA_KNOWLEDGE_DATABASE")
    return dsn


def migrate(connection, database: str) -> dict:
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_user, current_database()")
        if cursor.fetchone() != (MIGRATOR_ROLE, database):
            raise MigrationRefused("Session is not the Knowledge migrator on the expected database")
        cursor.execute(MIGRATION.read_text())
        for table in TABLES:
            cursor.execute("SELECT to_regclass(%s)", (f"public.{table}",))
            if cursor.fetchone()[0] is None:
                raise MigrationRefused("Knowledge table missing after migration")
            cursor.execute("SELECT tableowner FROM pg_tables WHERE schemaname='public' AND tablename=%s",
                           (table,))
            if cursor.fetchone() != (MIGRATOR_ROLE,):
                raise MigrationRefused("Knowledge table is not owned by the migrator")
            cursor.execute("SELECT has_table_privilege(%s, %s, 'SELECT'), "
                           "has_table_privilege(%s, %s, 'INSERT,UPDATE,DELETE,TRUNCATE')",
                           (RUNTIME_ROLE, f"public.{table}", RUNTIME_ROLE, f"public.{table}"))
            if cursor.fetchone() != (True, False):
                raise MigrationRefused("Runtime grants did not converge to read only")
            cursor.execute("SELECT has_table_privilege(%s, %s, 'SELECT,INSERT,UPDATE,DELETE')",
                           (INGEST_ROLE, f"public.{table}"))
            if cursor.fetchone() != (True,):
                raise MigrationRefused("Ingestor grants did not converge to DML")
    connection.commit()
    return {"tables": list(TABLES), "runtime_read_only": True, "ingestor_dml": True}


def main(argv: list[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--apply", action="store_true", help="connect and apply 001_knowledge.sql")
    args = parser.parse_args(argv)
    env = load_env_file(args.env_file) if args.env_file.is_file() else {}
    env.update({k: v for k, v in (os.environ if environ is None else environ).items()
                if k.startswith("INCUBIA_KNOWLEDGE_")})
    try:
        dsn = validate_env(env)
        target = sanitize_dsn_reference(dsn)
    except (MigrationRefused, BranchGuardError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    if not args.apply:
        print(f"dry-run ok: branch={EXPECTED_BRANCH} target={target}; pass --apply to migrate")
        return 0
    try:
        import psycopg
        with psycopg.connect(dsn, connect_timeout=10) as connection:
            if not connection.pgconn.ssl_in_use:
                raise MigrationRefused("Client TLS is not in use")
            report = migrate(connection, env["INCUBIA_KNOWLEDGE_DATABASE"])
    except MigrationRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"migration failed ({type(exc).__name__})", file=sys.stderr)
        return 1
    print(f"migrated: target={target} tables={','.join(report['tables'])} "
          f"runtime=read-only ingestor=dml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
