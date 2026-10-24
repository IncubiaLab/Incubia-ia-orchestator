"""Shared bounded PostgreSQL connection pool for the D0 hot path (E3-5).

Opening a TLS connection per transaction dominated latency against Neon. The
pool keeps connections warm; tenant scope is NEVER session state: callers set
it with ``set_config(..., true)`` inside their own transaction, so it vanishes
at COMMIT/ROLLBACK and a reused connection cannot carry a previous scope
(also required by pgbouncer transaction mode, hence no prepared statements).
"""
from __future__ import annotations

from contextlib import contextmanager
from time import monotonic
from typing import Any


class PooledConnections:
    def __init__(self, dsn: str, *, max_size: int, min_size: int = 1, timeout: float = 3.0,
                 connect_timeout: int = 3, max_lifetime: float = 300.0,
                 max_idle: float = 30.0, metrics: Any = None, pool: Any = None):
        if not dsn:
            raise ValueError("DATABASE_URL is required")
        if max_size < 1 or min_size < 1 or min_size > max_size:
            raise ValueError("Pool sizes must satisfy 1 <= min_size <= max_size")
        self.dsn, self.max_size, self.metrics = dsn, max_size, metrics
        if pool is None:
            from psycopg_pool import ConnectionPool
            pool = ConnectionPool(
                dsn, min_size=min_size, max_size=max_size, timeout=timeout,
                max_lifetime=max_lifetime, max_idle=max_idle, open=False,
                # pgbouncer transaction mode: no server-side prepared statements.
                kwargs={"connect_timeout": connect_timeout, "prepare_threshold": None},
            )
            pool.open()
        self._pool = pool

    def set_metrics(self, metrics: Any) -> None:
        self.metrics = metrics

    def _report(self, call: str, *args, **kwargs) -> None:
        if self.metrics is None:
            return
        try:
            getattr(self.metrics, call)(*args, **kwargs)
        except Exception:
            pass

    def _stats(self) -> None:
        if self.metrics is None:
            return
        try:
            stats = self._pool.get_stats()
            size = stats.get("pool_size", 0)
            self._report("pool_stats", in_use=max(0, size - stats.get("pool_available", 0)),
                         max_size=self.max_size, waiting=stats.get("requests_waiting", 0))
        except Exception:
            pass

    @contextmanager
    def connection(self):
        """Yield a pooled connection; it is rolled back/reset by the pool on return."""
        started, acquired = monotonic(), False
        self._stats()
        try:
            with self._pool.connection() as connection:
                acquired = True
                self._report("pool_wait", (monotonic() - started) * 1000, timed_out=False)
                self._stats()
                yield connection
        except Exception as exc:
            if not acquired and type(exc).__name__ == "PoolTimeout":
                self._report("pool_wait", (monotonic() - started) * 1000, timed_out=True)
            raise
        finally:
            self._stats()

    def close(self) -> None:
        self._pool.close()
