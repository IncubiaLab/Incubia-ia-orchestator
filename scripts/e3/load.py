"""Synthetic load probe for the E3-D0 HTTP contract.

Default target is loopback HTTP. A non-loopback target is allowed only over
https, with INCUBIA_E3_LOAD_ALLOW_REMOTE=1 and the host listed in
INCUBIA_E3_LOAD_ALLOWED_HOSTS (comma separated). A Bearer token is read from
INCUBIA_E3_PROBE_TOKEN and is never printed or written to the result. Redirects
are not followed so the token cannot leak to another host. The probe sends only
synthetic messages; spend is governed by the server-side budget (null = none).

Profiles: sessions (spaced turns), burst (N in flight, optionally --waves),
constant (--rate requests/second for --duration seconds).
"""

import argparse
import json
import math
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

LOOPBACK = {"127.0.0.1", "localhost", "::1"}
LIMIT_STATUSES = {429}
MAX_RATE = 200.0


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_OPENER = build_opener(_NoRedirect)


def validate_target(base_url: str, env: dict | None = None) -> str:
    env = os.environ if env is None else env
    parsed = urlsplit(base_url)
    host = parsed.hostname
    if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
        raise ValueError("Invalid target URL")
    if host in LOOPBACK:
        return base_url.rstrip("/")
    if parsed.scheme != "https":
        raise ValueError("A remote target must use https")
    if env.get("INCUBIA_E3_LOAD_ALLOW_REMOTE") != "1":
        raise ValueError("Remote target requires INCUBIA_E3_LOAD_ALLOW_REMOTE=1")
    allowed = {item.strip().lower() for item in env.get("INCUBIA_E3_LOAD_ALLOWED_HOSTS", "").split(",")
               if item.strip()}
    if host.lower() not in allowed:
        raise ValueError("Remote host is not in INCUBIA_E3_LOAD_ALLOWED_HOSTS")
    return base_url.rstrip("/")


def _json(url: str, *, body: dict | None = None, key: str | None = None,
          token: str | None = None) -> tuple[int, dict, float]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if key is not None:
        headers["Idempotency-Key"] = key
    request = Request(url, data=json.dumps(body).encode() if body is not None else None,
                      headers=headers)
    start = time.monotonic()
    try:
        with _OPENER.open(request, timeout=15) as response:
            return response.status, json.load(response), (time.monotonic() - start) * 1000
    except HTTPError as exc:
        try:
            payload = json.load(exc)
        except (ValueError, OSError):
            payload = {}
        return exc.code, payload if isinstance(payload, dict) else {}, (time.monotonic() - start) * 1000
    except (URLError, TimeoutError, OSError, ValueError):
        return 0, {}, (time.monotonic() - start) * 1000


def _redact(value, token: str | None):
    if not token:
        return value
    if isinstance(value, str):
        return value.replace(token, "[redacted]")
    if isinstance(value, dict):
        return {_redact(k, token): _redact(v, token) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v, token) for v in value]
    return value


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1)], 2)


