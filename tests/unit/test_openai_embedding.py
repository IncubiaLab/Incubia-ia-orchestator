import httpx
import pytest

from incubia_orchestrator.modules.knowledge.adapters.openai_embedding import EmbeddingBudget, OpenAIEmbedding


def test_budget_reserves_before_http_and_records_usage(tmp_path):
    budget = EmbeddingBudget(tmp_path / "budget.sqlite", max_calls=1, max_input_tokens=100,
                             usd_cap=0.10)
    requests = []

    def respond(request):
        requests.append(request)
        assert request.url.host == "api.openai.com"
        assert request.headers["Authorization"] == "Bearer test-key"
        assert request.read().decode().count('"dimensions":384') == 1
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.0] * 384}],
                                         "usage": {"total_tokens": 2}})

    client = httpx.Client(transport=httpx.MockTransport(respond))
    adapter = OpenAIEmbedding("test-key", budget, client=client)
    assert len(adapter.embed(("hola",))[0]) == 384
    assert budget.snapshot()["actual_tokens"] == 2
    with pytest.raises(RuntimeError, match="budget exhausted"):
        adapter.embed(("otra",))
    assert len(requests) == 1


def test_failed_request_consumes_reservation(tmp_path):
    budget = EmbeddingBudget(tmp_path / "budget.sqlite", max_calls=1, max_input_tokens=100,
                             usd_cap=0.10)
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(503)))
    with pytest.raises(RuntimeError, match="request failed"):
        OpenAIEmbedding("test-key", budget, client=client).embed(("hola",))
    assert budget.snapshot()["calls"] == 1
