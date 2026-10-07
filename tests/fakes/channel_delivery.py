from incubia_orchestrator.modules.conversation.ports.channel_delivery import DeliveryResult, DeliveryStatus


class FakeChannelDelivery:
    def __init__(self):
        self.delivered = []

    def deliver(self, response):
        self.delivered.append(response)
        return DeliveryResult(DeliveryStatus.CONFIRMED, f"fake-{len(self.delivered)}")
