import pytest

from incubia_orchestrator.foundation.contracts.execution import ExecutionScope
from incubia_orchestrator.interfaces.http.e3_probe import ProbeService, compose_from_env
from incubia_orchestrator.modules.orchestration.application.grounded_response import GroundedAnswer


def test_probe_token_scope_and_payload_contract():
    seen = []

    def workflow(query, product_ref, scope, execution_id):
        seen.append((query, product_ref, scope, execution_id))
        return GroundedAnswer("Respuesta sintética", (), ("https://docs.example.org/a",), False)

    service = ProbeService(token="t" * 40, scope=ExecutionScope("deployment", "tenant", "", "actor"),
                           workflow=workflow, ready=lambda: True)
    assert not service.authorized(None)
    assert not service.authorized("Bearer wrong")
    assert service.authorized("Bearer " + "t" * 40)
    with pytest.raises(ValueError):
        service.execute({"query": "synthetic", "tenant_id": "other"})
    with pytest.raises(ValueError):
        service.execute({"query": "synthetic", "product_ref": "https://internal"})
    result = service.execute({"query": "synthetic", "product_ref": "3017620422003"})
    assert result["status"] == "completed"
    assert result["public_references"] == ["https://docs.example.org/a"]
    assert seen[0][2].deployment_id == "deployment"
    assert seen[0][2].tenant_id == "tenant"
    assert seen[0][2].actor_id == "actor"
    assert seen[0][3] == result["execution_id"]
    assert len(seen) == 1


def test_real_probe_requires_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("INCUBIA_E3_PROBE_REAL", raising=False)
    with pytest.raises(ValueError, match="opt-in"):
        compose_from_env()
