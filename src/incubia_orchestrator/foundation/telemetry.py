"""Bounded process-local HTTP metrics without request content or dynamic labels."""

from threading import Lock


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

    def started(self) -> None:
        with self._lock:
            self._in_flight += 1
            self._peak_in_flight = max(self._peak_in_flight, self._in_flight)

    def finished(self, status: int, latency_ms: float) -> None:
        with self._lock:
            self._in_flight -= 1
            self._requests += 1
            self._errors += status >= 500
            bucket = next((i for i, bound in enumerate(self.BUCKETS_MS)
                           if latency_ms <= bound), len(self.BUCKETS_MS))
            self._latency_counts[bucket] += 1

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "deployment_id": self.deployment_id,
                "tenant_id": self.tenant_id,
                "requests": self._requests,
                "server_errors": self._errors,
                "in_flight": self._in_flight,
                "peak_in_flight": self._peak_in_flight,
                "latency_ms_buckets": dict(zip(
                    (*self.BUCKETS_MS, "+Inf"), self._latency_counts, strict=True
                )),
            }
