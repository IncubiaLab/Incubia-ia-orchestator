"""Offline tests for the integrated E3-5 campaign runner (no Neon, no OpenAI)."""
import json
import socket
import sys
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/e3"))
import e3_5_lib as lib  # noqa: E402
import run_e3_5_campaign as runner  # noqa: E402

_REAL_CREATE = socket.create_connection
_REAL_CONNECT = socket.socket.connect

RUNTIME = "postgresql://incubia_runtime:rt-secret-pw@ep-x-pooler.c-2.us-east-2.aws.neon.tech/neondb?sslmode=require"
MIGRATOR = "postgresql://incubia_migrator:mg-secret-pw@ep-x.c-2.us-east-2.aws.neon.tech/neondb?sslmode=require"
HOST = "ep-x.c-2.us-east-2.aws.neon.tech"
TEMP_DSN = "postgresql://incubia_migrator:tmp-secret-pw@ep-tmp.c-2.us-east-2.aws.neon.tech/neondb?sslmode=require"


def good_env(**extra):
    env = {"INCUBIA_E3_5_CAMPAIGN": "1", "INCUBIA_E3_NEON_TESTS": "1", "INCUBIA_E3_NEON_BRANCH": lib.BRANCH,
           "INCUBIA_E3_5_BUDGET_APPROVED": "1", "INCUBIA_E3_5_BUDGET_USD": "5",
           "DATABASE_URL": RUNTIME, "INCUBIA_MIGRATION_DATABASE_URL": MIGRATOR}
    env.update(extra)
    return env


@pytest.fixture(autouse=True)
def loopback_only(no_network, monkeypatch):
    def create(address, *a, **k):
        if address[0] != "127.0.0.1":
            raise AssertionError("Network access is disabled in local tests")
        return _REAL_CREATE(address, *a, **k)

    def connect(sock, address):
        if not isinstance(address, tuple) or address[0] != "127.0.0.1":
            raise AssertionError("Network access is disabled in local tests")
        return _REAL_CONNECT(sock, address)
    monkeypatch.setattr(socket, "create_connection", create)
    monkeypatch.setattr(socket.socket, "connect", connect)


# ------------------------------------------------------------------ fakes


class FakeCursor:
    def __init__(self, db, dsn):
        self.db, self.dsn, self.rows, self.rowcount = db, dsn, [(0,)], 1

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=()):
        self.db.log.append((self.dsn, sql, params))
        self.rows = [(0,)]
        for needle, rows in self.db.rules:
            if needle in sql:
                self.rows = rows
                break

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


class FakeConn:
    def __init__(self, db, dsn):
        self.db, self.dsn = db, dsn

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return FakeCursor(self.db, self.dsn)

    def transaction(self):
        return self


class FakeDB:
    def __init__(self, rules=None):
        self.log, self.rules = [], rules or []

    def __call__(self, dsn):
        return FakeConn(self, dsn)

    def sql(self):
        return [s for _, s, _ in self.log]


def load_result(status="passed", seed="s", **kw):
    base = {"status": status, "seed": seed, "profile": "burst", "requests": 10, "success_count": 10, "errors": 0,
            "limit_rejections": 0, "revisions_consistent": True, "unique_execution_ids": 10,
            "latency_ms": {"p50": 100.0, "p95": 900.0, "p99": 1500.0, "mean": 300.0},
            "http_status_counts": {"200": 10}, "duration_observed_seconds": 600.0,
            "metrics_before": {"db_pool": {"max": 5, "timeouts": 0}, "cost": []},
            "metrics_after": {"db_pool": {"max": 5, "peak_in_use": 5, "timeouts": 2, "waiting": 0},
                              "cost": [{"kind": "llm", "basis": "estimated", "calls": 3, "input_tokens": 30,
                                        "output_tokens": 9, "usd": 0.10},
                                       {"kind": "llm", "basis": "reconciled", "calls": 3, "input_tokens": 30,
                                        "output_tokens": 9, "usd": 0.105}]}}
    base.update(kw)
    return base


