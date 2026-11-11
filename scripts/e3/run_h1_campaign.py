"""Run the E3-1 H1 closing campaign without exposing credentials.

The campaign is deliberately conservative: a successful local or Neon command
does not close E3-1 by itself. M1 and M2 must provide signed, machine-readable
evidence artifacts, and a synthetic dataset manifest must be supplied before
the final result can become ``ready_for_gate``.

Neon is never contacted unless ``--include-neon`` and the explicit campaign
environment guards are both present. DSNs are read from the environment or a
local ignored env file and are never included in the evidence artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "evals/results"
DEFAULT_NEON_ENV = ROOT / "deploy/e3-neon.env"
EXPECTED_BRANCH = "e3-h1-synthetic"
ALLOWED_ENV_FILE_KEYS = {
    "INCUBIA_E3_NEON_BRANCH",
    "DATABASE_URL",
    "INCUBIA_MIGRATION_DATABASE_URL",
    "INCUBIA_E3_DB_POOL_MAX",
}
PASSED_EVIDENCE_STATUSES = {"passed", "complete", "accepted"}

DSN_PATTERN = re.compile(r"postgres(?:ql)?://[^\s\"'<>]+", re.IGNORECASE)
SECRET_ASSIGNMENT = re.compile(
    r"(?im)(\b(?:password|passwd|secret|token|api[_-]?key|database_url|dsn)\b\s*[=:]\s*)([^\s,;]+)"
)
ANSI_PATTERN = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    label: str
    status: str
    returncode: int | None
    duration_ms: int
    command: str
    output: str
    reason: str | None = None


def _sanitize(value: str) -> str:
    """Remove credentials and cap persisted subprocess output."""
    value = ANSI_PATTERN.sub("", value)
    value = DSN_PATTERN.sub("<redacted-dsn>", value)
    value = SECRET_ASSIGNMENT.sub(r"\1<redacted>", value)
    if len(value) > 4000:
        value = "[output truncated]\n" + value[-4000:]
    return value


def _shell_safe_command(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def _load_env_file(path: Path) -> None:
    """Load only known local campaign keys, without sourcing a shell."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, raw_value = stripped.split("=", 1)
        key = key.strip()
        if key not in ALLOWED_ENV_FILE_KEYS or key in os.environ:
            continue
        try:
            parsed = shlex.split(raw_value, comments=False)
        except ValueError as exc:
            raise ValueError(f"invalid quoting in campaign env file ({type(exc).__name__})") from None
        if len(parsed) != 1:
            raise ValueError("campaign env values must contain one shell word")
        os.environ[key] = parsed[0]


def _run_check(
    check_id: str,
    label: str,
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout: int = 1200,
) -> CheckResult:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        combined = (completed.stdout or "") + (completed.stderr or "")
        return CheckResult(
            check_id=check_id,
            label=label,
            status="passed" if completed.returncode == 0 else "failed",
            returncode=completed.returncode,
            duration_ms=round((time.monotonic() - started) * 1000),
            command=_shell_safe_command(command),
            output=_sanitize(combined),
        )
    except subprocess.TimeoutExpired as exc:
        output = "".join(
            item.decode(errors="replace") if isinstance(item, bytes) else item
            for item in (exc.stdout or "", exc.stderr or "")
        )
        return CheckResult(
            check_id=check_id,
            label=label,
            status="failed",
            returncode=None,
            duration_ms=round((time.monotonic() - started) * 1000),
            command=_shell_safe_command(command),
            output=_sanitize(output),
            reason=f"timeout after {timeout}s",
        )
    except OSError as exc:
        return CheckResult(
            check_id=check_id,
            label=label,
            status="failed",
            returncode=None,
            duration_ms=round((time.monotonic() - started) * 1000),
            command=_shell_safe_command(command),
            output="",
            reason=f"could not start command ({type(exc).__name__})",
        )


