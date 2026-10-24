"""OpenAI Responses HTTP adapter. Client injection keeps tests offline."""
import time

import httpx
from incubia_orchestrator.modules.orchestration.adapters.llm.monthly_limit import MonthlyCallLimiter
from incubia_orchestrator.foundation.contracts.execution import TokenUsage
from incubia_orchestrator.modules.orchestration.ports.llm import GenerationFailure, GenerationRequest, GenerationResponse


class OpenAILLM:
    def __init__(self, *, model: str, api_key: str, timeout: float = 30,
                 retries: int = 0, client: httpx.Client | None = None,
                 limiter: MonthlyCallLimiter | None = None, metrics=None,
                 deadline_seconds: float | None = None, sleep=time.sleep, clock=time.monotonic):
        if not model:
            raise ValueError("Define INCUBIA_MODEL/--model")
        if not api_key:
            raise ValueError("Define OPENAI_API_KEY; usa --fake sin credenciales")
        if timeout <= 0 or retries < 0:
            raise ValueError("Invalid transport limits")
        self.model, self.api_key, self.timeout, self.retries = model, api_key, timeout, retries
        self.client = client or httpx.Client(timeout=timeout)
        self.limiter = limiter
        self.metrics = metrics
        # Total budget for transient-429 waits; Retry-After never exceeds what is left.
        self.deadline_seconds = timeout if deadline_seconds is None else deadline_seconds
        self._sleep, self._clock = sleep, clock

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        try:
            response = self._generate(request)
        except GenerationFailure as exc:
            self._record_failure(exc.code)
            raise
        if self.metrics is not None and response.usage is not None:
            try:
                self.metrics.cost("llm", input_tokens=response.usage.input_tokens,
                                  output_tokens=response.usage.output_tokens)
            except Exception:
                pass
        return response

    @staticmethod
    def _is_quota_error(response) -> bool:
        try:
            error = response.json().get("error") or {}
            return (error.get("type") == "insufficient_quota"
                    or error.get("code") in ("insufficient_quota", "credit_balance_exhausted"))
        except (ValueError, AttributeError):
            return False

    @staticmethod
    def _retry_delay(response, attempt: int) -> float:
        try:
            value = float(response.headers.get("retry-after"))
            if value >= 0 and value == value and value != float("inf"):
                return value
        except (TypeError, ValueError):
            pass
        return min(0.5 * 2 ** attempt, 8.0)

    def _record_failure(self, code: str) -> None:
        if self.metrics is None:
            return
        category = {"PROVIDER_QUOTA": "provider_quota", "PROVIDER_RATE_LIMIT": "provider_limit",
                    "LOCAL_MONTHLY_LIMIT": "budget", "LOCAL_COOLDOWN": "budget"}.get(code)
        if category:
            try:
                self.metrics.rejection(category, code)
            except Exception:
                pass

    def _generate(self, request: GenerationRequest) -> GenerationResponse:
        if self.limiter is not None:
            self.limiter.reserve()
        messages = []
        for turn in request.history:
            messages.extend(({"role": "user", "content": turn.user},
                             {"role": "assistant", "content": turn.assistant}))
        messages.append({"role": "user", "content": request.text})
        body = {"model": request.model or self.model, "instructions": request.instructions, "input": messages,
                "max_output_tokens": request.max_output_tokens, "store": False}
        deadline = self._clock() + self.deadline_seconds
        for attempt in range(self.retries + 1):
            try:
                response = self.client.post("https://api.openai.com/v1/responses", json=body,
                                            headers={"Authorization": f"Bearer {self.api_key}"},
                                            timeout=self.timeout)
            except httpx.TimeoutException:
                if attempt < self.retries and self._clock() < deadline:
                    continue
                raise GenerationFailure("PROVIDER_TIMEOUT") from None
            except httpx.TransportError:
                if attempt < self.retries and self._clock() < deadline:
                    continue
                raise GenerationFailure("PROVIDER_UNAVAILABLE") from None
            if response.status_code == 401:
                raise GenerationFailure("PROVIDER_AUTH")
            if response.status_code == 429:
                # Quota/credit exhaustion is not transient: fail fast, never retry.
                if self._is_quota_error(response):
                    raise GenerationFailure("PROVIDER_QUOTA")
                if attempt < self.retries:
                    delay = self._retry_delay(response, attempt)
                    if delay <= deadline - self._clock():
                        if delay > 0:
                            self._sleep(delay)
                        continue
                raise GenerationFailure("PROVIDER_RATE_LIMIT")
            if response.status_code in (500, 502, 503, 504) and attempt < self.retries \
                    and self._clock() < deadline:
                continue
            if response.status_code >= 400:
                raise GenerationFailure("PROVIDER_ERROR")
            try:
                data = response.json()
                if data.get("status") != "completed":
                    raise GenerationFailure("PROVIDER_INCOMPLETE")
                text = "".join(part["text"] for item in data["output"]
                               if item.get("type") == "message"
                               for part in item.get("content", []) if part.get("type") == "output_text")
                if not text.strip():
                    raise GenerationFailure("EMPTY_RESPONSE")
                raw_usage = data.get("usage")
                usage = None
                if isinstance(raw_usage, dict) and isinstance(raw_usage.get("input_tokens"), int) and isinstance(raw_usage.get("output_tokens"), int):
                    usage = TokenUsage(raw_usage["input_tokens"], raw_usage["output_tokens"])
                return GenerationResponse(text, usage)
            except (ValueError, KeyError, TypeError, AttributeError):
                raise GenerationFailure("PROVIDER_INVALID_RESPONSE") from None
        raise AssertionError("Unreachable")