class FakeApp:
    instances = []

    def __init__(self, command, env, *, url, token=None, http_status=None):
        self.command, self.env, self.pid, self.stopped = command, env, 4242, False
        FakeApp.instances.append(self)

    def start(self):
        pass

    def stop(self):
        self.stopped = True

    def sigterm(self):
        return {"exited_within_deadline": True, "exit_code": 0, "drain_seconds": 1.2}


class FakeSampler:
    def __init__(self, pid):
        pass

    def start(self):
        return self

    def stop(self):
        return {"source": "fake", "cpu_percent_max": 50.0, "rss_mb_max": 100.0}


class FakeProxy:
    def __init__(self, upstream=None):
        self.base_url, self.hits, self.mode = "http://127.0.0.1:9", {}, "pass"

    def start(self):
        return self

    def set_mode(self, mode):
        self.mode = mode
        self.hits[mode] = self.hits.get(mode, 0) + 1

    def stop(self):
        pass


class FakeLedger:
    def __init__(self):
        self.now, self.claim = 0.0, None
        self.gen = 0

    def tick(self, seconds):
        self.now += seconds

    def acquire_claim(self, scope, *, resource_type, resource_key, owner_id, lease_seconds):
        if self.claim and self.claim["until"] > self.now:
            return None
        self.gen += 1
        self.claim = {"owner": owner_id, "gen": self.gen, "until": self.now + lease_seconds}
        return type("T", (), {"generation": self.gen, "owner_id": owner_id})()

    def renew_claim(self, token, *, lease_seconds):
        if self.claim and self.claim["gen"] == token.generation and self.claim["until"] > self.now:
            self.claim["until"] = self.now + lease_seconds
            return True
        return False

    def release_claim(self, token):
        if self.claim and self.claim["gen"] == token.generation:
            self.claim["until"] = self.now
            return True
        return False

    def lease_state(self, *args):
        return (self.claim["until"], self.now) if self.claim else (None, None)


class FakeNeon:
    def __init__(self, fail_delete=False, mismatch=False):
        self.calls, self.fail_delete, self.mismatch = [], fail_delete, mismatch

    def create_branch(self, name, parent, expires_at):
        lib.assert_restore_branch(name)
        assert parent == lib.BRANCH and expires_at > datetime.now(UTC)
        self.calls.append(("create", name))
        return {"endpoints": [{"host": "ep-tmp.c-2.us-east-2.aws.neon.tech"}]} if self.mismatch is False else \
            {"endpoints": [{"host": "ep-zzz.c-2.us-east-2.aws.neon.tech"}]}

    def connection_string(self, branch, role):
        self.calls.append(("dsn", branch))
        return TEMP_DSN

    def delete_branch(self, name):
        self.calls.append(("delete", name))
        if self.fail_delete:
            raise RuntimeError("boom")


class FakeBackup:
    counts = {"inbox_events": 3, "conversations": 2, "turns": 3, "outcomes": 3, "deliveries": 3}

    def __init__(self, dsn):
        self.dsn = dsn

    def export(self, scope, path):
        Path(path).write_text("{}")
        done = (datetime.now(UTC) - timedelta(seconds=30)).isoformat().replace("+00:00", "Z")
        return type("E", (), {"manifest": {"export_completed_at": done}, "table_counts": dict(self.counts),
                              "export_duration_seconds": 1.5})()

    def import_package(self, path, *, expected_scope=None, clear_claims=True):
        counts = dict(self.counts)

        class R:
            table_counts = counts

            def as_dict(self):
                return {"status": "COMPLETED", "table_counts": counts}
        return R()


