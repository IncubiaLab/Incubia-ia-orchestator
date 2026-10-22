"""Behaviour contract for scripts/e3/run_rag_v1_preflight.py.

The RAG-V1 preflight runner is fail-closed and offline: it validates the
branch-guard + private-artifact-dir contract but makes no network call, and
because Drive identity is undecided in this slice it must never claim RAG-V1
is ready. Every test here passes its own `env` mapping; the shared
`tests/conftest.py::no_network` fixture also blocks any real socket use.
"""
from __future__ import annotations

import json
import os
import stat

import pytest

from scripts.e3.run_rag_v1_preflight import (
    CHECK_OK,
    DRIVE_IDENTITY_UNRESOLVED,
    evaluate_checks,
    main,
)

REPO_ROOT_MARKER = __file__  # any path under the repo works for containment tests


def _private_dir(tmp_path):
    private = tmp_path / "private-bundles"
    private.mkdir(mode=0o700)
    os.chmod(private, 0o700)
    return private


def _authorized_env(branch: str) -> dict:
    return {"INCUBIA_E3_NEON_TESTS": "1", "INCUBIA_E3_NEON_BRANCH": branch}


# --- branch guard wiring -----------------------------------------------------

def test_missing_authorization_flag_refuses(tmp_path, capsys):
    private = _private_dir(tmp_path)
    env = {"INCUBIA_E3_NEON_BRANCH": "feat-knowledge-base"}
    code = main(["--branch", "feat-knowledge-base", "--private-artifact-dir", str(private)], env=env)
    assert code == 2
    assert capsys.readouterr().err  # a sanitized refusal message is printed


def test_prohibited_branch_refuses(tmp_path, capsys):
    private = _private_dir(tmp_path)
    env = _authorized_env("production")
    code = main(["--branch", "production", "--private-artifact-dir", str(private)], env=env)
    assert code == 2


def test_env_branch_mismatch_refuses(tmp_path):
    private = _private_dir(tmp_path)
    env = _authorized_env("some-other-branch")
    code = main(["--branch", "feat-knowledge-base", "--private-artifact-dir", str(private)], env=env)
    assert code == 2


# --- private-artifact-dir contract ------------------------------------------

def test_private_dir_inside_repo_refuses(tmp_path):
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[2]
    inside = repo_root / "tmp-rag-v1-preflight-test-dir"
    assert not inside.exists()
    env = _authorized_env("feat-knowledge-base")
    code = main(["--branch", "feat-knowledge-base", "--private-artifact-dir", str(inside)], env=env)
    assert code == 2


def test_private_dir_missing_refuses(tmp_path):
    missing = tmp_path / "does-not-exist"
    env = _authorized_env("feat-knowledge-base")
    code = main(["--branch", "feat-knowledge-base", "--private-artifact-dir", str(missing)], env=env)
    assert code == 2


def test_private_dir_wrong_mode_refuses(tmp_path):
    private = tmp_path / "loose-bundles"
    private.mkdir(mode=0o755)
    os.chmod(private, 0o755)
    env = _authorized_env("feat-knowledge-base")
    code = main(["--branch", "feat-knowledge-base", "--private-artifact-dir", str(private)], env=env)
    assert code == 2


# --- fail-closed readiness ----------------------------------------------------

def test_fully_valid_input_still_never_returns_zero(tmp_path, capsys):
    private = _private_dir(tmp_path)
    env = _authorized_env("feat-knowledge-base")
    code = main(["--branch", "feat-knowledge-base", "--private-artifact-dir", str(private)], env=env)
    assert code == 3
    report = json.loads(capsys.readouterr().out)
    assert report["drive_identity"] == "UNRESOLVED"
    assert report["status"] == "requiere_cambios"


def test_report_never_claims_ready_status(tmp_path, capsys):
    private = _private_dir(tmp_path)
    env = _authorized_env("feat-knowledge-base")
    main(["--branch", "feat-knowledge-base", "--private-artifact-dir", str(private)], env=env)
    out = capsys.readouterr().out
    assert "\"status\": \"ready\"" not in out
    assert "\"status\": \"listo\"" not in out


# --- structural fail-closed combinator ---------------------------------------

def test_evaluate_checks_is_ready_only_when_every_check_is_ok():
    status, code = evaluate_checks({"a": CHECK_OK, "b": CHECK_OK})
    assert (status, code) == ("listo", 0)


def test_evaluate_checks_is_not_ready_when_any_check_is_unresolved():
    status, code = evaluate_checks({"a": CHECK_OK, "b": DRIVE_IDENTITY_UNRESOLVED})
    assert status == "requiere_cambios"
    assert code == 3


def test_drive_identity_check_in_main_report_is_always_unresolved(tmp_path, capsys):
    private = _private_dir(tmp_path)
    env = _authorized_env("feat-knowledge-base")
    main(["--branch", "feat-knowledge-base", "--private-artifact-dir", str(private)], env=env)
    report = json.loads(capsys.readouterr().out)
    assert report["checks"]["drive_identity"] == DRIVE_IDENTITY_UNRESOLVED
