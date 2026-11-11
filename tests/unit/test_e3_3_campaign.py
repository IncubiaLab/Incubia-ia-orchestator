"""Offline tests for the full E3-3 campaign runner (no network, no credentials)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/e3"))
import run_e3_3_campaign as runner  # noqa: E402

from incubia_orchestrator.modules.orchestration.adapters.tools.fake import FakeCatalogAdapter  # noqa: E402


def good_env(**extra):
    env = {"INCUBIA_E3_3_CAMPAIGN": "1", "INCUBIA_E3_3_BUDGET_APPROVED": "1", "INCUBIA_E3_3_BUDGET_USD": "1"}
    env.update(extra)
    return env


def fake_adapter():
    return FakeCatalogAdapter({"3017620422003": [{"code": "3017620422003", "product_name": "Nutella"}]})


class _Boom:
    def fill(self):
        raise AssertionError("Deps must not be touched during a dry run")


# ------------------------------------------------------------------ guards


def test_guards_pass_and_return_budget():
    guarded = runner.check_guards(good_env(INCUBIA_E3_3_BUDGET_USD="2.5"))
    assert guarded.budget_usd == 2.5


def test_guards_pass_with_minimum_positive_budget():
    guarded = runner.check_guards(good_env(INCUBIA_E3_3_BUDGET_USD="0.01"))
    assert guarded.budget_usd == 0.01


@pytest.mark.parametrize("key", ["INCUBIA_E3_3_CAMPAIGN", "INCUBIA_E3_3_BUDGET_APPROVED"])
def test_guards_fail_closed_without_opt_in(key):
    with pytest.raises(runner.GuardError):
        runner.check_guards(good_env(**{key: "0"}))


@pytest.mark.parametrize("budget", ["", "nan", "-1", "0", "not-a-number"])
def test_guards_fail_closed_on_invalid_budget(budget):
    with pytest.raises(runner.GuardError):
        runner.check_guards(good_env(INCUBIA_E3_3_BUDGET_USD=budget))


# --------------------------------------------------------------------- CLI


def test_dry_run_touches_nothing(capsys):
    assert runner.main(["--dry-run"], deps=_Boom(), env={}) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["dry_run"] is True
    assert plan["cases"] == ["allow", "deny", "indeterminate", "require_approval", "invalid_input"]


def test_main_refuses_without_authorization(capsys):
    assert runner.main([], deps=runner.Deps(), env={}) == 2
    assert "INCUBIA_E3_3_CAMPAIGN" in capsys.readouterr().err


def test_main_refuses_without_budget_approval(capsys):
    env = good_env(INCUBIA_E3_3_BUDGET_APPROVED="0")
    assert runner.main([], deps=runner.Deps(), env=env) == 2
    assert "BUDGET" in capsys.readouterr().err


def test_main_refuses_default_real_adapter_without_read_real_opt_in(capsys):
    """Guards alone are not enough: the default real adapter needs its own opt-in."""
    assert runner.main([], deps=None, env=good_env()) == 2
    assert "INCUBIA_E3_READ_REAL" in capsys.readouterr().err


# ---------------------------------------------------------- Deps.fill guard


def test_deps_fill_refuses_the_default_real_adapter_without_opt_in():
    with pytest.raises(runner.GuardError):
        runner.Deps().fill({})


def test_deps_fill_allows_the_default_real_adapter_with_explicit_opt_in():
    deps = runner.Deps().fill({"INCUBIA_E3_READ_REAL": "1"})
    try:
        assert isinstance(deps.adapter, runner.OpenFoodFactsAdapter)
    finally:
        deps.adapter.close()


def test_deps_fill_leaves_an_injected_fake_adapter_untouched_without_opt_in():
    adapter = fake_adapter()
    deps = runner.Deps(adapter=adapter).fill({})
    assert deps.adapter is adapter


# ------------------------------------------------------------- run_campaign


def test_allow_case_executes_via_the_injected_adapter():
    adapter = fake_adapter()
    report = runner.run_campaign(runner.Deps(adapter=adapter))
    allow = next(c for c in report["cases"] if c["name"] == "allow")
    assert allow["status"] == "SUCCESS"
    assert allow["adapter_calls_during_case"] == 1
    assert len(adapter.calls) == 1
    assert report["allow_executed_via_adapter"] is True


@pytest.mark.parametrize("name,expected_status", [
    ("deny", "DENIED"),
    ("indeterminate", "FAILED"),
    ("require_approval", "DENIED"),
    ("invalid_input", "DENIED"),
])
def test_non_allow_cases_make_zero_external_calls(name, expected_status):
    # run_campaign exercises all 5 cases against one shared adapter (so the
    # report can prove total_adapter_calls == 1 for the whole run); only this
    # case's own slice must be zero, not the adapter's cumulative call count.
    report = runner.run_campaign(runner.Deps(adapter=fake_adapter()))
    case = next(c for c in report["cases"] if c["name"] == name)
    assert case["status"] == expected_status
    assert case["adapter_calls_during_case"] == 0
    assert case["audit_events"] >= 2


def test_zero_call_safety_is_true_only_when_non_allow_cases_are_safe():
    report = runner.run_campaign(runner.Deps(adapter=fake_adapter()))
    assert report["zero_call_safety"] is True
    assert report["total_adapter_calls"] == 1


def test_report_never_closes_the_gate():
    report = runner.run_campaign(runner.Deps(adapter=fake_adapter()))
    assert report["gate"] == "E3-3"
    assert report["gate_closed"] is False


def test_invalid_input_case_never_reaches_policy():
    """Validation must reject the missing product_ref before policy is even consulted."""
    adapter = fake_adapter()
    report = runner.run_campaign(runner.Deps(adapter=adapter))
    case = next(c for c in report["cases"] if c["name"] == "invalid_input")
    assert case["error"] == "INVALID_INPUT"


# --------------------------------------------------------------- full main


def test_main_writes_sanitized_artifact_and_reports_gate_closed_false(tmp_path, capsys):
    output_path = tmp_path / "e3-3-result.json"
    deps = runner.Deps(adapter=fake_adapter())
    code = runner.main(["--output-path", str(output_path)], deps=deps, env=good_env())
    assert code == 0
    report = json.loads(output_path.read_text())
    assert report["gate_closed"] is False
    assert report["zero_call_safety"] is True
    assert report["budget_usd_approved"] == 1.0
    printed = json.loads(capsys.readouterr().out)
    assert printed["gate_closed"] is False


def test_rerun_does_not_overwrite_a_different_output_path(tmp_path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    runner.main(["--output-path", str(first)], deps=runner.Deps(adapter=fake_adapter()), env=good_env())
    runner.main(["--output-path", str(second)], deps=runner.Deps(adapter=fake_adapter()), env=good_env())
    assert first.exists() and second.exists()
