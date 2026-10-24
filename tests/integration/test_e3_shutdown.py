"""E3-12/E3-5: detener en procesamiento/envío conserva estados recuperables.

Automatiza offline el procedimiento manual de
``evals/results/e3-ops-local-2026-10-15.md`` (``docker compose stop app`` y
``start app``). El proceso se simula con un ledger SQLite durable que se
cierra y se reabre; el apagado HTTP reproduce lo que hace el manejador de
SIGTERM de ``interfaces/http/main.py``: ``server.shutdown()`` desde otro hilo
y después ``server_close()``.
"""
import http.client
import json
import socket
import sqlite3
import threading

import httpx
import pytest

from incubia_orchestrator.bootstrap.d0 import D0Deployment, D0Runtime, D0Settings
from incubia_orchestrator.foundation.contracts.execution import CompletedExecution, ExecutionOutput
from incubia_orchestrator.foundation.contracts.specialty import Specialty
from incubia_orchestrator.interfaces.http.main import E3D0HttpServer
from incubia_orchestrator.modules.conversation.adapters.channels.telegram.client import TelegramClient
from incubia_orchestrator.modules.conversation.adapters.channels.telegram.runner import (
    DispatcherAlreadyActive,
    TelegramRunner,
)
from incubia_orchestrator.modules.conversation.adapters.persistence.sqlite_ledger import SqliteLedger

_REAL_CREATE_CONNECTION = socket.create_connection
_REAL_CONNECT = socket.socket.connect


@pytest.fixture(autouse=True)
def loopback_only(no_network, monkeypatch):
    """Sigue offline: solo reabre 127.0.0.1 para el servidor HTTP del test."""

    def create_connection(address, *args, **kwargs):
        if address[0] != "127.0.0.1":
            raise AssertionError("Network access is disabled in local tests")
        return _REAL_CREATE_CONNECTION(address, *args, **kwargs)

    def connect(sock, address):
        if not isinstance(address, tuple) or address[0] != "127.0.0.1":
            raise AssertionError("Network access is disabled in local tests")
        return _REAL_CONNECT(sock, address)

    monkeypatch.setattr(socket, "create_connection", create_connection)
    monkeypatch.setattr(socket.socket, "connect", connect)


SETTINGS = D0Settings("sqlite://unused", "deployment-e3", "tenant-e3", "actor-e3")


class _SimulatedKill(BaseException):
    """Interrumpe el hilo como lo haría la salida del proceso tras SIGTERM.

    Hereda de BaseException para que ningún ``except Exception`` de la ruta
    de aplicación lo convierta en una transición de limpieza: el estado
    durable queda exactamente como lo dejaría un proceso terminado.
    """


class _D0SqliteLedger:
    """Ledger D0 sobre SQLite con una conexión por hilo (ThreadingHTTPServer)."""

    def __init__(self, path):
        self.path = path
        self._local = threading.local()
        self._all = []
        self._lock = threading.Lock()

    def _ledger(self):
        ledger = getattr(self._local, "ledger", None)
        if ledger is None:
            ledger = self._local.ledger = SqliteLedger(self.path)
            with self._lock:
                self._all.append(ledger)
        return ledger

    def __getattr__(self, name):
        return getattr(self._ledger(), name)

    def ready(self):
        return True

    def outcome(self, execution_id, *, scope):
        row = self._ledger()._connection.execute(
            "SELECT o.outcome_json FROM outcomes o JOIN inbox_events e USING (execution_id) "
            "WHERE o.execution_id=? AND e.deployment_id=? AND e.tenant_id=?",
            (execution_id, scope.deployment_id, scope.tenant_id),
        ).fetchone()
        return None if row is None else json.loads(row[0])

    def close(self):
        with self._lock:
            for ledger in self._all:
                try:
                    ledger.close()
                except Exception:
                    pass
            self._all.clear()


class _GatedRuntime:
    """Runtime D0 real que se detiene en PROCESSING hasta que el test lo libera."""

    def __init__(self, *, kill=False):
        self._inner = D0Runtime(SETTINGS)
        self.entered, self.release = threading.Event(), threading.Event()
        self._kill = kill

    def execute(self, **kwargs):
        self.entered.set()
        assert self.release.wait(10)
        if self._kill:
            raise _SimulatedKill()
        return self._inner.execute(**kwargs)


def _state(path, execution_id=None):
    with sqlite3.connect(path) as connection:
        if execution_id is None:
            return [row[0] for row in connection.execute("SELECT state FROM inbox_events")]
        return connection.execute(
            "SELECT state FROM inbox_events WHERE execution_id=?", (execution_id,)
        ).fetchone()[0]


def _expire_leases(path):
    # Equivale a reiniciar después de que venzan los leases del proceso muerto.
    with sqlite3.connect(path) as connection:
        for table in ("resource_claims", "dispatcher_claims"):
            connection.execute(f"UPDATE {table} SET lease_until='1970-01-01T00:00:00+00:00'")


