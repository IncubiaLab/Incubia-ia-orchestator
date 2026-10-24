"""Offline tests for the E3-4 G6 review runner (no network, no credentials).

Covers: the fixture default stays the default, a real-read route through the
PEP exists but requires an explicit guard plus an injected adapter, the report
honestly states whether that route ran, and gate_closed/manual_rubric_complete
never flip true while reruns no longer clobber a historical artifact.
"""
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/e3"))
import run_h4_g6_review as runner  # noqa: E402

from incubia_orchestrator.modules.orchestration.adapters.tools.fake import FakeCatalogAdapter  # noqa: E402


def real_adapter():
    return FakeCatalogAdapter({"3017620422003": [{"code": "3017620422003", "product_name": "Nutella"}]})


# ------------------------------------------------------------------ default


def test_default_run_uses_fixture_and_never_claims_a_real_read(tmp_path):
    out = tmp_path / "review.json"
    report = runner.main(result_path=out)
    assert report["read_via_pep_fixture"] is True
    assert report["real_read_requested"] is False
    assert report["real_read_executed"] is False
    assert json.loads(out.read_text())["real_read_executed"] is False


def test_gate_and_rubric_stay_false(tmp_path):
    report = runner.main(result_path=tmp_path / "review.json")
    assert report["gate_closed"] is False
    assert report["manual_rubric_complete"] is False


def test_fixture_default_matches_previous_case_shape(tmp_path):
    report = runner.main(result_path=tmp_path / "review.json")
    assert report["cases"] == 24
    assert report["read_fixture_calls"] == 6
    assert report["tool_audit_events"] > 0


# ------------------------------------------------------- output path safety


def test_default_output_path_does_not_overwrite_the_historical_artifact(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    report = runner.main(now=lambda: datetime(2026, 10, 23, 9, 30, 0, tzinfo=UTC))
    assert report is not None
    assert not (tmp_path / "evals/results/e3-4-g6-local-review-2026-10-15.json").exists()


def test_default_output_path_varies_with_time(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    runner.main(now=lambda: datetime(2026, 10, 23, 9, 30, 0, tzinfo=UTC))
    runner.main(now=lambda: datetime(2026, 10, 23, 9, 30, 1, tzinfo=UTC))
    produced = sorted((tmp_path / "evals/results").glob("e3-4-g6-review-*.json"))
    assert len(produced) == 2


def test_rerun_with_explicit_path_is_still_supported(tmp_path):
    out = tmp_path / "e3-4-g6-neon-local-2026-10-15.json"
    report = runner.main(None, result_path=out)
    assert out.exists()
    assert report["gate_closed"] is False


# --------------------------------------------------------- real-read route


def test_real_read_route_is_ignored_without_the_explicit_guard(tmp_path):
    adapter = real_adapter()
    report = runner.main(result_path=tmp_path / "review.json", real_adapter=adapter, env={})
    assert report["real_read_executed"] is False
    assert report["read_via_pep_fixture"] is True
    assert len(adapter.calls) == 0


def test_real_read_route_rejects_partial_opt_in(tmp_path):
    with pytest.raises(RuntimeError, match="INCUBIA_E3_READ_REAL"):
        runner.main(result_path=tmp_path / "review.json", real_adapter=None,
                    env={"INCUBIA_E3_4_G6_REAL_READ": "1"})


def test_real_read_route_uses_default_adapter_only_after_both_opt_ins(monkeypatch, tmp_path):
    adapter = real_adapter()
    monkeypatch.setattr(runner, "OpenFoodFactsAdapter", lambda: adapter)
    report = runner.main(result_path=tmp_path / "review.json", env={
        "INCUBIA_E3_4_G6_REAL_READ": "1", "INCUBIA_E3_READ_REAL": "1",
    })
    assert report["real_read_requested"] is True
    assert report["real_read_executed"] is True
    assert len(adapter.calls) == 6
    assert report["read_via_pep_fixture"] is False


def test_real_read_route_runs_through_pep_when_explicitly_guarded(tmp_path):
    adapter = real_adapter()
    report = runner.main(result_path=tmp_path / "review.json", real_adapter=adapter,
                          env={"INCUBIA_E3_4_G6_REAL_READ": "1", "INCUBIA_E3_READ_REAL": "1"})
    assert report["real_read_requested"] is True
    assert report["real_read_executed"] is True
    assert len(adapter.calls) == 6
    assert report["read_via_pep_fixture"] is False
    assert report["read_fixture_calls"] == 0
    # The route change never relaxes the permanent gate posture.
    assert report["gate_closed"] is False
    assert report["manual_rubric_complete"] is False
