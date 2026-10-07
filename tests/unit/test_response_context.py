from incubia_orchestrator.foundation.contracts.execution import ExecutionScope
from incubia_orchestrator.foundation.contracts.specialty import Specialty
from incubia_orchestrator.modules.conversation.application.response_context import InProcessResponseContext
from incubia_orchestrator.modules.conversation.ports.response_context import ResponseContextRequest
from tests.fakes.channel_delivery import FakeChannelDelivery


def test_public_response_has_same_contract_for_two_channels():
    request = ResponseContextRequest("response", "request", "execution", ExecutionScope("d", "t", "c", "a"),
                                     "fake:binding", "respuesta pública", Specialty.VENTAS)
    response = InProcessResponseContext().contextualize(request)
    first, second = FakeChannelDelivery(), FakeChannelDelivery()
    assert first.deliver(response).status == second.deliver(response).status
    assert first.delivered[0].to_dict() == second.delivered[0].to_dict()
