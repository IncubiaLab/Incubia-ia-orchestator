from concurrent.futures import ThreadPoolExecutor

import pytest

from incubia_orchestrator.bootstrap.composition import compose_scoped
from incubia_orchestrator.foundation.contracts.execution import CompletedExecution, ExecutionScope
from incubia_orchestrator.interfaces.http.orbit_gateway import OrbitGatewayService


def test_scoped_generation_preserves_ids_and_isolates_concurrent_authorities():
    generate = compose_scoped(fake=True)

    def turn(index):
        scope = ExecutionScope('deployment', f'tenant-{index}', f'chat-{index}', f'actor-{index}')
        result = generate('hola', scope, (), f'request-{index}', f'turn-{index}')
        assert isinstance(result, CompletedExecution)
        assert result.output.kind == 'message'
        assert result.request_id == f'request-{index}'
        assert result.execution_id == f'turn-{index}'

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(turn, range(8)))


def test_gateway_rejects_short_secret():
    with pytest.raises(ValueError, match='at least 32'):
        OrbitGatewayService('short', None, 'test')


def test_real_gateway_fails_before_readiness_without_credentials(monkeypatch):
    monkeypatch.setenv('INCUBIA_ENV_FILE', '/dev/null')
    monkeypatch.setenv('OPENAI_API_KEY', '')
    with pytest.raises(ValueError, match='OPENAI_API_KEY'):
        compose_scoped(fake=False)
