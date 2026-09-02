from typing import Dict, List, Optional

from varuna_alerts.lifecycle import AlertRecord


class InMemoryAlertStore:
    """Mirrors `varuna_missions.repository.InMemoryMissionRepository`'s
    shape exactly — same "no second alert store" instruction applies to
    reusing an established, already-reviewed repository pattern rather than
    inventing a new persistence style for one more entity."""

    def __init__(self) -> None:
        self._alerts: Dict[str, AlertRecord] = {}

    def save(self, alert: AlertRecord) -> None:
        self._alerts[alert.alert_id] = alert

    def get(self, alert_id: str) -> Optional[AlertRecord]:
        return self._alerts.get(alert_id)

    def list_by_case(self, case_id: str) -> List[AlertRecord]:
        return [a for a in self._alerts.values() if a.case_id == case_id]

    def get_by_correlation_key(self, correlation_key: str) -> Optional[AlertRecord]:
        for a in self._alerts.values():
            if a.correlation_key == correlation_key:
                return a
        return None
