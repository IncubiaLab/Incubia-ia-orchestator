"""Product-owned, JSON-compatible execution contract."""
from dataclasses import asdict, dataclass
from typing import Literal, TypeAlias
from incubia_orchestrator.foundation.contracts.specialty import Specialty


@dataclass(frozen=True)
class ExecutionScope:
    deployment_id: str
    tenant_id: str
    conversation_id: str
    actor_id: str


@dataclass(frozen=True)
class ConversationTurn:
    user: str
    assistant: str


@dataclass(frozen=True)
class ExecutionInput:
    content: str
    content_type: Literal["text"] = "text"
    history: tuple[ConversationTurn, ...] = ()


@dataclass(frozen=True)
class StartExecutionRequest:
    request_id: str
    execution_id: str
    scope: ExecutionScope
    input: ExecutionInput


@dataclass(frozen=True)
class ResumeExecutionRequest:
    request_id: str
    execution_id: str
    scope: ExecutionScope
    continuation_id: str


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class ExecutionOutput:
    text: str
    kind: Literal["message", "policy_denied"] = "message"
    specialty: Specialty | None = None
    usage: TokenUsage | None = None


@dataclass(frozen=True)
class ExecutionError:
    code: str
    message: str
    specialty: Specialty | None = None


@dataclass(frozen=True)
class CompletedExecution:
    request_id: str
    execution_id: str
    output: ExecutionOutput
    status: Literal["completed"] = "completed"


@dataclass(frozen=True)
class SuspendedExecution:
    request_id: str
    execution_id: str
    continuation_id: str
    status: Literal["suspended"] = "suspended"


@dataclass(frozen=True)
class FailedExecution:
    request_id: str
    execution_id: str
    error: ExecutionError
    status: Literal["failed"] = "failed"


ExecutionOutcome: TypeAlias = CompletedExecution | SuspendedExecution | FailedExecution


def to_dict(value: StartExecutionRequest | ResumeExecutionRequest | ExecutionOutcome) -> dict:
    return asdict(value)


def request_from_dict(data: dict) -> StartExecutionRequest | ResumeExecutionRequest:
    scope = ExecutionScope(**data["scope"])
    if "continuation_id" in data:
        return ResumeExecutionRequest(data["request_id"], data["execution_id"], scope, data["continuation_id"])
    raw = data["input"]
    input_ = ExecutionInput(raw["content"], raw.get("content_type", "text"),
                            tuple(ConversationTurn(**turn) for turn in raw.get("history", ())))
    return StartExecutionRequest(data["request_id"], data["execution_id"], scope, input_)


def outcome_from_dict(data: dict) -> ExecutionOutcome:
    ids = (data["request_id"], data["execution_id"])
    match data["status"]:
        case "completed":
            output = data["output"]
            usage = TokenUsage(**output["usage"]) if output.get("usage") else None
            return CompletedExecution(*ids, ExecutionOutput(output["text"], output.get("kind", "message"),
                                                       Specialty(output["specialty"]) if output.get("specialty") else None,
                                                       usage))
        case "suspended":
            return SuspendedExecution(*ids, data["continuation_id"])
        case "failed":
            error = data["error"]
            return FailedExecution(*ids, ExecutionError(error["code"], error["message"],
                                                   Specialty(error["specialty"]) if error.get("specialty") else None))
        case _:
            raise ValueError("Unknown execution status")
