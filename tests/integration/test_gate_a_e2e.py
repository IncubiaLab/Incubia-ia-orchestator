"""Gate A: complete local path with durable inbox/outbox and no network."""
from dataclasses import dataclass

from incubia_orchestrator.foundation.contracts.execution import CompletedExecution, ExecutionOutput, ExecutionScope
from incubia_orchestrator.foundation.contracts.specialty import Specialty
from incubia_orchestrator.modules.conversation.adapters.persistence.sqlite_ledger import SqliteLedger
from incubia_orchestrator.modules.conversation.application.response_context import InProcessResponseContext
from incubia_orchestrator.modules.conversation.ports.response_context import ResponseContextRequest
from tests.fakes.channel_delivery import FakeChannelDelivery


@dataclass
class CountingRuntime:
    calls: int = 0

    def start(self, request):
        self.calls += 1
        return CompletedExecution(request_id=request.request_id, execution_id=request.execution_id,
                                  output=ExecutionOutput("respuesta fake", specialty=Specialty.VENTAS))


def _process(ledger, runtime, channel, payload):
    reserved = ledger.reserve_inbox("pilot", "tenant-a", "fake-bot", payload["event_id"], payload, channel="fake")
    if not reserved.is_new or not ledger.claim(reserved.execution_id):
        return reserved
    scope = ExecutionScope("pilot", "tenant-a", "conversation-a", "actor-a")
    request = type("Request", (), {"request_id": reserved.request_id, "execution_id": reserved.execution_id})()
    outcome = runtime.start(request)
    response = InProcessResponseContext().contextualize(ResponseContextRequest(
        "response-" + outcome.execution_id, outcome.request_id, outcome.execution_id, scope,
        "fake:binding-a", outcome.output.text, outcome.output.specialty))
    ledger.complete(outcome.execution_id, response.response_id, response.destination_ref, response.to_dict())
    assert ledger.reserve_delivery(outcome.execution_id, response.response_id, response.destination_ref)
    result = channel.deliver(response)
    assert ledger.mark_delivery_sent(outcome.execution_id, response.response_id, response.destination_ref,
                                     result.external_message_id or "missing")
    return reserved


def test_gate_a_fake_channel_is_once_only_across_duplicate_and_restart(tmp_path):
    path, payload = tmp_path / "e2.sqlite", {"event_id": "event-1", "text": "quiero vender"}
    runtime, channel = CountingRuntime(), FakeChannelDelivery()
    first_ledger = SqliteLedger(path)
    first = _process(first_ledger, runtime, channel, payload)
    duplicate = _process(first_ledger, runtime, channel, payload)
    first_ledger.close()

    restarted = SqliteLedger(path)
    after_restart = _process(restarted, runtime, channel, payload)
    restarted.close()

    assert first.is_new
    assert (duplicate.execution_id, after_restart.execution_id) == (first.execution_id, first.execution_id)
    assert runtime.calls == 1
    assert len(channel.delivered) == 1
