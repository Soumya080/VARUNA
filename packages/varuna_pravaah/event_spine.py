"""
VARUNA GRID — PRAVAAH Event Spine.

Event bus using EventRepository.
"""
from typing import List, Optional, Dict, Any, Callable
from varuna_domain.entities import DomainEvent
from varuna_domain.ports import EventRepository


class EventSpine:
    """Event store and publisher."""

    def __init__(self, event_repo: EventRepository):
        self._repo = event_repo
        self._subscribers: Dict[str, List[Callable]] = {}

    def emit(self, event_type: str, case_id: str, actor: str = "system",
             payload: Optional[Dict[str, Any]] = None) -> DomainEvent:
        event = DomainEvent(event_type, case_id, actor, case_id, payload)
        self._repo.append(event)
        # Notify subscribers
        for handler in self._subscribers.get(event_type, []):
            handler(event)
        for handler in self._subscribers.get("*", []):
            handler(event)
        return event

    def subscribe(self, event_type: str, handler: Callable):
        self._subscribers.setdefault(event_type, []).append(handler)

    def list_all(self) -> List[DomainEvent]:
        return self._repo.list_all()

    def list_by_case(self, case_id: str) -> List[DomainEvent]:
        return self._repo.list_by_case(case_id)

    def count(self) -> int:
        return self._repo.count()
