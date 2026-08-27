from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone

@dataclass
class DeliveryResult:
    channel: str
    recipient: str
    status: str    # "sent" | "suppressed" | "simulated" | "expired"
    reason: str
    is_simulated: bool
    idempotency_key: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

class AlertChannel(ABC):
    @abstractmethod
    def send(self, recipient: str, subject: str, body: str,
             *, is_simulated: bool) -> DeliveryResult: ...
    @property
    @abstractmethod
    def channel_name(self) -> str: ...
