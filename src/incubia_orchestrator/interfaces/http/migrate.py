"""One-shot E3-D0 PostgreSQL migration entry point."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from incubia_orchestrator.modules.conversation.adapters.persistence.postgres import PostgresLedger


def migration_files() -> tuple[Path, ...]:
    configured = os.getenv("INCUBIA_D0_MIGRATION_PATH")
    if configured:
        paths = (Path(configured),)
    else:
        root = Path.cwd() / "migrations/postgres"
        # D0 keeps an explicit, small migration chain.  006 supplies the
        # claim table used by the claim-aware HTTP runtime without requiring
        # the full H1 role/RLS/dispatcher chain.
        paths = (root / "001_e3_d0_ledger.sql", root / "006_e3_d0_runtime_claims.sql")
    missing = tuple(path for path in paths if not path.is_file())
    if missing:
        raise RuntimeError("E3-D0 migration file is unavailable")
    return paths


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        logging.getLogger(__name__).error("e3_d0_migration_failed reason=missing_database_url")
        return 1
    try:
        paths = migration_files()
        ledger = PostgresLedger(database_url)
        for path in paths:
            ledger.migrate(path)
    except Exception as exc:
        # Do not render a connection string or a driver exception in logs.
        logging.getLogger(__name__).error("e3_d0_migration_failed type=%s", type(exc).__name__)
        return 1
    logging.getLogger(__name__).info(
        "e3_d0_migration_applied versions=%s",
        ",".join(path.name for path in paths),
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
