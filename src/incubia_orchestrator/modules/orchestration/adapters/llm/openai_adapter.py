"""OpenAI Responses HTTP adapter. Client injection keeps tests offline."""
import httpx
from incubia_orchestrator.foundation.contracts.execution import TokenUsage
from incubia_orchestrator.modules.orchestration.ports.llm import GenerationFailure, GenerationRequest, GenerationResponse


class OpenAILLM:
    def __init__(self, *, model: str, api_key: str, timeout: float = 30,
                 retries: int = 0, client: httpx.Client | None = None):
        if not model:
            raise ValueError("Define INCUBIA_MODEL/--model")
        if not api_key:
            raise ValueError("Define OPENAI_API_KEY; usa --fake sin credenciales")
        if timeout <= 0 or retries < 0:
            raise ValueError("Invalid transport limits")
        self.model, self.api_key, self.timeout, self.retries = model, api_key, timeout, retries
        self.client = client or httpx.Client(timeout=timeout)

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        messages = []
        for turn in request.history:
            messages.extend(({"role": "user", "content": turn.user},
                             {"role": "assistant", "content": turn.assistant}))
        messages.append({"role": "user", "content": request.text})
        body = {"model": request.model or self.model, "instructions": request.instructions, "input": messages,
                "max_output_tokens": request.max_output_tokens, "store": False}
        for attempt in range(self.retries + 1):
            try:
                response = self.client.post("https://api.openai.com/v1/responses", json=body,
                                            headers={"Authorization": f"Bearer {self.api_key}"},
                                            timeout=self.timeout)
            except httpx.TimeoutException:
                if attempt < self.retries:
                    continue
                raise GenerationFailure("PROVIDER_TIMEOUT") from None
            except httpx.TransportError:
                if attempt < self.retries:
                    continue
                raise GenerationFailure("PROVIDER_UNAVAILABLE") from None
            if response.status_code in (429, 500, 502, 503, 504) and attempt < self.retries:
                continue
            if response.status_code == 401:
                raise GenerationFailure("PROVIDER_AUTH")
            if response.status_code == 429:
                raise GenerationFailure("PROVIDER_RATE_LIMIT")
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