def restore_rules():
    names = sorted(p.stem for p in (ROOT / "migrations/postgres").glob("*.sql"))
    return [
        ("SELECT version FROM schema_migrations", [(n,) for n in names]),
        ("to_regclass('public.knowledge_chunks')", [(False,)]),
        ("to_regclass('public.audit_events')", [(True,)]),
        ("count(*) FILTER", [(10, 10)]),
        ("GROUP BY state", [("DELIVERED", 90), ("UNKNOWN_EFFECT", 5)]),
        ("AND state=%s", [(5,)]),
        ("SELECT count(*) FROM turns WHERE", [(20,)]),
        ("role_table_grants", [("INSERT",), ("SELECT",)]),
    ]


def make_args(tmp_path, *extra):
    return runner.build_parser().parse_args(["--output-dir", str(tmp_path), "--allow-short", "--fault-seconds", "1",
                                              "--conversations", "10", "--turns", "40", "--chunks", "0",
                                              "--profile-seconds", "30", "--burst-waves", "2",
                                              "--burst-interval", "5", *extra])


def make_deps(db, load_fn=None):
    ledger = FakeLedger()
    calls = []

    def default_load(url, **kw):
        calls.append(kw)
        status = "failed" if "f-revoked" in kw["seed"] else "passed"
        return load_result(status, seed=kw["seed"])
    def fire(url, count, label, token=None, timeout=90.0):
        return [], [(200, f"e{i}") for i in range(count)]
    return runner.Deps(
        lease_state=ledger.lease_state, fire_requests=fire, in_flight=lambda u, t: 1,
        connect=db, neon=FakeNeon(), load_run=load_fn or default_load, http_status=lambda u, t: 200,
        app_factory=FakeApp, sampler_factory=FakeSampler, proxy_factory=FakeProxy,
        ledger_factory=lambda dsn: ledger, backup_factory=FakeBackup,
        run_cmd=lambda *a, **k: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
        which=lambda n: None, sleep=lambda s: ledger.tick(s), now=lib.utc_now), calls


# ------------------------------------------------------------------ guards


def test_guards_pass_and_return_branch():
    g = lib.check_guards(good_env(), resolve_host=lambda: HOST)
    assert g.branch == lib.BRANCH and g.budget_usd == 5.0
    assert "rt-secret-pw" not in repr(g)


@pytest.mark.parametrize("key,value", [
    ("INCUBIA_E3_5_CAMPAIGN", "0"), ("INCUBIA_E3_NEON_TESTS", ""), ("INCUBIA_E3_NEON_BRANCH", "main"),
    ("INCUBIA_E3_5_BUDGET_APPROVED", ""), ("INCUBIA_E3_5_BUDGET_USD", "nan"), ("INCUBIA_E3_5_BUDGET_USD", "0"),
    ("DATABASE_URL", MIGRATOR), ("INCUBIA_MIGRATION_DATABASE_URL", RUNTIME),
])
def test_guards_fail_closed(key, value):
    with pytest.raises(lib.GuardError):
        lib.check_guards(good_env(**{key: value}), resolve_host=lambda: HOST)


def test_guard_rejects_unapproved_branch_host():
    with pytest.raises(lib.GuardError):
        lib.check_guards(good_env(), resolve_host=lambda: "ep-other.c-2.us-east-2.aws.neon.tech")


def test_guard_does_not_leak_process_env():
    import os
    before = os.environ.get("DATABASE_URL")
    lib.check_guards(good_env(), resolve_host=lambda: HOST)
    assert os.environ.get("DATABASE_URL") == before


def test_synthetic_scope_and_restore_branch_guards():
    lib.assert_synthetic_scope(lib.SYNTH_DEPLOYMENT, lib.SYNTH_TENANT)
    with pytest.raises(lib.GuardError):
        lib.assert_synthetic_scope("prod", lib.SYNTH_TENANT)
    for bad in (lib.BRANCH, "main", "e3-5-restore-", "e3-5-restore-UP PER"):
        with pytest.raises(lib.GuardError):
            lib.assert_restore_branch(bad)
    lib.assert_restore_branch("e3-5-restore-20261023-abc")


