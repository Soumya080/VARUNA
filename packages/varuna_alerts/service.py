from datetime import datetime, timezone
from typing import List, Optional

from varuna_contracts.evidence import ValidityState
from varuna_alerts.protocol import AlertChannel, DeliveryResult
from varuna_alerts.dedupe import DedupeWindow
from varuna_alerts.materiality import check_materiality
from varuna_alerts.freshness import check_freshness
from varuna_alerts.role_router import get_recipients

class AlertService:
    def __init__(self, channels: List[AlertChannel],
                 dedupe_window_seconds: int = 300):
        self._channels = {ch.channel_name: ch for ch in channels}
        self._dedupe = DedupeWindow(dedupe_window_seconds)
        self._delivery_log: List[DeliveryResult] = []

    def route_and_send(self, event_type: str, case_id: str,
                       event_timestamp: datetime,
                       gate_state: Optional[ValidityState] = None,
                       subject: str = "", body: str = ""
                       ) -> List[DeliveryResult]:
        results = []

        # 1. Materiality check (L-01)
        should_send, mat_reason = check_materiality(gate_state, event_type)
        if not should_send:
            results.append(DeliveryResult(
                channel="none", recipient="none", status="suppressed",
                reason=mat_reason, is_simulated=False,
                idempotency_key=f"suppressed:{case_id}:{event_type}",
            ))
            self._delivery_log.extend(results)
            return results

        # 2. Freshness check (L-03)
        fresh, fresh_reason = check_freshness(event_timestamp)
        if not fresh:
            results.append(DeliveryResult(
                channel="none", recipient="none", status="expired",
                reason=fresh_reason, is_simulated=False,
                idempotency_key=f"expired:{case_id}:{event_type}",
            ))
            self._delivery_log.extend(results)
            return results

        # 3. Role routing (L-02)
        recipients = get_recipients(event_type)

        # 4. Dedupe + send (L-05)
        for recipient in recipients:
            idem_key = f"{case_id}:{event_type}:{recipient}"
            if self._dedupe.is_duplicate(idem_key):
                results.append(DeliveryResult(
                    channel="deduped", recipient=recipient, status="suppressed",
                    reason="duplicate within window", is_simulated=False,
                    idempotency_key=idem_key,
                ))
                continue
            for channel in self._channels.values():
                result = channel.send(recipient, subject, body, is_simulated=True)
                results.append(result)

        self._delivery_log.extend(results)
        return results

    def get_delivery_log(self) -> List[DeliveryResult]:
        return list(self._delivery_log)
