import copy
from pathlib import Path

import pytest
import yaml

from incubia_orchestrator.foundation.limits import LimitsError, load_limits, parse_limits

EXAMPLE = Path(__file__).resolve().parents[2] / "config/e3/limits.example.yaml"


def _doc():
    return yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))


def test_example_loads_and_is_provisional():
    limits = load_limits(EXAMPLE)
    assert limits.status == "provisional"
    assert limits.nfr.slo_p95_seconds == 5 and limits.nfr.rpo_hours == 24
    assert limits.nfr.rto_hours == 1
    assert limits.deadlines.tool_total_deadline_seconds <= 4
    assert limits.tenant.admission_rate_per_minute > 0 and limits.pool_max_size > 0
    assert "provisional" in EXAMPLE.read_text(encoding="utf-8")


@pytest.mark.parametrize("path", [
    ("eval-e3", "usd_cap"), ("eval-e3", "max_calls"), ("tenant", "usd_cap"),
    ("tenant", "admission_rate_per_minute"), ("pool", "max_size"),
    ("deadlines", "tool_total_deadline_seconds"), ("nfr", "rto_hours"),
])
@pytest.mark.parametrize("mode", ["null", "missing", "zero", "negative", "string", "bool"])
def test_fail_closed(path, mode):
    doc = copy.deepcopy(_doc())
    section, key = path
    if mode == "null":
        doc[section][key] = None
    elif mode == "missing":
        del doc[section][key]
    else:
        doc[section][key] = {"zero": 0, "negative": -1, "string": "5", "bool": True}[mode]
    with pytest.raises(LimitsError):
        parse_limits(doc)


def test_structural_rejections(tmp_path):
    for mutate in (lambda d: d.pop("tenant"), lambda d: d.update(version=2),
                   lambda d: d.update(status="draft"), lambda d: d.update(extra=1),
                   lambda d: d["pool"].update(max_size=1.5),
                   lambda d: d["pool"].update(max_size=float("nan")),
                   lambda d: d["deadlines"].update(tool_total_deadline_seconds=9),
                   lambda d: d["deadlines"].update(tool_call_timeout_seconds=9)):
        doc = copy.deepcopy(_doc())
        mutate(doc)
        with pytest.raises(LimitsError):
            parse_limits(doc)
    with pytest.raises(LimitsError):
        parse_limits(None)
    bad = tmp_path / "x.yaml"
    bad.write_text("a: [", encoding="utf-8")
    with pytest.raises(LimitsError):
        load_limits(bad)
    with pytest.raises(LimitsError):
        load_limits(tmp_path / "missing.yaml")


def test_boolean_version_is_rejected():
    import yaml
    data = yaml.safe_load(EXAMPLE.read_text())
    data["version"] = True
    with pytest.raises(LimitsError):
        parse_limits(data)
