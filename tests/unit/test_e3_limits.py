import copy
from pathlib import Path

import pytest
import yaml

from incubia_orchestrator.foundation.limits import LimitsError, load_limits, parse_limits

EXAMPLE = Path(__file__).resolve().parents[2] / "config/e3/limits.example.yaml"


def _doc():
    return yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))


def test_example_loads_and_is_ratified():
    limits = load_limits(EXAMPLE)
    assert limits.status == "ratified"
    assert limits.nfr.slo_p95_seconds == 5 and limits.nfr.rpo_hours == 12
    assert limits.nfr.rto_hours == 1
    assert limits.deadlines.tool_total_deadline_seconds <= 4
    assert limits.tenant.admission_rate_per_minute > 0 and limits.pool_max_size > 0


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


# --- runtime loading, ratification gate, admission, deadlines (E3-5) ---------
import http.client
import json
import socket
import threading

from incubia_orchestrator.foundation.limits import (
    AdmissionLimiter, load_runtime_limits)


_REAL_CREATE_CONNECTION, _REAL_CONNECT = socket.create_connection, socket.socket.connect


@pytest.fixture
def loopback(no_network, monkeypatch):
    def create_connection(address, *args, **kwargs):
        assert address[0] == "127.0.0.1", "Network access is disabled in local tests"
        return _REAL_CREATE_CONNECTION(address, *args, **kwargs)

    def connect(sock, address):
        assert isinstance(address, tuple) and address[0] == "127.0.0.1"
        return _REAL_CONNECT(sock, address)

    monkeypatch.setattr(socket, "create_connection", create_connection)
    monkeypatch.setattr(socket.socket, "connect", connect)


def _write(tmp_path, status):
    doc = _doc()
    doc["status"] = status
    path = tmp_path / "limits.yaml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return path


def test_production_requires_ratified(tmp_path):
    path = _write(tmp_path, "provisional")
    env = {"INCUBIA_E3_LIMITS_FILE": str(path)}
    with pytest.raises(LimitsError, match="ratified"):
        load_runtime_limits(env)
    assert load_runtime_limits({**env, "INCUBIA_E3_ALLOW_PROVISIONAL": "1"}).status == "provisional"
    assert load_runtime_limits(env, allow_provisional=True).status == "provisional"
    ratified = _write(tmp_path, "ratified")
    assert load_runtime_limits({"INCUBIA_E3_LIMITS_FILE": str(ratified)}).status == "ratified"


def test_runtime_load_fails_closed_on_missing_or_invalid(tmp_path):
    with pytest.raises(LimitsError):
        load_runtime_limits({"INCUBIA_E3_LIMITS_FILE": str(tmp_path / "nope.yaml")})
    bad = tmp_path / "bad.yaml"
    bad.write_text("version: 1\nstatus: ratified\n", encoding="utf-8")
    with pytest.raises(LimitsError):
        load_runtime_limits({"INCUBIA_E3_LIMITS_FILE": str(bad)})


def test_default_path_resolves_repo_example():
    assert load_runtime_limits({}).deadlines.tool_total_deadline_seconds == 4


def test_token_bucket_refills_and_isolates_tenants():
    now = [0.0]
    limiter = AdmissionLimiter(2, clock=lambda: now[0])
    assert limiter.try_acquire("a") and limiter.try_acquire("a")
    assert not limiter.try_acquire("a")
    assert limiter.try_acquire("b")
    now[0] = 30.0  # 2/min -> one token per 30 s
    assert limiter.try_acquire("a") and not limiter.try_acquire("a")


def test_probe_rate_limit_and_deadlines_from_limits(loopback):
    from incubia_orchestrator.foundation.contracts.execution import ExecutionScope
    from incubia_orchestrator.foundation.telemetry import HttpMetrics
    from incubia_orchestrator.interfaces.http.e3_probe import (
        ProbeHttpServer, ProbeService, RateLimited)
    from incubia_orchestrator.modules.orchestration.application.grounded_response import GroundedAnswer
    metrics = HttpMetrics("d", "t")
    service = ProbeService(
        token="t" * 40, scope=ExecutionScope("d", "t", "", "a"),
        workflow=lambda *a: GroundedAnswer("ok", (), (), False), ready=lambda: True,
        metrics=metrics, admission=AdmissionLimiter(1, clock=lambda: 0.0))
    service.execute({"query": "x"})
    with pytest.raises(RateLimited):
        service.execute({"query": "x"})
    assert "TENANT_RATE" in json.dumps(metrics.snapshot())
    server = ProbeHttpServer(("127.0.0.1", 0), service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        conn.request("POST", "/v1/probe", body=json.dumps({"query": "x"}), headers={
            "Content-Type": "application/json", "Authorization": "Bearer " + "t" * 40})
        response = conn.getresponse()
        assert response.status == 429 and response.getheader("Retry-After") == "60"
        response.read()
        conn.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def test_http_main_returns_429_when_tenant_rate_exceeded(loopback):
    from incubia_orchestrator.bootstrap.d0 import D0Settings
    from incubia_orchestrator.interfaces.http.main import E3D0HttpServer

    class Service:
        settings = D0Settings("x", "dep", "ten", "act")

        def execute(self, **_):
            return {"status": "completed"}

    limits = parse_limits({**_doc(), "tenant": {**_doc()["tenant"], "admission_rate_per_minute": 1}})
    server = E3D0HttpServer(("127.0.0.1", 0), Service(), limits)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    statuses = []
    try:
        for _ in range(2):
            conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
            conn.request("POST", "/v1/executions",
                         body=json.dumps({"message": "hi", "conversation_id": "c"}),
                         headers={"Content-Type": "application/json", "Idempotency-Key": "k"})
            response = conn.getresponse()
            response.read()
            statuses.append((response.status, response.getheader("Retry-After")))
        assert statuses[0][0] == 200 and statuses[1] == (429, "60")
        assert ("limit", "TENANT_RATE") in {tuple(k) if isinstance(k, tuple) else k
                                            for k in server.metrics._rejections}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def test_openfoodfacts_config_takes_deadlines_from_limits():
    from incubia_orchestrator.modules.orchestration.adapters.tools.openfoodfacts import OpenFoodFactsConfig
    d = load_limits(EXAMPLE).deadlines
    cfg = OpenFoodFactsConfig(timeout_seconds=d.tool_call_timeout_seconds,
                              total_deadline_seconds=d.tool_total_deadline_seconds,
                              max_attempts=d.tool_max_attempts)
    assert (cfg.timeout_seconds, cfg.total_deadline_seconds, cfg.max_attempts) == (2, 4, 2)


def test_admission_evicts_refilled_buckets_when_table_full():
    now = [0.0]
    limiter = AdmissionLimiter(60, clock=lambda: now[0], max_tenants=2)
    assert limiter.try_acquire("a") and limiter.try_acquire("b")
    assert not limiter.try_acquire("c")  # both active, table saturated
    now[0] = 5.0  # both refilled
    assert limiter.try_acquire("c")


def test_probe_env_override_is_clamped_to_ratified_ceiling(monkeypatch):
    from incubia_orchestrator.interfaces.http.e3_probe import _env_or
    monkeypatch.setenv("X_LIMIT", "20000")
    assert _env_or("X_LIMIT", int, 2000) == 2000
    monkeypatch.setenv("X_LIMIT", "20")
    assert _env_or("X_LIMIT", int, 2000) == 20
    monkeypatch.delenv("X_LIMIT")
    assert _env_or("X_LIMIT", int, 2000) == 2000
