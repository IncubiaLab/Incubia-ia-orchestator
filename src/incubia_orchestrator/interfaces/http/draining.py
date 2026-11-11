"""Threading HTTP server that drains in-flight requests on close, with a bound."""
from __future__ import annotations

import logging
import threading
from http.server import ThreadingHTTPServer
from time import monotonic

LOG = logging.getLogger(__name__)
DEFAULT_DRAIN_SECONDS = 10.0


class DrainingHTTPServer(ThreadingHTTPServer):
    # Daemon threads so a client that stopped reading cannot hold the process
    # past the drain deadline; server_close() still waits for them up to it.
    daemon_threads = True
    drain_seconds = DEFAULT_DRAIN_SECONDS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._inflight: set[threading.Thread] = set()
        self._inflight_lock = threading.Lock()

    def process_request_thread(self, request, client_address):
        current = threading.current_thread()
        with self._inflight_lock:
            self._inflight.add(current)
        try:
            super().process_request_thread(request, client_address)
        finally:
            with self._inflight_lock:
                self._inflight.discard(current)

    def server_close(self):
        super().server_close()
        deadline = monotonic() + self.drain_seconds
        with self._inflight_lock:
            pending = list(self._inflight)
        for thread in pending:
            thread.join(max(0.0, deadline - monotonic()))
        with self._inflight_lock:
            abandoned = len(self._inflight)
        if abandoned:
            LOG.warning("http_drain_abandoned=%s", abandoned)
