"""Offline output-path safety tests for the E3-4 Neon campaign."""
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.e3 import run_h4_neon_campaign as runner  # noqa: E402


def test_result_paths_are_timestamped_and_do_not_reuse_historical_evidence(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "RESULTS", tmp_path)
    moment = datetime(2026, 10, 24, 3, 30, 0, tzinfo=timezone.utc)

    campaign, g6 = runner.result_paths("local", moment)

    assert campaign == tmp_path / "e3-4-neon-local-20261024T033000Z.json"
    assert g6 == tmp_path / "e3-4-g6-neon-local-20261024T033000Z.json"
    assert campaign.name != "e3-4-neon-local-2026-10-15.json"
    assert g6.name != "e3-4-g6-neon-local-2026-10-15.json"
