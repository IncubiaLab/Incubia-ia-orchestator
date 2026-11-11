"""Separate bounded PostgreSQL pools per trusted Knowledge deployment."""
from contextlib import contextmanager
from threading import Lock
from time import monotonic
from typing import Callable

from psycopg_pool import ConnectionPool, PoolTimeout


class KnowledgePools:
    def __init__(self, resolve_dsn: Callable[[str], str], *, max_size: int = 4,
                 metrics=None):
        if max_size < 1:
            raise ValueError("Pool max_size must be positive")
        self._resolve_dsn, self._max_size = resolve_dsn, max_size
        self._pools: dict[str, ConnectionPool] = {}
        self._lock = Lock()
        self._metrics = metrics

    def _report_stats(self, pool: ConnectionPool) -> None:
        if self._metrics is None:
            return
        try:
            stats = pool.get_stats()
            size = stats.get("pool_size", 0)
            self._metrics.pool_stats(in_use=max(0, size - stats.get("pool_available", 0)),
                                     max_size=self._max_size,
                                     waiting=stats.get("requests_waiting", 0))
        except Exception:
            pass

    def _report_wait(self, elapsed_ms: float, *, timed_out: bool) -> None:
        if self._metrics is not None:
            try:
                self._metrics.pool_wait(elapsed_ms, timed_out=timed_out)
            except Exception:
                pass

    @contextmanager
    def connection(self, deployment_id: str):
        if not deployment_id:
            raise ValueError("Trusted deployment ID required")
        with self._lock:
            pool = self._pools.get(deployment_id)
            if pool is None:
                dsn = self._resolve_dsn(deployment_id)
                if not dsn:
                    raise ValueError("Unknown Knowledge deployment")
                pool = ConnectionPool(dsn, min_size=1, max_size=self._max_size,
                                      kwargs={"connect_timeout": 3}, timeout=3, open=True)
                self._pools[deployment_id] = pool
        self._report_stats(pool)
        started = monotonic()
        acquired = False
        try:
            with pool.connection() as connection:
                acquired = True
                self._report_wait((monotonic() - started) * 1000, timed_out=False)
                self._report_stats(pool)
                yield connection
        except PoolTimeout:
            if not acquired:
                self._report_wait((monotonic() - started) * 1000, timed_out=True)
            raise
        finally:
            self._report_stats(pool)

    def warm(self) -> None:
        with self._lock:
            pools = tuple(self._pools.values())
        for pool in pools:
            pool.wait(timeout=10)

    def close(self) -> None:
        with self._lock:
            pools = tuple(self._pools.values())
            self._pools.clear()
        for pool in pools:
            pool.close()
