"""Framework-neutral contracts for governed tools.

Descriptors are discoverable metadata, not grants of authority.  The
application layer must still evaluate policy immediately before execution.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from incubia_orchestrator.foundation.contracts.execution import ExecutionScope


class ToolOperationType(StrEnum):
    READ = "READ"
    MUTATION = "MUTATION"
    EXTERNAL_ACTION = "EXTERNAL_ACTION"


class IdempotencySemantics(StrEnum):
    IDEMPOTENT = "IDEMPOTENT"
    NON_IDEMPOTENT = "NON_IDEMPOTENT"
    IDEMPOTENT_WITH_KEY = "IDEMPOTENT_WITH_KEY"
    UNKNOWN = "UNKNOWN"


class Reversibility(StrEnum):
    REVERSIBLE = "REVERSIBLE"
    IRREVERSIBLE = "IRREVERSIBLE"
    UNKNOWN = "UNKNOWN"


class ToolAvailability(StrEnum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    DEGRADED = "degraded"


class ToolStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    DENIED = "DENIED"


@dataclass(frozen=True)
class ToolError:
    """Safe, product-owned error returned to callers.

    Adapter details, response bodies, credentials and URLs containing secrets
    must never be copied into ``message``.
    """

    code: str
    message: str
    retryable: bool = False


@dataclass(frozen=True)
class ToolDescriptor:
    """Declarative metadata for one version of a tool implementation."""

    tool_id: str
    version: str | int = "1.0"
    capabilities: frozenset[str] = frozenset()
    input_schema: Mapping[str, Any] = field(default_factory=dict)
    output_schema: Mapping[str, Any] = field(default_factory=dict)
    deployment_ids: frozenset[str] = frozenset()
    tenant_ids: frozenset[str] = frozenset()
    availability: ToolAvailability = ToolAvailability.ENABLED
    operation_type: ToolOperationType = ToolOperationType.READ
    idempotency_semantics: IdempotencySemantics = IdempotencySemantics.IDEMPOTENT
    reversibility: Reversibility = Reversibility.REVERSIBLE
    destructive: bool = False
    credential_profile_ref: str | None = None
    adapter_key: str = ""
    priority: int = 0
    input_schema_version: str = "1"
    policy_action: str | None = None

    def __post_init__(self) -> None:
        if not self.tool_id.strip():
            raise ValueError("tool_id is required")
        if not str(self.version).strip():
            raise ValueError("tool version is required")
        if not self.capabilities:
            raise ValueError("at least one tool capability is required")
        if not self.deployment_ids or not self.tenant_ids:
            raise ValueError("tool deployment and tenant scope are required")
        if not self.adapter_key.strip():
            raise ValueError("adapter_key is required")
        if not isinstance(self.availability, ToolAvailability):
            object.__setattr__(self, "availability", ToolAvailability(self.availability))
        if not isinstance(self.operation_type, ToolOperationType):
            object.__setattr__(self, "operation_type", ToolOperationType(self.operation_type))
        if not isinstance(self.idempotency_semantics, IdempotencySemantics):
            object.__setattr__(
                self, "idempotency_semantics", IdempotencySemantics(self.idempotency_semantics)
            )
        if not isinstance(self.reversibility, Reversibility):
            object.__setattr__(self, "reversibility", Reversibility(self.reversibility))
        object.__setattr__(self, "version", str(self.version))
        object.__setattr__(self, "capabilities", frozenset(self.capabilities))
        object.__setattr__(self, "deployment_ids", frozenset(self.deployment_ids))
        object.__setattr__(self, "tenant_ids", frozenset(self.tenant_ids))
        if self.priority < 0:
            raise ValueError("priority cannot be negative")
        if not self.input_schema_version.strip():
            raise ValueError("input_schema_version is required")

    @property
    def tool_version(self) -> str:
        """Compatibility spelling used by the ADR and audit records."""
        return self.version

    def allows_scope(self, scope: ExecutionScope) -> bool:
        return (
            scope.deployment_id in self.deployment_ids
            and scope.tenant_id in self.tenant_ids
        )

    def action(self) -> str:
        return self.policy_action or self.tool_id

    def validate_input(self, value: Mapping[str, Any] | object) -> tuple[str, ...]:
        """Validate the intentionally small JSON-Schema subset used by tools."""
        if not isinstance(value, Mapping):
            return ("INPUT_OBJECT_REQUIRED",)
        schema = self.input_schema
        if not schema:
            return ()
        expected_type = schema.get("type")
        if expected_type not in (None, "object"):
            return ("INPUT_SCHEMA_UNSUPPORTED",)
        required = schema.get("required", ())
        alternatives = schema.get("anyOf") or schema.get("oneOf")
        if alternatives:
            if not any(
                isinstance(option, Mapping)
                and not tuple(key for key in option.get("required", ()) if key not in value)
                for option in alternatives
            ):
                return ("INPUT_ALTERNATIVE_REQUIRED",)
        else:
            missing = tuple(str(key) for key in required if key not in value)
            if missing:
                return ("INPUT_REQUIRED:" + ",".join(sorted(missing)),)
        properties = schema.get("properties", {})
        if not isinstance(properties, Mapping):
            return ("INPUT_SCHEMA_INVALID",)
        if schema.get("additionalProperties") is False:
            unexpected = tuple(sorted(str(key) for key in value if key not in properties))
            if unexpected:
                return ("INPUT_UNEXPECTED:" + ",".join(unexpected),)
        for key, rules in properties.items():
            if key not in value or not isinstance(rules, Mapping):
                continue
            problem = _validate_value(value[key], rules)
            if problem:
                return (f"INPUT_{key.upper()}_{problem}",)
        return ()


def _validate_value(value: object, rules: Mapping[str, Any]) -> str | None:
    expected = rules.get("type")
    valid = {
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "object": isinstance(value, Mapping),
        "array": isinstance(value, (list, tuple)),
    }
    if expected in valid and not valid[expected]:
        return "TYPE"
    if isinstance(value, str) and isinstance(rules.get("maxLength"), int):
        if len(value) > rules["maxLength"]:
            return "TOO_LONG"
    if isinstance(value, str) and rules.get("pattern") == "no-url":
        lowered = value.casefold()
        if "://" in lowered or lowered.startswith(("file:", "gopher:")):
            return "URL_NOT_ALLOWED"
    return None


@dataclass(frozen=True)
class ToolInvocation:
    tool_call_id: str
    execution_id: str
    scope: ExecutionScope
    tool_id: str
    input: Mapping[str, Any]
    resource: str = ""
    deadline_seconds: float = 10.0
    input_schema_version: str = "1"
    tool_version: str | None = None

    @property
    def input_data(self) -> Mapping[str, Any]:
        return self.input

    def __post_init__(self) -> None:
        if not self.tool_call_id.strip() or not self.execution_id.strip() or not self.tool_id.strip():
            raise ValueError("tool invocation identifiers are required")
        if self.deadline_seconds <= 0:
            raise ValueError("deadline_seconds must be positive")
        if not self.input_schema_version.strip():
            raise ValueError("input_schema_version is required")


ToolInvocationRequest = ToolInvocation


@dataclass(frozen=True)
class ToolExecutionResult:
    tool_call_id: str
    tool_id: str
    status: ToolStatus
    output: Mapping[str, Any] | None = None
    error: ToolError | None = None
    attempts: int = 0
    external_reference: str | None = None
    source: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, ToolStatus):
            object.__setattr__(self, "status", ToolStatus(self.status))
        if self.attempts < 0:
            raise ValueError("attempts cannot be negative")
        if self.status is ToolStatus.SUCCESS and self.error is not None:
            raise ValueError("successful tool results cannot contain an error")
        if self.status in (ToolStatus.FAILED, ToolStatus.DENIED) and self.error is None:
            raise ValueError("failed or denied tool results require an error")


ToolResult = ToolExecutionResult


@dataclass(frozen=True)
class ToolCandidateSet:
    capability: str
    candidates: tuple[ToolDescriptor, ...]

    def __iter__(self):
        return iter(self.candidates)

    def __len__(self) -> int:
        return len(self.candidates)

    def __getitem__(self, index):
        return self.candidates[index]

    @property
    def empty(self) -> bool:
        return not self.candidates

    @property
    def tools(self) -> tuple[ToolDescriptor, ...]:
        return self.candidates
