"""Offline contract tests for the E3-1 campaign orchestrator."""
from __future__ import annotations

import json

from scripts.e3.run_h1_campaign import (
    _evidence_status,
    _manifest_status,
    _sanitize,
    main,
)


def test_sanitize_removes_dsn_and_secret_assignments():
    value = "DATABASE_URL=postgresql://runtime:password@branch.neon.tech/neondb?sslmode=require token=abc123"
    result = _sanitize(value)
    assert "branch.neon.tech" not in result
    assert "password" not in result
    assert "abc123" not in result
    assert "<redacted" in result


def test_campaign_is_open_without_m1_m2_and_dataset(tmp_path, monkeypatch):
    output = tmp_path / "campaign.json"
    monkeypatch.delenv("INCUBIA_E3_NEON_TESTS", raising=False)
    assert main(["--phase", "offline", "--output", str(output)]) == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "open"
    assert payload["gate_closed"] is False
    assert payload["milestones"]["M1"]["status"] == "pending"
    assert payload["milestones"]["M2"]["status"] == "pending"
    assert payload["milestones"]["dataset"]["status"] == "pending"
    assert all("postgres" not in item.get("output", "") for item in payload["checks"])


def test_evidence_and_manifest_require_explicit_synthetic_contract(tmp_path):
    m1 = tmp_path / "m1.json"
    m1.write_text(json.dumps({"milestone": "M1", "status": "passed", "critical_failures": 0}), encoding="utf-8")
    dataset = tmp_path / "dataset.json"
    dataset.write_text(json.dumps({"synthetic": False}), encoding="utf-8")
    assert _evidence_status(m1, "M1")["status"] == "passed"
    assert _manifest_status(dataset)["status"] == "failed"


def test_campaign_env_file_parser_does_not_override_process_environment(tmp_path, monkeypatch):
    env_file = tmp_path / "campaign.env"
    env_file.write_text(
        "INCUBIA_E3_NEON_BRANCH='e3-h1-synthetic'\n"
        "DATABASE_URL='postgresql://file-user:file-pass@branch.neon.tech/neondb?sslmode=require'\n",
        encoding="utf-8",
    )
    output = tmp_path / "campaign.json"
    monkeypatch.setenv("DATABASE_URL", "postgresql://process-value@branch.neon.tech/neondb?sslmode=require")
    assert main(["--phase", "neon", "--env-file", str(env_file), "--output", str(output)]) == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["checks"][0]["status"] == "pending"
    assert "process-value" not in output.read_text(encoding="utf-8")
