import json
import pytest
import httpx

from incubia_orchestrator.modules.orchestration.adapters.llm.openai_adapter import OpenAILLM
from incubia_orchestrator.modules.orchestration.adapters.llm.monthly_limit import MonthlyCallLimiter
from incubia_orchestrator.modules.orchestration.ports.llm import GenerationFailure, GenerationRequest


def test_monthly_limit_persists_across_instances(tmp_path):
    path = tmp_path / "budget.json"
    now = [1791291600.0]
    first = MonthlyCallLimiter(path, max_calls=2, min_interval_seconds=10, clock=lambda: now[0])
    second = MonthlyCallLimiter(path, max_calls=2, min_interval_seconds=10, clock=lambda: now[0])
    first.reserve()
    with pytest.raises(GenerationFailure, match="LOCAL_COOLDOWN"):
        second.reserve()
    now[0] += 10
    second.reserve()
    now[0] += 10
    with pytest.raises(GenerationFailure, match="LOCAL_MONTHLY_LIMIT"):
        first.reserve()
    assert json.loads(path.read_text())["calls"] == 2


def test_limit_state_fails_closed(tmp_path):
    path = tmp_path / "budget.json"
    path.write_text("invalid JSON")
    limiter = MonthlyCallLimiter(path)
    with pytest.raises(GenerationFailure, match="LOCAL_LIMIT_UNAVAILABLE"):
        limiter.reserve()


def test_month_changes_reset_allowance(tmp_path):
    path = tmp_path / "budget.json"
    now = [1791291600.0]
    limiter = MonthlyCallLimiter(path, max_calls=1, min_interval_seconds=0, clock=lambda: now[0])
    limiter.reserve()
    now[0] += 40 * 24 * 60 * 60
    limiter.reserve()
    assert json.loads(path.read_text())["calls"] == 1


def test_limit_blocks_second_provider_request(tmp_path):
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"status": "completed", "output": [
            {"type": "message", "content": [{"type": "output_text", "text": "ok"}]}]})
    client = httpx.Client(transport=httpx.MockTransport(respond))
    limiter = MonthlyCallLimiter(tmp_path / "budget.json", max_calls=1, min_interval_seconds=0)
    provider = OpenAILLM(model="gpt-5.4-mini", api_key="test-key", client=client, limiter=limiter)
    request = GenerationRequest("hola", (), "responde", 64)
    assert provider.generate(request).text == "ok"
    with pytest.raises(GenerationFailure, match="LOCAL_MONTHLY_LIMIT"):
        provider.generate(request)
    assert len(requests) == 1
