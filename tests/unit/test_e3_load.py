import importlib.util
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "e3_load", Path(__file__).resolve().parents[2] / "scripts/e3/load.py")
load = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(load)

_REAL_CREATE_CONNECTION = socket.create_connection
_REAL_CONNECT = socket.socket.connect


@pytest.fixture(autouse=True)
def loopback_only(no_network, monkeypatch):
    """Stay offline: reopen only 127.0.0.1 for the in-process fake server."""

    def create_connection(address, *args, **kwargs):
        if address[0] != "127.0.0.1":
            raise AssertionError("Network access is disabled in local tests")
        return _REAL_CREATE_CONNECTION(address, *args, **kwargs)

    def connect(sock, address):
        if not isinstance(address, tuple) or address[0] != "127.0.0.1":
            raise AssertionError("Network access is disabled in local tests")
        return _REAL_CONNECT(sock, address)

    monkeypatch.setattr(socket, "create_connection", create_connection)
    monkeypatch.setattr(socket.socket, "connect", connect)


TOKEN = "s3cret-token-" + "x" * 30


class _Server:
    def __init__(self, *, reject_every=0, contract=True):
        outer = self
        self.revisions, self.auth_seen, self.count = {}, [], 0
        self.lock = threading.Lock()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, status, body):
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                outer.auth_seen.append(self.headers.get("Authorization"))
                if self.headers.get("Authorization") != "Bearer " + TOKEN and outer.require_auth:
                    return self._send(401, {})
                self._send(200, {"requests": outer.count})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if outer.require_auth and self.headers.get("Authorization") != "Bearer " + TOKEN:
                    return self._send(401, {})
                with outer.lock:
                    outer.count += 1
                    n = outer.count
                    if reject_every and n % reject_every == 0:
                        return self._send(429, {"error": "limit"})
                    conv = body["conversation_id"]
                    outer.revisions[conv] = outer.revisions.get(conv, 0) + 1
                    rev = outer.revisions[conv]
                if not contract:
                    return self._send(200, {"ok": True})
                self._send(200, {"execution_id": f"x{n}", "conversation_id": conv, "revision": rev})

        self.require_auth = False
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def server():
    srv = _Server()
    yield srv
    srv.close()


def test_target_validation():
    assert load.validate_target("http://127.0.0.1:1/", {}) == "http://127.0.0.1:1"
    for url, env in [
        ("https://svc.example.org", {}),
        ("https://svc.example.org", {"INCUBIA_E3_LOAD_ALLOW_REMOTE": "1"}),
        ("https://svc.example.org", {"INCUBIA_E3_LOAD_ALLOW_REMOTE": "1",
                                     "INCUBIA_E3_LOAD_ALLOWED_HOSTS": "other.example.org"}),
        ("http://svc.example.org", {"INCUBIA_E3_LOAD_ALLOW_REMOTE": "1",
                                    "INCUBIA_E3_LOAD_ALLOWED_HOSTS": "svc.example.org"}),
        ("https://user:pw@svc.example.org", {"INCUBIA_E3_LOAD_ALLOW_REMOTE": "1",
                                            "INCUBIA_E3_LOAD_ALLOWED_HOSTS": "svc.example.org"}),
        ("ftp://127.0.0.1", {}),
    ]:
        with pytest.raises(ValueError):
            load.validate_target(url, env)
    ok = load.validate_target("https://SVC.example.org/", {
        "INCUBIA_E3_LOAD_ALLOW_REMOTE": "1", "INCUBIA_E3_LOAD_ALLOWED_HOSTS": "a.org, svc.example.org"})
    assert ok == "https://SVC.example.org"


def test_burst_profile(server):
    result = load.run(server.url, profile="burst", duration=1, sessions=5, interval=0.2,
                      seed="t", waves=2)
    assert result["status"] == "passed" and result["requests"] == 10
    assert result["revisions_consistent"] and result["unique_execution_ids"] == 10
    assert result["errors"] == 0 and result["limit_rejections"] == 0
    assert result["latency_ms"]["p99"] is not None and result["remote"] is False


