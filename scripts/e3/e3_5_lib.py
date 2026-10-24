"""Helpers for the integrated E3-5 campaign (guards, seed, faults, restore, report).

Everything that touches the network or a database receives its collaborator
(connect, neon CLI, command runner, http probe) as an argument so the logic is
testable offline. Nothing here prints or persists a DSN, token or API key.
All destructive operations are scoped to the synthetic Neon branch and the
synthetic tenant and are re-validated right before they run.
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import re
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

BRANCH = "e3-h1-synthetic"
NEON_CLI = "neon@8.3.3"
DATABASE = "neondb"
SYNTH_PREFIX = "e3-5-synth"
SYNTH_DEPLOYMENT = "e3-5-synth-deployment"
SYNTH_TENANT = "e3-5-synth-tenant"
SYNTH_ACTOR = "e3-5-synth-actor"
RESTORE_BRANCH_PREFIX = "e3-5-restore-"
RUNTIME_ROLE = "incubia_runtime"
MIGRATOR_ROLE = "incubia_migrator"

TARGET_RPO_SECONDS = 12 * 3600
TARGET_RTO_SECONDS = 3600
TARGET_P95_MS = 5000.0
MIN_PROFILE_SECONDS = 600.0
COST_TOLERANCE = 0.10
MIN_BUDGET_USD = 0.01

INCONCLUSIVE = {"not_run", "skipped", "inconclusive"}
PHASE_ORDER = ("seed", "load", "faults", "restore", "rollback", "cost")


class GuardError(RuntimeError):
    """A safety precondition failed; nothing was touched."""


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, module)
    spec.loader.exec_module(module)
    return module


def load_neon_guards():
    return _load_module("e3_5_run_neon_h1", HERE / "run_neon_h1.py")


def load_load_module():
    return _load_module("e3_5_load", HERE / "load.py")


# --------------------------------------------------------------------- env


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def load_env(paths: list[Path], env: dict[str, str]) -> dict[str, str]:
    """Merge env files under the real environment (the environment wins)."""
    merged: dict[str, str] = {}
    for path in paths:
        merged.update(parse_env_file(path))
    merged.update(env)
    return merged


def redact(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        if secret and len(secret) >= 6:
            text = text.replace(secret, "[redacted]")
    text = re.sub(r"postgres(?:ql)?://[^\s\"'<>]+", "[redacted-dsn]", text)
    return re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "[redacted-key]", text)


def secrets_in(env: dict[str, str]) -> list[str]:
    out = []
    for key in ("DATABASE_URL", "INCUBIA_MIGRATION_DATABASE_URL", "INCUBIA_E3_PROBE_TOKEN",
                "OPENAI_API_KEY"):
        value = env.get(key, "")
        if value:
            out.append(value)
            password = urlsplit(value).password if "://" in value else None
            if password:
                out.append(unquote(password))
    return out


# ------------------------------------------------------------------ guards


@dataclass(frozen=True)
class Guarded:
    runtime_dsn: str = field(repr=False)
    migrator_dsn: str = field(repr=False)
    budget_usd: float = 0.0
    branch: str = BRANCH
    host_fingerprint: str = ""


def check_guards(env: dict[str, str], *, resolve_host: Callable[[], str] | None = None) -> Guarded:
    """Fail closed unless this is the approved synthetic Neon campaign."""
    neon = load_neon_guards()
    if env.get("INCUBIA_E3_5_CAMPAIGN") != "1":
        raise GuardError("Set INCUBIA_E3_5_CAMPAIGN=1 to authorize the E3-5 campaign")
    if env.get("INCUBIA_E3_NEON_TESTS") != "1":
        raise GuardError("Set INCUBIA_E3_NEON_TESTS=1 to authorize Neon access")
    if env.get("INCUBIA_E3_NEON_BRANCH") != BRANCH:
        raise GuardError(f"INCUBIA_E3_NEON_BRANCH must be {BRANCH}")
    if env.get("INCUBIA_E3_5_BUDGET_APPROVED") != "1":
        raise GuardError("Set INCUBIA_E3_5_BUDGET_APPROVED=1 once the budget is approved")
    try:
        budget = float(env.get("INCUBIA_E3_5_BUDGET_USD", ""))
    except ValueError:
        budget = float("nan")
    if not (math.isfinite(budget) and budget >= MIN_BUDGET_USD):
        raise GuardError("INCUBIA_E3_5_BUDGET_USD must be a finite approved amount")
    previous = {k: os.environ.get(k) for k in ("DATABASE_URL", "INCUBIA_MIGRATION_DATABASE_URL")}
    try:
        os.environ["DATABASE_URL"] = env.get("DATABASE_URL", "")
        os.environ["INCUBIA_MIGRATION_DATABASE_URL"] = env.get("INCUBIA_MIGRATION_DATABASE_URL", "")
        try:
            runtime = neon._validated_url("DATABASE_URL", RUNTIME_ROLE, pooled=True)
            migrator = neon._validated_url("INCUBIA_MIGRATION_DATABASE_URL", MIGRATOR_ROLE, pooled=False)
        except ValueError as exc:
            raise GuardError(str(exc)) from None
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    rt, mg = urlsplit(runtime), urlsplit(migrator)
    if rt.path != mg.path or rt.hostname.replace("-pooler.", ".", 1) != mg.hostname:
        raise GuardError("Runtime and migrator URLs do not identify the same branch/database")
    resolver = resolve_host or neon._expected_branch_host
    try:
        expected = resolver()
    except (OSError, ValueError) as exc:
        raise GuardError(f"Cannot resolve the approved branch endpoint ({type(exc).__name__})") from None
    if mg.hostname.lower() != expected.lower():
        raise GuardError("URLs do not identify the approved e3-h1-synthetic branch")
    return Guarded(runtime, migrator, budget, BRANCH, mg.hostname.split(".")[0][:8] + "...")


def assert_synthetic_scope(deployment_id: str, tenant_id: str) -> None:
    if not (deployment_id.startswith(SYNTH_PREFIX) and tenant_id.startswith(SYNTH_PREFIX)):
        raise GuardError(f"Scope must start with {SYNTH_PREFIX}; refusing non-synthetic scope")


def assert_restore_branch(name: str) -> None:
    if name == BRANCH or not name.startswith(RESTORE_BRANCH_PREFIX) or not re.fullmatch(RESTORE_BRANCH_PREFIX + r"[a-z0-9-]{4,40}", name):
        raise GuardError("Temporary restore branch name is not allowed")


# -------------------------------------------------------------------- seed


@dataclass(frozen=True)
class SeedPlan:
    conversations: int
    turns: int
    chunks: int
    batch: int = 10_000
    sending_every: int = 100  # one in N deliveries stays SENDING (quarantine fodder)

    def validate(self) -> None:
        if self.conversations < 1 or self.turns < self.conversations or self.chunks < 0 or self.batch < 1:
            raise ValueError("Invalid seed sizes (turns must be >= conversations >= 1)")
        if self.turns > 1_000_000 or self.chunks > 200_000:
            raise ValueError("Seed sizes exceed the synthetic cap")


SCOPE_SET = "SELECT set_config('app.deployment_id', %s, true), set_config('app.tenant_id', %s, true)"


def seed_statements(plan: SeedPlan, deployment_id: str, tenant_id: str) -> list[tuple[str, str, tuple]]:
    """Return (table, sql, params) triples. Every row is keyed deterministically and uses
    ON CONFLICT DO NOTHING so a re-run is a no-op. Batches are sliced on the turn index."""
    plan.validate()
    assert_synthetic_scope(deployment_id, tenant_id)
    out: list[tuple[str, str, tuple]] = []
    d, t, c = deployment_id, tenant_id, plan.conversations
    out.append((
        "conversations",
        "INSERT INTO conversations (deployment_id, tenant_id, conversation_id, actor_id, revision) "
        "SELECT %s, %s, 'e3-5-seed-c' || g, %s, ((%s - g) / %s) + 1 "
        "FROM generate_series(1, %s) AS g ON CONFLICT DO NOTHING",
        (d, t, SYNTH_ACTOR, plan.turns, c, c),
    ))
    for start in range(1, plan.turns + 1, plan.batch):
        end = min(plan.turns, start + plan.batch - 1)
        exe = "md5('e3-5-seed-turn-' || g)::uuid"
        out.append(("inbox_events",
                    "INSERT INTO inbox_events (deployment_id, tenant_id, channel, channel_account_ref, "
                    "external_event_id, payload_hash, payload_json, request_id, execution_id, state, terminal_at) "
                    f"SELECT %s, %s, 'e3-5-seed', 'e3-5-seed', 'e3-5-seed-' || g, md5('p' || g), '{{}}'::jsonb, "
                    f"{exe}, {exe}, 'COMPLETED', now() FROM generate_series(%s, %s) AS g ON CONFLICT DO NOTHING",
                    (d, t, start, end)))
        out.append(("turns",
                    "INSERT INTO turns (execution_id, deployment_id, tenant_id, conversation_id, actor_id, "
                    "user_text, assistant_text) "
                    f"SELECT {exe}, %s, %s, 'e3-5-seed-c' || (((g - 1) %% %s) + 1), %s, "
                    "'consulta sintetica ' || g, 'respuesta sintetica ' || g "
                    "FROM generate_series(%s, %s) AS g ON CONFLICT DO NOTHING",
                    (d, t, c, SYNTH_ACTOR, start, end)))
        out.append(("outcomes",
                    "INSERT INTO outcomes (execution_id, deployment_id, tenant_id, outcome_json) "
                    f"SELECT {exe}, %s, %s, '{{\"status\":\"ok\"}}'::jsonb "
                    "FROM generate_series(%s, %s) AS g ON CONFLICT DO NOTHING",
                    (d, t, start, end)))
        out.append(("deliveries",
                    "INSERT INTO deliveries (execution_id, deployment_id, tenant_id, response_id, destination_ref, "
                    "payload_json, state) "
                    f"SELECT {exe}, %s, %s, 'r' || g, 'e3-5-seed', '{{}}'::jsonb, "
                    "CASE WHEN g %% %s = 0 THEN 'SENDING' ELSE 'DELIVERED' END "
                    "FROM generate_series(%s, %s) AS g ON CONFLICT DO NOTHING",
                    (d, t, plan.sending_every, start, end)))
    return out


def knowledge_statements(plan: SeedPlan) -> list[tuple[str, str, tuple]]:
    """Synthetic chunks in a RETIRED generation (never competes with the ACTIVE one)."""
    if plan.chunks == 0:
        return []
    out = [
        ("knowledge_generations",
         "INSERT INTO knowledge_generations (generation_id, status, model_version, dimension, corpus_hash) "
         "VALUES ('e3-5-synth-gen', 'RETIRED', 'e3-5-synthetic', 384, 'e3-5-synthetic') ON CONFLICT DO NOTHING", ()),
        ("knowledge_sources",
         "INSERT INTO knowledge_sources (source_id, version, content_hash) "
         "VALUES ('e3-5-synth-source', '1', 'e3-5-synthetic') ON CONFLICT DO NOTHING", ()),
    ]
    for start in range(1, plan.chunks + 1, 2000):
        end = min(plan.chunks, start + 1999)
        out.append(("knowledge_chunks",
                    "INSERT INTO knowledge_chunks (generation_id, source_id, source_version, chunk_id, content, embedding) "
                    "SELECT 'e3-5-synth-gen', 'e3-5-synth-source', '1', 'e3-5-chunk-' || g, 'fragmento sintetico ' || g, "
                    "(SELECT array_agg(sin(g * k::float8))::vector(384) FROM generate_series(1, 384) AS k) "
                    "FROM generate_series(%s, %s) AS g ON CONFLICT DO NOTHING", (start, end)))
    return out


def run_seed(connect: Callable[[str], Any], migrator_dsn: str, plan: SeedPlan,
             deployment_id: str = SYNTH_DEPLOYMENT, tenant_id: str = SYNTH_TENANT) -> dict:
    started = time.monotonic()
    statements = seed_statements(plan, deployment_id, tenant_id)
    inserted: dict[str, int] = {}
    with connect(migrator_dsn) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(SCOPE_SET, (deployment_id, tenant_id))
                for table, sql, params in statements:
                    cur.execute(sql, params)
                    inserted[table] = inserted.get(table, 0) + max(0, cur.rowcount or 0)
        knowledge_present = False
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.knowledge_chunks') IS NOT NULL")
            knowledge_present = bool(cur.fetchone()[0])
        if knowledge_present and plan.chunks:
            with conn.transaction():
                with conn.cursor() as cur:
                    for table, sql, params in knowledge_statements(plan):
                        cur.execute(sql, params)
                        inserted[table] = inserted.get(table, 0) + max(0, cur.rowcount or 0)
        counts: dict[str, int] = {}
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(SCOPE_SET, (deployment_id, tenant_id))
                for table in ("conversations", "inbox_events", "turns", "outcomes", "deliveries"):
                    cur.execute(f"SELECT count(*) FROM {table} WHERE deployment_id=%s AND tenant_id=%s",
                                (deployment_id, tenant_id))
                    counts[table] = cur.fetchone()[0]
    checks = {
        "turns_at_least_target": counts["turns"] >= plan.turns,
        "conversations_at_least_target": counts["conversations"] >= plan.conversations,
    }
    return {
        "status": "passed" if all(checks.values()) else "failed",
        "scope": {"deployment_id": deployment_id, "tenant_id": tenant_id},
        "plan": {"conversations": plan.conversations, "turns": plan.turns, "chunks": plan.chunks},
        "inserted_this_run": inserted,
        "counts_in_scope": counts,
        "knowledge_tables_present": knowledge_present,
        "knowledge_skipped_reason": None if knowledge_present or not plan.chunks else "knowledge tables absent",
        "idempotent_rerun": sum(inserted.values()) == 0,
        "duration_seconds": round(time.monotonic() - started, 3),
        "checks": checks,
    }


# --------------------------------------------------------- process sampling


class ProcessSampler:
    """CPU%/RSS of one pid; psutil when installed, /proc otherwise."""

    def __init__(self, pid: int, *, interval: float = 2.0, proc_root: str = "/proc",
                 clock: Callable[[], float] = time.monotonic):
        self.pid, self.interval, self.proc_root, self._clock = pid, interval, proc_root, clock
        self.samples: list[dict] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last: tuple[float, float] | None = None
        try:
            import psutil  # type: ignore
            self._psutil = psutil.Process(pid)
            self.source = "psutil"
        except Exception:
            self._psutil = None
            self.source = "proc"

    def _read_proc(self) -> tuple[float, int] | None:
        try:
            stat = Path(self.proc_root, str(self.pid), "stat").read_text()
            fields = stat.rsplit(")", 1)[1].split()
            ticks = int(fields[11]) + int(fields[12])
            cpu_seconds = ticks / os.sysconf("SC_CLK_TCK")
            rss = 0
            for line in Path(self.proc_root, str(self.pid), "status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    rss = int(line.split()[1]) * 1024
            return cpu_seconds, rss
        except (OSError, ValueError, IndexError):
            return None

    def sample_once(self) -> dict | None:
        now = self._clock()
        if self._psutil is not None:
            try:
                times = self._psutil.cpu_times()
                cpu_seconds, rss = times.user + times.system, self._psutil.memory_info().rss
            except Exception:
                return None
        else:
            read = self._read_proc()
            if read is None:
                return None
            cpu_seconds, rss = read
        cpu_pct = None
        if self._last is not None and now > self._last[0]:
            cpu_pct = round(100.0 * (cpu_seconds - self._last[1]) / (now - self._last[0]), 2)
        self._last = (now, cpu_seconds)
        row = {"cpu_percent": cpu_pct, "rss_bytes": rss}
        self.samples.append(row)
        return row

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            self.sample_once()

    def start(self) -> "ProcessSampler":
        self.sample_once()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> dict:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.interval + 1)
        self.sample_once()
        return self.summary()

    def summary(self) -> dict:
        cpus = [s["cpu_percent"] for s in self.samples if s["cpu_percent"] is not None]
        rss = [s["rss_bytes"] for s in self.samples]
        return {
            "source": self.source, "samples": len(self.samples),
            "cpu_percent_max": max(cpus) if cpus else None,
            "cpu_percent_mean": round(sum(cpus) / len(cpus), 2) if cpus else None,
            "rss_mb_max": round(max(rss) / 1048576, 1) if rss else None,
            "rss_mb_last": round(rss[-1] / 1048576, 1) if rss else None,
        }


# ----------------------------------------------------------- metrics helpers


def pool_summary(before: dict, after: dict) -> dict:
    pool = (after or {}).get("db_pool") or {}
    prev = (before or {}).get("db_pool") or {}
    return {
        "max": pool.get("max"), "peak_in_use": pool.get("peak_in_use"),
        "waiting_last": pool.get("waiting"), "timeouts_delta": (pool.get("timeouts") or 0) - (prev.get("timeouts") or 0),
        "wait_count_delta": (pool.get("wait_count") or 0) - (prev.get("wait_count") or 0),
        "wait_ms_total_delta": round((pool.get("wait_ms_total") or 0.0) - (prev.get("wait_ms_total") or 0.0), 2),
    }


def cost_delta(before: dict, after: dict) -> dict:
    """USD/tokens per (kind, basis) added between two /metrics snapshots."""
    def index(snapshot):
        return {(r.get("kind"), r.get("basis")): r for r in (snapshot or {}).get("cost", [])}
    b, a = index(before), index(after)
    out = {}
    for key, row in a.items():
        old = b.get(key, {})
        out[f"{key[0]}:{key[1]}"] = {
            "calls": row.get("calls", 0) - old.get("calls", 0),
            "input_tokens": row.get("input_tokens", 0) - old.get("input_tokens", 0),
            "output_tokens": row.get("output_tokens", 0) - old.get("output_tokens", 0),
            "usd": round(row.get("usd", 0.0) - old.get("usd", 0.0), 8),
        }
    return out


def load_slim(result: dict) -> dict:
    keep = ("status", "profile", "seed", "sessions", "requests", "success_count", "errors", "limit_rejections",
            "rps_observed", "rate_target_rps", "interval_seconds", "waves", "duration_target_seconds",
            "duration_observed_seconds", "http_status_counts", "unique_execution_ids",
            "revisions_consistent", "latency_ms", "authenticated", "started_at")
    slim = {k: result.get(k) for k in keep}
    slim["pool"] = pool_summary(result.get("metrics_before"), result.get("metrics_after"))
    slim["cost_delta"] = cost_delta(result.get("metrics_before"), result.get("metrics_after"))
    slim["metrics_after_cost"] = (result.get("metrics_after") or {}).get("cost")
    slim["stage_latency_ms"] = (result.get("metrics_after") or {}).get("stage_latency_ms")
    slim["rejections_after"] = (result.get("metrics_after") or {}).get("rejections")
    return slim


# -------------------------------------------------------------- fault proxy


class FaultProxy:
    """Loopback-only HTTP fault injector for LLM/READ/embeddings traffic.

    modes: pass (forward to upstream), timeout (hold the socket open past client
    timeouts), http_5xx (503), reset (close without answering)."""

    MODES = {"pass", "timeout", "http_5xx", "reset"}

    def __init__(self, upstream: str | None = None, *, hold_seconds: float = 30.0):
        if upstream:
            parts = urlsplit(upstream)
            local = parts.hostname in {"127.0.0.1", "localhost", "::1"}
            if not (parts.scheme == "https" or (parts.scheme == "http" and local)):
                raise ValueError("Proxy upstream must be https (or loopback http for tests)")
        self.upstream, self.hold_seconds = (upstream.rstrip("/") if upstream else None), hold_seconds
        self.mode = "pass"
        self.hits: dict[str, int] = {}
        self._lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _handle(self):
                mode = outer.mode
                with outer._lock:
                    outer.hits[mode] = outer.hits.get(mode, 0) + 1
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                if mode == "reset":
                    self.close_connection = True
                    self.connection.close()
                    return
                if mode == "timeout":
                    outer._stop.wait(outer.hold_seconds)
                    self.close_connection = True
                    return
                if mode == "http_5xx" or outer.upstream is None:
                    data = b'{"error":"fault-proxy"}'
                    status = 503 if mode == "http_5xx" else 502
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                headers = {k: v for k, v in self.headers.items()
                           if k.lower() not in {"host", "content-length", "connection"}}
                request = Request(outer.upstream + self.path, data=body or None, headers=headers,
                                  method=self.command)
                try:
                    with urlopen(request, timeout=60) as response:  # noqa: S310 - validated upstream
                        data, status, ctype = response.read(), response.status, response.headers.get("Content-Type")
                except Exception as exc:  # HTTPError carries a body
                    status = getattr(exc, "code", 502)
                    data = exc.read() if hasattr(exc, "read") else b"{}"
                    ctype = "application/json"
                self.send_response(status)
                self.send_header("Content-Type", ctype or "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = do_PUT = do_DELETE = _handle

        self._stop = threading.Event()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def set_mode(self, mode: str) -> None:
        if mode not in self.MODES:
            raise ValueError("unknown fault mode")
        self.mode = mode

    def start(self) -> "FaultProxy":
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        self._server.shutdown()
        self._server.server_close()


# -------------------------------------------------------------- app process


class AppProcess:
    """Owns the D0/probe app subprocess so CPU/mem, SIGTERM and restarts are measurable."""

    def __init__(self, command: list[str], env: dict[str, str], *, url: str, token: str | None = None,
                 popen: Callable[..., Any] = subprocess.Popen, http_status: Callable[[str, str | None], int] | None = None):
        self.command, self.env, self.url, self.token = command, env, url.rstrip("/"), token
        self._popen = popen
        self._http_status = http_status or _http_status
        self.proc: Any = None

    @property
    def pid(self) -> int | None:
        return self.proc.pid if self.proc else None

    def start(self, *, ready_timeout: float = 60.0, sleep: Callable[[float], None] = time.sleep) -> None:
        self.proc = self._popen(self.command, env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + ready_timeout
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError("app exited before becoming ready")
            if self._http_status(self.url + "/readyz", self.token) == 200:
                return
            sleep(0.5)
        raise RuntimeError("app did not become ready in time")

    def sigterm(self, *, wait: float = 40.0) -> dict:
        started = time.monotonic()
        self.proc.send_signal(signal.SIGTERM)
        try:
            code = self.proc.wait(timeout=wait)
            exited = True
        except subprocess.TimeoutExpired:
            code, exited = None, False
            self.proc.kill()
            self.proc.wait(timeout=10)
        return {"exited_within_deadline": exited, "exit_code": code,
                "drain_seconds": round(time.monotonic() - started, 3)}

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def _http_status(url: str, token: str | None) -> int:
    headers = {"Authorization": "Bearer " + token} if token else {}
    try:
        with urlopen(Request(url, headers=headers), timeout=5) as response:  # noqa: S310 - loopback
            return response.status
    except Exception as exc:
        return getattr(exc, "code", 0)


# ----------------------------------------------------- db-side fault checks


def integrity_check(connect, dsn: str, deployment_id: str, tenant_id: str, conversation_prefix: str) -> dict:
    """No lost/duplicated logical turns for conversations created by one load run."""
    assert_synthetic_scope(deployment_id, tenant_id)
    like = conversation_prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    with connect(dsn) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(SCOPE_SET, (deployment_id, tenant_id))
                cur.execute(
                    "SELECT count(*) FROM conversations c WHERE c.deployment_id=%s AND c.tenant_id=%s "
                    "AND c.conversation_id LIKE %s AND c.revision <> (SELECT count(*) FROM turns t WHERE "
                    "t.deployment_id=c.deployment_id AND t.tenant_id=c.tenant_id AND t.conversation_id=c.conversation_id "
                    "AND t.actor_id=c.actor_id)", (deployment_id, tenant_id, like))
                revision_mismatch = cur.fetchone()[0]
                cur.execute(
                    "SELECT count(*) FROM (SELECT execution_id FROM deliveries WHERE deployment_id=%s AND tenant_id=%s "
                    "AND execution_id IN (SELECT execution_id FROM turns WHERE deployment_id=%s AND tenant_id=%s "
                    "AND conversation_id LIKE %s) GROUP BY execution_id HAVING count(*) > 1) d",
                    (deployment_id, tenant_id, deployment_id, tenant_id, like))
                duplicate_deliveries = cur.fetchone()[0]
                cur.execute(
                    "SELECT count(*) FROM turns WHERE deployment_id=%s AND tenant_id=%s AND conversation_id LIKE %s",
                    (deployment_id, tenant_id, like))
                turns = cur.fetchone()[0]
    return {"turns": turns, "revision_mismatch": revision_mismatch, "duplicate_deliveries": duplicate_deliveries,
            "ok": revision_mismatch == 0 and duplicate_deliveries == 0}


def audit_correlation(connect, dsn: str, deployment_id: str, tenant_id: str, conversation_prefix: str) -> dict:
    """G7: every execution of the campaign has at least one audit event. A missing audit
    table is reported as unavailable, never as a pass."""
    assert_synthetic_scope(deployment_id, tenant_id)
    like = conversation_prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    with connect(dsn) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(SCOPE_SET, (deployment_id, tenant_id))
                cur.execute("SELECT to_regclass('public.audit_events') IS NOT NULL")
                if not cur.fetchone()[0]:
                    return {"available": False, "ok": False}
                cur.execute(
                    "SELECT count(*), count(*) FILTER (WHERE EXISTS (SELECT 1 FROM audit_events a WHERE "
                    "a.deployment_id=t.deployment_id AND a.tenant_id=t.tenant_id AND a.execution_id=t.execution_id::text)) "
                    "FROM turns t WHERE t.deployment_id=%s AND t.tenant_id=%s AND t.conversation_id LIKE %s",
                    (deployment_id, tenant_id, like))
                total, covered = cur.fetchone()
    return {"available": True, "executions": total, "with_audit": covered,
            "coverage": round(covered / total, 6) if total else None, "ok": bool(total) and covered == total}


GRANT_TABLE = "inbox_events"


def capture_grants(connect, dsn: str, table: str = GRANT_TABLE, role: str = RUNTIME_ROLE) -> list[str]:
    if table != GRANT_TABLE or role != RUNTIME_ROLE:
        raise GuardError("Only the runtime role grants on the synthetic ledger table may be touched")
    with connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT privilege_type FROM information_schema.role_table_grants WHERE grantee=%s "
                    "AND table_schema='public' AND table_name=%s ORDER BY 1", (role, table))
        return [row[0] for row in cur.fetchall()]


_PRIVS = {"SELECT", "INSERT", "UPDATE", "DELETE"}


def set_grants(connect, dsn: str, privileges: list[str], *, revoke: bool, table: str = GRANT_TABLE,
               role: str = RUNTIME_ROLE) -> None:
    if table != GRANT_TABLE or role != RUNTIME_ROLE or not privileges or not set(privileges) <= _PRIVS:
        raise GuardError("Refusing grant change outside the approved reversible scope")
    verb = "REVOKE {p} ON {t} FROM {r}" if revoke else "GRANT {p} ON {t} TO {r}"
    with connect(dsn) as conn, conn.transaction(), conn.cursor() as cur:
        cur.execute(verb.format(p=", ".join(sorted(privileges)), t=table, r=role))


# ---------------------------------------------------------------- Neon CLI


class NeonCli:
    """Thin wrapper over the pinned Neon CLI; DSNs are returned, never logged."""

    def __init__(self, run: Callable[..., Any] = subprocess.run):
        self._run = run

    def _exec(self, args: list[str]) -> str:
        result = self._run(["npx", "--yes", NEON_CLI, *args, "--output", "json", "--analytics", "false"],
                           capture_output=True, text=True, check=False)
        if result.returncode:
            raise RuntimeError("Neon CLI command failed: " + args[0] + " " + args[1])
        return result.stdout

    def create_branch(self, name: str, parent: str, expires_at: datetime) -> dict:
        assert_restore_branch(name)
        if parent != BRANCH:
            raise GuardError("Temporary branches may only be created from the synthetic branch")
        out = self._exec(["branches", "create", "--name", name, "--parent", parent,
                          "--expires-at", expires_at.strftime("%Y-%m-%dT%H:%M:%SZ")])
        return json.loads(out) if out.strip().startswith(("{", "[")) else {}

    def connection_string(self, branch: str, role: str) -> str:
        assert_restore_branch(branch)
        if role != MIGRATOR_ROLE:
            raise GuardError("Only the migrator role is used on temporary branches")
        out = self._exec(["connection-string", branch, "--role-name", role, "--database-name", DATABASE,
                          "--ssl", "require"])
        match = re.search(r"postgres(?:ql)?://[^\s\"'<>]+", out)
        if not match:
            raise RuntimeError("Neon CLI returned no connection string")
        dsn = match.group(0)
        host = (urlsplit(dsn).hostname or "")
        if not host.endswith(".neon.tech") or "-pooler." in host:
            raise GuardError("Unexpected endpoint for the temporary branch")
        return dsn

    def delete_branch(self, name: str) -> None:
        assert_restore_branch(name)
        self._exec(["branches", "delete", name])


# ----------------------------------------------------------------- restore

RESTORE_TABLES_DELETE_ORDER = ("deliveries", "outcomes", "turns", "inbox_events", "conversations")


def wipe_scope(connect, dsn: str, deployment_id: str, tenant_id: str, *, primary_host: str) -> None:
    """Empty the synthetic scope on the TEMPORARY branch so the restore is a real restore."""
    assert_synthetic_scope(deployment_id, tenant_id)
    host = urlsplit(dsn).hostname or ""
    if not host or host == primary_host:
        raise GuardError("Refusing to wipe: DSN points at the primary synthetic branch")
    with connect(dsn) as conn, conn.transaction(), conn.cursor() as cur:
        cur.execute(SCOPE_SET, (deployment_id, tenant_id))
        for table in RESTORE_TABLES_DELETE_ORDER:
            cur.execute(f"DELETE FROM {table} WHERE deployment_id=%s AND tenant_id=%s", (deployment_id, tenant_id))
        cur.execute("DELETE FROM resource_claims WHERE deployment_id=%s AND tenant_id=%s", (deployment_id, tenant_id))


def pgvector_check(connect, dsn: str) -> dict:
    with connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.knowledge_chunks') IS NOT NULL")
        if not cur.fetchone()[0]:
            return {"available": False, "ok": False, "reason": "knowledge tables absent in restored branch"}
        cur.execute("SELECT extversion FROM pg_extension WHERE extname='vector'")
        row = cur.fetchone()
        cur.execute("SELECT indexname, indexdef FROM pg_indexes WHERE tablename='knowledge_chunks'")
        indexes = cur.fetchall()
        cur.execute("SELECT indexrelid::regclass::text FROM pg_index WHERE indrelid='knowledge_chunks'::regclass "
                    "AND NOT indisvalid")
        invalid = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT count(*) FROM knowledge_chunks")
        chunks = cur.fetchone()[0]
        nearest = 0
        if chunks:
            cur.execute("SELECT count(*) FROM (SELECT 1 FROM knowledge_chunks ORDER BY embedding <=> "
                        "(SELECT embedding FROM knowledge_chunks LIMIT 1) LIMIT 5) q")
            nearest = cur.fetchone()[0]
    names = [i[0] for i in indexes]
    return {"available": True, "vector_extension": row[0] if row else None, "indexes": names,
            "hnsw_present": any("hnsw" in (i[1] or "").lower() for i in indexes),
            "invalid_indexes": invalid, "chunks": chunks, "nearest_query_rows": nearest,
            "ok": bool(row) and not invalid and (nearest > 0 or chunks == 0)}


def quarantine_check(connect, dsn: str, deployment_id: str, tenant_id: str, *, marker_execution_id: str,
                     seeded_sending: int) -> dict:
    """After restore: nothing may be SENDING, the in-flight ones became UNKNOWN_EFFECT, no claims
    remain and the post-backup marker delivery is absent (it must be reconciled, not replayed)."""
    assert_synthetic_scope(deployment_id, tenant_id)
    with connect(dsn) as conn, conn.transaction(), conn.cursor() as cur:
        cur.execute(SCOPE_SET, (deployment_id, tenant_id))
        cur.execute("SELECT state, count(*) FROM deliveries WHERE deployment_id=%s AND tenant_id=%s GROUP BY state",
                    (deployment_id, tenant_id))
        states = {s: n for s, n in cur.fetchall()}
        cur.execute("SELECT count(*) FROM deliveries WHERE deployment_id=%s AND tenant_id=%s AND execution_id=%s::uuid",
                    (deployment_id, tenant_id, marker_execution_id))
        marker_present = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM resource_claims WHERE deployment_id=%s AND tenant_id=%s",
                    (deployment_id, tenant_id))
        claims = cur.fetchone()[0]
    checks = {
        "no_sending_left": states.get("SENDING", 0) == 0,
        "in_flight_quarantined": states.get("UNKNOWN_EFFECT", 0) >= seeded_sending,
        "post_backup_delivery_absent": marker_present == 0,
        "claims_cleared": claims == 0,
    }
    return {"delivery_states": states, "marker_present": marker_present, "claims": claims,
            "checks": checks, "ok": all(checks.values())}


def insert_post_backup_marker(connect, dsn: str, deployment_id: str, tenant_id: str, execution_id: str) -> None:
    """A delivery that exists only AFTER the backup point (must not survive the restore)."""
    assert_synthetic_scope(deployment_id, tenant_id)
    with connect(dsn) as conn, conn.transaction(), conn.cursor() as cur:
        cur.execute(SCOPE_SET, (deployment_id, tenant_id))
        cur.execute(
            "INSERT INTO inbox_events (deployment_id, tenant_id, channel, channel_account_ref, external_event_id, "
            "payload_hash, payload_json, request_id, execution_id, state) VALUES (%s, %s, 'e3-5-seed', 'e3-5-seed', "
            "%s, 'marker', '{}'::jsonb, %s::uuid, %s::uuid, 'COMPLETED') ON CONFLICT DO NOTHING",
            (deployment_id, tenant_id, "e3-5-marker-" + execution_id, execution_id, execution_id))
        cur.execute(
            "INSERT INTO deliveries (execution_id, deployment_id, tenant_id, response_id, destination_ref, "
            "payload_json, state) VALUES (%s::uuid, %s, %s, 'marker', 'e3-5-seed', '{}'::jsonb, 'PENDING') "
            "ON CONFLICT DO NOTHING", (execution_id, deployment_id, tenant_id))


def count_state(connect, dsn: str, deployment_id: str, tenant_id: str, state: str) -> int:
    assert_synthetic_scope(deployment_id, tenant_id)
    with connect(dsn) as conn, conn.transaction(), conn.cursor() as cur:
        cur.execute(SCOPE_SET, (deployment_id, tenant_id))
        cur.execute("SELECT count(*) FROM deliveries WHERE deployment_id=%s AND tenant_id=%s AND state=%s",
                    (deployment_id, tenant_id, state))
        return cur.fetchone()[0]


def branch_hosts(created: Any) -> set[str]:
    """Neon hosts reported by `branches create` for the new branch (direct and pooled)."""
    hosts = {h.lower().replace("-pooler.", ".", 1) for h in re.findall(r"[A-Za-z0-9.-]+\.neon\.tech", json.dumps(created))}
    return hosts


def assert_dsn_is_new_branch(dsn: str, created: Any, *, primary_host: str) -> None:
    """Fail closed unless the DSN host is one the create call reported for the temporary branch."""
    host = (urlsplit(dsn).hostname or "").lower()
    if host == primary_host.lower() or host not in branch_hosts(created):
        raise GuardError("Temporary branch DSN does not match the endpoint of the branch just created")


def rpo_rto(export_completed_at: datetime, disaster_at: datetime, rto_seconds: float) -> dict:
    rpo = max(0.0, (disaster_at - export_completed_at).total_seconds())
    return {"rpo_seconds": round(rpo, 3), "rto_seconds": round(rto_seconds, 3),
            "rpo_target_seconds": TARGET_RPO_SECONDS, "rto_target_seconds": TARGET_RTO_SECONDS,
            "rpo_ok": rpo <= TARGET_RPO_SECONDS, "rto_ok": rto_seconds <= TARGET_RTO_SECONDS}


# ---------------------------------------------------------------- rollback

DIGEST_RE = re.compile(r"^[A-Za-z0-9./_:-]+@sha256:[0-9a-f]{64}$")


def check_migration_chain(connect, dsn: str, migrations_dir: Path) -> dict:
    expected = sorted(p.stem for p in Path(migrations_dir).glob("*.sql"))
    with connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT version FROM schema_migrations")
        applied = {row[0] for row in cur.fetchall()}
    # schema_migrations may store either the stem or the file name.
    missing = [e for e in expected if e not in applied and e + ".sql" not in applied
               and e.split("_")[0] not in applied]
    return {"expected": expected, "applied_count": len(applied), "missing": missing, "ok": not missing}


# ----------------------------------------------------------------- cost


def reconcile_cost(estimated_usd: float, reported_usd: float | None, *, tolerance: float = COST_TOLERANCE,
                   budget_usd: float | None = None) -> dict:
    if reported_usd is None:
        return {"status": "skipped", "reason": "provider-reported usage not available", "ok": False,
                "estimated_usd": round(estimated_usd, 6)}
    denom = max(reported_usd, 1e-9)
    deviation = abs(estimated_usd - reported_usd) / denom
    ok = deviation <= tolerance and (budget_usd is None or reported_usd <= budget_usd)
    return {"status": "passed" if ok else "failed", "estimated_usd": round(estimated_usd, 6),
            "reported_usd": round(reported_usd, 6), "deviation": round(deviation, 4), "tolerance": tolerance,
            "within_budget": budget_usd is None or reported_usd <= budget_usd, "ok": ok}


# -------------------------------------------------------------- reporting


def utc_now() -> datetime:
    return datetime.now(UTC)


def write_json(path: Path, payload: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _phase(results: dict, name: str) -> dict:
    return results.get(name) or {"status": "not_run"}


def build_summary(results: dict, *, run_id: str, dry_run: bool = False, budget_usd: float | None = None,
                  short_run: bool = False) -> dict:
    """Pass/fail per criterion. A criterion is only 'passed' when its evidence ran and passed;
    skipped/not_run evidence is 'inconclusive'. gate_closed is always False (the owner ratifies)."""
    def verdict(flag: bool | None) -> str:
        return "inconclusive" if flag is None else ("passed" if flag else "failed")

    load = _phase(results, "load")
    profiles = load.get("profiles", {}) if load.get("status") not in {"not_run", "skipped"} else {}
    p95s = [p["latency_ms"]["p95"] for p in profiles.values() if p.get("latency_ms", {}).get("p95") is not None]
    ran_load = bool(profiles) and not short_run
    slo_latency = None if not ran_load or not p95s else max(p95s) <= TARGET_P95_MS
    load_clean = None if not ran_load else all(p.get("errors", 1) == 0 and p.get("revisions_consistent")
                                              for p in profiles.values())
    def phase_ok(name: str) -> bool | None:
        status = _phase(results, name).get("status")
        return None if status in INCONCLUSIVE else status == "passed"

    faults, restore = _phase(results, "faults"), _phase(results, "restore")
    fault_ok, restore_ok = phase_ok("faults"), phase_ok("restore")
    rollback_ok, cost_ok = phase_ok("rollback"), phase_ok("cost")
    audit = (load.get("audit_correlation") or {}) if profiles else {}
    g7 = None if not audit else bool(audit.get("ok"))
    rpo_rto_block = restore.get("rpo_rto") or {}
    criteria = {
        "G7_audit_correlation_100pct": verdict(g7),
        "G9_load_measured_10min_profiles": verdict(None if not profiles else (not short_run)),
        "G9_zero_loss_duplication_under_load": verdict(load_clean),
        "G9_faults_recovered": verdict(fault_ok),
        "G9_restore_reproduced": verdict(restore_ok),
        "G9_rollback_rehearsed": verdict(rollback_ok),
        "G9_cost_reconciled": verdict(cost_ok),
        "SLO_p95_reception_to_outcome_le_5s": verdict(slo_latency),
        "SLO_rpo_le_12h": verdict(rpo_rto_block.get("rpo_ok") if rpo_rto_block else None),
        "SLO_rto_le_1h": verdict(rpo_rto_block.get("rto_ok") if rpo_rto_block else None),
    }
    return {
        "run_id": run_id, "dry_run": dry_run, "gate": "E3-5", "gate_closed": False,
        "synthetic": True, "branch": BRANCH, "budget_usd_approved": budget_usd,
        "generated_at": utc_now().isoformat(),
        "phases": {name: _phase(results, name).get("status", "not_run") for name in PHASE_ORDER},
        "criteria": criteria,
        "all_criteria_passed": all(v == "passed" for v in criteria.values()),
        "note": "gate_closed stays false: closing E3-5 is the owner's decision after reviewing this evidence.",
    }


def expires_at(minutes: int = 120, now: datetime | None = None) -> datetime:
    return (now or utc_now()) + timedelta(minutes=minutes)
