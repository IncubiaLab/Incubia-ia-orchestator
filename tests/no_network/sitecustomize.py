"""Loaded by Python subprocesses when tests/no_network is on PYTHONPATH."""
import socket


def blocked(*args, **kwargs):
    raise AssertionError("Network access is disabled in local tests")


socket.socket.connect = blocked
socket.create_connection = blocked
