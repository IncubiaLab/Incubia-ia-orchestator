import os
import socket
import subprocess
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args, input_text=None, api_key=None):
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    if api_key is not None:
        env["OPENAI_API_KEY"] = api_key
    env["PYTHONPATH"] = str(ROOT / "tests" / "no_network")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run([sys.executable, "-m", "incubia_orchestrator.interfaces.cli.main", "chat", *args],
                          input=input_text, capture_output=True, text=True, env=env, timeout=15)


def test_network_block_is_active_in_parent_and_subprocess():
    with pytest.raises(AssertionError, match="Network access"):
        socket.create_connection(("127.0.0.1", 1))
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "tests" / "no_network")
    result = subprocess.run([sys.executable, "-c", "import socket; socket.create_connection(('127.0.0.1', 1))"],
                            env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert "Network access is disabled" in result.stderr


def test_three_turn_repl_and_commands():
    result = run_cli("--fake", input_text="/help\nquiero vender\nnecesito una campaña\nhola\n/exit\n")
    assert result.returncode == 0
    assert "Comandos: /help, /exit" in result.stdout
    assert "especialista en ventas" in result.stdout
    assert "especialista en marketing" in result.stdout
    assert "especialista en general" in result.stdout
    assert result.stderr.count("request_id=") == 3
    assert "specialty=ventas" in result.stderr


def test_no_key_and_invalid_input_are_safe():
    result = run_cli("-m", "hola")
    assert result.returncode == 2
    assert "OPENAI_API_KEY" in result.stderr
    result = run_cli("--fake", "-m", "")
    assert result.returncode == 2
    assert "Entrada inválida" in result.stderr


def test_canaries_stay_out_of_diagnostics():
    secret = "secret-canary-8342"
    content = "content-canary-4811"
    result = run_cli("--fake", "-m", content, api_key=secret)
    assert result.returncode == 0
    assert content in result.stdout
    assert content not in result.stderr
    assert secret not in result.stdout + result.stderr
