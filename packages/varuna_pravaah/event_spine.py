"""
VARUNA GRID — PRAVAAH Event Spine.

In-memory event bus. No Redis/Kafka required.
"""
from typing import List, Optional, Dict, Any, Callable
from datetime import datetime, timezone
import uuid


class Event:
    def __init__(self, event_type: str, case_id: str, actor: str,
                 correlation_id: str, payload: Optional[Dict[str, Any]] = None):
        self.event_id = uuid.uuid4().hex[:12]
        self.event_type = event_type
        self.case_id = case_id
        self.actor = actor
        self.correlation_id = correlation_id
        self.payload = payload or {}
        self.timestamp = datetime.now(timezone.utc)
        self.idempotency_key = f"{event_type}:{case_id}:{self.event_id}"


class EventSpine:
    """In-memory event store and publisher."""

    def __init__(self):
        self._events: List[Event] = []
        self._subscribers: Dict[str, List[Callable]] = {}

    def emit(self, event_type: str, case_id: str, actor: str = "system",
             payload: Optional[Dict[str, Any]] = None) -> Event:
        event = Event(event_type, case_id, actor, case_id, payload)
        self._events.append(event)
        # Notify subscribers
        for handler in self._subscribers.get(event_type, []):
            handler(event)
        for handler in self._subscribers.get("*", []):
            handler(event)
        return event

    def subscribe(self, event_type: str, handler: Callable):
        self._subscribers.setdefault(event_type, []).append(handler)

    def list_all(self) -> List[Event]:
        return list(self._events)

    def list_by_case(self, case_id: str) -> List[Event]:
        return [e for e in self._events if e.case_id == case_id]

    def count(self) -> int:
        return len(self._events)
