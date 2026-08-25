"""
VARUNA GRID — In-memory repositories for local demo.
No PostgreSQL, Redis, or MinIO required.
"""
from typing import Dict, List, Optional
from varuna_domain.entities import Case, Artifact, DomainEvent


class InMemoryCaseRepository:
    def __init__(self):
        self._cases: Dict[str, Case] = {}

    def save(self, case: Case):
        self._cases[case.case_id] = case

    def get(self, case_id: str) -> Optional[Case]:
        return self._cases.get(case_id)

    def list_all(self) -> List[Case]:
        return list(self._cases.values())


class InMemoryArtifactRepository:
    def __init__(self):
        self._artifacts: Dict[str, Artifact] = {}

    def save(self, artifact: Artifact):
        self._artifacts[artifact.artifact_id] = artifact

    def get(self, artifact_id: str) -> Optional[Artifact]:
        return self._artifacts.get(artifact_id)

    def list_by_case(self, case_id: str) -> List[Artifact]:
        return [a for a in self._artifacts.values() if a.case_id == case_id]


class InMemoryEventStore:
    def __init__(self):
        self._events: List[DomainEvent] = []

    def append(self, event: DomainEvent):
        self._events.append(event)

    def list_all(self) -> List[DomainEvent]:
        return list(self._events)

    def list_by_case(self, case_id: str) -> List[DomainEvent]:
        return [e for e in self._events if e.case_id == case_id]

    def count(self) -> int:
        return len(self._events)
