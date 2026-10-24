"""Strict, fail-closed loader for the E3 limits file (config/e3/limits.example.yaml).

A missing, null, non-numeric, boolean or non-positive value is rejected: a null
budget never authorizes spend. Values may be provisional until ratified (E3-0/D9);
production composition requires status "ratified".
"""

import math
import os
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml


class LimitsError(ValueError):
    """The limits document is incomplete or invalid; no spend is authorized."""


@dataclass(frozen=True)
class Nfr:
    slo_p95_seconds: float
    rpo_hours: float
    rto_hours: float


@dataclass(frozen=True)
class Deadlines:
    tool_call_timeout_seconds: float
    tool_total_deadline_seconds: float
    tool_max_attempts: int


@dataclass(frozen=True)
class Budget:
    max_calls: int
    max_input_tokens: int
    max_output_tokens: int
    usd_cap: float


@dataclass(frozen=True)
class TenantLimits(Budget):
    admission_rate_per_minute: int


@dataclass(frozen=True)
class Limits:
    status: str
    nfr: Nfr
    deadlines: Deadlines
    eval_e3: Budget
    tenant: TenantLimits
    pool_max_size: int


def _section(data: dict, name: str, fields: dict[str, type]) -> dict:
    section = data.get(name)
    if not isinstance(section, dict):
        raise LimitsError(f"missing section: {name}")
    unknown = set(section) - set(fields)
    if unknown:
        raise LimitsError(f"{name}: unknown keys {sorted(unknown)}")
    out = {}
    for key, kind in fields.items():
        value = section.get(key)
        if value is None:
            raise LimitsError(f"{name}.{key}: missing or null")
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise LimitsError(f"{name}.{key}: must be a number")
        if not math.isfinite(value) or value <= 0:
            raise LimitsError(f"{name}.{key}: must be a finite positive number")
        if kind is int and value != int(value):
            raise LimitsError(f"{name}.{key}: must be an integer")
        out[key] = kind(value)
    return out


def parse_limits(data: object) -> Limits:
    if not isinstance(data, dict):
        raise LimitsError("limits document must be a mapping")
    if type(data.get("version")) is not int or data["version"] != 1:
        raise LimitsError("unsupported or missing version")
    status = data.get("status")
    if status not in {"provisional", "ratified"}:
        raise LimitsError("status must be 'provisional' or 'ratified'")
    allowed = {"version", "status", "nfr", "deadlines", "eval-e3", "tenant", "pool"}
    if set(data) - allowed:
        raise LimitsError(f"unknown top-level keys {sorted(set(data) - allowed)}")
    budget = {"max_calls": int, "max_input_tokens": int, "max_output_tokens": int,
              "usd_cap": float}
    deadlines = Deadlines(**_section(data, "deadlines", {
        "tool_call_timeout_seconds": float, "tool_total_deadline_seconds": float,
        "tool_max_attempts": int}))
    if deadlines.tool_call_timeout_seconds > deadlines.tool_total_deadline_seconds:
        raise LimitsError("deadlines: per-call timeout exceeds total deadline")
    nfr = Nfr(**_section(data, "nfr", {"slo_p95_seconds": float, "rpo_hours": float,
                                       "rto_hours": float}))
    if deadlines.tool_total_deadline_seconds > nfr.slo_p95_seconds:
        raise LimitsError("deadlines: tool total deadline exceeds the p95 SLO")
    return Limits(
        status=status, nfr=nfr, deadlines=deadlines,
        eval_e3=Budget(**_section(data, "eval-e3", budget)),
        tenant=TenantLimits(**_section(data, "tenant",
                                       {**budget, "admission_rate_per_minute": int})),
        pool_max_size=_section(data, "pool", {"max_size": int})["max_size"])


def load_limits(path: Path) -> Limits:
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise LimitsError(f"cannot read limits: {type(exc).__name__}") from exc
    return parse_limits(data)


LIMITS_FILE_ENV = "INCUBIA_E3_LIMITS_FILE"
ALLOW_PROVISIONAL_ENV = "INCUBIA_E3_ALLOW_PROVISIONAL"
DEFAULT_LIMITS_FILE = "config/e3/limits.example.yaml"


def load_runtime_limits(environ: Mapping[str, str] | None = None, *,
                        allow_provisional: bool | None = None) -> Limits:
    """Load limits for a process at startup; fail closed on any problem.

    Production (default) requires status "ratified". Provisional limits are
    accepted only with allow_provisional=True or INCUBIA_E3_ALLOW_PROVISIONAL=1
    (tests/local).
    """
    env = os.environ if environ is None else environ
    if allow_provisional is None:
        allow_provisional = env.get(ALLOW_PROVISIONAL_ENV) == "1"
    raw = env.get(LIMITS_FILE_ENV) or DEFAULT_LIMITS_FILE
    path = Path(raw)
    if not path.is_absolute() and not path.exists() and not env.get(LIMITS_FILE_ENV):
        path = Path(__file__).resolve().parents[3] / raw  # repo root fallback
    limits = load_limits(path)
    if limits.status != "ratified" and not allow_provisional:
        raise LimitsError("limits are not ratified; production requires status 'ratified'")
    return limits


class AdmissionLimiter:
    """Per-tenant token bucket: capacity and refill derive from calls per minute."""

    def __init__(self, per_minute: int, *, clock: Callable[[], float] = time.monotonic,
                 max_tenants: int = 1024):
        if per_minute < 1:
            raise ValueError("per_minute must be positive")
        self._capacity = float(per_minute)
        self._rate = per_minute / 60.0
        self._clock, self._max = clock, max_tenants
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def try_acquire(self, tenant_id: str) -> bool:
        now = self._clock()
        with self._lock:
            tokens, last = self._buckets.get(tenant_id, (self._capacity, now))
            tokens = min(self._capacity, tokens + (now - last) * self._rate)
            allowed = tokens >= 1.0
            if tenant_id not in self._buckets and len(self._buckets) >= self._max:
                # Bounded memory: drop buckets that have fully refilled (equivalent to new).
                self._buckets = {k: v for k, v in self._buckets.items()
                                 if v[0] + (now - v[1]) * self._rate < self._capacity}
                if len(self._buckets) >= self._max:
                    return False  # still saturated by active tenants: fail closed
            self._buckets[tenant_id] = (tokens - 1.0 if allowed else tokens, now)
            return allowed

    @property
    def retry_after_seconds(self) -> int:
        return max(1, math.ceil(1.0 / self._rate))