def test_neon_cli_refuses_non_synthetic_parent_and_names():
    cli = lib.NeonCli(run=lambda *a, **k: pytest.fail("must not run"))
    with pytest.raises(lib.GuardError):
        cli.create_branch("e3-5-restore-abcdef12", "main", lib.utc_now())
    with pytest.raises(lib.GuardError):
        cli.delete_branch(lib.BRANCH)
    with pytest.raises(lib.GuardError):
        cli.connection_string("e3-5-restore-abcdef12", "neondb_owner")


def test_neon_cli_command_and_dsn_validation():
    seen = []

    def run(cmd, **kw):
        seen.append(cmd)
        out = TEMP_DSN if "connection-string" in cmd else "{}"
        return type("R", (), {"returncode": 0, "stdout": out, "stderr": ""})()
    cli = lib.NeonCli(run=run)
    cli.create_branch("e3-5-restore-abcdef12", lib.BRANCH, lib.utc_now() + timedelta(hours=2))
    assert "--expires-at" in seen[0] and "--parent" in seen[0]
    assert cli.connection_string("e3-5-restore-abcdef12", lib.MIGRATOR_ROLE) == TEMP_DSN
    cli.delete_branch("e3-5-restore-abcdef12")


def test_wipe_refuses_primary_host_and_non_synthetic():
    db = FakeDB()
    with pytest.raises(lib.GuardError):
        lib.wipe_scope(db, MIGRATOR, lib.SYNTH_DEPLOYMENT, lib.SYNTH_TENANT, primary_host=HOST)
    with pytest.raises(lib.GuardError):
        lib.wipe_scope(db, TEMP_DSN, "prod", "x", primary_host=HOST)
    assert not db.log
    lib.wipe_scope(db, TEMP_DSN, lib.SYNTH_DEPLOYMENT, lib.SYNTH_TENANT, primary_host=HOST)
    assert all("deployment_id=%s AND tenant_id=%s" in s or "set_config" in s for s in db.sql())


def test_grant_changes_are_scoped():
    db = FakeDB([("role_table_grants", [("SELECT",)])])
    with pytest.raises(lib.GuardError):
        lib.set_grants(db, MIGRATOR, ["SELECT"], revoke=True, table="turns")
    with pytest.raises(lib.GuardError):
        lib.set_grants(db, MIGRATOR, ["ALL"], revoke=True)
    with pytest.raises(lib.GuardError):
        lib.capture_grants(db, MIGRATOR, role="neondb_owner")
    lib.set_grants(db, MIGRATOR, ["SELECT", "INSERT"], revoke=True)
    assert db.sql()[-1] == "REVOKE INSERT, SELECT ON inbox_events FROM incubia_runtime"


# -------------------------------------------------------------------- seed


def test_seed_statements_are_idempotent_and_scoped():
    plan = lib.SeedPlan(5000, 50000, 100)
    stmts = lib.seed_statements(plan, lib.SYNTH_DEPLOYMENT, lib.SYNTH_TENANT)
    assert all("ON CONFLICT DO NOTHING" in sql for _, sql, _ in stmts)
    assert {t for t, _, _ in stmts} == {"conversations", "inbox_events", "turns", "outcomes", "deliveries"}
    assert sum(t == "turns" for t, _, _ in stmts) == 5
    with pytest.raises(lib.GuardError):
        lib.seed_statements(plan, "tenant-real", lib.SYNTH_TENANT)
    with pytest.raises(ValueError):
        lib.SeedPlan(10, 5, 0).validate()


def test_run_seed_with_and_without_knowledge():
    rules = [("to_regclass('public.knowledge_chunks')", [(True,)]), ("SELECT count(*)", [(40,)])]
    db = FakeDB(rules)
    out = lib.run_seed(db, MIGRATOR, lib.SeedPlan(10, 40, 4000))
    assert out["status"] == "passed" and out["knowledge_tables_present"]
    assert any("knowledge_chunks" in s for s in db.sql())
    db2 = FakeDB([("to_regclass('public.knowledge_chunks')", [(False,)]), ("SELECT count(*)", [(40,)])])
    out2 = lib.run_seed(db2, MIGRATOR, lib.SeedPlan(10, 40, 50))
    assert out2["knowledge_skipped_reason"] and not any("knowledge_chunks (" in s for s in db2.sql())


