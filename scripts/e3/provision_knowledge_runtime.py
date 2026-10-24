"""Provision the read-only Knowledge identity in a migrated deployment database.

Set INCUBIA_E3_KNOWLEDGE_ADMIN_DSN to a direct Neon owner URL and
INCUBIA_E3_KNOWLEDGE_RUNTIME_PASSWORD to a newly generated password. Neither
value is printed. Use the password in INCUBIA_E3_PROBE_KNOWLEDGE_DSN.
"""
from __future__ import annotations

import os
from urllib.parse import parse_qs, unquote, urlsplit


ROLE = "incubia_knowledge_runtime"
TABLES = ("knowledge_generations", "knowledge_sources", "knowledge_chunks")


class ProvisionError(RuntimeError):
    pass


def provision(admin_dsn: str, password: str) -> None:
    from psycopg import connect, sql

    parts = urlsplit(admin_dsn)
    if (parts.scheme not in {"postgres", "postgresql"}
            or not (parts.hostname or "").endswith(".neon.tech")
            or "-pooler." in (parts.hostname or "")
            or unquote(parts.username or "") != "neondb_owner"
            or parse_qs(parts.query).get("sslmode") != ["require"]
            or not parts.path.lstrip("/") or len(password) < 32):
        raise ProvisionError("A direct Neon owner DSN and a 32-character runtime password are required")
    try:
        with connect(admin_dsn, connect_timeout=10, sslmode="require") as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_user, current_database(), rolcreaterole "
                               "FROM pg_roles WHERE rolname=current_user")
                if cursor.fetchone() != ("neondb_owner", unquote(parts.path.lstrip("/")), True):
                    raise ProvisionError("The admin session is not the expected Neon owner")
                cursor.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (ROLE,))
                if cursor.fetchone():
                    raise ProvisionError("Knowledge runtime role already exists")
                for table in TABLES:
                    cursor.execute("SELECT to_regclass(%s)", (f"public.{table}",))
                    if cursor.fetchone()[0] is None:
                        raise ProvisionError("Knowledge migrations must run before provisioning")
                cursor.execute(sql.SQL(
                    "CREATE ROLE {} WITH LOGIN NOINHERIT NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD {}"
                ).format(sql.Identifier(ROLE), sql.Literal(password)))
                cursor.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(unquote(parts.path.lstrip("/"))), sql.Identifier(ROLE)))
                cursor.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
                cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(ROLE)))
                cursor.execute(sql.SQL("GRANT SELECT ON {} TO {}").format(
                    sql.SQL(", ").join(sql.Identifier("public", table) for table in TABLES),
                    sql.Identifier(ROLE)))
                cursor.execute("SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls "
                               "FROM pg_roles WHERE rolname=%s", (ROLE,))
                flags = cursor.fetchone()
                if flags is None or any(flags):
                    raise ProvisionError("Knowledge runtime role has privileged attributes")
                cursor.execute("SELECT pg_has_role(%s, 'neondb_owner', 'MEMBER'), "
                               "has_schema_privilege(%s, 'public', 'CREATE')", (ROLE, ROLE))
                if any(cursor.fetchone()):
                    raise ProvisionError("Knowledge runtime role has owner or schema DDL privileges")
                for table in TABLES:
                    cursor.execute("SELECT has_table_privilege(%s, %s, 'SELECT'), "
                                   "has_table_privilege(%s, %s, 'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')",
                                   (ROLE, f"public.{table}", ROLE, f"public.{table}"))
                    if cursor.fetchone() != (True, False):
                        raise ProvisionError("Knowledge table grants did not converge to read only")
    except ProvisionError:
        raise
    except Exception as exc:
        raise ProvisionError(f"Knowledge role provisioning failed ({type(exc).__name__})") from None


def main() -> int:
    try:
        provision(os.getenv("INCUBIA_E3_KNOWLEDGE_ADMIN_DSN", ""),
                  os.getenv("INCUBIA_E3_KNOWLEDGE_RUNTIME_PASSWORD", ""))
    except ProvisionError as exc:
        print(str(exc))
        return 1
    print("Knowledge runtime role provisioned with read-only table grants.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
