import structlog
from varuna_alerts.protocol import AlertChannel, DeliveryResult

logger = structlog.get_logger()

class ConsoleChannel(AlertChannel):
    @property
    def channel_name(self) -> str:
        return "console"

    def send(self, recipient: str, subject: str, body: str, *, is_simulated: bool = False) -> DeliveryResult:
        logger.info("alert.sent", channel="console", recipient=recipient,
                    subject=subject, is_simulated=is_simulated)
        return DeliveryResult(
            channel="console", recipient=recipient,
            status="simulated" if is_simulated else "sent",
            reason="logged to console",
            is_simulated=is_simulated,
            idempotency_key=f"console:{recipient}:{subject}",
        )