# ----------------------------------------------------------- fault proxy


def _get(url, timeout=3):
    try:
        with urlopen(Request(url, data=b"{}", method="POST"), timeout=timeout) as r:
            return r.status, r.read()
    except HTTPError as exc:
        return exc.code, exc.read()


def test_fault_proxy_modes():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    up = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=up.serve_forever, daemon=True).start()
    proxy = lib.FaultProxy(f"http://127.0.0.1:{up.server_address[1]}", hold_seconds=5).start()
    try:
        assert _get(proxy.base_url + "/v1/x")[0] == 200
        proxy.set_mode("http_5xx")
        assert _get(proxy.base_url + "/v1/x")[0] == 503
        proxy.set_mode("timeout")
        with pytest.raises(Exception):
            _get(proxy.base_url + "/v1/x", timeout=0.5)
        proxy.set_mode("reset")
        with pytest.raises(Exception):
            _get(proxy.base_url + "/v1/x")
        with pytest.raises(ValueError):
            proxy.set_mode("nope")
        assert set(proxy.hits) == {"pass", "http_5xx", "timeout", "reset"}
    finally:
        proxy.stop()
        up.shutdown()
    with pytest.raises(ValueError):
        lib.FaultProxy("http://example.com")


# --------------------------------------------------------------- sampling


def test_process_sampler_proc_fallback(tmp_path, monkeypatch):
    proc = tmp_path / "77"
    proc.mkdir()
    (proc / "status").write_text("Name:\tx\nVmRSS:\t   2048 kB\n")
    ticks = iter([100, 300])
    clock = iter([0.0, 2.0, 4.0])
    sampler = lib.ProcessSampler(77, proc_root=str(tmp_path), clock=lambda: next(clock))
    sampler._psutil, sampler.source = None, "proc"
    hz = __import__("os").sysconf("SC_CLK_TCK")
    for ticks_now in (100, 100 + 2 * hz):
        (proc / "stat").write_text(f"77 (x y) S 1 1 1 0 -1 0 0 0 0 0 {ticks_now} 0 0 0 20 0 1 0 1 1 1")
        sampler.sample_once()
    summary = sampler.summary()
    assert summary["samples"] == 2 and summary["rss_mb_max"] == 2.0
    assert summary["cpu_percent_max"] == pytest.approx(100.0, rel=0.01)
    del ticks


def test_pool_and_cost_helpers():
    r = load_result()
    pool = lib.pool_summary(r["metrics_before"], r["metrics_after"])
    assert pool["peak_in_use"] == 5 and pool["timeouts_delta"] == 2
    delta = lib.cost_delta(r["metrics_before"], r["metrics_after"])
    assert delta["llm:estimated"]["usd"] == 0.10
    slim = lib.load_slim(r)
    assert "metrics_before" not in slim and slim["pool"]["max"] == 5


def test_reconcile_cost_and_rpo_rto():
    assert lib.reconcile_cost(0.10, 0.105, budget_usd=1)["ok"]
    assert not lib.reconcile_cost(0.10, 0.20)["ok"]
    assert not lib.reconcile_cost(0.10, 0.105, budget_usd=0.05)["ok"]
    assert lib.reconcile_cost(0.1, None)["status"] == "skipped"
    now = lib.utc_now()
    assert lib.rpo_rto(now - timedelta(hours=1), now, 120)["rpo_ok"]
    sla = lib.rpo_rto(now - timedelta(hours=13), now, 4000)
    assert not sla["rpo_ok"] and not sla["rto_ok"]


def test_redact_hides_dsn_and_secrets():
    out = lib.redact(f"failed {RUNTIME} token=abc123456 sk-abcdefghijk", ["abc123456"])
    assert "rt-secret-pw" not in out and "abc123456" not in out and "sk-abcdefghijk" not in out


