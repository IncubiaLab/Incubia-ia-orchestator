import os
import socket
import subprocess
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args, input_text=None, api_key=None, log_file=None):
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    if api_key is not None:
        env["OPENAI_API_KEY"] = api_key
    env["PYTHONPATH"] = str(ROOT / "tests" / "no_network")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["INCUBIA_ENV_FILE"] = str(ROOT / "tests" / "no_network" / "missing.env")
    env["INCUBIA_LOG_FILE"] = str(log_file) if log_file else os.devnull
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
    assert "[Sales.specialist]:" in result.stdout
    assert "[Marketing.specialist]:" in result.stdout
    assert "[General.specialist]:" in result.stdout
    assert "especialista en ventas" in result.stdout
    assert "especialista en marketing" in result.stdout
    assert "especialista en general" in result.stdout
    assert result.stderr == ""


def test_metrics_are_written_to_a_separate_log(tmp_path):
    log_file = tmp_path / "logs" / "incubia-cli.log"
    result = run_cli("--fake", "-m", "hola", log_file=log_file)
    assert result.returncode == 0
    assert result.stderr == ""
    event = __import__("json").loads(log_file.read_text(encoding="utf-8"))
    assert event["status"] == "completed"
    assert event["specialty"] == "general"
    assert event["input_tokens"] is None


def test_no_key_and_invalid_input_are_safe():
    result = run_cli("-m", "hola")
    assert result.returncode == 2
    assert "OPENAI_API_KEY" in result.stderr
    result = run_cli("--fake", "-m", "")
    assert result.returncode == 2
    assert "Entrada inválida" in result.stderr


def test_real_limits_reject_expensive_settings_before_call():
    result = run_cli("--max-output-tokens", "1000", "-m", "hola", api_key="test-key")
    assert result.returncode == 2
    assert "hasta 128 tokens" in result.stderr
    result = run_cli("--retries", "1", "-m", "hola", api_key="test-key")
    assert result.returncode == 2
    assert "cero reintentos" in result.stderr


def test_canaries_stay_out_of_diagnostics():
    secret = "secret-canary-8342"
    content = "content-canary-4811"
    result = run_cli("--fake", "-m", content, api_key=secret)
    assert result.returncode == 0
    assert content in result.stdout
    assert content not in result.stderr
    assert secret not in result.stdout + result.stderr
