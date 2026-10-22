#!/usr/bin/env python3
"""Fail-closed preflight runner for RAG-V1 (Task 3 — guards only, NOT ingestion).

This makes **no** network call and reads no credential file. It validates
only the environment/filesystem contract that every later RAG-V1 step must
satisfy: an explicit, authorized, dedicated isolated Neon campaign branch
(never a shared/production branch — see scripts/e3/neon_branch_guard.py) and
a private-artifact directory that is outside the Git working tree and locked
down to mode 0700.

Drive identity (which account/service RAG-V1 ingestion will read Drive
documents as) is not yet decided anywhere in this repository. This runner
therefore always reports that check as ``UNRESOLVED`` and can never report
RAG-V1 as ready: the exit code is derived from the check results, so it is
structurally impossible to return 0 while any check -- including this one --
is not ``ok``. It returns ``3`` ("requiere_cambios") whenever every check it
*can* satisfy passes but readiness still cannot be claimed, and ``2`` when it
refuses outright (bad branch/environment or bad private-artifact directory).

Example (offline; the env mapping shown here is what a caller/test injects)::

    python scripts/e3/run_rag_v1_preflight.py \\
      --branch feat-knowledge-base \\
      --private-artifact-dir /private/rag-v1-bundles
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path
from typing import Mapping

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
# Also ensure the repo root itself is importable so `scripts.e3.*` resolves
# as a namespace package even when this file is invoked directly (rather
# than via `python -m pytest` from the repo root, which already puts the
# repo root on sys.path).
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from incubia_orchestrator.modules.knowledge.private_artifacts import (  # noqa: E402
    DIR_MODE,
    PrivateArtifactPathError,
    resolve_private_artifact_dir,
)

from scripts.e3.neon_branch_guard import (  # noqa: E402
    BranchGuardError,
    guard_campaign_environment,
)

CHECK_OK = "ok"
DRIVE_IDENTITY_UNRESOLVED = "UNRESOLVED"

_STATUS_READY = "listo"
_STATUS_REQUIERE_CAMBIOS = "requiere_cambios"
_EXIT_READY = 0
_EXIT_REQUIERE_CAMBIOS = 3
_EXIT_REFUSED = 2


class PreflightError(ValueError):
    """Raised when the RAG-V1 preflight environment/contract is not satisfiable."""


def evaluate_checks(checks: Mapping[str, str]) -> tuple[str, int]:
    """Fail-closed combinator: ready only when every check equals ``CHECK_OK``.

    This is the only place that decides the overall status/exit code, so a
    single unresolved or failing check (by name or by value, present or
    future) always keeps the result at "requiere_cambios" / non-zero. There
    is no code path that returns the ready status while any entry differs
    from ``CHECK_OK``.
    """
    if all(status == CHECK_OK for status in checks.values()):
        return _STATUS_READY, _EXIT_READY
    return _STATUS_REQUIERE_CAMBIOS, _EXIT_REQUIERE_CAMBIOS


def _require_private_artifact_dir(path: Path) -> None:
    """Raise PreflightError unless ``path`` is an existing, outside-repo, 0700 directory."""
    try:
        resolved = resolve_private_artifact_dir(path, repo_root=ROOT)
    except PrivateArtifactPathError as exc:
        raise PreflightError(str(exc)) from exc
    try:
        info = os.stat(resolved)
    except OSError as exc:
        raise PreflightError("private artifact directory must already exist") from exc
    if not stat.S_ISDIR(info.st_mode):
        raise PreflightError("private artifact directory path is not a directory")
    if stat.S_IMODE(info.st_mode) != DIR_MODE:
        raise PreflightError("private artifact directory must be mode 0700")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="RAG-V1 offline preflight (guards only)")
    parser.add_argument(
        "--branch", required=True,
        help="dedicated isolated Neon campaign branch this preflight targets",
    )
    parser.add_argument(
        "--private-artifact-dir", required=True, type=Path,
        help="existing, outside-repo, mode-0700 directory for private RAG-V1 artifacts",
    )
    return parser


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    args = _parser().parse_args(argv)
    environment = os.environ if env is None else env

    try:
        validated_branch = guard_campaign_environment(environment, expected_branch=args.branch)
    except BranchGuardError as exc:
        print(f"Refusing RAG-V1 preflight: {exc}", file=sys.stderr)
        return _EXIT_REFUSED

    try:
        _require_private_artifact_dir(args.private_artifact_dir)
    except PreflightError as exc:
        print(f"Refusing RAG-V1 preflight: {exc}", file=sys.stderr)
        return _EXIT_REFUSED

    checks = {
        "campaign_environment": CHECK_OK,
        "private_artifact_dir": CHECK_OK,
        # Drive identity (which account/service RAG-V1 will read Drive as) is
        # not decided anywhere in this repository yet. This is reported
        # honestly as unresolved; nothing in this file can set it to CHECK_OK.
        "drive_identity": DRIVE_IDENTITY_UNRESOLVED,
    }
    status, exit_code = evaluate_checks(checks)
    report = {
        "status": status,
        "branch": validated_branch,
        "drive_identity": DRIVE_IDENTITY_UNRESOLVED,
        "checks": checks,
    }
    print(json.dumps(report, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