# ----------------------------------------------------------------- summary


def test_summary_shape_never_closes_gate():
    s = lib.build_summary({}, run_id="r")
    assert s["gate_closed"] is False and not s["all_criteria_passed"]
    assert set(s["criteria"].values()) == {"inconclusive"}
    assert list(s["phases"]) == list(lib.PHASE_ORDER)


# -------------------------------------------------------------- orchestration


def test_dry_run_touches_nothing(capsys):
    boom = runner.Deps(connect=lambda d: pytest.fail("db"), neon=object(), load_run=lambda *a, **k: pytest.fail("load"))
    assert runner.main(["--dry-run"], deps=boom, env={}) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["dry_run"] and [p["name"] for p in plan["phases"]] == list(lib.PHASE_ORDER)
    assert any("INCUBIA_E3_5_CAMPAIGN=1" in e for e in plan["required_env"])


def test_main_refuses_without_authorization(capsys, tmp_path):
    assert runner.main(["--output-dir", str(tmp_path)], deps=runner.Deps(), env={}) == 2
    assert "Refusing E3-5 campaign" in capsys.readouterr().err
    assert not list(tmp_path.iterdir())


def test_main_rejects_unknown_phase(capsys):
    assert runner.main(["--phases", "seed,boom", "--dry-run"]) == 2


def test_short_profiles_rejected_without_flag(tmp_path):
    args = runner.build_parser().parse_args(["--output-dir", str(tmp_path)])
    args.profile_seconds, args.burst_waves = 10, 1
    deps, _ = make_deps(FakeDB(restore_rules()))
    c = runner.Campaign(args, good_env(), lib.check_guards(good_env(), resolve_host=lambda: HOST), deps, tmp_path, "e3-5-2026-10-23-abc123")
    c.start_app()
    out = c.run(["load"])
    assert out["phases"]["load"] == "error"
    assert "profile sessions" in json.loads((tmp_path / "load.json").read_text())["error"]


def test_full_campaign_with_fakes(tmp_path):
    FakeApp.instances.clear()
    db = FakeDB(restore_rules())
    deps, calls = make_deps(db)
    args = make_args(tmp_path)
    guarded = lib.check_guards(good_env(), resolve_host=lambda: HOST)
    campaign = runner.Campaign(args, good_env(), guarded, deps, tmp_path, "e3-5-2026-10-23-abc123")
    summary = campaign.run(list(lib.PHASE_ORDER))
    assert summary["gate_closed"] is False
    assert list(summary["phases"]) == list(lib.PHASE_ORDER)
    for name in lib.PHASE_ORDER:
        data = json.loads((tmp_path / f"{name}.json").read_text())
        assert data["gate_closed"] is False and data["phase"] == name
    assert (tmp_path / "summary.json").exists()
    # evidence never contains secrets
    blob = "".join(p.read_text() for p in tmp_path.glob("*.json"))
    for secret in ("rt-secret-pw", "mg-secret-pw", "tmp-secret-pw"):
        assert secret not in blob
    # unique seeds per load invocation within the run, and the run id is embedded
    seeds = [c["seed"] for c in calls if c["profile"] in {"sessions", "constant"}]
    assert len(seeds) == len(set(seeds)) and all("abc123" in s for s in seeds)
    faults = json.loads((tmp_path / "faults.json").read_text())
    assert faults["steps"]["claim_expiry_fencing"]["status"] == "passed"
    assert faults["steps"]["credential_revocation"]["status"] == "passed"
    assert faults["steps"]["sigterm_drain"]["status"] == "passed"
    assert faults["steps"]["provider_down"]["status"] == "passed"
    # grants were revoked then granted back, saved first
    ddl = [s for s in db.sql() if s.startswith(("REVOKE", "GRANT"))]
    assert [d.split()[0] for d in ddl] == ["REVOKE", "GRANT"]
    assert (tmp_path / "grants-to-restore.json").exists()
    restore = json.loads((tmp_path / "restore.json").read_text())
    assert restore["status"] == "passed" and restore["temp_branch"]["deleted"]
    assert [c[0] for c in deps.neon.calls] == ["create", "dsn", "delete"]
    assert restore["rpo_rto"]["rpo_ok"] and restore["rpo_rto"]["rto_ok"]
    # wipe/import only ever hit the temp DSN, never the primary
    wipes = [(dsn, s) for dsn, s, _ in db.log if s.startswith("DELETE")]
    assert wipes and all(dsn == TEMP_DSN for dsn, _ in wipes)
    rollback = json.loads((tmp_path / "rollback.json").read_text())
    assert rollback["status"] == "inconclusive" and rollback["steps"]["image_n1"]["status"] == "skipped"
    cost = json.loads((tmp_path / "cost.json").read_text())
    assert cost["status"] == "passed"
    # short run can never produce G9 load evidence
    assert summary["criteria"]["G9_load_measured_10min_profiles"] == "failed"
    assert all(app.stopped for app in FakeApp.instances)


