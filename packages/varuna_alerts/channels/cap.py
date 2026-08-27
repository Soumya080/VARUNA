from varuna_alerts.protocol import AlertChannel
from varuna_contracts.schemas import StrEnum

class CAPChannel(AlertChannel):
    def send(self, recipient: str, template_id: str, context: dict) -> None:
        pass
        
    @property
    def channel_type(self) -> StrEnum:
        return "CAP"
