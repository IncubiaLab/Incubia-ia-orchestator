"""One-shot E3-D0 PostgreSQL migration entry point."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from incubia_orchestrator.modules.conversation.adapters.persistence.postgres import PostgresLedger


def migration_file() -> Path:
    configured = os.getenv("INCUBIA_D0_MIGRATION_PATH")
    path = Path(configured) if configured else Path.cwd() / "migrations/postgres/001_e3_d0_ledger.sql"
    if not path.is_file():
        raise RuntimeError("E3-D0 migration file is unavailable")
    return path


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        logging.getLogger(__name__).error("e3_d0_migration_failed reason=missing_database_url")
        return 1
    try:
        path = migration_file()
        PostgresLedger(database_url).migrate(path)
    except Exception as exc:
        # Do not render a connection string or a driver exception in logs.
        logging.getLogger(__name__).error("e3_d0_migration_failed type=%s", type(exc).__name__)
        return 1
    logging.getLogger(__name__).info("e3_d0_migration_applied version=%s", path.name)
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