def test_revocation_grants_restored_even_if_probe_raises(tmp_path):
    db = FakeDB(restore_rules())

    def exploding(url, **kw):
        if "f-revoked" in kw["seed"]:
            raise KeyError("boom")
        return load_result(seed=kw["seed"])
    deps, _ = make_deps(db, load_fn=exploding)
    args = make_args(tmp_path)
    c = runner.Campaign(args, good_env(), lib.check_guards(good_env(), resolve_host=lambda: HOST), deps, tmp_path, "e3-5-2026-10-23-abc123")
    out = c.run(["faults"])
    step = json.loads((tmp_path / "faults.json").read_text())["steps"]["credential_revocation"]
    assert step["status"] == "error"
    assert [s.split()[0] for s in db.sql() if s.startswith(("REVOKE", "GRANT"))] == ["REVOKE", "GRANT"]
    assert out["phases"]["faults"] == "failed" or out["phases"]["faults"] == "error"


def test_restore_deletes_branch_even_when_import_fails(tmp_path):
    db = FakeDB(restore_rules())
    deps, _ = make_deps(db)

    class Bad(FakeBackup):
        def import_package(self, *a, **k):
            if self.dsn == TEMP_DSN:
                raise RuntimeError("import exploded")
            return super().import_package(*a, **k)
    deps.backup_factory = Bad
    c = runner.Campaign(make_args(tmp_path), good_env(), lib.check_guards(good_env(), resolve_host=lambda: HOST),
                        deps, tmp_path, "e3-5-2026-10-23-abc123")
    summary = c.run(["restore"])
    assert summary["phases"]["restore"] == "error"
    assert any(x[0] == "delete" for x in deps.neon.calls)


def test_restore_fails_when_branch_not_deleted(tmp_path):
    deps, _ = make_deps(FakeDB(restore_rules()))
    deps.neon = FakeNeon(fail_delete=True)
    c = runner.Campaign(make_args(tmp_path), good_env(), lib.check_guards(good_env(), resolve_host=lambda: HOST),
                        deps, tmp_path, "e3-5-2026-10-23-abc123")
    c.run(["restore"])
    assert json.loads((tmp_path / "restore.json").read_text())["status"] == "failed"


def test_rollback_image_digest_rules(tmp_path):
    deps, _ = make_deps(FakeDB(restore_rules()))
    c = runner.Campaign(make_args(tmp_path), good_env(), lib.check_guards(good_env(), resolve_host=lambda: HOST),
                        deps, tmp_path, "e3-5-2026-10-23-abc123")
    assert c._rollback_image()["status"] == "skipped"
    c.args.image_n1_digest = "repo/app:latest"
    assert c._rollback_image()["status"] == "failed"
    c.args.image_n1_digest = "repo/app@sha256:" + "a" * 64
    assert c._rollback_image()["status"] == "skipped"  # docker missing
    cmds = []
    deps.which = lambda n: "/usr/bin/docker"
    deps.run_cmd = lambda cmd, **k: cmds.append(cmd) or type("R", (), {"returncode": 0})()
    out = c._rollback_image()
    assert out["status"] == "passed" and out["digest_pinned"]
    assert cmds[0][:3] == ["docker", "run", "-d"] and cmds[-1][:3] == ["docker", "rm", "-f"]
    assert not any("postgres" in part for cmd in cmds for part in cmd)  # DSNs never on the command line