def test_sessions_profile(server):
    result = load.run(server.url, profile="sessions", duration=0.5, sessions=3, interval=0.2, seed="t")
    assert result["status"] == "passed" and result["requests"] >= 6


def test_constant_profile_and_rate_bounds(server):
    result = load.run(server.url, profile="constant", duration=1, sessions=4, interval=1,
                      seed="t", rate=10)
    assert result["status"] == "passed" and result["requests"] == 10
    assert result["rate_target_rps"] == 10
    for bad in (0, -1, 1000):
        with pytest.raises(ValueError):
            load.run(server.url, profile="constant", duration=1, sessions=1, interval=1,
                     seed="t", rate=bad)


def test_limit_rejections_counted_and_fail_unless_tolerated():
    srv = _Server(reject_every=2)
    try:
        strict = load.run(srv.url, profile="burst", duration=1, sessions=6, interval=1, seed="t")
        assert strict["limit_rejections"] == 3 and strict["errors"] == 0
        assert strict["status"] == "failed" and strict["http_status_counts"]["429"] == 3
        tolerant = load.run(srv.url, profile="burst", duration=1, sessions=6, interval=1,
                            seed="t2", tolerate_limit_rejections=True)
        assert tolerant["status"] == "passed"
    finally:
        srv.close()


def test_token_sent_and_never_in_result(server):
    server.require_auth = True
    result = load.run(server.url, profile="burst", duration=1, sessions=2, interval=1,
                      seed="t", token=TOKEN)
    assert result["status"] == "passed" and result["authenticated"] is True
    assert TOKEN not in json.dumps(result)
    assert set(server.auth_seen) == {"Bearer " + TOKEN}
    with pytest.raises(RuntimeError):
        load.run(server.url, profile="burst", duration=1, sessions=1, interval=1, seed="t")


def test_unreachable_counts_as_error():
    srv = _Server()
    url = srv.url
    result = load.run(url, profile="burst", duration=1, sessions=1, interval=1, seed="t")
    assert result["status"] == "passed"
    srv.close()
    with pytest.raises(RuntimeError):
        load.run(url, profile="burst", duration=1, sessions=1, interval=1, seed="t")


def test_main_cli_token_from_env_not_printed(server, tmp_path, monkeypatch, capsys):
    server.require_auth = True
    monkeypatch.setenv("INCUBIA_E3_PROBE_TOKEN", TOKEN)
    out = tmp_path / "r.json"
    monkeypatch.setattr("sys.argv", ["load.py", "--url", server.url, "--profile", "burst",
                                     "--sessions", "2", "--output", str(out)])
    assert load.main() == 0
    assert TOKEN not in capsys.readouterr().out + out.read_text()


def test_nonfinite_duration_rejected(server):
    for bad in (float("nan"), float("inf"), 0):
        with pytest.raises(ValueError):
            load.run(server.url, profile="sessions", duration=bad, sessions=1, interval=1, seed="t")


def test_all_rejected_never_passes():
    srv = _Server(reject_every=1)
    try:
        result = load.run(srv.url, profile="burst", duration=1, sessions=3, interval=1, seed="t",
                          tolerate_limit_rejections=True)
        assert result["status"] == "failed" and result["limit_rejections"] == 3
    finally:
        srv.close()


def test_redact_token_in_metrics():
    assert load._redact({"a": ["x" + TOKEN], TOKEN: 1}, TOKEN) == {"a": ["x[redacted]"], "[redacted]": 1}


def test_ok_without_contract_fields_is_an_error_not_a_success():
    srv = _Server(contract=False)
    try:
        result = load.run(srv.url, profile="burst", duration=1, sessions=3, interval=1, seed="nc")
        assert result["status"] == "failed"
        assert result["success_count"] == 0 and result["errors"] == 3
    finally:
        srv.close()
