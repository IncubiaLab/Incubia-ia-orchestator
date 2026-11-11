#!/usr/bin/env python3
"""Run the E3-05 scoped backup/restore flow without printing DSNs.

Examples (credentials stay in the environment or ignored local env file)::

    python scripts/e3/h1_backup.py export \
      --database-url-env DATABASE_URL --deployment-id d --tenant-id t \
      --output evals/results/e3-h1-backup.json

    python scripts/e3/h1_backup.py import \
      --database-url-env INCUBIA_MIGRATION_DATABASE_URL \
      --package evals/results/e3-h1-backup.json

The command output is a sanitized manifest/report only; no payload or
connection string is emitted.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from incubia_orchestrator.foundation.contracts.execution import ExecutionScope  # noqa: E402
from incubia_orchestrator.modules.conversation.adapters.persistence.postgres.backup import (  # noqa: E402
    PostgresLedgerBackup,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="E3-05 scoped PostgreSQL backup/restore")
    subparsers = parser.add_subparsers(dest="operation", required=True)

    export = subparsers.add_parser("export", help="export one deployment/tenant scope")
    export.add_argument("--database-url-env", default="DATABASE_URL")
    export.add_argument("--deployment-id", required=True)
    export.add_argument("--tenant-id", required=True)
    export.add_argument("--output", type=Path, required=True)

    restore = subparsers.add_parser("import", help="import and reconcile one backup package")
    restore.add_argument("--database-url-env", default="INCUBIA_MIGRATION_DATABASE_URL")
    restore.add_argument("--package", type=Path, required=True)
    restore.add_argument("--deployment-id")
    restore.add_argument("--tenant-id")
    restore.add_argument("--keep-claims", action="store_true", help="for diagnostics only; do not use for service")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    variable = args.database_url_env
    database_url = os.environ.get(variable)
    if not database_url:
        print(f"{variable} is required", file=sys.stderr)
        return 2
    backup = PostgresLedgerBackup(database_url)
    if args.operation == "export":
        result = backup.export(
            ExecutionScope(args.deployment_id, args.tenant_id, "backup", "backup"), args.output
        )
        print(json.dumps({
            "operation": "export",
            "path": str(result.path),
            "manifest": result.manifest,
            "table_counts": result.table_counts,
            "export_duration_seconds": result.export_duration_seconds,
        }, sort_keys=True))
        return 0

    scope = None
    if bool(args.deployment_id) != bool(args.tenant_id):
        print("--deployment-id and --tenant-id must be provided together", file=sys.stderr)
        return 2
    if args.deployment_id:
        scope = (args.deployment_id, args.tenant_id)
    report = backup.import_package(args.package, expected_scope=scope, clear_claims=not args.keep_claims)
    print(json.dumps({"operation": "import", **report.as_dict()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
