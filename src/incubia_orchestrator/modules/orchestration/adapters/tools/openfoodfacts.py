"""Open Food Facts v3 READ adapter for product-code lookups.

The provider is read-only in this adapter.  Product data is community
contributed and is returned as untrusted evidence; it cannot alter policy or
trigger another tool.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from ipaddress import ip_address
import json
import re
import time
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from incubia_orchestrator.modules.audit.domain.audit import AuditEvent, AuditEventType
from incubia_orchestrator.modules.audit.ports.sink import AuditSinkPort
from incubia_orchestrator.modules.orchestration.domain.tools import (
    ToolDescriptor,
    ToolError,
    ToolExecutionResult,
    ToolInvocation,
    ToolStatus,
)
from incubia_orchestrator.modules.orchestration.ports.tool_executor import (
    ResolvedCredential,
    ToolAdapterPort,
)


_BARCODE = re.compile(r"^[0-9]{7,18}$")
_INJECTION_MARKERS = re.compile(
    r"ignore\s+(?:all\s+)?previous|system\s+message|<\|(?:system|assistant)", re.I
)
_ALLOWED_PRODUCT_FIELDS = (
    "code",
    "product_name",
    "product_name_en",
    "brands",
    "quantity",
    "nutriscore_grade",
    "ingredients_text",
    "ingredients_text_en",
    "categories",
    "countries",
)


@dataclass(frozen=True)
class OpenFoodFactsConfig:
    base_url: str = "https://world.openfoodfacts.org"
    api_version: str = "v3"
    fields: str = ",".join(_ALLOWED_PRODUCT_FIELDS)
    user_agent: str = "IncubiaOrchestrator/0.1 (E3 READ fixture)"
    timeout_seconds: float = 3.0
    total_deadline_seconds: float = 10.0
    max_attempts: int = 1
    max_response_bytes: int = 64_000

    def __post_init__(self) -> None:
        _validate_base_url(self.base_url)
        if self.api_version != "v3":
            raise ValueError("Open Food Facts adapter is pinned to API v3")
        if not self.user_agent.strip() or "\n" in self.user_agent or "\r" in self.user_agent:
            raise ValueError("A safe identifying User-Agent is required")
        if self.timeout_seconds <= 0 or self.total_deadline_seconds <= 0:
            raise ValueError("HTTP timeouts must be positive")
        if self.max_attempts < 1 or self.max_attempts > 2:
            raise ValueError("Open Food Facts allows at most two physical attempts")
        if self.max_response_bytes < 1:
            raise ValueError("max_response_bytes must be positive")


class OpenFoodFactsAdapter(ToolAdapterPort):
    def __init__(self, config: OpenFoodFactsConfig | None = None, *,
                 client: httpx.Client | None = None, clock=time.monotonic):
        self.config = config or OpenFoodFactsConfig()
        self._client = client or httpx.Client()
        self._clock = clock

    def execute(self, invocation: ToolInvocation, descriptor: ToolDescriptor, *,
                credential: ResolvedCredential | None,
                audit: AuditSinkPort | None = None) -> ToolExecutionResult:
        del credential  # READ endpoint uses an identifying User-Agent, not a secret.
        product_ref = invocation.input_data.get("product_ref")
        if product_ref is None:
            product_ref = invocation.input_data.get("query")
        if not isinstance(product_ref, str) or not _BARCODE.fullmatch(product_ref):
            return _failure(invocation, descriptor.tool_id, "INVALID_INPUT", "A numeric product code is required")

        url = (
            self.config.base_url.rstrip("/")
            + f"/api/{self.config.api_version}/product/{product_ref}"
        )
        started = self._clock()
        deadline = min(
            started + self.config.total_deadline_seconds,
            started + invocation.deadline_seconds,
        )
        attempts = 0
        for attempt in range(1, self.config.max_attempts + 1):
            remaining = deadline - self._clock()
            if remaining <= 0:
                return _failure(invocation, descriptor.tool_id, "TOOL_TIMEOUT", "Tool deadline exceeded", attempts)
            attempts = attempt
            _attempt(audit, invocation, descriptor, attempt)
            try:
                response = self._client.get(
                    url,
                    params={"fields": self.config.fields},
                    headers={
                        "Accept": "application/json",
                        "User-Agent": self.config.user_agent,
                    },
                    timeout=min(self.config.timeout_seconds, remaining),
                )
            except httpx.TimeoutException:
                if attempt < self.config.max_attempts and self._clock() < deadline:
                    continue
                return _failure(invocation, descriptor.tool_id, "TOOL_TIMEOUT", "Catalog request timed out", attempts)
            except httpx.RequestError:
                if attempt < self.config.max_attempts and self._clock() < deadline:
                    continue
                return _failure(invocation, descriptor.tool_id, "TOOL_TRANSPORT", "Catalog request failed", attempts)

            if response.status_code == 429:
                return _failure(invocation, descriptor.tool_id, "RATE_LIMIT", "Open Food Facts rate limit reached",
                                attempts, retryable=True)
            if response.status_code == 404:
                return _not_found(invocation, descriptor.tool_id, product_ref, attempts, self.config)
            if response.status_code >= 500:
                if attempt < self.config.max_attempts and self._clock() < deadline:
                    continue
                return _failure(invocation, descriptor.tool_id, "UPSTREAM_ERROR", "Catalog service failed", attempts,
                                retryable=True)
            if response.status_code >= 400:
                return _failure(invocation, descriptor.tool_id, "UPSTREAM_REJECTED", "Catalog rejected the request", attempts)

            content_length = response.headers.get("content-length")
            if content_length and _as_int(content_length) > self.config.max_response_bytes:
                return _failure(invocation, descriptor.tool_id, "OUTPUT_TOO_LARGE", "Catalog response is too large", attempts)
            if len(response.content) > self.config.max_response_bytes:
                return _failure(invocation, descriptor.tool_id, "OUTPUT_TOO_LARGE", "Catalog response is too large", attempts)
            try:
                body = response.json()
            except (ValueError, json.JSONDecodeError):
                return _failure(invocation, descriptor.tool_id, "INVALID_RESPONSE", "Catalog response is not valid JSON", attempts)
            return _map_response(invocation, descriptor, product_ref, body, attempts, self.config)

        return _failure(invocation, descriptor.tool_id, "TOOL_TIMEOUT", "Catalog deadline exceeded", attempts)

    def close(self) -> None:
        self._client.close()


def _map_response(invocation, descriptor, product_ref, body, attempts, config):
    if not isinstance(body, Mapping):
        return _failure(invocation, descriptor.tool_id, "INVALID_RESPONSE", "Catalog response shape is invalid", attempts)
    status = body.get("status")
    result_id = body.get("result", {}).get("id") if isinstance(body.get("result"), Mapping) else None
    if status in (0, "not_found") or (status == "failure" and result_id == "product_not_found"):
        return _not_found(invocation, descriptor.tool_id, product_ref, attempts, config)
    if status not in (1, "success"):
        return _failure(invocation, descriptor.tool_id, "INVALID_RESPONSE", "Catalog response shape is invalid", attempts)
    product = body.get("product")
    if not isinstance(product, Mapping):
        return _failure(invocation, descriptor.tool_id, "INVALID_RESPONSE", "Catalog product shape is invalid", attempts)
    try:
        selected = {
            key: _json_safe(product[key], depth=0)
            for key in _ALLOWED_PRODUCT_FIELDS
            if key in product
        }
    except ValueError:
        return _failure(invocation, descriptor.tool_id, "INVALID_RESPONSE", "Catalog product is not safe JSON", attempts)
    output = {
        "items": [selected],
        "found": True,
        "source": "openfoodfacts",
        "version": "v3",
        "fetched_at": datetime.now(UTC).isoformat(),
        "source_url": (
            config.base_url.rstrip("/") + f"/api/{config.api_version}/product/{product_ref}"
        ),
        "untrusted_content": _contains_injection(selected),
    }
    return ToolExecutionResult(
        invocation.tool_call_id,
        descriptor.tool_id,
        ToolStatus.SUCCESS,
        output=output,
        attempts=attempts,
        source="openfoodfacts",
    )


def _not_found(invocation, tool_id, product_ref, attempts, config):
    return ToolExecutionResult(
        invocation.tool_call_id,
        tool_id,
        ToolStatus.SUCCESS,
        output={
            "items": [],
            "found": False,
            "source": "openfoodfacts",
            "version": "v3",
            "fetched_at": datetime.now(UTC).isoformat(),
            "source_url": config.base_url.rstrip("/") + f"/api/{config.api_version}/product/{product_ref}",
            "untrusted_content": False,
        },
        attempts=attempts,
        source="openfoodfacts",
    )


def _json_safe(value, *, depth):
    if depth > 5:
        raise ValueError("JSON nesting is too deep")
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, str) and len(value) > 8_000:
            raise ValueError("JSON string is too large")
        return value
    if isinstance(value, Mapping):
        return {str(key)[:128]: _json_safe(item, depth=depth + 1) for key, item in value.items()}
    if isinstance(value, list):
        if len(value) > 100:
            raise ValueError("JSON array is too large")
        return [_json_safe(item, depth=depth + 1) for item in value]
    raise ValueError("JSON value is not supported")


def _contains_injection(value):
    if isinstance(value, str):
        return bool(_INJECTION_MARKERS.search(value))
    if isinstance(value, Mapping):
        return any(_contains_injection(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_injection(item) for item in value)
    return False


def _validate_base_url(value: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Open Food Facts base URL must be an HTTPS URL without credentials")
    host = parsed.hostname.casefold()
    if host != "world.openfoodfacts.org":
        raise ValueError("Open Food Facts adapter is pinned to world.openfoodfacts.org")
    try:
        address = ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("Open Food Facts base URL targets a private address")


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _failure(invocation, tool_id, code, message, attempts=0, *, retryable=False):
    return ToolExecutionResult(
        invocation.tool_call_id,
        tool_id,
        ToolStatus.FAILED,
        error=ToolError(code, message, retryable),
        attempts=attempts,
    )


def _attempt(audit, invocation, descriptor, attempt):
    if audit is None:
        return
    audit.append(AuditEvent.now(
        event_id=str(uuid4()),
        event_type=AuditEventType.TOOL_ATTEMPT,
        tool_call_id=invocation.tool_call_id,
        execution_id=invocation.execution_id,
        scope=invocation.scope,
        tool_id=descriptor.tool_id,
        resource=invocation.resource[:256],
        attempt=attempt,
        metadata={"adapter": "openfoodfacts", "method": "GET"},
    ))
