"""Prepare the isolated E3-H1 Neon branch without exposing credentials."""
from __future__ import annotations

import argparse
import os
import re
import secrets
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[2]
BRANCH = "e3-h1-synthetic"
DATABASE = "neondb"
NEON_CLI = "neon@8.3.3"
RUNTIME_ROLE = "incubia_runtime"
MIGRATOR_ROLE = "incubia_migrator"
OUTPUT = ROOT / "deploy/e3-neon.env"
DSN_RE = re.compile(r"postgres(?:ql)?://[^\s\"'<>]+", re.IGNORECASE)


class PreparationError(RuntimeError):
    pass


def _run_neon_connection(role: str, *, pooled: bool = False) -> str:
    command = [
        "npx", "--yes", NEON_CLI, "connection-string", BRANCH,
        "--role-name", role, "--database-name", DATABASE,
        "--ssl", "require", "--output", "json", "--analytics", "false",
    ]
    if pooled:
        command.append("--pooled")
    try:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise PreparationError("Neon CLI could not be started") from None
    if result.returncode:
        raise PreparationError(f"Neon CLI could not resolve the {role} connection")
    matches = DSN_RE.findall(result.stdout)
    if not matches:
        raise PreparationError(f"Neon CLI returned no {role} connection URL")
    return _normalize_and_validate_dsn(matches[-1], role=role, pooled=pooled)


def _normalize_and_validate_dsn(dsn: str, *, role: str, pooled: bool) -> str:
    parts = urlsplit(dsn)
    if parts.scheme not in {"postgres", "postgresql"} or not parts.hostname:
        raise PreparationError("Neon returned an invalid PostgreSQL URL")
    hostname = parts.hostname.lower()
    if not hostname.endswith(".neon.tech"):
        raise PreparationError("Refusing to save a URL outside Neon")
    username = unquote(parts.username or "")
    if username != role:
        raise PreparationError(f"Neon returned a URL for an unexpected role ({role})")
    if (parts.path or "").lstrip("/") != DATABASE:
        raise PreparationError("Neon returned a URL for an unexpected database")
    if pooled != ("-pooler." in hostname):
        raise PreparationError("Neon returned the wrong direct/pooled endpoint type")
    query = parse_qs(parts.query)
    if query.get("sslmode", [None])[0] not in {"require", "verify-ca", "verify-full"}:
        raise PreparationError("Neon connection URL does not require TLS")
    # Percent-encode credentials so the local env file remains safe to source
    # from a shell and parse as a dotenv file even if Neon rotates its alphabet.
    password = unquote(parts.password or "")
    userinfo = quote(username, safe="") + ":" + quote(password, safe="")
    netloc = userinfo + "@" + parts.netloc.rsplit("@", 1)[-1]
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _admin_connection() -> str:
    # Used only in memory for the one-time grants. It is never written or logged.
    return _run_neon_connection("neondb_owner")


