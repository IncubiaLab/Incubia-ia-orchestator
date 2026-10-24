#!/usr/bin/env python3
"""Integrated E3-5 campaign on the synthetic Neon branch e3-h1-synthetic.

Phases: seed, load, faults, restore, rollback, cost (see docs/roadmap/etapa-3/E3-5-CAMPAIGN.md).
Evidence: evals/results/e3-5-<date>/<phase>.json + summary.json (gate_closed is always false).

    python scripts/e3/run_e3_5_campaign.py --dry-run            # plan only, touches nothing
    INCUBIA_E3_5_CAMPAIGN=1 INCUBIA_E3_NEON_TESTS=1 INCUBIA_E3_NEON_BRANCH=e3-h1-synthetic \
    INCUBIA_E3_5_BUDGET_APPROVED=1 INCUBIA_E3_5_BUDGET_USD=5 \
        python scripts/e3/run_e3_5_campaign.py

Secrets (DSNs, probe token, API keys) come from deploy/e3-neon.env, .env or the environment
and are never printed or written to evidence.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import e3_5_lib as lib  # noqa: E402


@dataclass
class Deps:
    """Every side-effecting collaborator; tests replace them with fakes."""
    connect: Callable[[str], Any] = None
    neon: Any = None
    load_run: Callable[..., dict] = None
    http_status: Callable[[str, str | None], int] = lib._http_status
    app_factory: Callable[..., Any] = lib.AppProcess
    sampler_factory: Callable[..., Any] = lib.ProcessSampler
    proxy_factory: Callable[..., Any] = lib.FaultProxy
    ledger_factory: Callable[[str], Any] = None
    backup_factory: Callable[[str], Any] = None
    run_cmd: Callable[..., Any] = subprocess.run
    which: Callable[[str], str | None] = shutil.which
    sleep: Callable[[float], None] = time.sleep
    now: Callable[[], datetime] = lib.utc_now
    lease_state: Callable[..., tuple] = lib.claim_lease_state
    fire_requests: Callable[..., tuple] = lib.fire_inflight_requests
    in_flight: Callable[[str, str | None], int] = lib.metrics_in_flight

    def fill(self) -> "Deps":
        if self.connect is None:
            def connect(dsn):
                import psycopg
                return psycopg.connect(dsn, connect_timeout=10)
            self.connect = connect
        if self.neon is None:
            self.neon = lib.NeonCli()
        if self.load_run is None:
            self.load_run = lib.load_load_module().run
        if self.ledger_factory is None:
            def ledger(dsn):
                sys.path.insert(0, str(ROOT / "src"))
                from incubia_orchestrator.modules.conversation.adapters.persistence.postgres import PostgresLedger
                return PostgresLedger(dsn)
            self.ledger_factory = ledger
        if self.backup_factory is None:
            def backup(dsn):
                sys.path.insert(0, str(ROOT / "src"))
                from incubia_orchestrator.modules.conversation.adapters.persistence.postgres.backup import (
                    PostgresLedgerBackup)
                return PostgresLedgerBackup(dsn)
            self.backup_factory = backup
        return self


# ------------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Integrated E3-5 campaign (synthetic Neon branch only)")
    p.add_argument("--dry-run", action="store_true", help="print the plan; touch nothing")
    p.add_argument("--phases", default=",".join(lib.PHASE_ORDER), help="comma separated subset, in order")
    p.add_argument("--date", default=datetime.now(UTC).strftime("%Y-%m-%d"))
    p.add_argument("--output-dir", type=Path, default=None)
    p.add_argument("--url", default="http://127.0.0.1:18080", help="D0/probe app base URL (loopback)")
    p.add_argument("--external-app", action="store_true",
                   help="do not spawn the app; faults needing a process (provider, SIGTERM) are skipped")
    p.add_argument("--app-pid", type=int, default=None, help="pid to sample when --external-app")
    p.add_argument("--app-cmd", default=None, help="command to spawn the app (default: D0 main on --url's port)")
    p.add_argument("--provider-env", action="append", default=None,
                   help="env var(s) pointed at the fault proxy (default OPENAI_BASE_URL)")
    p.add_argument("--provider-upstream", default="https://api.openai.com")
    p.add_argument("--conversations", type=int, default=5000)
    p.add_argument("--turns", type=int, default=50000)
    p.add_argument("--chunks", type=int, default=2000)
    p.add_argument("--sessions", type=int, default=80)
    p.add_argument("--session-interval", type=float, default=60.0)
    p.add_argument("--constant-rate", type=float, default=2.0)
    p.add_argument("--burst-waves", type=int, default=10)
    p.add_argument("--burst-interval", type=float, default=60.0)
    p.add_argument("--profile-seconds", type=float, default=600.0)
    p.add_argument("--allow-short", action="store_true", help="allow <600s profiles (never counts as G9 evidence)")
    p.add_argument("--tolerate-429", action="store_true")
    p.add_argument("--fault-seconds", type=float, default=90.0)
    p.add_argument("--image-n1-digest", default=None, help="image N-1 pinned by digest (repo@sha256:...)")
    p.add_argument("--provider-reported-usd", type=float, default=None)
    p.add_argument("--cost-tolerance", type=float, default=lib.COST_TOLERANCE)
    p.add_argument("--recover-grants", type=Path, default=None,
                   help="re-grant the privileges saved by an interrupted credential-revocation step, then exit")
    return p


def build_plan(args) -> dict:
    phases = [x.strip() for x in args.phases.split(",") if x.strip()]
    unknown = [x for x in phases if x not in lib.PHASE_ORDER]
    if unknown:
        raise ValueError("unknown phases: " + ",".join(unknown))
    out_dir = args.output_dir or ROOT / "evals/results" / f"e3-5-{args.date}"
    steps = {
        "seed": [f"seed {args.conversations} conversations / {args.turns} turns / {args.chunks} knowledge chunks "
                 f"(idempotent, migrator, scope {lib.SYNTH_DEPLOYMENT}/{lib.SYNTH_TENANT})"],
        "load": [f"sessions: {args.sessions} sessions, {args.session_interval:g}s interval, >= {args.profile_seconds:g}s",
                 f"constant: {args.constant_rate:g} rps, >= {args.profile_seconds:g}s",
                 f"burst: {args.sessions} in flight x {args.burst_waves} waves every {args.burst_interval:g}s",
                 "collect p50/p95/p99, errors, 429s, CPU/RSS, pool stats, cost; audit correlation + integrity (G7)"],
        "faults": ["provider down (fault proxy timeout/5xx/reset) during load", "pool saturation burst",
                   "claim expiry + fencing with two workers", "credential revocation (reversible grant on "
                   f"{lib.GRANT_TABLE}, synthetic branch only)", "SIGTERM during load (drain)"],
        "restore": ["export synthetic scope (h1_backup)", "post-backup marker delivery",
                    f"create temp Neon branch {lib.RESTORE_BRANCH_PREFIX}* from {lib.BRANCH} with expiry",
                    "wipe scope on temp branch, import, compare counts", "pgvector index + quarantine checks",
                    f"RPO <= {lib.TARGET_RPO_SECONDS // 3600}h / RTO <= {lib.TARGET_RTO_SECONDS // 60}min", "delete temp branch"],
        "rollback": ["expand/contract offline check", "schema_migrations vs migrations/postgres",
                     "image N-1 by digest rehearsal (skipped with reason if digest/docker absent)"],
        "cost": [f"estimated vs reconciled usage, tolerance {args.cost_tolerance:.0%}, within approved budget"],
    }
    return {
        "dry_run": args.dry_run, "branch": lib.BRANCH, "output_dir": str(out_dir),
        "required_env": ["INCUBIA_E3_5_CAMPAIGN=1", "INCUBIA_E3_NEON_TESTS=1", f"INCUBIA_E3_NEON_BRANCH={lib.BRANCH}",
                         "INCUBIA_E3_5_BUDGET_APPROVED=1", "INCUBIA_E3_5_BUDGET_USD=<amount>", "DATABASE_URL (runtime, pooled)",
                         "INCUBIA_MIGRATION_DATABASE_URL (migrator, direct)"],
        "phases": [{"name": name, "steps": steps[name]} for name in phases],
        "estimated_minimum_load_seconds": 3 * args.profile_seconds if "load" in phases else 0,
    }


# ------------------------------------------------------------- campaign


@dataclass
class Campaign:
    args: Any
    env: dict
    guarded: Any
    deps: Deps
    out_dir: Path
    run_id: str
    app: Any = None
    proxy: Any = None
    results: dict = field(default_factory=dict)
    deployment_id: str = lib.SYNTH_DEPLOYMENT
    tenant_id: str = lib.SYNTH_TENANT

    # -- helpers
    @property
    def token(self) -> str | None:
        return self.env.get("INCUBIA_E3_PROBE_TOKEN") or None

    def _load(self, profile: str, seed_suffix: str, **kw) -> dict:
        seed = f"{self.run_id}-{seed_suffix}"
        base = dict(profile=profile, duration=kw.pop("duration", 10.0), sessions=kw.pop("sessions", 1),
                    interval=kw.pop("interval", 1.0), seed=seed, token=self.token,
                    tolerate_limit_rejections=kw.pop("tolerate", True),
                    env={"INCUBIA_E3_LOAD_TIMEOUT": "90", **self.env})  # remote Neon: >15s per request is normal
        base.update(kw)
        try:
            return self.deps.load_run(self.args.url, **base)
        except (ValueError, RuntimeError) as exc:
            return {"status": "failed", "error": lib.redact(str(exc), lib.secrets_in(self.env)), "seed": seed,
                    "errors": 1, "requests": 0, "success_count": 0}

    def _metrics_in_flight(self) -> tuple[bool, int]:
        try:
            return True, int(self.deps.in_flight(self.args.url, self.token))
        except Exception:
            return False, 0

    def _probe_once(self, label: str) -> dict:
        return self._load("burst", label, sessions=1, waves=1)

    def _recovers(self, label: str, attempts: int = 10) -> bool:
        for i in range(attempts):
            if self._probe_once(f"{label}-{i}").get("status") == "passed":
                return True
            self.deps.sleep(3)
        return False

    def _background_load(self, label: str, seconds: float, rate: float = 2.0):
        import threading
        box: dict = {}

        def work():
            box["result"] = self._load("constant", label, duration=seconds, rate=rate,
                                       sessions=min(self.args.sessions, 20))
        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        return thread, box

    def _sampler(self):
        pid = self.app.pid if self.app is not None else self.args.app_pid
        if not pid:
            return None
        return self.deps.sampler_factory(pid).start()

    def _integrity(self, prefix: str) -> dict:
        return lib.integrity_check(self.deps.connect, self.guarded.migrator_dsn, self.deployment_id,
                                   self.tenant_id, prefix)

    def _app_env(self) -> dict:
        env = {k: v for k, v in os.environ.items()}
        env.update({
            "DATABASE_URL": self.guarded.runtime_dsn,
            "INCUBIA_D0_DEPLOYMENT_ID": self.deployment_id, "INCUBIA_D0_TENANT_ID": self.tenant_id,
            "INCUBIA_D0_ACTOR_ID": lib.SYNTH_ACTOR,
            "INCUBIA_D0_AUDIT": "postgres",  # G7: durable audit, runtime role, fail closed
        })
        for key in ("INCUBIA_E3_DB_POOL_MAX", "INCUBIA_E3_PROBE_TOKEN", "OPENAI_API_KEY"):
            if self.env.get(key):
                env[key] = self.env[key]
        if self.proxy is not None:
            for name in self.args.provider_env or ["OPENAI_BASE_URL"]:
                env[name] = self.proxy.base_url + ("/v1" if name == "OPENAI_BASE_URL" else "")
        return env

    def start_app(self) -> None:
        if self.args.external_app:
            return
        from urllib.parse import urlsplit
        port = urlsplit(self.args.url).port or 18080
        command = shlex.split(self.args.app_cmd) if self.args.app_cmd else [
            sys.executable, "-m", "incubia_orchestrator.interfaces.http.main", "--host", "127.0.0.1", "--port", str(port)]
        self.app = self.deps.app_factory(command, self._app_env(), url=self.args.url, token=self.token,
                                         http_status=self.deps.http_status)
        self.app.start()

    def stop_app(self) -> None:
        if self.app is not None:
            self.app.stop()

    # -- phases
    def phase_seed(self) -> dict:
        plan = lib.SeedPlan(self.args.conversations, self.args.turns, self.args.chunks)
        return lib.run_seed(self.deps.connect, self.guarded.migrator_dsn, plan, self.deployment_id, self.tenant_id)

    def _profile_specs(self) -> dict:
        a = self.args
        burst_span = a.burst_waves * a.burst_interval
        return {
            "sessions": dict(duration=a.profile_seconds, sessions=a.sessions, interval=a.session_interval),
            "constant": dict(duration=a.profile_seconds, rate=a.constant_rate, sessions=a.sessions),
            "burst": dict(duration=max(burst_span, 1.0), sessions=a.sessions, interval=a.burst_interval,
                          waves=a.burst_waves),
        }

    def phase_load(self) -> dict:
        profiles: dict = {}
        short = False
        for name, spec in self._profile_specs().items():
            span = spec["duration"] if name != "burst" else spec["waves"] * spec["interval"]
            meets = span >= lib.MIN_PROFILE_SECONDS
            if not meets and not self.args.allow_short:
                raise lib.GuardError(f"profile {name} spans {span:g}s < {lib.MIN_PROFILE_SECONDS:g}s; use --allow-short "
                                     "only for rehearsals")
            short = short or not meets
            sampler = self._sampler()
            result = self._load(name, name, tolerate=self.args.tolerate_429, **spec)
            resources = sampler.stop() if sampler else {"source": None, "note": "no pid to sample"}
            slim = lib.load_slim(result) if "latency_ms" in result else dict(result)
            slim.update({"resources": resources, "meets_min_duration": meets,
                         "concurrency": spec.get("sessions"), "seed": result.get("seed")})
            profiles[name] = slim
        prefix = f"e3-load-{self.run_id}"
        integrity = self._integrity(prefix)
        audit = lib.audit_correlation(self.deps.connect, self.guarded.migrator_dsn, self.deployment_id,
                                      self.tenant_id, prefix)
        ok = (all(p.get("status") == "passed" for p in profiles.values()) and integrity["ok"]
              and all(p["meets_min_duration"] for p in profiles.values()))
        return {"status": "passed" if ok else "failed", "short_run": short, "profiles": profiles,
                "integrity": integrity, "audit_correlation": audit}

    def phase_faults(self) -> dict:
        steps: dict = {}
        managed = self.app is not None
        prefix = f"e3-load-{self.run_id}-f"

        def run_step(name, fn, *, needs_app=False, needs_proxy=False):
            if needs_app and not managed:
                steps[name] = {"status": "skipped", "reason": "requires a managed app process (not --external-app)"}
                return
            if needs_proxy and self.proxy is None:
                steps[name] = {"status": "skipped", "reason": "fault proxy not configured"}
                return
            try:
                steps[name] = fn()
            except Exception as exc:  # evidence must survive a failing step
                steps[name] = {"status": "error", "error": lib.redact(f"{type(exc).__name__}: {exc}",
                                                                      lib.secrets_in(self.env))}

        def provider_down():
            modes = {}
            for mode in ("timeout", "http_5xx", "reset"):
                self.proxy.set_mode(mode)
                thread, box = self._background_load(f"f-{mode}", self.args.fault_seconds, rate=1.0)
                thread.join(self.args.fault_seconds + 120)
                self.proxy.set_mode("pass")
                if thread.is_alive():
                    raise RuntimeError(f"fault load for mode {mode} did not finish; aborting remaining modes")
                res = box.get("result", {})
                modes[mode] = {"requests": res.get("requests"), "errors": res.get("errors"),
                               "status_counts": res.get("http_status_counts"),
                               "revisions_consistent": res.get("revisions_consistent"),
                               "latency_ms": res.get("latency_ms"), "proxy_hits": dict(self.proxy.hits),
                               "recovered": self._recovers(f"f-{mode}-rec")}
            integrity = self._integrity(prefix)
            ok = all(m["recovered"] and m["revisions_consistent"] is not False for m in modes.values()) and integrity["ok"]
            return {"status": "passed" if ok else "failed", "modes": modes, "integrity": integrity}

        def pool_saturation():
            res = self._load("burst", "f-pool", sessions=self.args.sessions, waves=3, interval=5.0)
            pool = lib.pool_summary(res.get("metrics_before"), res.get("metrics_after"))
            integrity = self._integrity(f"e3-load-{self.run_id}-f-pool")
            recovered = self._recovers("f-pool-rec")
            ok = recovered and integrity["ok"] and res.get("revisions_consistent") is not False
            return {"status": "passed" if ok else "failed", "pool": pool, "requests": res.get("requests"),
                    "errors": res.get("errors"), "limit_rejections": res.get("limit_rejections"),
                    "status_counts": res.get("http_status_counts"), "recovered": recovered, "integrity": integrity}

        def claim_fencing():
            ledger = self.deps.ledger_factory(self.guarded.runtime_dsn)
            from importlib import import_module
            sys.path.insert(0, str(ROOT / "src"))
            scope_cls = import_module("incubia_orchestrator.foundation.contracts.execution").ExecutionScope
            scope = scope_cls(self.deployment_id, self.tenant_id, "e3-5-fencing", lib.SYNTH_ACTOR)
            kw = dict(resource_type="e3-5-fencing-probe", resource_key=self.run_id)
            # Latency-robust: the lease must comfortably outlive several Neon round trips, and
            # expiry is judged on the DB clock (lease_until vs clock_timestamp()), not wall time.
            lease = 20
            conn, migrator = self.deps.connect, self.guarded.migrator_dsn
            lease_args = (self.deployment_id, self.tenant_id, kw["resource_type"], kw["resource_key"])
            a = ledger.acquire_claim(scope, owner_id="worker-a", lease_seconds=lease, **kw)
            b_early = ledger.acquire_claim(scope, owner_id="worker-b", lease_seconds=30, **kw)
            lease_until, db_now = self.deps.lease_state(conn, migrator, *lease_args)
            # The early attempt only proves fencing if A's lease was still live at DB time after it.
            early_valid = lease_until is not None and db_now is not None and db_now < lease_until
            deadline = time.monotonic() + 120
            while lease_until is not None and time.monotonic() < deadline:
                _, db_now = self.deps.lease_state(conn, migrator, *lease_args)
                if db_now is not None and db_now > lease_until:
                    break
                self.deps.sleep(1.0)
            b = ledger.acquire_claim(scope, owner_id="worker-b", lease_seconds=30, **kw)
            checks = {
                "a_acquired": a is not None,
                "b_blocked_while_lease_live": b_early is None and early_valid,
                "b_acquired_after_expiry": b is not None,
                "generation_increased": bool(a and b and b.generation > a.generation),
                "stale_a_renew_rejected": bool(a) and ledger.renew_claim(a, lease_seconds=30) is False,
                "stale_a_release_rejected": bool(a) and ledger.release_claim(a) is False,
                "b_renew_ok": bool(b) and ledger.renew_claim(b, lease_seconds=30) is True,
            }
            if b:
                ledger.release_claim(b)
            return {"status": "passed" if all(checks.values()) else "failed", "checks": checks,
                    "generations": [getattr(a, "generation", None), getattr(b, "generation", None)]}

        def credential_revocation():
            conn = self.deps.connect
            dsn = self.guarded.migrator_dsn
            privileges = lib.capture_grants(conn, dsn)
            if not privileges:
                return {"status": "skipped", "reason": "runtime role has no grant to revoke"}
            saved = self.out_dir / "grants-to-restore.json"
            lib.write_json(saved, {"table": lib.GRANT_TABLE, "role": lib.RUNTIME_ROLE, "privileges": privileges,
                                   "recover": "run_e3_5_campaign.py --recover-grants <this file>"})
            blocked = restored = False
            try:
                lib.set_grants(conn, dsn, privileges, revoke=True)
                self.deps.sleep(2)
                during = self._probe_once("f-revoked")
                blocked = during.get("status") != "passed"
            finally:
                lib.set_grants(conn, dsn, privileges, revoke=False)
                after = lib.capture_grants(conn, dsn)
                restored = sorted(after) == sorted(privileges)
            recovered = self._recovers("f-restored")
            ok = blocked and restored and recovered
            return {"status": "passed" if ok else "failed",
                    "checks": {"blocked_while_revoked": blocked, "grants_restored": restored,
                               "recovered_after_restore": recovered},
                    "privileges": privileges, "status_counts_during": during.get("http_status_counts")}

        def sigterm_drain():
            n = max(1, min(self.args.sessions, 3))
            label = f"e3-load-{self.run_id}-f-term"
            # Request latency on remote Neon can exceed the 10s drain budget, so a SIGTERM issued
            # at t=0 would legitimately abandon the request. Measure the baseline latency and
            # signal while the requests are still in flight but with <= ~4s of work left.
            base_ms = (self._probe_once("f-pre-drain").get("latency_ms") or {}).get("p50") or 8000.0
            t_fire = time.monotonic()
            threads, results = self.deps.fire_requests(self.args.url, n, label, token=self.token)
            # Wait until requests are really in flight in the server (not merely scheduled).
            inflight = 0
            for _ in range(100):
                ok, inflight = self._metrics_in_flight()
                if ok and inflight >= 1:
                    break
                self.deps.sleep(0.1)
            if inflight < 1:
                for t in threads:
                    t.join(60)
                self.stop_app()
                self.start_app()
                return {"status": "failed", "reason": "no request was in flight when SIGTERM was due",
                        "requests": len(results)}
            fired_at = time.monotonic()
            self.deps.sleep(max(0.0, base_ms / 1000.0 - 4.0 - (fired_at - t_fire)))
            ok_now, inflight_now = self._metrics_in_flight()
            inflight = inflight_now if ok_now else inflight
            if inflight < 1:  # requests finished while waiting: the drain would prove nothing
                for t in threads:
                    t.join(60)
                self.stop_app()
                self.start_app()
                return {"status": "failed", "reason": "requests finished before SIGTERM (drain not exercised)",
                        "requests": len(results), "baseline_latency_ms": base_ms}
            term = self.app.sigterm()
            for t in threads:
                t.join(60)
            self.stop_app()
            self.start_app()  # restore service for later phases
            ready = self.deps.http_status(self.args.url + "/readyz", self.token) == 200
            integrity = self._integrity(label)
            statuses = [code for code, _ in results]
            completed = [code for code, _ in results if code == 200]
            expected_turns = len(completed)
            checks = {"exited_within_deadline": term["exited_within_deadline"], "clean_exit_code": term["exit_code"] == 0,
                      "inflight_started": inflight >= 1 and len(results) == n,
                      "inflight_completed": len(results) == n and all(code == 200 for code in statuses),
                      "no_loss_or_duplication": integrity["ok"] and integrity["turns"] >= expected_turns,
                      "restarted_ready": ready}
            return {"status": "passed" if all(checks.values()) else "failed", "checks": checks, "term": term,
                    "requests": n, "inflight_at_sigterm": inflight, "baseline_latency_ms": base_ms,
                    "status_counts": {str(c): statuses.count(c) for c in sorted(set(statuses))},
                    "integrity": integrity}

        run_step("provider_down", provider_down, needs_app=True, needs_proxy=True)
        run_step("pool_saturation", pool_saturation)
        run_step("claim_expiry_fencing", claim_fencing)
        run_step("credential_revocation", credential_revocation)
        run_step("sigterm_drain", sigterm_drain, needs_app=True)
        statuses = {s["status"] for s in steps.values()}
        if statuses <= {"passed"}:
            status = "passed"
        elif statuses & {"failed", "error"}:
            status = "failed"
        else:
            status = "inconclusive"
        if status == "passed" and any(s["status"] == "skipped" for s in steps.values()):
            status = "inconclusive"
        return {"status": status, "steps": steps}

    def phase_restore(self) -> dict:
        d, t = self.deployment_id, self.tenant_id
        conn, migrator = self.deps.connect, self.guarded.migrator_dsn
        package = self.out_dir / "restore-package.json"
        seeded_sending = lib.count_state(conn, migrator, d, t, "SENDING")
        export = self.deps.backup_factory(self.guarded.runtime_dsn).export((d, t), package)
        export_done = datetime.fromisoformat(export.manifest["export_completed_at"].replace("Z", "+00:00"))
        marker = str(uuid.uuid5(uuid.NAMESPACE_URL, "e3-5-marker/" + self.run_id))
        lib.insert_post_backup_marker(conn, migrator, d, t, marker)
        suffix = self.run_id.replace("e3-5-", "").replace("_", "-")[:30]
        branch = f"{lib.RESTORE_BRANCH_PREFIX}{suffix}"
        lib.assert_restore_branch(branch)
        primary_host = lib.urlsplit(migrator).hostname
        disaster_at = self.deps.now()
        started = time.monotonic()
        created = deleted = False
        report = None
        pgvector = quarantine = migrations = {}
        counts_match = False
        try:
            created_info = self.deps.neon.create_branch(branch, lib.BRANCH, lib.expires_at(120, self.deps.now()))
            created = True
            temp_dsn = self.deps.neon.connection_string(branch, lib.MIGRATOR_ROLE)
            lib.assert_dsn_is_new_branch(temp_dsn, created_info, primary_host=primary_host)
            lib.wipe_scope(conn, temp_dsn, d, t, primary_host=primary_host)
            report = self.deps.backup_factory(temp_dsn).import_package(package, expected_scope=(d, t))
            counts_match = dict(report.table_counts) == dict(export.table_counts)
            migrations = lib.check_migration_chain(conn, temp_dsn, ROOT / "migrations/postgres")
            pgvector = lib.pgvector_check(conn, temp_dsn)
            quarantine = lib.quarantine_check(conn, temp_dsn, d, t, marker_execution_id=marker,
                                              seeded_sending=seeded_sending)
            rto_seconds = time.monotonic() - started
        finally:
            if created:
                try:
                    self.deps.neon.delete_branch(branch)
                    deleted = True
                except Exception:
                    deleted = False
        sla = lib.rpo_rto(export_done, disaster_at, rto_seconds)
        checks = {"counts_match_manifest": counts_match, "migrations_complete": bool(migrations.get("ok")),
                  "quarantine_ok": bool(quarantine.get("ok")), "temp_branch_deleted": deleted,
                  "rpo_ok": sla["rpo_ok"], "rto_ok": sla["rto_ok"],
                  "pgvector_ok_or_absent": bool(pgvector.get("ok")) or pgvector.get("available") is False}
        return {"status": "passed" if all(checks.values()) else "failed", "checks": checks, "rpo_rto": sla,
                "restore_report": report.as_dict() if report else None, "export_counts": export.table_counts,
                "export_duration_seconds": export.export_duration_seconds,
                "pgvector": pgvector, "quarantine": quarantine, "migrations": migrations,
                "temp_branch": {"name": branch, "expiry_minutes": 120, "deleted": deleted},
                "pgvector_note": None if pgvector.get("available") else "knowledge tables absent: vector index not checked"}

    def phase_rollback(self) -> dict:
        steps: dict = {}
        offline = self.deps.run_cmd([sys.executable, "-m", "pytest", "-q", "tests/unit/test_e3_migration_rollback.py"],
                                    cwd=ROOT, capture_output=True, text=True, check=False,
                                    env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
        steps["expand_contract_offline"] = {"status": "passed" if offline.returncode == 0 else "failed"}
        chain = lib.check_migration_chain(self.deps.connect, self.guarded.migrator_dsn, ROOT / "migrations/postgres")
        steps["schema_migrations_chain"] = {"status": "passed" if chain["ok"] else "failed", **chain}
        steps["image_n1"] = self._rollback_image()
        core = all(steps[k]["status"] == "passed" for k in ("expand_contract_offline", "schema_migrations_chain"))
        image = steps["image_n1"]["status"]
        if not core or image == "failed":
            status = "failed"
        elif image == "passed":
            status = "passed"
        else:
            status = "inconclusive"
        return {"status": status, "steps": steps}

    def _rollback_image(self) -> dict:
        digest = self.args.image_n1_digest or self.env.get("INCUBIA_E3_5_IMAGE_N1_DIGEST")
        if not digest:
            return {"status": "skipped", "reason": "no image N-1 digest provided (--image-n1-digest or "
                                                    "INCUBIA_E3_5_IMAGE_N1_DIGEST)"}
        if not lib.DIGEST_RE.match(digest) or ":latest" in digest:
            return {"status": "failed", "reason": "image N-1 must be pinned by sha256 digest, never latest"}
        if not self.deps.which("docker"):
            return {"status": "skipped", "reason": "docker not available on this host"}
        name = f"e3-5-n1-{self.run_id[-8:]}"
        env = {**os.environ, "DATABASE_URL": self.guarded.runtime_dsn, "INCUBIA_D0_DEPLOYMENT_ID": self.deployment_id,
               "INCUBIA_D0_TENANT_ID": self.tenant_id, "INCUBIA_D0_ACTOR_ID": lib.SYNTH_ACTOR,
               "INCUBIA_D0_CONTAINER_BIND": "1"}
        from urllib.parse import urlsplit
        port = urlsplit(self.args.url).port or 18080
        self.stop_app()  # readiness false: admission stops, durable state stays in the ledger
        started = time.monotonic()
        try:
            run = self.deps.run_cmd(
                ["docker", "run", "-d", "--rm", "--name", name, "-p", f"127.0.0.1:{port}:8080", "-e", "DATABASE_URL",
                 "-e", "INCUBIA_D0_DEPLOYMENT_ID", "-e", "INCUBIA_D0_TENANT_ID", "-e", "INCUBIA_D0_ACTOR_ID",
                 "-e", "INCUBIA_D0_CONTAINER_BIND", digest], capture_output=True, text=True, check=False, env=env)
            if run.returncode:
                return {"status": "failed", "reason": "docker run failed"}
            ready = False
            for _ in range(60):
                if self.deps.http_status(self.args.url + "/readyz", self.token) == 200:
                    ready = True
                    break
                self.deps.sleep(1)
            probe = self._probe_once("n1-probe") if ready else {}
            ok = ready and probe.get("status") == "passed"
            return {"status": "passed" if ok else "failed", "ready": ready, "probe_ok": probe.get("status") == "passed",
                    "rollback_seconds": round(time.monotonic() - started, 3), "digest_pinned": True}
        finally:
            self.deps.run_cmd(["docker", "rm", "-f", name], capture_output=True, text=True, check=False)
            self.start_app()

    def phase_cost(self) -> dict:
        estimated = reported = 0.0
        seen_reconciled = False
        profiles = (self.results.get("load") or {}).get("profiles") or {}
        sources = [p.get("cost_delta") or {} for p in profiles.values()]
        for delta in sources:
            for key, row in delta.items():
                if key.endswith(":estimated"):
                    estimated += row.get("usd", 0.0)
                elif key.endswith(":reconciled"):
                    reported += row.get("usd", 0.0)
                    seen_reconciled = True
        provider = reported if seen_reconciled else self.args.provider_reported_usd
        if not any(sources) or (estimated == 0 and provider in (None, 0)):
            return {"status": "skipped", "reason": "no LLM cost recorded (fake/no-spend run?)",
                    "estimated_usd": estimated}
        out = lib.reconcile_cost(estimated, provider, tolerance=self.args.cost_tolerance,
                                 budget_usd=self.guarded.budget_usd)
        out["reported_source"] = "metrics reconciled basis" if seen_reconciled else "--provider-reported-usd"
        out["budget_usd_approved"] = self.guarded.budget_usd
        if out["status"] == "skipped":
            out["status"] = "inconclusive"
        return out

    # -- orchestration
    def run(self, phases: list[str]) -> dict:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        needs_app = bool(set(phases) & {"load", "faults", "rollback"}) and not self.args.external_app
        secrets_list = lib.secrets_in(self.env)
        try:
            if needs_app or "faults" in phases:
                if "faults" in phases and not self.args.external_app:
                    self.proxy = self.deps.proxy_factory(self.args.provider_upstream).start()
                if needs_app:
                    self.start_app()
            for name in phases:
                started = time.monotonic()
                try:
                    result = getattr(self, f"phase_{name}")()
                except Exception as exc:
                    result = {"status": "error", "error": lib.redact(f"{type(exc).__name__}: {exc}", secrets_list)}
                result.update({"phase": name, "run_id": self.run_id, "gate_closed": False, "synthetic": True,
                               "duration_seconds": round(time.monotonic() - started, 3)})
                self.results[name] = result
                lib.write_json(self.out_dir / f"{name}.json", result)
        finally:
            self.stop_app()
            if self.proxy is not None:
                self.proxy.stop()
        short = bool((self.results.get("load") or {}).get("short_run"))
        summary = lib.build_summary(self.results, run_id=self.run_id, budget_usd=self.guarded.budget_usd, short_run=short)
        lib.write_json(self.out_dir / "summary.json", summary)
        return summary


def new_run_id(date: str) -> str:
    return f"e3-5-{date}-{secrets.token_hex(3)}"


def main(argv: list[str] | None = None, *, deps: Deps | None = None, env: dict | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        plan = build_plan(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.dry_run:
        print(json.dumps(plan, indent=2))
        return 0
    base_env = dict(os.environ if env is None else env)
    merged = lib.load_env([ROOT / "deploy/e3-neon.env", ROOT / ".env"], base_env) if env is None else base_env
    try:
        guarded = lib.check_guards(merged)
        lib.assert_synthetic_scope(lib.SYNTH_DEPLOYMENT, lib.SYNTH_TENANT)
    except lib.GuardError as exc:
        print(f"Refusing E3-5 campaign: {lib.redact(str(exc), lib.secrets_in(merged))}", file=sys.stderr)
        return 2
    deps = (deps or Deps()).fill()
    if args.recover_grants:
        saved = json.loads(args.recover_grants.read_text())
        lib.set_grants(deps.connect, guarded.migrator_dsn, saved["privileges"], revoke=False,
                       table=saved["table"], role=saved["role"])
        print(json.dumps({"recovered": saved["privileges"]}))
        return 0
    from urllib.parse import urlsplit
    try:
        load_mod_url = urlsplit(args.url)
        lib.load_load_module().validate_target(args.url, merged)
        if load_mod_url.hostname not in {"127.0.0.1", "localhost", "::1"} and not args.external_app:
            raise ValueError("a managed app must be loopback")
    except ValueError as exc:
        print(f"Invalid --url: {exc}", file=sys.stderr)
        return 2
    phases = [x.strip() for x in args.phases.split(",") if x.strip()]
    out_dir = args.output_dir or ROOT / "evals/results" / f"e3-5-{args.date}"
    campaign = Campaign(args=args, env=merged, guarded=guarded, deps=deps, out_dir=out_dir,
                        run_id=new_run_id(args.date))
    summary = campaign.run(phases)
    print(json.dumps({"run_id": summary["run_id"], "phases": summary["phases"], "criteria": summary["criteria"],
                      "gate_closed": False, "output_dir": str(out_dir)}, indent=2))
    if {"failed", "error"} & set(summary["phases"].values()):
        return 1
    # 3 = nothing failed but evidence is missing/inconclusive (never a clean pass).
    return 0 if summary["all_criteria_passed"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
