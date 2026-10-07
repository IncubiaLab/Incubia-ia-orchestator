"""Pilot-only Telegram runner. Secrets are read from the environment."""
import argparse
import os
import sys
from pathlib import Path

import yaml

from incubia_orchestrator.modules.conversation.adapters.channels.telegram.client import TelegramClient, TelegramTransportError
from incubia_orchestrator.modules.conversation.adapters.channels.telegram.runner import TelegramRunner
from incubia_orchestrator.modules.conversation.adapters.persistence.sqlite_ledger import RunnerAlreadyActive, SqliteLedger


def _load_telegram_env():
    path = Path(os.getenv("INCUBIA_ENV_FILE", ".env"))
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("TELEGRAM_BOT_TOKEN="):
            os.environ.setdefault("TELEGRAM_BOT_TOKEN", line.split("=", 1)[1].strip().strip("\"'"))


def _load_bindings(path: Path):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("contract_version") != 1 or not isinstance(data.get("bindings"), list):
        raise ValueError("Invalid bindings configuration")
    if len(data["bindings"]) != 2:
        raise ValueError("Pilot requires exactly two bindings")
    required = {"channel", "channel_account_ref", "external_chat_ref", "external_sender_ref",
                "deployment_id", "tenant_id", "conversation_id", "actor_id"}
    rows = data["bindings"]
    if any(not isinstance(row, dict) or set(row) != required or row["channel"] != "telegram" for row in rows):
        raise ValueError("Invalid binding fields")
    if len({row["tenant_id"] for row in rows}) != 2 or len({(row["external_chat_ref"], row["external_sender_ref"]) for row in rows}) != 2:
        raise ValueError("Pilot bindings must use distinct tenants and participants")
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(prog="incubia-bot")
    parser.add_argument("command", choices=("run", "inspect"))
    parser.add_argument("--db", type=Path, default=Path.home() / ".local/state/incubia/e2.sqlite3")
    parser.add_argument("--bindings", type=Path)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    try:
        _load_telegram_env()
        ledger = SqliteLedger(args.db, acquire_runner_lock=args.command == "run")
        try:
            if args.command == "inspect":
                pending = ledger.inspect()
                print(f"events_needing_inspection={len(pending['events'])} deliveries_unknown={len(pending['deliveries'])}")
                return 0
            token = os.getenv("TELEGRAM_BOT_TOKEN", "")
            if not token:
                raise ValueError("TELEGRAM_BOT_TOKEN is required")
            if args.bindings is None:
                raise ValueError("--bindings is required")
            rows = _load_bindings(args.bindings)
            account = rows[0]["channel_account_ref"]
            if any(row["channel_account_ref"] != account for row in rows):
                raise ValueError("Both bindings must belong to one bot")
            from incubia_orchestrator.modules.orchestration.application.router import route
            def fake_generation(text, scope):
                from types import SimpleNamespace
                specialty = route(text).specialty
                return SimpleNamespace(text=f"[fake:{specialty.value}] Recibido: " + text[:500], specialty=specialty)
            runner = TelegramRunner(ledger, TelegramClient(token), account=account, generate=fake_generation)
            runner.preflight()
            for row in rows:
                ledger.add_binding(channel=row["channel"], account=row["channel_account_ref"],
                                   chat=row["external_chat_ref"], sender=row["external_sender_ref"],
                                   deployment_id=row["deployment_id"], tenant_id=row["tenant_id"],
                                   conversation_id=row["conversation_id"], actor_id=row["actor_id"])
            ledger.recover()
            while True:
                runner.cycle()
                if args.once:
                    return 0
        finally:
            ledger.close()
    except (ValueError, RuntimeError, OSError, RunnerAlreadyActive, TelegramTransportError) as error:
        print(f"bot_error={type(error).__name__}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
