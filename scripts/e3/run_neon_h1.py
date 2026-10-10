"""Run only the explicit, isolated Neon H1 integration campaign."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from urllib.parse import parse_qs, unquote, urlsplit


NEON_CLI = "neon@8.3.3"
BRANCH = "e3-h1-synthetic"
DATABASE = "neondb"
DSN_RE = re.compile(r"postgres(?:ql)?://[^\s\"'<>]+", re.IGNORECASE)


def _validated_url(name: str, role: str, *, pooled: bool) -> str:
    value = os.getenv(name, "")
    parts = urlsplit(value)
    host = (parts.hostname or "").lower()
    username = unquote(parts.username or "")
    if parts.scheme not in {"postgres", "postgresql"} or not host.endswith(".neon.tech"):
        raise ValueError(f"{name} must target a Neon PostgreSQL host")
    if username != role or (parts.path or "").lstrip("/") != "neondb":
        raise ValueError(f"{name} must use the expected role and database")
    if pooled != ("-pooler." in host):
        raise ValueError(f"{name} has the wrong direct/pooled endpoint type")
    if parse_qs(parts.query).get("sslmode", [None])[0] not in {"require", "verify-ca", "verify-full"}:
        raise ValueError(f"{name} must require TLS")
    return value


def _expected_branch_host() -> str:
    command = [
        "npx", "--yes", NEON_CLI, "connection-string", BRANCH,
        "--role-name", "neondb_owner", "--database-name", DATABASE,
        "--ssl", "require", "--output", "json", "--analytics", "false",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        raise ValueError("Neon CLI could not resolve the approved branch endpoint")
    matches = DSN_RE.findall(result.stdout)
    if not matches:
        raise ValueError("Neon CLI returned no approved branch endpoint")
    parts = urlsplit(matches[-1])
    if not parts.hostname or "-pooler." in parts.hostname or not parts.hostname.endswith(".neon.tech"):
        raise ValueError("Neon CLI resolved an unexpected endpoint")
    if unquote(parts.username or "") != "neondb_owner" or (parts.path or "").lstrip("/") != DATABASE:
        raise ValueError("Neon CLI resolved an unexpected branch identity")
    return parts.hostname.lower()


def main() -> int:
    if os.getenv("INCUBIA_E3_NEON_TESTS") != "1":
        print("Set INCUBIA_E3_NEON_TESTS=1 to authorize the Neon campaign.", file=sys.stderr)
        return 2
    if os.getenv("INCUBIA_E3_NEON_BRANCH") != "e3-h1-synthetic":
        print("Refusing to run: INCUBIA_E3_NEON_BRANCH must be e3-h1-synthetic.", file=sys.stderr)
        return 2
    try:
        runtime_url = _validated_url("DATABASE_URL", "incubia_runtime", pooled=True)
        migration_url = _validated_url(
            "INCUBIA_MIGRATION_DATABASE_URL", "incubia_migrator", pooled=False
        )
    except ValueError as exc:
        print(f"Refusing Neon campaign: {exc}", file=sys.stderr)
        return 2
    runtime_parts, migration_parts = urlsplit(runtime_url), urlsplit(migration_url)
    try:
        expected_host = _expected_branch_host()
    except (OSError, ValueError) as exc:
        print(f"Refusing Neon campaign ({type(exc).__name__}).", file=sys.stderr)
        return 2
    if (runtime_parts.path != migration_parts.path
            or runtime_parts.hostname.replace("-pooler.", ".", 1) != migration_parts.hostname
            or migration_parts.hostname.lower() != expected_host):
        print("Refusing Neon campaign: URLs do not identify the approved branch/database.", file=sys.stderr)
        return 2

    environment = os.environ.copy()
    environment["INCUBIA_E3_NEON_TESTS"] = "1"
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-m", "neon", "tests/integration/neon"],
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            env=environment,
            check=False,
        )
    except OSError as exc:
        print(f"Could not start Neon integration runner ({type(exc).__name__}).", file=sys.stderr)
        return 2
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
