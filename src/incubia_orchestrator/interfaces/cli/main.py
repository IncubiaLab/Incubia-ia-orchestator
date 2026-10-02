import argparse
import sys
import time
from incubia_orchestrator.bootstrap.composition import compose
from incubia_orchestrator.foundation.contracts.execution import CompletedExecution, FailedExecution
from incubia_orchestrator.modules.orchestration.application.session import ConversationSession


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="incubia")
    commands = parser.add_subparsers(dest="command", required=True)
    chat = commands.add_parser("chat")
    chat.add_argument("--fake", action="store_true")
    chat.add_argument("-m", "--message")
    chat.add_argument("--model")
    chat.add_argument("--max-turns", type=int, default=10)
    chat.add_argument("--max-message-chars", type=int, default=8000)
    chat.add_argument("--max-output-tokens", type=int, default=512)
    chat.add_argument("--timeout", type=float, default=30)
    chat.add_argument("--retries", type=int, default=0)
    args = parser.parse_args(argv)
    try:
        session = ConversationSession(compose(fake=args.fake, model=args.model,
                                              max_output_tokens=args.max_output_tokens,
                                              timeout=args.timeout, retries=args.retries),
                                      args.max_turns, args.max_message_chars)
    except ValueError as exc:
        print(f"Configuración inválida: {exc}", file=sys.stderr)
        return 2

    def send(message):
        started = time.monotonic()
        try:
            outcome = session.send(message)
        except ValueError as exc:
            print(f"Entrada inválida: {exc}", file=sys.stderr)
            return 2
        if isinstance(outcome, CompletedExecution):
            print(outcome.output.text)
            specialty = outcome.output.specialty
            code = 0
        elif isinstance(outcome, FailedExecution):
            print(f"Error: {outcome.error.code}", file=sys.stderr)
            specialty = outcome.error.specialty
            code = 3
        else:
            print("Ejecución suspendida", file=sys.stderr)
            specialty = None
            code = 3
        profile_text = f" specialty={specialty.value}" if specialty else ""
        print(f"request_id={outcome.request_id} status={outcome.status}{profile_text} latency_ms={int((time.monotonic()-started)*1000)}", file=sys.stderr)
        return code

    if args.message is not None:
        return send(args.message)
    try:
        for line in sys.stdin:
            message = line.rstrip("\n")
            if message == "/exit":
                break
            if message == "/help":
                print("Comandos: /help, /exit")
                continue
            if message.startswith("/"):
                print("Comando desconocido", file=sys.stderr)
                continue
            send(message)
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
