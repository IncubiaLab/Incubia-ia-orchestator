"""Separate bounded PostgreSQL pools per trusted Knowledge deployment."""
from threading import Lock
from typing import Callable

from psycopg_pool import ConnectionPool


class KnowledgePools:
    def __init__(self, resolve_dsn: Callable[[str], str], *, max_size: int = 4):
        if max_size < 1:
            raise ValueError("Pool max_size must be positive")
        self._resolve_dsn, self._max_size = resolve_dsn, max_size
        self._pools: dict[str, ConnectionPool] = {}
        self._lock = Lock()

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
        return pool.connection()

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
