"""Scoped E3-05 export/import and restore support.

The backup format is a deterministic JSON envelope rather than a raw
``pg_dump``.  That is intentional: a Conversation restore must never carry
credentials, another tenant's rows, or provider-owned database metadata.  A
manifest commits the row counts and hashes before import; the importer checks
all conflicts in the same transaction that writes the rows.

Claims are not part of a backup.  They are ephemeral ownership state and are
cleared before a restored branch is returned to service.  A delivery which
was ``SENDING`` at the backup point is changed to ``UNKNOWN_EFFECT`` so a
restore cannot silently issue a second external effect.
"""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from incubia_orchestrator.foundation.contracts.execution import ExecutionScope


BACKUP_FORMAT = "incubia-e3-h1-ledger"
BACKUP_VERSION = "e3-h1-v1"
TABLES = ("inbox_events", "conversations", "turns", "outcomes", "deliveries")


class BackupError(RuntimeError):
    """Base class for errors that must leave the target unchanged."""


class BackupManifestError(BackupError):
    """The package is malformed, incomplete, or tampered with."""


class BackupConflict(BackupError):
    """A target row has the same identity but a different value."""


class BackupSchemaError(BackupError):
    """The E3-05 audit migration is not available on the target."""


@dataclass(frozen=True)
class ExportResult:
    path: Path
    manifest: dict[str, Any]
    table_counts: dict[str, int]
    export_duration_seconds: float


@dataclass(frozen=True)
class RestoreReport:
    import_id: str
    manifest_hash: str
    status: str
    idempotent: bool
    table_counts: dict[str, int]
    revision_min: int | None
    revision_max: int | None
    cleared_claims: int
    reconciled_unknown_effects: int
    rpo_seconds: float
    rto_seconds: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "import_id": self.import_id,
            "manifest_hash": self.manifest_hash,
            "status": self.status,
            "idempotent": self.idempotent,
            "table_counts": self.table_counts,
            "revision_min": self.revision_min,
            "revision_max": self.revision_max,
            "cleared_claims": self.cleared_claims,
            "reconciled_unknown_effects": self.reconciled_unknown_effects,
            "rpo_seconds": self.rpo_seconds,
            "rto_seconds": self.rto_seconds,
        }


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return sha256(_canonical(value).encode("utf-8")).hexdigest()


def _json_value(value: Any) -> Any:
    """Convert psycopg values into stable JSON values."""
    if isinstance(value, datetime):
        normalized = value if value.tzinfo else value.replace(tzinfo=UTC)
        return normalized.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if hasattr(value, "hex") and value.__class__.__name__ == "UUID":
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _now() -> datetime:
    return datetime.now(UTC)


def _timestamp(value: str | None) -> str | None:
    # PostgreSQL accepts both RFC3339 and the JSON backup's Z suffix.
    return value


def _scope_from_manifest(manifest: dict[str, Any]) -> tuple[str, str]:
    scope = manifest.get("scope")
    if not isinstance(scope, dict):
        raise BackupManifestError("manifest scope is missing")
    deployment_id, tenant_id = scope.get("deployment_id"), scope.get("tenant_id")
    if not isinstance(deployment_id, str) or not deployment_id:
        raise BackupManifestError("manifest deployment_id is missing")
    if not isinstance(tenant_id, str) or not tenant_id:
        raise BackupManifestError("manifest tenant_id is missing")
    return deployment_id, tenant_id


