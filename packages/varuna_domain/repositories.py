"""
VARUNA GRID — In-memory repositories for local demo.
No PostgreSQL, Redis, or MinIO required.
"""
import threading
from typing import Dict, List, Optional, Set, Tuple
from varuna_domain.entities import Case, Artifact, DomainEvent
from varuna_domain.ports import CaseRepository, ArtifactRepository, EventRepository


class InMemoryCaseRepository(CaseRepository):
    def __init__(self):
        self._cases: Dict[str, Case] = {}

    def save(self, case: Case):
        self._cases[case.case_id] = case

    def get(self, case_id: str) -> Optional[Case]:
        return self._cases.get(case_id)

    def list_all(self) -> List[Case]:
        return list(self._cases.values())


class InMemoryArtifactRepository(ArtifactRepository):
    def __init__(self):
        self._artifacts: Dict[str, Artifact] = {}

    def save(self, artifact: Artifact):
        self._artifacts[artifact.artifact_id] = artifact

    def get(self, artifact_id: str) -> Optional[Artifact]:
        return self._artifacts.get(artifact_id)

    def list_by_case(self, case_id: str) -> List[Artifact]:
        return [a for a in self._artifacts.values() if a.case_id == case_id]


class InMemoryEventStore(EventRepository):
    """Thread-safe in-memory event store with per-case monotonic sequences
    and idempotency deduplication."""

    def __init__(self):
        self._events: List[DomainEvent] = []
        self._lock = threading.Lock()
        self._case_sequences: Dict[str, int] = {}  # case_id -> current seq
        self._idempotency_seen: Set[Tuple[str, str]] = set()  # (case_id, key)

    def append(self, event: DomainEvent):
        with self._lock:
            # Idempotency check: UNIQUE(case_id, idempotency_key)
            idem_tuple = (event.case_id, event.idempotency_key)
            if idem_tuple in self._idempotency_seen:
                return  # Silently deduplicate
            self._idempotency_seen.add(idem_tuple)

            # Concurrency-safe per-case sequence allocation
            current = self._case_sequences.get(event.case_id, 0)
            current += 1
            self._case_sequences[event.case_id] = current
            event.sequence = current

            self._events.append(event)

    def list_all(self) -> List[DomainEvent]:
        return list(self._events)

    def list_by_case(self, case_id: str) -> List[DomainEvent]:
        return sorted(
            [e for e in self._events if e.case_id == case_id],
            key=lambda e: e.sequence or 0,
        )

    def count(self) -> int:
        return len(self._events)

