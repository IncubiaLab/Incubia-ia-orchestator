"""HTTP READ adapter for the governed catalog lookup capability."""

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
    CredentialError,
    ResolvedCredential,
    ToolAdapterPort,
)


@dataclass(frozen=True)
class CatalogHttpConfig:
    base_url: str
    lookup_path: str = "/v1/catalog/lookup"
    source_name: str = "business-catalog"
    source_version: str = "fixture-1"
    timeout_seconds: float = 3.0
    total_deadline_seconds: float = 10.0
    max_attempts: int = 2
    max_response_bytes: int = 64_000
    max_items: int = 100
    allow_loopback_for_fixture: bool = False

    def __post_init__(self) -> None:
        _validate_base_url(self.base_url, allow_loopback=self.allow_loopback_for_fixture)
        if not self.lookup_path.startswith("/") or "://" in self.lookup_path or ".." in self.lookup_path:
            raise ValueError("lookup_path must be a fixed relative HTTP path")
        if self.timeout_seconds <= 0 or self.total_deadline_seconds <= 0:
            raise ValueError("HTTP timeouts must be positive")
        if self.max_attempts < 1 or self.max_attempts > 2:
            raise ValueError("READ adapters allow at most two physical attempts")
        if self.max_response_bytes < 1 or self.max_items < 1:
            raise ValueError("HTTP output limits must be positive")


class CatalogHttpAdapter(ToolAdapterPort):
    def __init__(self, config: CatalogHttpConfig, *, client: httpx.Client | None = None,
                 clock=time.monotonic):
        self.config = config
        self._client = client or httpx.Client()
        self._clock = clock

    def execute(self, invocation: ToolInvocation, descriptor: ToolDescriptor, *,
                credential: ResolvedCredential | None,
                audit: AuditSinkPort | None = None) -> ToolExecutionResult:
        if credential is None and descriptor.credential_profile_ref:
            return _failure(invocation, descriptor.tool_id, "CREDENTIAL_UNAVAILABLE", "Credential is unavailable")
        query = invocation.input_data.get("query") or invocation.input_data.get("product_ref")
        if not isinstance(query, str) or not query.strip():
            return _failure(invocation, descriptor.tool_id, "INVALID_INPUT", "Catalog lookup input is invalid")

        url = self.config.base_url.rstrip("/") + self.config.lookup_path
        # Re-check the operator-configured URL at use time to defend against
        # mutable configuration objects and DNS/IP-shaped SSRF targets.
        try:
            _validate_base_url(self.config.base_url, allow_loopback=self.config.allow_loopback_for_fixture)
        except ValueError:
            return _failure(invocation, descriptor.tool_id, "SSRF_BLOCKED", "Configured catalog URL is not allowed")

        headers = {"Accept": "application/json", "User-Agent": "incubia-tool-catalog/1"}
        if credential is not None:
            headers["Authorization"] = f"Bearer {credential.token}"
        payload = {"query": query}
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
            _attempt(audit, invocation, descriptor, attempt, self.config.source_name)
            try:
                response = self._client.post(
                    url,
                    json=payload,
                    headers=headers,
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

            if response.status_code in (401, 403):
                return _failure(invocation, descriptor.tool_id, "CREDENTIAL_REVOKED", "Catalog credential was rejected", attempts)
            if response.status_code == 429:
                if attempt < self.config.max_attempts and self._clock() < deadline:
                    continue
                return _failure(invocation, descriptor.tool_id, "RATE_LIMIT", "Catalog rate limit reached", attempts, retryable=True)
            if response.status_code in (408, 425, 500, 502, 503, 504):
                if attempt < self.config.max_attempts and self._clock() < deadline:
                    continue
                return _failure(invocation, descriptor.tool_id, "UPSTREAM_ERROR", "Catalog service failed", attempts, retryable=True)
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
            result = _catalog_result(invocation, descriptor, body, attempts, self.config)
            return result

        return _failure(invocation, descriptor.tool_id, "TOOL_TIMEOUT", "Catalog deadline exceeded", attempts)

    def close(self) -> None:
        self._client.close()


def _catalog_result(invocation, descriptor, body, attempts, config) -> ToolExecutionResult:
    if not isinstance(body, Mapping) or not isinstance(body.get("items"), list):
        return _failure(invocation, descriptor.tool_id, "INVALID_RESPONSE", "Catalog response shape is invalid", attempts)
    if len(body["items"]) > config.max_items:
        return _failure(invocation, descriptor.tool_id, "OUTPUT_TOO_LARGE", "Catalog returned too many items", attempts)
    normalized = []
    suspicious = False
    try:
        for item in body["items"]:
            if not isinstance(item, Mapping):
                return _failure(invocation, descriptor.tool_id, "INVALID_RESPONSE", "Catalog item shape is invalid", attempts)
            clean = _json_safe(dict(item), depth=0)
            suspicious = suspicious or _contains_injection(clean)
            normalized.append(clean)
    except ValueError:
        return _failure(invocation, descriptor.tool_id, "INVALID_RESPONSE", "Catalog item is not safe JSON", attempts)
    output = {
        "items": normalized,
        "source": config.source_name,
        "version": config.source_version,
        "fetched_at": datetime.now(UTC).isoformat(),
        # Returned text is data only; the next layer must not treat it as
        # instructions. This marker makes that boundary observable.
        "untrusted_content": suspicious,
    }
    return ToolExecutionResult(
        invocation.tool_call_id,
        descriptor.tool_id,
        ToolStatus.SUCCESS,
        output=output,
        attempts=attempts,
        source=config.source_name,
    )


def _json_safe(value, *, depth: int):
    if depth > 5:
        raise ValueError("JSON nesting is too deep")
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, str) and len(value) > 8_000:
            raise ValueError("JSON string is too large")
        return value
    if isinstance(value, Mapping):
        if len(value) > 100:
            raise ValueError("JSON object is too large")
        return {str(key)[:128]: _json_safe(item, depth=depth + 1) for key, item in value.items()}
    if isinstance(value, list):
        if len(value) > 100:
            raise ValueError("JSON array is too large")
        return [_json_safe(item, depth=depth + 1) for item in value]
    raise ValueError("JSON value is not supported")


_INJECTION_MARKERS = re.compile(r"ignore\s+(?:all\s+)?previous|system\s+message|<\|(?:system|assistant)", re.I)


def _contains_injection(value) -> bool:
    if isinstance(value, str):
        return bool(_INJECTION_MARKERS.search(value))
    if isinstance(value, Mapping):
        return any(_contains_injection(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_injection(item) for item in value)
    return False


def _validate_base_url(value: str, *, allow_loopback: bool) -> None:
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Catalog base URL is not a valid HTTP URL")
    host = parsed.hostname.casefold()
    if host in {"localhost", "metadata.google.internal", "instance-data.ec2.internal"} or host.endswith((".local", ".internal")):
        if not allow_loopback:
            raise ValueError("Catalog base URL targets a private host")
    try:
        address = ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        if not (allow_loopback and address.is_loopback):
            raise ValueError("Catalog base URL targets a private address")


def _as_int(value: str) -> int:
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


def _attempt(audit, invocation, descriptor, attempt, source):
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
        metadata={"adapter": source},
    ))
