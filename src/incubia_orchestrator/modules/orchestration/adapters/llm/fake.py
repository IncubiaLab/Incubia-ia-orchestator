from incubia_orchestrator.modules.orchestration.ports.llm import GenerationFailure, GenerationRequest, GenerationResponse


class FakeLLM:
    def __init__(self, failure: str | None = None):
        self.failure = failure
        self.calls: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.calls.append(request)
        if self.failure:
            raise GenerationFailure(self.failure)
        return GenerationResponse(f"[fake] {request.text}")
