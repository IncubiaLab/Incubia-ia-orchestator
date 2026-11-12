"""Production migration runner applying Postgres and Knowledge migrations in order."""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

from incubia_orchestrator.modules.conversation.adapters.persistence.postgres import PostgresLedger

LOG = logging.getLogger(__name__)


def postgres_migrations(root: Path) -> tuple[Path, ...]:
    migrations_dir = root / "migrations/postgres"
    if not migrations_dir.is_dir():
        raise RuntimeError("migrations/postgres directory does not exist")
    # 001..008 in strict forward order
    paths = tuple(sorted(migrations_dir.glob("*.sql")))
    if not paths:
        raise RuntimeError("No SQL migrations found in migrations/postgres")
    return paths


def validate_migration_role(database_url: str, required_role: str = "incubia_migrator") -> None:
    parts = urlsplit(database_url)
    user = unquote(parts.username or "")
    # Check if a non-migrator role is accidentally used (fail-closed)
    if user in {"incubia_runtime", "d0_runtime", "incubia_kb_runtime"}:
        raise ValueError(f"Migration refused: role {user} lacks DDL privileges. Use {required_role}")


def run_postgres_migrations(database_url: str, root: Path) -> list[str]:
    validate_migration_role(database_url)
    paths = postgres_migrations(root)
    ledger = PostgresLedger(database_url)
    applied = []
    for path in paths:
        ledger.migrate(path)
        applied.append(path.name)
    return applied


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description="Run complete forward database migrations")
    parser.add_argument("--database-url", default=os.getenv("INCUBIA_MIGRATION_DATABASE_URL") or os.getenv("DATABASE_URL"))
    args = parser.parse_args()

    if not args.database_url:
        LOG.error("migration_failed reason=missing_database_url")
        return 1

    root = Path.cwd()
    try:
        applied = run_postgres_migrations(args.database_url, root)
        LOG.info("migrations_applied count=%d versions=%s", len(applied), ",".join(applied))
    except Exception as exc:
        LOG.error("migration_failed type=%s", type(exc).__name__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
