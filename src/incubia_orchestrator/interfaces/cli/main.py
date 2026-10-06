import argparse
import sys
import time
from incubia_orchestrator.bootstrap.composition import (
    REAL_MAX_MESSAGE_CHARS, REAL_MAX_OUTPUT_TOKENS, REAL_MAX_TURNS, compose,
)
from incubia_orchestrator.foundation.contracts.execution import CompletedExecution, FailedExecution
from incubia_orchestrator.modules.orchestration.application.session import ConversationSession


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="incubia")
    commands = parser.add_subparsers(dest="command", required=True)
    chat = commands.add_parser("chat")
    chat.add_argument("--fake", action="store_true")
    chat.add_argument("-m", "--message")
    chat.add_argument("--model")
    chat.add_argument("--max-turns", type=int)
    chat.add_argument("--max-message-chars", type=int)
    chat.add_argument("--max-output-tokens", type=int)
    chat.add_argument("--timeout", type=float, default=30)
    chat.add_argument("--retries", type=int, default=0)
    args = parser.parse_args(argv)
    max_turns = args.max_turns if args.max_turns is not None else (10 if args.fake else REAL_MAX_TURNS)
    max_message_chars = args.max_message_chars if args.max_message_chars is not None else (8000 if args.fake else REAL_MAX_MESSAGE_CHARS)
    max_output_tokens = args.max_output_tokens if args.max_output_tokens is not None else (512 if args.fake else REAL_MAX_OUTPUT_TOKENS)
    try:
        if not args.fake and (max_turns > REAL_MAX_TURNS or max_message_chars > REAL_MAX_MESSAGE_CHARS):
            raise ValueError("Límite real: hasta 2 turnos de historial y 500 caracteres por mensaje")
        session = ConversationSession(compose(fake=args.fake, model=args.model,
                                              max_output_tokens=max_output_tokens,
                                              timeout=args.timeout, retries=args.retries),
                                      max_turns, max_message_chars)
    except ValueError as exc:
        print(f"category=config Configuración inválida: {exc}", file=sys.stderr)
        return 2

    def send(message):
        started = time.monotonic()
        try:
            outcome = session.send(message)
        except ValueError as exc:
            print(f"category=input Entrada inválida: {exc}", file=sys.stderr)
            return 2
        if isinstance(outcome, CompletedExecution):
            print(outcome.output.text)
            specialty = outcome.output.specialty
            usage = outcome.output.usage
            code = 0
        elif isinstance(outcome, FailedExecution):
            print(f"Error: {outcome.error.code}", file=sys.stderr)
            specialty = outcome.error.specialty
            usage = None
            category = ("provider" if outcome.error.code.startswith(("PROVIDER_", "EMPTY_RESPONSE"))
                        else "local_limit" if outcome.error.code.startswith("LOCAL_")
                        else "policy" if outcome.error.code.startswith(("POLICY_", "APPROVAL_"))
                        else "runtime")
            code = 3
        else:
            print("Ejecución suspendida", file=sys.stderr)
            specialty = None
            usage = None
            category = "runtime"
            code = 3
        profile_text = f" specialty={specialty.value}" if specialty else ""
        usage_text = f" input_tokens={usage.input_tokens} output_tokens={usage.output_tokens}" if usage else ""
        category_text = f" category={category}" if code else ""
        print(f"request_id={outcome.request_id} status={outcome.status}{profile_text}{category_text} latency_ms={int((time.monotonic()-started)*1000)}{usage_text}", file=sys.stderr)
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
                print("category=input Comando desconocido", file=sys.stderr)
                continue
            send(message)
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