def _start(service):
    server = E3D0HttpServer(("127.0.0.1", 0), service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _sigterm(server, thread):
    # Igual que main.shutdown(): shutdown() fuera del hilo de serve_forever.
    stopper = threading.Thread(target=server.shutdown, daemon=True)
    stopper.start()
    stopper.join(5)
    thread.join(5)
    assert not thread.is_alive()
    server.server_close()


def _post(port, key, message="hola", conversation_id="conv-1", timeout=10):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    body = json.dumps({"message": message, "conversation_id": conversation_id})
    connection.request("POST", "/v1/executions", body=body, headers={
        "Content-Type": "application/json", "Idempotency-Key": key})
    response = connection.getresponse()
    payload = json.loads(response.read())
    connection.close()
    return response.status, payload


def _post_async(port, key, results, **kwargs):
    thread = threading.Thread(target=lambda: results.append(_post(port, key, **kwargs)), daemon=True)
    thread.start()
    return thread


def test_sigterm_drains_in_flight_request_and_replay_survives_restart(tmp_path):
    path = tmp_path / "d0.sqlite"
    ledger, runtime = _D0SqliteLedger(path), _GatedRuntime()
    server, thread = _start(D0Deployment(SETTINGS, ledger, runtime))
    port, results = server.server_address[1], []
    client = _post_async(port, "key-1", results)
    assert runtime.entered.wait(5)
    assert _state(path) == ["PROCESSING"]

    stopper = threading.Thread(target=server.shutdown, daemon=True)
    stopper.start()
    stopper.join(5)
    thread.join(5)
    # El listener ya no acepta trabajo nuevo, pero el request en vuelo sigue.
    assert not thread.is_alive()
    runtime.release.set()
    client.join(10)
    server.server_close()
    ledger.close()
    assert results[0][0] == 200 and results[0][1]["revision"] == 1
    assert _state(path) == ["COMPLETED"]

    restarted = _D0SqliteLedger(path)
    server, thread = _start(D0Deployment(SETTINGS, restarted, D0Runtime(SETTINGS)))
    try:
        status, replay = _post(server.server_address[1], "key-1")
        assert status == 200 and replay["replayed"] is True
        assert replay["execution_id"] == results[0][1]["execution_id"]
        assert replay["revision"] == 1
    finally:
        _sigterm(server, thread)
        restarted.close()


# El hilo del handler muere a propósito (proceso terminado) y el cliente pierde la conexión.
@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_kill_during_processing_leaves_recoverable_state_and_replay_completes_once(tmp_path):
    path = tmp_path / "d0.sqlite"
    ledger, runtime = _D0SqliteLedger(path), _GatedRuntime(kill=True)
    server, thread = _start(D0Deployment(SETTINGS, ledger, runtime))
    results = []
    client = _post_async(server.server_address[1], "key-2", results, timeout=2)
    assert runtime.entered.wait(5)
    # El proceso muere mientras server_close() drena el request en vuelo.
    threading.Timer(0.2, runtime.release.set).start()
    _sigterm(server, thread)
    # El cliente termina cuando el handler muere y cierra el socket: sin sleeps fijos.
    client.join(5)
    assert not client.is_alive()
    ledger.close()
    # Sin respuesta ni commit: no hay efecto externo y el registro sigue PROCESSING.
    assert _state(path) == ["PROCESSING"]

    restarted = _D0SqliteLedger(path)
    service = D0Deployment(SETTINGS, restarted, D0Runtime(SETTINGS))
    # Con el lease del proceso muerto vigente, el arranque no roba el trabajo.
    assert service.recover_interrupted() == 0
    _expire_leases(path)
    assert service.recover_interrupted() == 1
    assert _state(path) == ["RECEIVED"]
    server, thread = _start(service)
    try:
        port = server.server_address[1]
        status, first = _post(port, "key-2")
        assert status == 200 and first["replayed"] is False and first["revision"] == 1
        status, again = _post(port, "key-2")
        assert status == 200 and again["replayed"] is True
        assert again["execution_id"] == first["execution_id"] and again["revision"] == 1
        assert _state(path) == ["COMPLETED"]
    finally:
        _sigterm(server, thread)
        restarted.close()


def test_restart_before_lease_expiry_rejects_retry_without_duplicating(tmp_path):
    path = tmp_path / "d0.sqlite"
    ledger = _D0SqliteLedger(path)
    scope = SETTINGS.scope_for("conv-1")
    reservation = ledger.reserve_inbox(SETTINGS.deployment_id, SETTINGS.tenant_id, SETTINGS.account,
                                       "key-3", {"conversation_id": "conv-1", "message": "hola"},
                                       channel="http")
    assert ledger.claim(reservation.execution_id, scope=scope, owner_id="dead", lease_seconds=120)
    ledger.close()

    restarted = _D0SqliteLedger(path)
    server, thread = _start(D0Deployment(SETTINGS, restarted, D0Runtime(SETTINGS)))
    try:
        status, body = _post(server.server_address[1], "key-3")
        assert status == 409 and body == {"error": "execution_in_progress"}
        assert _state(path, reservation.execution_id) == "PROCESSING"
    finally:
        _sigterm(server, thread)
        restarted.close()


def test_server_close_waits_for_in_flight_requests(tmp_path):
    path = tmp_path / "d0.sqlite"
    ledger, runtime = _D0SqliteLedger(path), _GatedRuntime()
    server, thread = _start(D0Deployment(SETTINGS, ledger, runtime))
    results = []
    client = _post_async(server.server_address[1], "key-4", results)
    assert runtime.entered.wait(5)
    try:
        timer = threading.Timer(0.5, runtime.release.set)
        timer.start()
        _sigterm(server, thread)
        # server_close() sólo retorna tras el commit del handler en vuelo.
        drained = _state(path) == ["COMPLETED"]
    finally:
        runtime.release.set()
        client.join(10)
        ledger.close()
    assert drained
    assert results and results[0][0] == 200


def _update(number, chat, text):
    return {"update_id": number, "message": {"chat": {"id": chat, "type": "private"},
            "from": {"id": chat}, "date": 1, "text": text}}


def _bound_ledger(path):
    ledger = SqliteLedger(path)
    ledger.add_binding(channel="telegram", account="42", chat="7", sender="7",
                       deployment_id="d", tenant_id="t", conversation_id="c", actor_id="a")
    return ledger


def _generate(text, scope, history, request_id, execution_id):
    return CompletedExecution(request_id, execution_id, ExecutionOutput("respuesta " + text, Specialty.GENERAL))


def _client(updates, sent, *, kill_on_send=False):
    def handler(request):
        if request.url.path.endswith("getUpdates"):
            return httpx.Response(200, json={"ok": True, "result": updates})
        if request.url.path.endswith("sendMessage"):
            sent.append(request.read())
            if kill_on_send:
                raise _SimulatedKill()
            return httpx.Response(200, json={"ok": True, "result": {"message_id": len(sent)}})
        raise AssertionError("Unexpected endpoint")
    return TelegramClient("secret", httpx.Client(transport=httpx.MockTransport(handler)))


def _delivery_states(path):
    with sqlite3.connect(path) as connection:
        return [row[0] for row in connection.execute("SELECT state FROM deliveries")]


def test_kill_during_sending_becomes_unknown_effect_and_is_not_retried(tmp_path):
    path = tmp_path / "e3.sqlite"
    ledger, sent = _bound_ledger(path), []
    runner = TelegramRunner(ledger, _client([_update(1, 7, "hola")], sent, kill_on_send=True),
                            account="42", generate=_generate)
    with pytest.raises(_SimulatedKill):
        runner.cycle()
    ledger.close()
    assert len(sent) == 1
    assert _delivery_states(path) == ["SENDING"]
    assert _state(path) == ["COMPLETED"]

    restarted, resent = SqliteLedger(path), []
    restarted.recover()
    assert _delivery_states(path) == ["UNKNOWN_EFFECT"]
    assert len(restarted.inspect()["deliveries"]) == 1
    runner = TelegramRunner(restarted, _client([_update(1, 7, "hola")], resent),
                            account="42", generate=_generate)
    # El dispatcher muerto conserva la cuenta hasta que vence su lease.
    with pytest.raises(DispatcherAlreadyActive):
        runner.cycle()
    _expire_leases(path)
    runner.cycle()
    runner.cycle()
    # Ni el update repetido ni el dispatcher vuelven a enviar un efecto incierto.
    assert resent == []
    assert _delivery_states(path) == ["UNKNOWN_EFFECT"]
    assert _state(path) == ["COMPLETED"]
    restarted.close()


def test_kill_during_telegram_processing_is_retried_after_restart(tmp_path):
    path = tmp_path / "e3.sqlite"
    ledger, sent = _bound_ledger(path), []

    def killed(*_args):
        raise _SimulatedKill()

    with pytest.raises(_SimulatedKill):
        TelegramRunner(ledger, _client([_update(1, 7, "hola")], sent),
                       account="42", generate=killed).cycle()
    ledger.close()
    assert _state(path) == ["PROCESSING"] and _delivery_states(path) == [] and sent == []

    restarted = SqliteLedger(path)
    restarted.recover()
    assert _state(path) == ["PROCESSING"]  # lease vigente: sin robo de trabajo
    _expire_leases(path)
    restarted.recover()
    assert _state(path) == ["RECEIVED"]
    TelegramRunner(restarted, _client([_update(1, 7, "hola")], sent),
                   account="42", generate=_generate).cycle()
    assert len(sent) == 1
    assert _state(path) == ["COMPLETED"] and _delivery_states(path) == ["SENT"]
    restarted.close()