def _pending(check_id: str, label: str, reason: str) -> CheckResult:
    return CheckResult(check_id, label, "pending", None, 0, "", "", reason)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path) -> str:
    return str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)


def _evidence_status(path: Path | None, milestone: str) -> dict[str, Any]:
    if path is None:
        return {"status": "pending", "reason": f"{milestone} evidence artifact not supplied"}
    if not path.is_file():
        return {"status": "failed", "reason": f"{milestone} evidence artifact does not exist"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"status": "failed", "reason": f"{milestone} evidence is not valid JSON ({type(exc).__name__})"}
    if not isinstance(payload, dict):
        return {"status": "failed", "reason": f"{milestone} evidence root must be an object"}
    status = str(payload.get("status", "")).lower()
    if payload.get("milestone") != milestone:
        return {"status": "failed", "reason": f"artifact milestone is not {milestone}"}
    if status not in PASSED_EVIDENCE_STATUSES:
        return {"status": "pending", "reason": f"{milestone} artifact status is {status or 'missing'}"}
    critical = payload.get("critical_failures", 0)
    if not isinstance(critical, int) or critical != 0:
        return {"status": "failed", "reason": f"{milestone} artifact reports critical failures"}
    return {"status": "passed", "path": _relative(path), "sha256": _sha256(path)}


def _manifest_status(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"status": "pending", "reason": "synthetic dataset manifest not supplied"}
    if not path.is_file():
        return {"status": "failed", "reason": "synthetic dataset manifest does not exist"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"status": "failed", "reason": f"dataset manifest is not valid JSON ({type(exc).__name__})"}
    if not isinstance(payload, dict) or payload.get("synthetic") is not True:
        return {"status": "failed", "reason": "dataset manifest must declare synthetic=true"}
    return {"status": "passed", "path": _relative(path), "sha256": _sha256(path)}


def _migration_inventory() -> list[dict[str, str]]:
    return [
        {"file": path.name, "sha256": _sha256(path)}
        for path in sorted((ROOT / "migrations/postgres").glob("*.sql"))
    ]


def _neon_guard() -> tuple[bool, str | None]:
    if os.getenv("INCUBIA_E3_NEON_TESTS") != "1":
        return False, "set INCUBIA_E3_NEON_TESTS=1 to authorize Neon"
    if os.getenv("INCUBIA_E3_NEON_BRANCH") != EXPECTED_BRANCH:
        return False, f"INCUBIA_E3_NEON_BRANCH must be {EXPECTED_BRANCH}"
    for name in ("DATABASE_URL", "INCUBIA_MIGRATION_DATABASE_URL"):
        value = os.getenv(name, "")
        parts = urlsplit(value)
        if not parts.hostname or not parts.hostname.endswith(".neon.tech"):
            return False, f"{name} must target a Neon host"
    return True, None


