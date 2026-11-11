"""Offline parsing tests for the local E3 Neon DSN file."""
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/e3"))
import neon_h1  # noqa: E402


RUNTIME = "postgresql://incubia_runtime:pass%2Fword@ep-test-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require"
MIGRATOR = "postgresql://incubia_migrator:pass%2Fword@ep-test.us-east-2.aws.neon.tech/neondb?sslmode=require"


def test_quote_existing_env_accepts_shell_quoted_dsns(monkeypatch, tmp_path):
    output = tmp_path / "e3-neon.env"
    output.write_text(
        "INCUBIA_E3_NEON_BRANCH=e3-h1-synthetic\n"
        f"DATABASE_URL={shlex.quote(RUNTIME)}\n"
        f"INCUBIA_MIGRATION_DATABASE_URL={shlex.quote(MIGRATOR)}\n"
        "INCUBIA_E3_DB_POOL_MAX=4\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(neon_h1, "OUTPUT", output)

    neon_h1.quote_existing_env()

    written = output.read_text(encoding="utf-8")
    assert "DATABASE_URL=" + shlex.quote(RUNTIME) in written
    assert "INCUBIA_MIGRATION_DATABASE_URL=" + shlex.quote(MIGRATOR) in written