def _provision_sql_roles_and_grants(admin_dsn: str) -> tuple[str, str]:
    try:
        import psycopg
        from psycopg import sql
    except ImportError as exc:  # pragma: no cover - depends on deployment extra
        raise PreparationError("Install the deployment extra to prepare Neon roles") from None
    runtime_password = secrets.token_urlsafe(48)
    migrator_password = secrets.token_urlsafe(48)
    admin_parts = urlsplit(admin_dsn)
    if not admin_parts.hostname or "-pooler." in admin_parts.hostname:
        raise PreparationError("Admin connection must use the direct Neon endpoint")
    runtime_host = admin_parts.hostname.replace(".", "-pooler.", 1)
    runtime_url = _build_dsn(RUNTIME_ROLE, runtime_password, runtime_host, admin_parts.query)
    migrator_url = _build_dsn(MIGRATOR_ROLE, migrator_password, admin_parts.hostname, admin_parts.query)
    env_written = False
    try:
        with psycopg.connect(admin_dsn, connect_timeout=10, sslmode="require") as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT current_user, current_database(), rolcreaterole "
                    "FROM pg_roles WHERE rolname=current_user"
                )
                owner = cursor.fetchone()
                if owner != ("neondb_owner", DATABASE, True):
                    raise PreparationError("Admin session is not the expected Neon owner with CREATEROLE")
                cursor.execute(
                    "SELECT rolname "
                    "FROM pg_roles WHERE rolname IN (%s, %s)",
                    (RUNTIME_ROLE, MIGRATOR_ROLE),
                )
                if cursor.fetchall():
                    raise PreparationError("Target SQL roles already exist; refusing to rotate or overwrite credentials")
                for role, password in ((RUNTIME_ROLE, runtime_password), (MIGRATOR_ROLE, migrator_password)):
                    cursor.execute(sql.SQL(
                        "CREATE ROLE {} WITH LOGIN NOINHERIT NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD {}"
                    ).format(sql.Identifier(role), sql.Literal(password)))

                cursor.execute(
                    "SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolbypassrls "
                    "FROM pg_roles WHERE rolname IN (%s, %s)",
                    (RUNTIME_ROLE, MIGRATOR_ROLE),
                )
                role_flags = cursor.fetchall()
                if len(role_flags) != 2 or any(any(row[1:]) for row in role_flags):
                    raise PreparationError("SQL-created roles did not converge to non-privileged attributes")
                cursor.execute(
                    "SELECT pg_has_role(%s, %s, 'MEMBER'), pg_has_role(%s, %s, 'MEMBER')",
                    (RUNTIME_ROLE, "neondb_owner", MIGRATOR_ROLE, "neondb_owner"),
                )
                membership = cursor.fetchone()
                if membership and any(membership):
                    raise PreparationError("Application roles must not inherit neondb_owner")
                cursor.execute("SELECT current_database()")
                if cursor.fetchone()[0] != DATABASE:
                    raise PreparationError("Admin connection reached an unexpected database")

                cursor.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}, {}").format(
                    sql.Identifier(DATABASE), sql.Identifier(MIGRATOR_ROLE), sql.Identifier(RUNTIME_ROLE)
                ))
                # The branch is dedicated to this synthetic H1 campaign. Remove
                # PostgreSQL's inherited PUBLIC CREATE right, then grant DDL only
                # to the migration identity.
                cursor.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
                cursor.execute(sql.SQL("GRANT USAGE, CREATE ON SCHEMA public TO {}").format(
                    sql.Identifier(MIGRATOR_ROLE)
                ))
                cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(
                    sql.Identifier(RUNTIME_ROLE)
                ))
                cursor.execute(sql.SQL("REVOKE CREATE ON SCHEMA public FROM {}").format(
                    sql.Identifier(RUNTIME_ROLE)
                ))
                cursor.execute(
                    "SELECT has_schema_privilege(%s, 'public', 'CREATE'), "
                    "has_schema_privilege(%s, 'public', 'CREATE')",
                    (RUNTIME_ROLE, MIGRATOR_ROLE),
                )
                runtime_create, migrator_create = cursor.fetchone()
                if runtime_create or not migrator_create:
                    raise PreparationError("Neon schema DDL grants did not converge to the least-privilege state")
                _write_local_env(runtime_url, migrator_url)
                env_written = True
    except PreparationError:
        if env_written:
            OUTPUT.unlink(missing_ok=True)
        raise
    except Exception as exc:
        # Database exceptions can contain host/user details; keep output generic.
        if env_written:
            OUTPUT.unlink(missing_ok=True)
        raise PreparationError(f"Neon role grants failed ({type(exc).__name__})") from None
    return runtime_url, migrator_url


def inspect_roles() -> None:
    """Print only role-attribute metadata needed to resolve a privilege blocker."""
    try:
        import psycopg
    except ImportError:
        raise PreparationError("Install the deployment extra to inspect Neon roles") from None
    dsn = _admin_connection()
    try:
        with psycopg.connect(dsn, connect_timeout=10, sslmode="require") as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolbypassrls "
                    "FROM pg_roles WHERE rolname IN (current_user, %s, %s) ORDER BY rolname",
                    (RUNTIME_ROLE, MIGRATOR_ROLE),
                )
                for role, superuser, createdb, createrole, bypassrls in cursor.fetchall():
                    flags = ",".join(
                        name for name, enabled in (
                            ("SUPERUSER", superuser), ("CREATEDB", createdb),
                            ("CREATEROLE", createrole), ("BYPASSRLS", bypassrls),
                        ) if enabled
                    ) or "none"
                    print(f"{role}: privileged_attributes={flags}")
    except Exception as exc:
        raise PreparationError(f"Neon role inspection failed ({type(exc).__name__})") from None


