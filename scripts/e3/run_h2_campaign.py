"""Run and record the local E3-2 tenant-isolation campaign.

This campaign is intentionally local and synthetic.  It validates the
identity, scope, policy, revocation, Telegram revalidation, and PostgreSQL
schema-contract checks without contacting Neon or any external service.  A
successful local run does not close E3-2: PostgreSQL/RLS runtime behaviour,
pool reuse, and the real discovery adapter still require their own evidence.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "evals/results/e3-2-campaign-2026-10-15-local.json"
TARGETS = (
    "tests/integration/test_tenant_isolation.py",
    "tests/unit/test_e3_contracts.py",
    "tests/integration/test_telegram_runner.py",
    "tests/unit/test_d0_postgres_schema.py",
)
NEON_ENV_KEYS = {
    "DATABASE_URL",
    "INCUBIA_MIGRATION_DATABASE_URL",
}
DSN_PATTERN = re.compile(r"postgres(?:ql)?://[^\s\"'<>]+", re.IGNORECASE)
SECRET_ASSIGNMENT = re.compile(
    r"(?im)(\b(?:password|passwd|secret|token|api[_-]?key|database_url|dsn)\b\s*[=:]\s*)([^\s,;]+)"
)


def _command() -> list[str]:
    return [sys.executable, "-m", "pytest", "-q", *TARGETS, "-m", "not neon"]


def _relative(path: Path) -> str:
    return str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)


def _sanitize(value: str) -> str:
    value = DSN_PATTERN.sub("<redacted-dsn>", value)
    return SECRET_ASSIGNMENT.sub(r"\1<redacted>", value)[-8000:]


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key not in NEON_ENV_KEYS or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        os.environ[key] = value


def _neon_guard() -> tuple[bool, str | None]:
    if os.getenv("INCUBIA_E3_NEON_TESTS") != "1":
        return False, "set INCUBIA_E3_NEON_TESTS=1 to authorize Neon"
    if os.getenv("INCUBIA_E3_NEON_BRANCH") != "e3-h1-synthetic":
        return False, "INCUBIA_E3_NEON_BRANCH must be e3-h1-synthetic"
    runtime = urlsplit(os.getenv("DATABASE_URL", ""))
    migrator = urlsplit(os.getenv("INCUBIA_MIGRATION_DATABASE_URL", ""))
    if runtime.scheme not in {"postgres", "postgresql"} or not (runtime.hostname or "").endswith(".neon.tech"):
        return False, "DATABASE_URL must target Neon"
    if migrator.scheme not in {"postgres", "postgresql"} or not (migrator.hostname or "").endswith(".neon.tech"):
        return False, "INCUBIA_MIGRATION_DATABASE_URL must target Neon"
    if unquote(runtime.username or "") != "incubia_runtime" or "-pooler." not in (runtime.hostname or ""):
        return False, "DATABASE_URL must be the pooled incubia_runtime endpoint"
    if unquote(migrator.username or "") != "incubia_migrator" or "-pooler." in (migrator.hostname or ""):
        return False, "INCUBIA_MIGRATION_DATABASE_URL must be the direct incubia_migrator endpoint"
    if runtime.hostname.replace("-pooler.", ".", 1) != migrator.hostname:
        return False, "runtime and migrator URLs must identify the same Neon branch"
    for value in (runtime, migrator):
        if (value.path or "").lstrip("/") != "neondb":
            return False, "Neon URLs must target neondb"
        if parse_qs(value.query).get("sslmode", [None])[0] not in {"require", "verify-ca", "verify-full"}:
            return False, "Neon URLs must require TLS"
    return True, None


def _run(command: list[str], *, timeout: int = 1200) -> dict[str, object]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        output = _sanitize((completed.stdout or "") + (completed.stderr or ""))
        return {
            "status": "passed" if completed.returncode == 0 else "failed",
            "returncode": completed.returncode,
            "duration_ms": round((time.monotonic() - started) * 1000),
            "command": " ".join(shlex.quote(part) for part in command),
            "output": output,
        }
    except subprocess.TimeoutExpired as exc:
        output = "".join(
            item.decode(errors="replace") if isinstance(item, bytes) else item
            for item in (exc.stdout or "", exc.stderr or "")
        )
        return {
            "status": "failed",
            "returncode": None,
            "duration_ms": round((time.monotonic() - started) * 1000),
            "command": " ".join(shlex.quote(part) for part in command),
            "output": _sanitize(output),
            "reason": f"timeout after {timeout}s",
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--include-neon", action="store_true", help="opt in to the approved synthetic Neon branch")
    parser.add_argument("--env-file", type=Path, default=ROOT / "deploy/e3-neon.env")
    args = parser.parse_args(argv)

    local = _run(_command())
    checks: list[dict[str, object]] = [{
        "check_id": "e3-2-local-pytest",
        "label": "tenant isolation, identity contracts, Telegram revalidation, and PostgreSQL schema contract",
        **local,
    }]
    if args.include_neon:
        _load_env_file(args.env_file)
        allowed, reason = _neon_guard()
        if not allowed:
            checks.append({
                "check_id": "e3-2-neon",
                "label": "approved Neon PostgreSQL/RLS identity campaign",
                "status": "pending",
                "returncode": None,
                "duration_ms": 0,
                "command": "",
                "output": "",
                "reason": reason,
            })
        else:
            neon = _run([
                sys.executable, "scripts/e3/run_neon_h1.py",
            ])
            checks.append({
                "check_id": "e3-2-neon",
                "label": "approved Neon PostgreSQL/RLS identity campaign",
                **neon,
            })
    else:
        checks.append({
            "check_id": "e3-2-neon",
            "label": "approved Neon PostgreSQL/RLS identity campaign",
            "status": "pending",
            "returncode": None,
            "duration_ms": 0,
            "command": "",
            "output": "",
            "reason": "run with --include-neon and the explicit synthetic-branch guards",
        })
    local_passed = local["status"] == "passed"
    neon_check = checks[-1]
    neon_passed = neon_check["status"] == "passed"
    all_passed = local_passed and neon_passed
    artifact = {
        "schema_version": "e3-2-campaign/v1",
        "campaign_id": str(uuid4()),
        "created_at": datetime.now(UTC).isoformat(),
        "scope": "local-synthetic+approved-neon" if neon_check["status"] == "passed" else "local-synthetic",
        "status": "ready_for_gate" if all_passed else ("failed" if local["status"] == "failed" or neon_check["status"] == "failed" else "open"),
        "gate_closed": False,
        "reason": (
            "All local and approved Neon E3-2 checks passed; formal gate decision remains pending."
            if all_passed
            else "The local E3-2 campaign passed but the approved Neon PostgreSQL/RLS campaign is pending."
            if local_passed and neon_check["status"] == "pending"
            else "The E3-2 campaign failed; inspect the recorded pytest output."
        ),
        "checks": checks,
        "scenarios": [
            "two tenants and two actors resolve only their own trusted scopes",
            "revocation is effective before the next operation",
            "policy denies foreign resources and insufficient roles",
            "fake discovery is scoped by deployment and tenant",
            "Telegram revalidates binding before generation and delivery",
            "PostgreSQL migration declares scoped identity tables and RLS policies",
        ],
        "pending": [] if all_passed else [
            "PostgreSQL runtime isolation with seeded tenants, actors, and pool reuse",
            "Neon/RLS campaign under the explicit opt-in guards",
        ],
        "synthetic_only": True,
    }

    output_path = args.output if args.output.is_absolute() else ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(f"artifact={_relative(output_path)}")
    print(f"status={artifact['status']} gate_closed={artifact['gate_closed']}")
    for check in checks:
        if check["output"]:
            print(check["output"])
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
