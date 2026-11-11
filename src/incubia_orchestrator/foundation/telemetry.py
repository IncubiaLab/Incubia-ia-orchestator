"""Bounded process-local HTTP metrics without request content or dynamic labels."""

import logging
import re
from collections.abc import Callable
from threading import Lock

LOG = logging.getLogger(__name__)
_REASON = re.compile(r"[A-Z][A-Z0-9_]{0,39}")
_KIND = re.compile(r"[a-z][a-z0-9_]{0,31}")
_MAX_KINDS = 32  # bounds label cardinality


def _safe_label(value: object, pattern: re.Pattern, fallback: str = "other") -> str:
    """Only short code-like tokens may become labels; free text/secrets collapse."""
    return value if isinstance(value, str) and pattern.fullmatch(value) else fallback


class HttpMetrics:
    BUCKETS_MS = (10, 50, 100, 250, 500, 1000, 5000)

    def __init__(self, deployment_id: str, tenant_id: str):
        self.deployment_id = deployment_id
        self.tenant_id = tenant_id
        self._lock = Lock()
        self._in_flight = 0
        self._peak_in_flight = 0
        self._requests = 0
        self._errors = 0
        self._latency_counts = [0] * (len(self.BUCKETS_MS) + 1)
        self._exporters: list[Callable[[str, dict], None]] = []
        self._pool = {"in_use": 0, "max": 0, "waiting": 0, "peak_in_use": 0,
                      "wait_ms_total": 0.0, "wait_count": 0, "timeouts": 0}
        self._cost: dict[tuple[str, str], dict] = {}
        self._rejections: dict[tuple[str, str], int] = {}
        self._stage = {name: [0] * (len(self.BUCKETS_MS) + 1)
                       for name in ("reception_to_outcome", "reception_to_delivery")}

    # -- sinks: failures here must never reach callers (commits, requests) --
    def add_exporter(self, exporter: Callable[[str, dict], None]) -> None:
        with self._lock:
            self._exporters.append(exporter)

    def _emit(self, event: str, payload: dict) -> None:
        with self._lock:
            exporters = tuple(self._exporters)
        for exporter in exporters:
            try:
                exporter(event, {"deployment_id": self.deployment_id,
                                 "tenant_id": self.tenant_id, **payload})
            except Exception as exc:
                LOG.warning("metrics_exporter_failed type=%s", type(exc).__name__)

    def _bucket(self, value_ms: float) -> int:
        return next((i for i, bound in enumerate(self.BUCKETS_MS)
                     if value_ms <= bound), len(self.BUCKETS_MS))

    def started(self) -> None:
        with self._lock:
            self._in_flight += 1
            self._peak_in_flight = max(self._peak_in_flight, self._in_flight)

    def finished(self, status: int, latency_ms: float) -> None:
        with self._lock:
            self._in_flight -= 1
            self._requests += 1
            self._errors += status >= 500
            self._latency_counts[self._bucket(latency_ms)] += 1
        self._emit("http_request", {"status_class": f"{int(status) // 100}xx"})

    def pool_stats(self, *, in_use: int, max_size: int, waiting: int = 0) -> None:
        with self._lock:
            self._pool.update(in_use=in_use, max=max_size, waiting=waiting)
            self._pool["peak_in_use"] = max(self._pool["peak_in_use"], in_use)
        self._emit("db_pool", {"in_use": in_use, "max": max_size, "waiting": waiting})

    def pool_wait(self, wait_ms: float, *, timed_out: bool = False) -> None:
        with self._lock:
            self._pool["wait_ms_total"] += max(0.0, wait_ms)
            self._pool["wait_count"] += 1
            self._pool["timeouts"] += bool(timed_out)
        self._emit("db_pool_wait", {"wait_ms": wait_ms, "timed_out": bool(timed_out)})

    def cost(self, kind: str, *, input_tokens: int = 0, output_tokens: int = 0,
             usd: float = 0.0, reconciled: bool = False) -> None:
        """kind is 'llm' or 'embedding'-like; estimated and reconciled are tracked apart."""
        key = (_safe_label(kind, _KIND), "reconciled" if reconciled else "estimated")
        with self._lock:
            if key not in self._cost and len(self._cost) >= _MAX_KINDS:
                key = ("other", key[1])
            row = self._cost.setdefault(key, {"calls": 0, "input_tokens": 0,
                                              "output_tokens": 0, "usd": 0.0})
            row["calls"] += 1
            row["input_tokens"] += max(0, int(input_tokens))
            row["output_tokens"] += max(0, int(output_tokens))
            row["usd"] += max(0.0, float(usd))
        self._emit("cost", {"kind": key[0], "basis": key[1], "input_tokens": input_tokens,
                            "output_tokens": output_tokens, "usd": usd})

    def rejection(self, category: str, reason: str) -> None:
        """category: provider_quota | provider_limit | budget (code-like tokens only)."""
        key = (_safe_label(category, _KIND), _safe_label(reason, _REASON))
        with self._lock:
            if key not in self._rejections and len(self._rejections) >= _MAX_KINDS:
                key = ("other", "OTHER")
            self._rejections[key] = self._rejections.get(key, 0) + 1
        self._emit("rejection", {"category": key[0], "reason": key[1]})

    def stage_latency(self, stage: str, latency_ms: float) -> None:
        if stage not in self._stage:
            return
        with self._lock:
            self._stage[stage][self._bucket(latency_ms)] += 1
        self._emit("stage_latency", {"stage": stage, "latency_ms": latency_ms})

    def percentile(self, stage: str, q: float) -> float | str | None:
        """Upper-bound estimate (bucket edge) of the q-quantile, q in (0,1]."""
        with self._lock:
            counts = list(self._stage[stage]) if stage in self._stage else None
        if not counts or not sum(counts):
            return None
        target, seen = q * sum(counts), 0
        for bound, count in zip((*self.BUCKETS_MS, "+Inf"), counts, strict=True):  # JSON-safe overflow
            seen += count
            if seen >= target:
                return bound
        return "+Inf"

    def snapshot(self) -> dict:
        with self._lock:
            stages = {name: {"buckets": dict(zip((*self.BUCKETS_MS, "+Inf"), counts, strict=True)),
                             "count": sum(counts)} for name, counts in self._stage.items()}
            snap = {
                "deployment_id": self.deployment_id,
                "tenant_id": self.tenant_id,
                "requests": self._requests,
                "server_errors": self._errors,
                "in_flight": self._in_flight,
                "peak_in_flight": self._peak_in_flight,
                "latency_ms_buckets": dict(zip(
                    (*self.BUCKETS_MS, "+Inf"), self._latency_counts, strict=True
                )),
                "db_pool": dict(self._pool),
                "cost": [{"kind": k, "basis": b, **row} for (k, b), row in sorted(self._cost.items())],
                "rejections": [{"category": c, "reason": r, "count": n}
                               for (c, r), n in sorted(self._rejections.items())],
                "stage_latency_ms": stages,
            }
        for name in stages:
            snap["stage_latency_ms"][name].update(
                {f"p{int(q * 100)}": self.percentile(name, q) for q in (0.5, 0.95, 0.99)})
        return snap
