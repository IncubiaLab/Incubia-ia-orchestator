"""Product-owned, JSON-compatible execution contract."""
from dataclasses import asdict, dataclass
from typing import Literal, TypeAlias


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
class ExecutionOutput:
    text: str
    kind: Literal["message", "policy_denied"] = "message"


@dataclass(frozen=True)
class ExecutionError:
    code: str
    message: str


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
            return CompletedExecution(*ids, ExecutionOutput(**data["output"]))
        case "suspended":
            return SuspendedExecution(*ids, data["continuation_id"])
        case "failed":
            return FailedExecution(*ids, ExecutionError(**data["error"]))
        case _:
            raise ValueError("Unknown execution status")
