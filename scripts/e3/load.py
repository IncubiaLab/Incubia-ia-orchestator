"""Synthetic loopback load probe for the E3-D0 HTTP contract.

This measures local mechanics only. It never invokes a real LLM or connector.
"""

import argparse
import json
import math
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def _json(url: str, *, body: dict | None = None, key: str | None = None) -> tuple[int, dict, float]:
    headers = {"Content-Type": "application/json"}
    if key is not None:
        headers["Idempotency-Key"] = key
    request = Request(url, data=json.dumps(body).encode() if body is not None else None,
                      headers=headers)
    start = time.monotonic()
    try:
        with urlopen(request, timeout=15) as response:
            return response.status, json.load(response), (time.monotonic() - start) * 1000
    except HTTPError as exc:
        return exc.code, json.load(exc), (time.monotonic() - start) * 1000
    except (URLError, TimeoutError):
        return 0, {}, (time.monotonic() - start) * 1000


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1)], 2)


def run(base_url: str, *, profile: str, duration: float, sessions: int,
        interval: float, seed: str) -> dict:
    parsed = urlsplit(base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Only a local HTTP endpoint is allowed")
    base_url = base_url.rstrip("/")
    before_status, before, _ = _json(base_url + "/metrics")
    if before_status != 200:
        raise RuntimeError("The local metrics endpoint is unavailable")
    started = time.monotonic()

    def session(index: int) -> list[tuple[int, dict, float]]:
        results = []
        turn = 0
        while True:
            if profile == "burst" and turn >= 1:
                break
            if profile == "sessions" and turn > 0 and time.monotonic() - started >= duration:
                break
            conversation_id = f"e3-load-{seed}-{index}"
            results.append(_json(base_url + "/v1/executions",
                                 body={"message": "Consulta sintética", "conversation_id": conversation_id},
                                 key=f"e3-load-{seed}-{index}-{turn}"))
            turn += 1
            if profile == "sessions":
                time.sleep(max(0, started + turn * interval - time.monotonic()))
        return results

    with ThreadPoolExecutor(max_workers=sessions) as pool:
        rows = [row for batch in pool.map(session, range(sessions)) for row in batch]
    elapsed = round(time.monotonic() - started, 3)
    after_status, after, _ = _json(base_url + "/metrics")
    if after_status != 200:
        raise RuntimeError("Metrics endpoint failed after the campaign")
    successes = [body for status, body, _ in rows if status == 200]
    ids = [body.get("execution_id") for body in successes]
    revisions: dict[str, list[int]] = {}
    for body in successes:
        revisions.setdefault(body.get("conversation_id", ""), []).append(body.get("revision"))
    consistent = all(sorted(values) == list(range(1, len(values) + 1))
                     for values in revisions.values())
    latencies = [latency for _, _, latency in rows]
    return {
        "status": "passed" if len(successes) == len(rows) and len(ids) == len(set(ids)) and consistent else "failed",
        "gate_closed": False,
        "synthetic": True,
        "started_at": datetime.now(UTC).isoformat(),
        "profile": profile,
        "seed": seed,
        "sessions": sessions,
        "interval_seconds": interval if profile == "sessions" else None,
        "duration_target_seconds": duration if profile == "sessions" else None,
        "duration_observed_seconds": elapsed,
        "requests": len(rows),
        "rps_observed": round(len(rows) / elapsed, 3) if elapsed else None,
        "http_status_counts": {str(code): sum(item[0] == code for item in rows)
                               for code in sorted({item[0] for item in rows})},
        "unique_execution_ids": len(set(ids)),
        "revisions_consistent": consistent,
        "latency_ms": {"p50": _percentile(latencies, .5),
                       "p95": _percentile(latencies, .95),
                       "p99": _percentile(latencies, .99),
                       "mean": round(statistics.mean(latencies), 2) if latencies else None},
        "metrics_before": before,
        "metrics_after": after,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--profile", choices=("sessions", "burst"), required=True)
    parser.add_argument("--duration", type=float, default=600)
    parser.add_argument("--sessions", type=int, default=80)
    parser.add_argument("--interval", type=float, default=15)
    parser.add_argument("--seed", default="local")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.sessions < 1 or args.sessions > 80 or args.duration <= 0 or args.interval <= 0:
        parser.error("sessions must be 1..80 and duration/interval must be positive")
    result = run(args.url, profile=args.profile, duration=args.duration,
                 sessions=args.sessions, interval=args.interval, seed=args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("status", "profile", "requests", "duration_observed_seconds")}))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