class PostgresLedgerBackup:
    """Export and restore one deployment/tenant scope using a direct DSN.

    The DSN is held only in memory and is never included in a package or a
    report.  For production-like evidence use the direct migrator DSN for
    restore and a pooled runtime DSN for export/read checks.
    """

    CONNECT_TIMEOUT_SECONDS = 10

    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("DATABASE_URL is required")
        self.database_url = database_url

    @staticmethod
    def _driver():
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - deployment dependency
            raise RuntimeError("Install psycopg to use PostgreSQL backup support") from exc
        return psycopg

    @contextmanager
    def _transaction(self, scope: tuple[str, str] | None = None) -> Iterator[Any]:
        connection = self._driver().connect(
            self.database_url, connect_timeout=self.CONNECT_TIMEOUT_SECONDS
        )
        try:
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                    if scope is not None:
                        cursor.execute(
                            "SELECT set_config('app.deployment_id', %s, true), "
                            "set_config('app.tenant_id', %s, true)", scope
                        )
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _queries(scope: tuple[str, str]) -> dict[str, tuple[str, tuple[Any, ...]]]:
        deployment_id, tenant_id = scope
        return {
            "inbox_events": (
                "SELECT deployment_id, tenant_id, channel, channel_account_ref, "
                "external_event_id, payload_hash, payload_json, request_id, execution_id, "
                "state, received_at, terminal_at FROM inbox_events "
                "WHERE deployment_id=%s AND tenant_id=%s "
                "ORDER BY channel, channel_account_ref, external_event_id",
                (deployment_id, tenant_id),
            ),
            "conversations": (
                "SELECT deployment_id, tenant_id, conversation_id, actor_id, revision "
                "FROM conversations WHERE deployment_id=%s AND tenant_id=%s "
                "ORDER BY conversation_id, actor_id",
                (deployment_id, tenant_id),
            ),
            "turns": (
                "SELECT execution_id, deployment_id, tenant_id, conversation_id, actor_id, "
                "user_text, assistant_text, created_at FROM turns "
                "WHERE deployment_id=%s AND tenant_id=%s ORDER BY execution_id",
                (deployment_id, tenant_id),
            ),
            "outcomes": (
                "SELECT execution_id, deployment_id, tenant_id, outcome_json, created_at "
                "FROM outcomes WHERE deployment_id=%s AND tenant_id=%s ORDER BY execution_id",
                (deployment_id, tenant_id),
            ),
            "deliveries": (
                "SELECT execution_id, deployment_id, tenant_id, response_id, destination_ref, "
                "payload_json, state, created_at FROM deliveries "
                "WHERE deployment_id=%s AND tenant_id=%s "
                "ORDER BY execution_id, response_id, destination_ref",
                (deployment_id, tenant_id),
            ),
        }

    @classmethod
    def _read_tables(cls, cursor: Any, scope: tuple[str, str]) -> dict[str, list[dict[str, Any]]]:
        column_names = {
            "inbox_events": ("deployment_id", "tenant_id", "channel", "channel_account_ref",
                              "external_event_id", "payload_hash", "payload_json", "request_id",
                              "execution_id", "state", "received_at", "terminal_at"),
            "conversations": ("deployment_id", "tenant_id", "conversation_id", "actor_id", "revision"),
            "turns": ("execution_id", "deployment_id", "tenant_id", "conversation_id", "actor_id",
                       "user_text", "assistant_text", "created_at"),
            "outcomes": ("execution_id", "deployment_id", "tenant_id", "outcome_json", "created_at"),
            "deliveries": ("execution_id", "deployment_id", "tenant_id", "response_id",
                           "destination_ref", "payload_json", "state", "created_at"),
        }
        result: dict[str, list[dict[str, Any]]] = {}
        for table in TABLES:
            sql, params = cls._queries(scope)[table]
            cursor.execute(sql, params)
            result[table] = [
                {name: _json_value(value) for name, value in zip(column_names[table], row)}
                for row in cursor.fetchall()
            ]
        return result

    @staticmethod
    def _table_hash(rows: list[dict[str, Any]]) -> str:
        return _digest(rows)

    @classmethod
    def _make_manifest(
        cls, scope: tuple[str, str], tables: dict[str, list[dict[str, Any]]],
        started_at: datetime, completed_at: datetime,
    ) -> dict[str, Any]:
        revisions = [row["revision"] for row in tables["conversations"]]
        table_meta = {
            table: {"count": len(rows), "sha256": cls._table_hash(rows)}
            for table, rows in tables.items()
        }
        manifest: dict[str, Any] = {
            "format": BACKUP_FORMAT,
            "version": BACKUP_VERSION,
            "export_id": str(uuid4()),
            "scope": {"deployment_id": scope[0], "tenant_id": scope[1]},
            "export_started_at": started_at.isoformat().replace("+00:00", "Z"),
            "export_completed_at": completed_at.isoformat().replace("+00:00", "Z"),
            "tables": table_meta,
            "revision_range": {
                "min": min(revisions) if revisions else None,
                "max": max(revisions) if revisions else None,
            },
            "claims_included": False,
        }
        manifest["manifest_sha256"] = _digest(manifest)
        manifest["content_sha256"] = _digest({"tables": tables, "table_meta": table_meta})
        return manifest

    def export(self, scope: ExecutionScope | tuple[str, str], destination: Path) -> ExportResult:
        if isinstance(scope, ExecutionScope):
            scope_values = (scope.deployment_id, scope.tenant_id)
        else:
            scope_values = scope
        if not all(isinstance(value, str) and value for value in scope_values):
            raise ValueError("deployment and tenant scope are required")
        started = _now()
        with self._transaction(scope_values) as connection:
            with connection.cursor() as cursor:
                tables = self._read_tables(cursor, scope_values)
        completed = _now()
        manifest = self._make_manifest(scope_values, tables, started, completed)
        package = {"manifest": manifest, "tables": tables}
        destination = Path(destination)
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
        temporary.write_text(_canonical(package) + "\n", encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(destination)
        destination.chmod(0o600)
        return ExportResult(
            destination, manifest,
            {table: len(rows) for table, rows in tables.items()},
            (completed - started).total_seconds(),
        )

    @staticmethod
    def _load_package(path: Path) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]], str]:
        try:
            package = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BackupManifestError(f"cannot read backup package ({type(exc).__name__})") from None
        if not isinstance(package, dict) or set(package) != {"manifest", "tables"}:
            raise BackupManifestError("backup package must contain only manifest and tables")
        manifest, tables = package["manifest"], package["tables"]
        if not isinstance(manifest, dict) or not isinstance(tables, dict):
            raise BackupManifestError("manifest and tables must be objects")
        if manifest.get("format") != BACKUP_FORMAT or manifest.get("version") != BACKUP_VERSION:
            raise BackupManifestError("unsupported backup format/version")
        if manifest.get("claims_included") is not False:
            raise BackupManifestError("claims must not be included in a ledger backup")
        _scope_from_manifest(manifest)
        if not isinstance(manifest.get("export_id"), str) or not manifest["export_id"]:
            raise BackupManifestError("manifest export_id is missing")
        supplied_manifest_hash = manifest.get("manifest_sha256")
        supplied_content_hash = manifest.get("content_sha256")
        if not isinstance(supplied_manifest_hash, str) or not isinstance(supplied_content_hash, str):
            raise BackupManifestError("manifest integrity hashes are missing")
        unsigned = dict(manifest)
        unsigned.pop("manifest_sha256", None)
        unsigned.pop("content_sha256", None)
        if _digest(unsigned) != supplied_manifest_hash:
            raise BackupManifestError("manifest hash mismatch")
        if set(tables) != set(TABLES) or not isinstance(manifest.get("tables"), dict):
            raise BackupManifestError("backup must contain every ledger table")
        normalized: dict[str, list[dict[str, Any]]] = {}
        for table in TABLES:
            rows = tables[table]
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise BackupManifestError(f"{table} rows are malformed")
            metadata = manifest.get("tables", {}).get(table)
            if not isinstance(metadata, dict) or metadata.get("count") != len(rows):
                raise BackupManifestError(f"{table} count does not match manifest")
            if metadata.get("sha256") != _digest(rows):
                raise BackupManifestError(f"{table} hash mismatch")
            deployment_id, tenant_id = _scope_from_manifest(manifest)
            for row in rows:
                if row.get("deployment_id") != deployment_id or row.get("tenant_id") != tenant_id:
                    raise BackupManifestError(f"{table} contains a row outside the manifest scope")
            normalized[table] = rows
        if _digest({"tables": normalized, "table_meta": manifest["tables"]}) != supplied_content_hash:
            raise BackupManifestError("backup content hash mismatch")
        revision_range = manifest.get("revision_range")
        revisions = [row.get("revision") for row in normalized["conversations"]]
        expected_range = {
            "min": min(revisions) if revisions else None,
            "max": max(revisions) if revisions else None,
        }
        if revision_range != expected_range:
            raise BackupManifestError("revision range does not match conversation rows")
        return manifest, normalized, supplied_manifest_hash

    @staticmethod
    def _key(table: str, row: dict[str, Any]) -> tuple[Any, ...]:
        fields = {
            "inbox_events": ("deployment_id", "tenant_id", "channel", "channel_account_ref", "external_event_id"),
            "conversations": ("deployment_id", "tenant_id", "conversation_id", "actor_id"),
            "turns": ("execution_id",),
            "outcomes": ("execution_id",),
            "deliveries": ("execution_id", "response_id", "destination_ref"),
        }[table]
        return tuple(row.get(field) for field in fields)

    @staticmethod
    def _same_row(table: str, expected: dict[str, Any], actual: dict[str, Any]) -> bool:
        if expected == actual:
            return True
        # An interrupted provider send is intentionally reconciled on restore.
        # It is safe to accept the post-restore state as the same logical row.
        if table == "deliveries" and expected.get("state") == "SENDING" \
                and actual.get("state") == "UNKNOWN_EFFECT":
            candidate = dict(actual)
            candidate["state"] = "SENDING"
            return candidate == expected
        return False

    @classmethod
    def _existing_rows(cls, cursor: Any, table: str, scope: tuple[str, str]) -> dict[tuple[Any, ...], dict[str, Any]]:
        rows = cls._read_tables(cursor, scope)[table]
        return {cls._key(table, row): row for row in rows}

    @classmethod
    def _check_conflicts(
        cls, cursor: Any, scope: tuple[str, str], tables: dict[str, list[dict[str, Any]]]
    ) -> None:
        for table in TABLES:
            current = cls._existing_rows(cursor, table, scope)
            for expected in tables[table]:
                key = cls._key(table, expected)
                actual = current.get(key)
                if actual is not None and not cls._same_row(table, expected, actual):
                    raise BackupConflict(f"{table} row conflict for key {key!r}")

    @staticmethod
    def _insert_rows(cursor: Any, tables: dict[str, list[dict[str, Any]]]) -> None:
        for row in tables["inbox_events"]:
            cursor.execute(
                "INSERT INTO inbox_events (deployment_id, tenant_id, channel, channel_account_ref, "
                "external_event_id, payload_hash, payload_json, request_id, execution_id, state, "
                "received_at, terminal_at) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::uuid,%s::uuid,%s,%s,%s) "
                "ON CONFLICT DO NOTHING",
                (row["deployment_id"], row["tenant_id"], row["channel"], row["channel_account_ref"],
                 row["external_event_id"], row["payload_hash"], _canonical(row["payload_json"]),
                 row["request_id"], row["execution_id"], row["state"], _timestamp(row["received_at"]),
                 _timestamp(row["terminal_at"])),
            )
        for row in tables["conversations"]:
            cursor.execute(
                "INSERT INTO conversations (deployment_id,tenant_id,conversation_id,actor_id,revision) "
                "VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (row["deployment_id"], row["tenant_id"], row["conversation_id"], row["actor_id"], row["revision"]),
            )
        for row in tables["turns"]:
            cursor.execute(
                "INSERT INTO turns (execution_id,deployment_id,tenant_id,conversation_id,actor_id,"
                "user_text,assistant_text,created_at) VALUES (%s::uuid,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (row["execution_id"], row["deployment_id"], row["tenant_id"], row["conversation_id"],
                 row["actor_id"], row["user_text"], row["assistant_text"], _timestamp(row["created_at"])),
            )
        for row in tables["outcomes"]:
            cursor.execute(
                "INSERT INTO outcomes (execution_id,deployment_id,tenant_id,outcome_json,created_at) "
                "VALUES (%s::uuid,%s,%s,%s::jsonb,%s) ON CONFLICT DO NOTHING",
                (row["execution_id"], row["deployment_id"], row["tenant_id"],
                 _canonical(row["outcome_json"]), _timestamp(row["created_at"])),
            )
        for row in tables["deliveries"]:
            cursor.execute(
                "INSERT INTO deliveries (execution_id,deployment_id,tenant_id,response_id,destination_ref,"
                "payload_json,state,created_at) VALUES (%s::uuid,%s,%s,%s,%s,%s::jsonb,%s,%s) ON CONFLICT DO NOTHING",
                (row["execution_id"], row["deployment_id"], row["tenant_id"], row["response_id"],
                 row["destination_ref"], _canonical(row["payload_json"]), row["state"],
                 _timestamp(row["created_at"])),
            )

    @staticmethod
    def _require_audit_table(cursor: Any) -> None:
        cursor.execute("SELECT to_regclass('public.ledger_imports')")
        if cursor.fetchone()[0] is None:
            raise BackupSchemaError("005_e3_h1_backup.sql is not applied")

    @staticmethod
    def _audit_running(cursor: Any, manifest: dict[str, Any], manifest_hash: str) -> tuple[str, bool]:
        import_id = manifest["export_id"]
        scope = manifest["scope"]
        cursor.execute(
            "SELECT import_id,status FROM ledger_imports WHERE manifest_hash=%s FOR UPDATE",
            (manifest_hash,),
        )
        existing = cursor.fetchone()
        if existing is not None:
            if existing[1] == "COMPLETED":
                return str(existing[0]), True
            cursor.execute(
                "UPDATE ledger_imports SET status='RUNNING', error_code=NULL, started_at=clock_timestamp(), "
                "completed_at=NULL WHERE manifest_hash=%s",
                (manifest_hash,),
            )
            return str(existing[0]), False
        cursor.execute(
            "INSERT INTO ledger_imports (import_id,manifest_hash,deployment_id,tenant_id,manifest_version,"
            "status,table_counts,revision_min,revision_max) VALUES (%s,%s,%s,%s,%s,'RUNNING',%s::jsonb,%s,%s)",
            (import_id, manifest_hash, scope["deployment_id"], scope["tenant_id"], manifest["version"],
             _canonical({table: metadata["count"] for table, metadata in manifest["tables"].items()}),
             manifest["revision_range"]["min"], manifest["revision_range"]["max"]),
        )
        return import_id, False

    def _record_failure(self, manifest: dict[str, Any], manifest_hash: str, error_code: str) -> None:
        # Best effort audit outside the rolled-back data transaction.  Never
        # include exception text: SQL diagnostics may contain connection data.
        try:
            with self._transaction() as connection:
                with connection.cursor() as cursor:
                    self._require_audit_table(cursor)
                    scope = manifest["scope"]
                    cursor.execute(
                        "INSERT INTO ledger_imports (import_id,manifest_hash,deployment_id,tenant_id,"
                        "manifest_version,status,table_counts,revision_min,revision_max,error_code) "
                        "VALUES (%s,%s,%s,%s,%s,'FAILED',%s::jsonb,%s,%s,%s) "
                        "ON CONFLICT (manifest_hash) DO UPDATE SET status='FAILED',error_code=EXCLUDED.error_code,"
                        "completed_at=clock_timestamp()",
                        (manifest["export_id"], manifest_hash, scope["deployment_id"], scope["tenant_id"],
                         manifest["version"], _canonical({table: metadata["count"] for table, metadata in manifest["tables"].items()}),
                         manifest["revision_range"]["min"], manifest["revision_range"]["max"], error_code),
                    )
        except Exception:
            pass

    def import_package(
        self, package_path: Path, *, expected_scope: ExecutionScope | tuple[str, str] | None = None,
        clear_claims: bool = True,
    ) -> RestoreReport:
        manifest, tables, manifest_hash = self._load_package(Path(package_path))
        package_scope = _scope_from_manifest(manifest)
        if expected_scope is not None:
            expected = (expected_scope.deployment_id, expected_scope.tenant_id) \
                if isinstance(expected_scope, ExecutionScope) else expected_scope
            if tuple(expected) != package_scope:
                raise BackupManifestError("restore target scope does not match manifest scope")
        started_monotonic = time.monotonic()
        export_completed = datetime.fromisoformat(manifest["export_completed_at"].replace("Z", "+00:00"))
        rpo_seconds = max(0.0, (_now() - export_completed).total_seconds())
        try:
            with self._transaction(package_scope) as connection:
                with connection.cursor() as cursor:
                    self._require_audit_table(cursor)
                    import_id, idempotent = self._audit_running(cursor, manifest, manifest_hash)
                    self._check_conflicts(cursor, package_scope, tables)
                    if not idempotent:
                        self._insert_rows(cursor, tables)
                    cleared_claims = 0
                    if clear_claims:
                        cursor.execute(
                            "DELETE FROM resource_claims WHERE deployment_id=%s AND tenant_id=%s",
                            package_scope,
                        )
                        cleared_claims = cursor.rowcount
                    cursor.execute(
                        "UPDATE deliveries SET state='UNKNOWN_EFFECT' WHERE deployment_id=%s AND tenant_id=%s "
                        "AND state='SENDING'",
                        package_scope,
                    )
                    reconciled_unknown_effects = cursor.rowcount
                    # A processing event without a durable outcome is safe to
                    # replay. Events with an outcome remain terminal.
                    cursor.execute(
                        "UPDATE inbox_events AS event SET state='RECEIVED' WHERE event.deployment_id=%s "
                        "AND event.tenant_id=%s AND event.state='PROCESSING' AND NOT EXISTS ("
                        "SELECT 1 FROM outcomes AS outcome WHERE outcome.execution_id=event.execution_id "
                        "AND outcome.deployment_id=event.deployment_id AND outcome.tenant_id=event.tenant_id)",
                        package_scope,
                    )
                    cursor.execute(
                        "UPDATE ledger_imports SET status='COMPLETED',completed_at=clock_timestamp(), "
                        "rpo_seconds=%s,rto_seconds=%s,reconciled_unknown_effects=%s,cleared_claims=%s "
                        "WHERE manifest_hash=%s",
                        (rpo_seconds, max(0.0, time.monotonic() - started_monotonic),
                         reconciled_unknown_effects, cleared_claims, manifest_hash),
                    )
            rto_seconds = max(0.0, time.monotonic() - started_monotonic)
            return RestoreReport(
                import_id, manifest_hash, "COMPLETED", idempotent,
                {table: len(rows) for table, rows in tables.items()},
                manifest["revision_range"]["min"], manifest["revision_range"]["max"],
                cleared_claims, reconciled_unknown_effects, rpo_seconds, rto_seconds,
            )
        except BackupError as exc:
            self._record_failure(manifest, manifest_hash, type(exc).__name__)
            raise
        except Exception:
            self._record_failure(manifest, manifest_hash, "DATABASE_ERROR")
            raise


__all__ = [
    "BACKUP_FORMAT", "BACKUP_VERSION", "BackupConflict", "BackupError",
    "BackupManifestError", "BackupSchemaError", "ExportResult", "PostgresLedgerBackup",
    "RestoreReport",
]