def _run_campaign(args: argparse.Namespace) -> dict[str, Any]:
    try:
        _load_env_file(Path(args.env_file))
    except ValueError as exc:
        return {
            "schema_version": "e3-1-campaign/v1",
            "campaign_id": str(uuid4()),
            "status": "blocked",
            "gate_closed": False,
            "reason": str(exc),
            "checks": [],
            "milestones": {},
        }

    checks: list[CheckResult] = []
    if args.phase in {"offline", "all"}:
        checks.append(_run_check(
            "offline-directed",
            "offline contract and recovery suite",
            [
                sys.executable, "-m", "pytest", "-q",
                "tests/unit/test_d0_deployment.py",
                "tests/unit/test_d0_postgres_schema.py",
                "tests/unit/test_e3_contracts.py",
                "tests/integration/test_gate_a_e2e.py",
                "tests/integration/test_sqlite_ledger.py",
                "tests/integration/test_telegram_runner.py",
                "-m", "not neon",
            ],
        ))
    if args.phase in {"postgres", "all"}:
        suite = ROOT / "tests/integration/postgres"
        database_url = os.getenv("E3_POSTGRES_TEST_DATABASE_URL", "")
        compose_smoke = os.getenv("E3_D0_COMPOSE_SMOKE") == "1"
        if not database_url and compose_smoke:
            checks.append(_run_check(
                "postgres",
                "local PostgreSQL Compose smoke",
                ["bash", "scripts/e3/d0_smoke.sh"],
                env=os.environ.copy(),
                timeout=1200,
            ))
        elif not database_url:
            checks.append(_pending("postgres", "local PostgreSQL integration suite", "E3_POSTGRES_TEST_DATABASE_URL is not set"))
        elif not suite.is_dir():
            checks.append(_pending("postgres", "local PostgreSQL integration suite", "tests/integration/postgres is not present"))
        else:
            postgres_env = os.environ.copy()
            postgres_env["DATABASE_URL"] = database_url
            checks.append(_run_check(
                "postgres", "local PostgreSQL integration suite",
                [sys.executable, "-m", "pytest", "-q", "tests/integration/postgres", "-m", "not neon"],
                env=postgres_env,
            ))
    if args.phase in {"neon", "all"}:
        if not args.include_neon:
            checks.append(_pending("neon", "isolated Neon H1 suite", "Neon requires --include-neon"))
        else:
            allowed, reason = _neon_guard()
            if not allowed:
                checks.append(_pending("neon", "isolated Neon H1 suite", reason or "Neon guard rejected campaign"))
            else:
                checks.append(_run_check(
                    "neon", "isolated Neon H1 suite",
                    [sys.executable, "scripts/e3/run_neon_h1.py"],
                    env=os.environ.copy(),
                ))

    m1 = _evidence_status(Path(args.m1_evidence) if args.m1_evidence else None, "M1")
    m2 = _evidence_status(Path(args.m2_evidence) if args.m2_evidence else None, "M2")
    dataset = _manifest_status(Path(args.dataset_manifest) if args.dataset_manifest else None)
    commands_ok = bool(checks) and all(item.status == "passed" for item in checks)
    prerequisites_ok = all(item["status"] == "passed" for item in (m1, m2, dataset))
    ready = commands_ok and prerequisites_ok
    return {
        "schema_version": "e3-1-campaign/v1",
        "campaign_id": str(uuid4()),
        "created_at": datetime.now(UTC).isoformat(),
        "branch": EXPECTED_BRANCH,
        "synthetic_only": True,
        "status": "ready_for_gate" if ready else "open",
        "gate_closed": False,
        "reason": None if ready else "M1, M2, dataset evidence, or campaign checks remain incomplete",
        "migrations": _migration_inventory(),
        "milestones": {"M1": m1, "M2": m2, "dataset": dataset},
        "checks": [asdict(item) for item in checks],
        "secret_policy": "DSNs, passwords, tokens and prompt payloads are excluded from this artifact",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("offline", "postgres", "neon", "all"), default="offline")
    parser.add_argument("--include-neon", action="store_true", help="opt in to the isolated Neon campaign")
    parser.add_argument("--env-file", default=str(DEFAULT_NEON_ENV), help="ignored local env file; values are not printed")
    parser.add_argument("--m1-evidence", help="machine-readable M1 evidence JSON")
    parser.add_argument("--m2-evidence", help="machine-readable M2 evidence JSON")
    parser.add_argument("--dataset-manifest", help="synthetic dataset manifest JSON")
    parser.add_argument("--output", help="evidence JSON path; defaults to evals/results/e3-1-campaign-<timestamp>.json")
    args = parser.parse_args(argv)
    result = _run_campaign(args)
    output = Path(args.output) if args.output else DEFAULT_OUTPUT_DIR / (
        "e3-1-campaign-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + ".json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"E3-1 campaign status: {result['status']}; evidence: {output}")
    return 0 if result["status"] == "ready_for_gate" else 1


if __name__ == "__main__":
    raise SystemExit(main())
