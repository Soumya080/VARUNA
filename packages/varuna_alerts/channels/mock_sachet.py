from varuna_alerts.protocol import AlertChannel, DeliveryResult

class MockSachetChannel(AlertChannel):
    """Threat L-04: is_simulated=True always."""

    @property
    def channel_name(self) -> str:
        return "mock_sachet"

    def send(self, recipient: str, subject: str, body: str, *, is_simulated: bool = True) -> DeliveryResult:
        return DeliveryResult(
            channel="mock_sachet", recipient=recipient,
            status="simulated", reason="SACHET provider simulated",
            is_simulated=True,  # ALWAYS True - threat L-04
            idempotency_key=f"sachet:{recipient}:{subject}",
        )
