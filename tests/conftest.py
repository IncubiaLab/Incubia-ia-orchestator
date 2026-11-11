import os
import socket
from urllib.parse import urlsplit

import pytest


def _explicit_neon_campaign(request):
    if request.node.get_closest_marker("neon") is None:
        return False
    if os.getenv("INCUBIA_E3_NEON_TESTS") != "1":
        return False
    if os.getenv("INCUBIA_E3_NEON_BRANCH") != "e3-h1-synthetic":
        return False
    database_url = os.getenv("DATABASE_URL", "")
    host = urlsplit(database_url).hostname or ""
    return host.endswith(".neon.tech")


@pytest.fixture(autouse=True)
def no_network(monkeypatch, request):
    # Only marked Neon integration cases can use network, and only under the
    # explicit campaign flag plus the dedicated synthetic branch guard. Every
    # ordinary unit/integration test remains offline.
    if _explicit_neon_campaign(request):
        return

    def blocked(*args, **kwargs):
        raise AssertionError("Network access is disabled in local tests")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