def run(base_url: str, *, profile: str, duration: float, sessions: int,
        interval: float, seed: str, rate: float = 0.0, waves: int = 1,
        token: str | None = None, env: dict | None = None,
        tolerate_limit_rejections: bool = False) -> dict:
    base_url = validate_target(base_url, env)
    if not (math.isfinite(duration) and math.isfinite(interval) and duration > 0 and interval > 0):
        raise ValueError("duration and interval must be finite and positive")
    if profile == "constant" and not 0 < rate <= MAX_RATE:
        raise ValueError(f"constant profile requires 0 < rate <= {MAX_RATE}")
    before_status, before, _ = _json(base_url + "/metrics", token=token)
    if before_status != 200:
        raise RuntimeError("The metrics endpoint is unavailable")
    started = time.monotonic()

    def post(conversation_id: str, key: str):
        return _json(base_url + "/v1/executions",
                     body={"message": "Consulta sintética", "conversation_id": conversation_id},
                     key=key, token=token)

    def session(index: int) -> list[tuple[int, dict, float]]:
        results = []
        turn = 0
        while True:
            if profile == "burst" and turn >= waves:
                break
            if profile == "sessions" and turn > 0 and time.monotonic() - started >= duration:
                break
            if profile == "burst" and turn > 0:
                time.sleep(max(0, started + turn * interval - time.monotonic()))
            results.append(post(f"e3-load-{seed}-{index}", f"e3-load-{seed}-{index}-{turn}"))
            turn += 1
            if profile == "sessions":
                time.sleep(max(0, started + turn * interval - time.monotonic()))
        return results

    def scheduled(number: int, due: float) -> tuple[int, dict, float]:
        # Latency counts from the scheduled time so queueing is not hidden.
        status, body, _ = post(f"e3-load-{seed}-c{number}", f"e3-load-{seed}-c{number}-0")
        return status, body, (time.monotonic() - due) * 1000

    if profile == "constant":
        total = max(1, int(duration * rate))
        with ThreadPoolExecutor(max_workers=sessions) as pool:
            futures = []
            for number in range(total):
                due = started + number / rate
                time.sleep(max(0, due - time.monotonic()))
                futures.append(pool.submit(scheduled, number, due))
            rows = [future.result() for future in futures]
    else:
        with ThreadPoolExecutor(max_workers=sessions) as pool:
            rows = [row for batch in pool.map(session, range(sessions)) for row in batch]
    elapsed = round(time.monotonic() - started, 3)
    after_status, after, _ = _json(base_url + "/metrics", token=token)
    if after_status != 200:
        raise RuntimeError("Metrics endpoint failed after the campaign")
    ok = [body for status, body, _ in rows if status == 200]
    # Un 200 sin el contrato (ids y revisión entera) no cuenta como éxito.
    successes = [body for body in ok if isinstance(body, dict) and body.get("execution_id")
                 and body.get("conversation_id") and type(body.get("revision")) is int]
    malformed = len(ok) - len(successes)
    ids = [body.get("execution_id") for body in successes]
    revisions: dict[str, list[int]] = {}
    for body in successes:
        revisions.setdefault(body.get("conversation_id", ""), []).append(body.get("revision"))
    consistent = all(sorted(values) == list(range(1, len(values) + 1))
                     for values in revisions.values())
    latencies = [latency for _, _, latency in rows]
    rejections = sum(status in LIMIT_STATUSES for status, _, _ in rows)
    errors = sum(status not in LIMIT_STATUSES and status != 200 for status, _, _ in rows) + malformed
    clean = bool(successes) and errors == 0 and (rejections == 0 or tolerate_limit_rejections)
    return {
        "status": "passed" if clean and len(ids) == len(set(ids)) and consistent else "failed",
        "remote": urlsplit(base_url).hostname not in LOOPBACK,
        "authenticated": bool(token),
        "limit_rejections": rejections,
        "errors": errors,
        "success_count": len(successes),
        "rate_target_rps": rate if profile == "constant" else None,
        "waves": waves if profile == "burst" else None,
        "gate_closed": False,
        "synthetic": True,
        "started_at": datetime.now(UTC).isoformat(),
        "profile": profile,
        "seed": seed,
        "sessions": sessions,
        "interval_seconds": interval if profile in {"sessions", "burst"} else None,
        "duration_target_seconds": duration if profile in {"sessions", "constant"} else None,
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
        "metrics_before": _redact(before, token),
        "metrics_after": _redact(after, token),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--profile", choices=("sessions", "burst", "constant"), required=True)
    parser.add_argument("--duration", type=float, default=600)
    parser.add_argument("--sessions", type=int, default=80)
    parser.add_argument("--interval", type=float, default=15)
    parser.add_argument("--rate", type=float, default=0.0, help="requests/second (constant)")
    parser.add_argument("--waves", type=int, default=1, help="burst repetitions, spaced by --interval")
    parser.add_argument("--tolerate-limit-rejections", action="store_true")
    parser.add_argument("--seed", default="local")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not (math.isfinite(args.duration) and math.isfinite(args.interval)
            and math.isfinite(args.rate)):
        parser.error("duration, interval and rate must be finite")
    if args.sessions < 1 or args.sessions > 80 or args.duration <= 0 or args.interval <= 0:
        parser.error("sessions must be 1..80 and duration/interval must be positive")
    if args.waves < 1 or args.waves > 1000:
        parser.error("waves must be 1..1000")
    try:
        result = run(args.url, profile=args.profile, duration=args.duration,
                     sessions=args.sessions, interval=args.interval, seed=args.seed,
                     rate=args.rate, waves=args.waves,
                     token=os.environ.get("INCUBIA_E3_PROBE_TOKEN") or None,
                     tolerate_limit_rejections=args.tolerate_limit_rejections)
    except (ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("status", "profile", "requests", "duration_observed_seconds")}))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
