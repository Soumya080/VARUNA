"""
VARUNA GRID ?" Domain Ports (Repository Interfaces).
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Any, Dict
from varuna_domain.entities import Case, Artifact, DomainEvent


class CaseRepository(ABC):
    @abstractmethod
    def save(self, case: Case) -> None:
        pass

    @abstractmethod
    def get(self, case_id: str) -> Optional[Case]:
        pass

    @abstractmethod
    def list_all(self) -> List[Case]:
        pass


class ArtifactRepository(ABC):
    @abstractmethod
    def save(self, artifact: Artifact) -> None:
        pass

    @abstractmethod
    def get(self, artifact_id: str) -> Optional[Artifact]:
        pass

    @abstractmethod
    def list_by_case(self, case_id: str) -> List[Artifact]:
        pass


class EventRepository(ABC):
    @abstractmethod
    def append(self, event: DomainEvent) -> None:
        pass

    @abstractmethod
    def list_all(self) -> List[DomainEvent]:
        pass

    @abstractmethod
    def list_by_case(self, case_id: str) -> List[DomainEvent]:
        pass

    @abstractmethod
    def count(self) -> int:
        pass


class ObjectStore(ABC):
    @abstractmethod
    async def put(self, key: str, data: bytes, metadata: Dict[str, str]) -> str:
        pass

    @abstractmethod
    async def get(self, key: str) -> bytes:
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        pass

    @abstractmethod
    async def list_prefix(self, prefix: str) -> List[str]:
        pass