def _build_dsn(role: str, password: str, hostname: str, query: str) -> str:
    if not hostname.endswith(".neon.tech"):
        raise PreparationError("Refusing to construct a URL outside Neon")
    username = quote(role, safe="")
    encoded_password = quote(password, safe="")
    return urlunsplit(("postgresql", f"{username}:{encoded_password}@{hostname}", f"/{DATABASE}", query, ""))


def _write_local_env(runtime_url: str, migrator_url: str) -> None:
    if OUTPUT.exists():
        raise PreparationError("deploy/e3-neon.env already exists; move it aside manually before regeneration")
    content = (
        f"INCUBIA_E3_NEON_BRANCH={BRANCH}\n"
        f"DATABASE_URL={shlex.quote(runtime_url)}\n"
        f"INCUBIA_MIGRATION_DATABASE_URL={shlex.quote(migrator_url)}\n"
        "INCUBIA_E3_DB_POOL_MAX=4\n"
    )
    OUTPUT.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".e3-neon-", dir=OUTPUT.parent, text=True)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, OUTPUT)
        os.chmod(OUTPUT, 0o600)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def quote_existing_env() -> None:
    """Repair shell quoting of this tool's local DSN file without printing it."""
    if not OUTPUT.is_file():
        raise PreparationError("deploy/e3-neon.env does not exist")
    values = {}
    try:
        for line in OUTPUT.read_text(encoding="utf-8").splitlines():
            key, value = line.split("=", 1)
            values[key] = value
        runtime = _normalize_and_validate_dsn(values["DATABASE_URL"], role=RUNTIME_ROLE, pooled=True)
        migrator = _normalize_and_validate_dsn(
            values["INCUBIA_MIGRATION_DATABASE_URL"], role=MIGRATOR_ROLE, pooled=False
        )
        if values.get("INCUBIA_E3_NEON_BRANCH") != BRANCH:
            raise PreparationError("Local env file has an unexpected branch value")
        runtime_parts, migrator_parts = urlsplit(runtime), urlsplit(migrator)
        if runtime_parts.hostname.replace("-pooler.", ".", 1) != migrator_parts.hostname:
            raise PreparationError("Local DSNs do not identify the same endpoint")
        content = (
            f"INCUBIA_E3_NEON_BRANCH={BRANCH}\n"
            f"DATABASE_URL={shlex.quote(runtime)}\n"
            f"INCUBIA_MIGRATION_DATABASE_URL={shlex.quote(migrator)}\n"
            "INCUBIA_E3_DB_POOL_MAX=4\n"
        )
        fd, temp_name = tempfile.mkstemp(prefix=".e3-neon-", dir=OUTPUT.parent, text=True)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, OUTPUT)
            os.chmod(OUTPUT, 0o600)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise
    except (KeyError, ValueError) as exc:
        raise PreparationError("Local Neon env file is malformed; credentials were not printed") from None
    print("Quoted deploy/e3-neon.env safely for shell use; credentials were not displayed.")


def prepare() -> None:
    if OUTPUT.exists():
        raise PreparationError("deploy/e3-neon.env already exists; move it aside manually before regeneration")
    admin_dsn = _admin_connection()
    _provision_sql_roles_and_grants(admin_dsn)
    print("Prepared deploy/e3-neon.env (0600); DSNs were not displayed or written to logs.")
    print("SQL roles are NOBYPASSRLS; runtime is pooled TLS and migrator is direct TLS.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "inspect-roles", "quote-local-env"))
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare()
        elif args.command == "inspect-roles":
            inspect_roles()
        elif args.command == "quote-local-env":
            quote_existing_env()
    except PreparationError as exc:
        print(f"E3-H1 preparation stopped: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
