"""Telegram long-polling runner wired to the application composition root."""
import argparse
import os
import sys
from pathlib import Path

import yaml

from incubia_orchestrator.modules.conversation.adapters.channels.telegram.client import TelegramClient, TelegramTransportError
from incubia_orchestrator.modules.conversation.adapters.channels.telegram.inbound import normalize_update
from incubia_orchestrator.modules.conversation.adapters.channels.telegram.runner import TelegramRunner
from incubia_orchestrator.modules.conversation.adapters.persistence.sqlite_ledger import RunnerAlreadyActive, SqliteLedger


def _load_telegram_env():
    path = Path(os.getenv("INCUBIA_ENV_FILE", ".env"))
    if not path.is_file():
        return
    supported = {"TELEGRAM_BOT_TOKEN", "OPENAI_API_KEY", "INCUBIA_MODEL", "INCUBIA_BUDGET_FILE",
                 "INCUBIA_TELEGRAM_DEPLOYMENT_ID", "INCUBIA_TELEGRAM_TENANT_ID"}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() in supported:
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def _load_bindings(path: Path):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("contract_version") != 1 or not isinstance(data.get("bindings"), list):
        raise ValueError("Invalid bindings configuration")
    if not data["bindings"]:
        raise ValueError("At least one Telegram binding is required")
    required = {"channel", "channel_account_ref", "external_chat_ref", "external_sender_ref",
                "deployment_id", "tenant_id", "conversation_id", "actor_id"}
    rows = data["bindings"]
    normalized = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != required or row["channel"] != "telegram":
            raise ValueError("Invalid binding fields")
        values = dict(row)
        for field in ("channel_account_ref", "external_chat_ref", "external_sender_ref"):
            value = values[field]
            if isinstance(value, bool) or not isinstance(value, (str, int)) or not str(value).strip():
                raise ValueError("Invalid binding fields")
            values[field] = str(value)
        if any(not isinstance(values[field], str) or not values[field].strip()
               for field in required - {"channel", "channel_account_ref", "external_chat_ref", "external_sender_ref"}):
            raise ValueError("Invalid binding fields")
        normalized.append(values)
    rows = normalized
    identities = [(row["channel_account_ref"], row["external_chat_ref"], row["external_sender_ref"]) for row in rows]
    if len(set(identities)) != len(identities):
        raise ValueError("Telegram bindings must be unique")
    return rows


def _resolve_account(rows, bot_id: int):
    account = str(bot_id)
    resolved = []
    for row in rows:
        configured = row["channel_account_ref"]
        if configured not in {"auto", account}:
            raise ValueError("Binding channel_account_ref does not match the configured Telegram bot")
        resolved.append({**row, "channel_account_ref": account})
    return account, resolved


def main(argv=None):
    parser = argparse.ArgumentParser(prog="incubia-bot")
    parser.add_argument("command", choices=("run", "inspect", "discover"))
    parser.add_argument("--db", type=Path,
                        default=Path(os.getenv("INCUBIA_TELEGRAM_DB", str(Path.home() / ".local/state/incubia/telegram.sqlite3"))))
    parser.add_argument("--bindings", type=Path)
    parser.add_argument("--multi-session", action="store_true",
                        help="Create an isolated session for each new private chat")
    parser.add_argument("--deployment-id",
                        default=os.getenv("INCUBIA_TELEGRAM_DEPLOYMENT_ID", "incubia-telegram"))
    parser.add_argument("--tenant-id",
                        default=os.getenv("INCUBIA_TELEGRAM_TENANT_ID", "telegram-users"))
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--fake", action="store_true", help="Use the deterministic local model")
    parser.add_argument("--model", help="Override INCUBIA_MODEL for real generation")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--max-output-tokens", type=int, default=128)
    parser.add_argument("--history-limit", type=int, default=2)
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
            if args.command == "discover":
                updates = TelegramClient(token).get_updates()
                found = 0
                for update in updates:
                    inbound = normalize_update(update, "discovery")
                    if inbound is None:
                        continue
                    found += 1
                    print(f"chat_id={inbound.external_chat_ref} sender_id={inbound.external_sender_ref}")
                if not found:
                    print("No hay mensajes privados de texto pendientes. Envía /start al bot y repite discover.")
                return 0
            if args.bindings is None and not args.multi_session:
                raise ValueError("--bindings is required")
            rows = _load_bindings(args.bindings) if args.bindings is not None else []
            client = TelegramClient(token)
            account, rows = _resolve_account(rows, client.get_me().get("id"))
            from incubia_orchestrator.bootstrap.composition import compose_scoped
            generation = compose_scoped(fake=args.fake, model=args.model,
                                        max_output_tokens=args.max_output_tokens,
                                        timeout=args.timeout)
            bind_unknown = None
            if args.multi_session:
                if not args.deployment_id.strip() or not args.tenant_id.strip():
                    raise ValueError("--deployment-id and --tenant-id must be non-empty")

                def bind_unknown(inbound):
                    conversation_id = "telegram-chat-" + inbound.external_chat_ref
                    actor_id = "telegram-user-" + inbound.external_sender_ref
                    binding = (args.deployment_id, args.tenant_id, conversation_id, actor_id)
                    ledger.add_binding(channel="telegram", account=account,
                                       chat=inbound.external_chat_ref,
                                       sender=inbound.external_sender_ref,
                                       deployment_id=binding[0], tenant_id=binding[1],
                                       conversation_id=binding[2], actor_id=binding[3])
                    return binding

            runner = TelegramRunner(ledger, client, account=account, generate=generation,
                                    history_limit=args.history_limit, bind_unknown=bind_unknown)
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
        print(f"bot_error={type(error).__name__} detail={error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
