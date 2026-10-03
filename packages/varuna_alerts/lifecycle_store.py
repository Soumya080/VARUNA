from pathlib import Path
from typing import Dict, List, Optional

from varuna_alerts.lifecycle import AlertRecord


class InMemoryAlertStore:
    """The ONE alert store.

    Name kept for the many existing call sites, but it is now optionally
    disk-backed: pass `path=` and every alert, acknowledgement, escalation
    and resolution survives an API restart. Without a path it stays purely
    in-memory, which is what the unit tests want.

    Why this matters: before persistence, restarting the API erased every
    human decision in the system — who acknowledged what, who escalated,
    who approved a dispatch — while the advisory SMRITI summary survived.
    That is exactly backwards for an auditable operational product.

    A `correlation_key -> alert_id` index is maintained alongside, because
    dedupe hits `get_by_correlation_key` on every material change and the
    previous implementation scanned every alert linearly.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self._alerts: Dict[str, AlertRecord] = {}
        self._by_correlation: Dict[str, str] = {}
        self._store = None
        if path is not None:
            from varuna_infra.jsonl_store import KeyedJsonlStore

            self._store = KeyedJsonlStore(
                path,
                key=lambda a: a.alert_id,
                loads=AlertRecord.model_validate_json,
                dumps=lambda a: a.model_dump_json(),
            )
            for alert in self._store.all():
                self._index(alert)

    # ---------------------------------------------------------------- internal
    def _index(self, alert: AlertRecord) -> None:
        self._alerts[alert.alert_id] = alert
        if alert.correlation_key:
            self._by_correlation[alert.correlation_key] = alert.alert_id

    @property
    def load_errors(self) -> int:
        """Corrupt lines skipped when loading persisted state. Non-zero means
        the state file is damaged and should be inspected."""
        return getattr(self._store, "load_errors", 0)

    @property
    def persisted(self) -> bool:
        return self._store is not None

    # ------------------------------------------------------------------- write
    def save(self, alert: AlertRecord) -> None:
        self._index(alert)
        if self._store is not None:
            self._store.put(alert)

    # -------------------------------------------------------------------- read
    def get(self, alert_id: str) -> Optional[AlertRecord]:
        return self._alerts.get(alert_id)

    def list_by_case(self, case_id: str) -> List[AlertRecord]:
        return [a for a in self._alerts.values() if a.case_id == case_id]

    def all(self) -> List[AlertRecord]:
        return list(self._alerts.values())

    def get_by_correlation_key(self, correlation_key: str) -> Optional[AlertRecord]:
        alert_id = self._by_correlation.get(correlation_key)
        return self._alerts.get(alert_id) if alert_id else None
