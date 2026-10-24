"""Strict, fail-closed loader for the E3 limits file (config/e3/limits.example.yaml).

A missing, null, non-numeric, boolean or non-positive value is rejected: a null
budget never authorizes spend. Values stay provisional until ratified (E3-0/D9).
"""

import math
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
