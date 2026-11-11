"""E3-12: scoped metrics; a failing exporter never breaks commits or requests."""
import httpx
import pytest

from incubia_orchestrator.foundation.telemetry import HttpMetrics
from incubia_orchestrator.modules.orchestration.adapters.llm.openai_adapter import OpenAILLM
from incubia_orchestrator.modules.orchestration.ports.llm import GenerationFailure, GenerationRequest
from tests.integration.test_e3_shutdown import (  # noqa: F401  (fixture reuse)
    SETTINGS, D0Deployment, D0Runtime, _D0SqliteLedger, _post, _start, _sigterm, _state, loopback_only,
)


def _boom(event, payload):
    raise RuntimeError("exporter down")


def test_raising_exporter_does_not_break_http_request_or_ledger_commit(tmp_path):
    path = tmp_path / "d0.sqlite"
    ledger = _D0SqliteLedger(path)
    service = D0Deployment(SETTINGS, ledger, D0Runtime(SETTINGS))
    server, thread = _start(service)
    server.metrics.add_exporter(_boom)
    try:
        status, body = _post(server.server_address[1], "k1")
        assert status == 200 and body["revision"] == 1
        assert _state(path) == ["COMPLETED"]
        snap = server.metrics.snapshot()
        assert snap["requests"] == 1
        stages = snap["stage_latency_ms"]
        assert stages["reception_to_outcome"]["count"] == 1
        assert stages["reception_to_delivery"]["count"] == 1
        assert stages["reception_to_delivery"]["p99"] is not None
    finally:
        _sigterm(server, thread)
        ledger.close()


def test_scoped_metrics_snapshot_and_percentiles():
    m = HttpMetrics("dep", "ten")
    m.pool_stats(in_use=3, max_size=5, waiting=1)
    m.pool_wait(12.5)
    m.cost("llm", input_tokens=10, output_tokens=5, usd=0.01)
    m.cost("llm", input_tokens=10, output_tokens=5, usd=0.011, reconciled=True)
    m.rejection("budget", "LOCAL_MONTHLY_LIMIT")
    for ms in (5, 5, 5, 60, 900):
        m.stage_latency("reception_to_outcome", ms)
    s = m.snapshot()
    assert s["db_pool"]["in_use"] == 3 and s["db_pool"]["max"] == 5 and s["db_pool"]["waiting"] == 1
    assert {(c["basis"]) for c in s["cost"]} == {"estimated", "reconciled"}
    assert s["rejections"] == [{"category": "budget", "reason": "LOCAL_MONTHLY_LIMIT", "count": 1}]
    st = s["stage_latency_ms"]["reception_to_outcome"]
    assert (st["p50"], st["p95"], st["p99"]) == (10, 1000, 1000)


def test_labels_never_carry_free_text_or_secrets():
    m = HttpMetrics("dep", "ten")
    secret = "sk-CANARY-secret transcript: hola quiero mi saldo"
    m.rejection(secret, secret)
    m.cost(secret, usd=1)
    for i in range(100):
        m.rejection("budget", f"R{i}")
    s = repr(m.snapshot())
    assert "CANARY" not in s and "transcript" not in s
    assert len(m.snapshot()["rejections"]) <= 33


def test_llm_adapter_records_cost_and_rejections_and_survives_bad_sink():
    m = HttpMetrics("dep", "ten")
    m.add_exporter(_boom)
    ok = {"status": "completed", "usage": {"input_tokens": 7, "output_tokens": 3},
          "output": [{"type": "message", "content": [{"type": "output_text", "text": "hi"}]}]}
    req = GenerationRequest("q", (), "i", 10)
    llm = OpenAILLM(model="m", api_key="k", metrics=m,
                    client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=ok))))
    assert llm.generate(req).text == "hi"
    quota = httpx.Response(429, json={"error": {"type": "insufficient_quota"}})
    llm = OpenAILLM(model="m", api_key="k", metrics=m,
                    client=httpx.Client(transport=httpx.MockTransport(lambda _: quota)))
    with pytest.raises(GenerationFailure):
        llm.generate(req)
    s = m.snapshot()
    assert s["cost"][0]["input_tokens"] == 7 and s["cost"][0]["output_tokens"] == 3
    assert s["rejections"][0]["category"] == "provider_quota"


def test_overflow_percentile_is_strict_json():
    import json
    m = HttpMetrics("d", "t")
    m.stage_latency("reception_to_outcome", 60000)
    assert json.loads(json.dumps(m.snapshot(), allow_nan=False))["stage_latency_ms"][
        "reception_to_outcome"]["p99"] == "+Inf"
