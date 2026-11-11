"""Local administrative commands for H2 memberships and channel bindings.

The command operates on the protected SQLite control-plane file. It is not an
HTTP administration endpoint and must not be exposed as a public service.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from incubia_orchestrator.modules.conversation.adapters.persistence.sqlite_ledger import SqliteLedger
from incubia_orchestrator.modules.identity_tenant.domain.principal import Role


def _required(parser: argparse.ArgumentParser, *names: str) -> None:
    for name in names:
        parser.add_argument(name, required=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="incubia-tenant")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(os.getenv(
            "INCUBIA_TELEGRAM_DB",
            str(Path.home() / ".local/state/incubia/telegram.sqlite3"),
        )),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    membership = commands.add_parser("membership")
    membership_commands = membership.add_subparsers(dest="operation", required=True)
    upsert = membership_commands.add_parser("upsert")
    _required(upsert, "--deployment-id", "--tenant-id", "--subject-id")
    upsert.add_argument("--role", choices=tuple(role.value for role in Role), default=Role.ACTOR.value)
    revoke = membership_commands.add_parser("revoke")
    _required(revoke, "--deployment-id", "--tenant-id", "--subject-id")

    binding = commands.add_parser("binding")
    binding_commands = binding.add_subparsers(dest="operation", required=True)
    bind = binding_commands.add_parser("upsert")
    _required(
        bind, "--channel", "--account", "--chat", "--sender", "--deployment-id",
        "--tenant-id", "--conversation-id", "--actor-id",
    )
    bind.add_argument("--role", choices=tuple(role.value for role in Role), default=Role.ACTOR.value)
    unbind = binding_commands.add_parser("revoke")
    _required(unbind, "--channel", "--account", "--chat", "--sender")
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    ledger = SqliteLedger(args.db)
    try:
        if args.command == "membership":
            if args.operation == "upsert":
                membership = ledger.upsert_membership(
                    deployment_id=args.deployment_id,
                    tenant_id=args.tenant_id,
                    subject_id=args.subject_id,
                    role=Role(args.role),
                )
                print(
                    f"membership=active deployment={membership.deployment_id} "
                    f"tenant={membership.tenant_id} subject={membership.subject_id} "
                    f"role={membership.role.value}"
                )
                return 0
            changed = ledger.revoke_membership(
                deployment_id=args.deployment_id,
                tenant_id=args.tenant_id,
                subject_id=args.subject_id,
            )
            print(f"membership={'revoked' if changed else 'unchanged'}")
            return 0

        if args.operation == "upsert":
            ledger.add_binding(
                channel=args.channel,
                account=args.account,
                chat=args.chat,
                sender=args.sender,
                deployment_id=args.deployment_id,
                tenant_id=args.tenant_id,
                conversation_id=args.conversation_id,
                actor_id=args.actor_id,
            )
            ledger.upsert_membership(
                deployment_id=args.deployment_id,
                tenant_id=args.tenant_id,
                subject_id=args.actor_id,
                role=Role(args.role),
            )
            print("binding=active membership=active")
            return 0
        changed = ledger.revoke_binding(
            channel=args.channel, account=args.account,
            chat=args.chat, sender=args.sender,
        )
        print(f"binding={'revoked' if changed else 'unchanged'}")
        return 0
    finally:
        ledger.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
