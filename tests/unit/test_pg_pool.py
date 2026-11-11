"""Pooled connections must never carry tenant scope between transactions."""
from contextlib import contextmanager

import pytest

from incubia_orchestrator.foundation.contracts.execution import ExecutionScope
from incubia_orchestrator.foundation.pg_pool import PooledConnections
from incubia_orchestrator.modules.conversation.adapters.persistence.postgres import PostgresLedger


class FakeConnection:
    """Emulates Postgres: set_config(..., true) lives only until transaction end."""

    def __init__(self):
        self.local: dict[str, str] = {}
        self.in_tx = False
        self.seen: list[dict] = []

    @contextmanager
    def transaction(self):
        self.in_tx, self.local = True, {}
        try:
            yield
        finally:
            self.in_tx, self.local = False, {}  # COMMIT/ROLLBACK drops local settings

    @contextmanager
    def cursor(self):
        yield self

    def execute(self, sql, params=()):
        if "set_config" in sql:
            assert self.in_tx and "true)" in sql  # transaction-local only
            names = ["app.deployment_id", "app.tenant_id"][: len(params)]
            self.local.update(zip(names, params))
        else:
            self.seen.append(dict(self.local))

    def fetchone(self):
        return None


class FakePool:
    def __init__(self, connection):
        self.connection_obj, self.closed, self.waits = connection, False, 0

    @contextmanager
    def connection(self):
        yield self.connection_obj

    def get_stats(self):
        return {"pool_size": 1, "pool_available": 0, "requests_waiting": 0}

    def close(self):
        self.closed = True


class Metrics:
    def __init__(self):
        self.stats, self.waits = [], []

    def pool_stats(self, **kw):
        self.stats.append(kw)

    def pool_wait(self, ms, *, timed_out=False):
        self.waits.append(timed_out)


def _scope(tenant):
    return ExecutionScope("d", tenant, "c", "a")


def test_reused_connection_does_not_keep_previous_tenant_scope():
    conn = FakeConnection()
    ledger = PostgresLedger("postgresql://x", pool=PooledConnections(
        "postgresql://x", max_size=1, pool=FakePool(conn)))
    with ledger._transaction(_scope("tenant-a")) as c:
        c.execute("SELECT 1")
    with ledger._transaction() as c:  # unscoped: must see no tenant at all
        c.execute("SELECT 1")
    with ledger._transaction(_scope("tenant-b")) as c:
        c.execute("SELECT 1")
    assert conn.seen == [
        {"app.deployment_id": "d", "app.tenant_id": "tenant-a"},
        {},
        {"app.deployment_id": "d", "app.tenant_id": "tenant-b"},
    ]


def test_scope_is_dropped_even_when_the_transaction_fails():
    conn = FakeConnection()
    ledger = PostgresLedger("postgresql://x", pool=PooledConnections(
        "postgresql://x", max_size=1, pool=FakePool(conn)))
    with pytest.raises(RuntimeError):
        with ledger._transaction(_scope("tenant-a")):
            raise RuntimeError("boom")
    assert conn.local == {} and not conn.in_tx


def test_pool_metrics_and_close():
    metrics, fake = Metrics(), FakePool(FakeConnection())
    pool = PooledConnections("postgresql://x", max_size=4, pool=fake, metrics=metrics)
    with pool.connection():
        pass
    assert metrics.waits == [False] and metrics.stats[0]["max_size"] == 4
    pool.close()
    assert fake.closed


def test_pool_timeout_is_reported_and_raised():
    class PoolTimeout(Exception):
        pass

    class Failing(FakePool):
        @contextmanager
        def connection(self):
            raise PoolTimeout()
            yield

    metrics = Metrics()
    pool = PooledConnections("postgresql://x", max_size=1, pool=Failing(None), metrics=metrics)
    with pytest.raises(PoolTimeout):
        with pool.connection():
            pass
    assert metrics.waits == [True]


def test_pool_rejects_bad_sizes():
    with pytest.raises(ValueError):
        PooledConnections("postgresql://x", max_size=0, pool=object())


def test_unpooled_path_is_unchanged(monkeypatch):
    conn = FakeConnection()
    conn.close = lambda: setattr(conn, "closed", True)

    class Driver:
        @staticmethod
        def connect(url, **kw):
            return conn

    monkeypatch.setattr(PostgresLedger, "_driver", staticmethod(lambda: Driver))
    with PostgresLedger("postgresql://x")._transaction(_scope("t")) as c:
        c.execute("SELECT 1")
    assert conn.closed and conn.seen == [{"app.deployment_id": "d", "app.tenant_id": "t"}]