def test_external_app_skips_process_faults(tmp_path):
    deps, _ = make_deps(FakeDB(restore_rules()))
    args = make_args(tmp_path, "--external-app")
    c = runner.Campaign(args, good_env(), lib.check_guards(good_env(), resolve_host=lambda: HOST), deps, tmp_path, "e3-5-2026-10-23-abc123")
    c.run(["faults"])
    steps = json.loads((tmp_path / "faults.json").read_text())["steps"]
    assert steps["provider_down"]["status"] == "skipped" and steps["sigterm_drain"]["status"] == "skipped"
    assert json.loads((tmp_path / "faults.json").read_text())["status"] == "inconclusive"


def test_recover_grants_mode(tmp_path, capsys, monkeypatch):
    saved = tmp_path / "g.json"
    saved.write_text(json.dumps({"table": lib.GRANT_TABLE, "role": lib.RUNTIME_ROLE, "privileges": ["SELECT"]}))
    monkeypatch.setattr(lib, "check_guards", lambda env, **k: lib.Guarded(RUNTIME, MIGRATOR, 5.0))
    db = FakeDB()
    assert runner.main(["--recover-grants", str(saved)], deps=runner.Deps(connect=db), env=good_env()) == 0
    assert db.sql() == ["GRANT SELECT ON inbox_events TO incubia_runtime"]


def test_restore_refuses_when_dsn_not_the_new_branch(tmp_path):
    db = FakeDB(restore_rules())
    deps, _ = make_deps(db)
    deps.neon = FakeNeon(mismatch=True)
    c = runner.Campaign(make_args(tmp_path), good_env(), lib.check_guards(good_env(), resolve_host=lambda: HOST),
                        deps, tmp_path, "e3-5-2026-10-23-abc123")
    out = c.run(["restore"])
    assert out["phases"]["restore"] == "error"
    assert not [1 for dsn, s, _ in db.log if s.startswith("DELETE")]  # nothing wiped
    assert ("delete", "e3-5-restore-2026-10-23-abc123") in deps.neon.calls  # temp branch still cleaned up


def test_hung_fault_load_aborts_step(tmp_path):
    gate = threading.Event()

    def hung(url, **kw):
        if "f-timeout" in kw["seed"] and kw["profile"] == "constant":
            gate.wait(5)
        return load_result(seed=kw["seed"])
    deps, _ = make_deps(FakeDB(restore_rules()), load_fn=hung)
    args = make_args(tmp_path, "--fault-seconds", "-118")  # join timeout = fault_seconds + 120 = 2s
    c = runner.Campaign(args, good_env(), lib.check_guards(good_env(), resolve_host=lambda: HOST), deps, tmp_path,
                        "e3-5-2026-10-23-abc123")
    c.start_app()
    c.proxy = FakeProxy()
    try:
        c.run(["faults"])
    finally:
        gate.set()
    step = json.loads((tmp_path / "faults.json").read_text())["steps"]["provider_down"]
    assert step["status"] == "error" and "did not finish" in step["error"]


def test_exit_code_distinguishes_inconclusive(tmp_path, monkeypatch):
    deps, _ = make_deps(FakeDB(restore_rules()))
    monkeypatch.setattr(lib, "check_guards", lambda env, **k: lib.Guarded(RUNTIME, MIGRATOR, 5.0))
    code = runner.main(["--output-dir", str(tmp_path), "--phases", "rollback", "--external-app"], deps=deps, env=good_env())
    assert code == 3
