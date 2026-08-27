from abc import ABC, abstractmethod
from typing import Callable, List
from varuna_contracts.schemas import BBox

class PrahariProvider(ABC):
    @abstractmethod
    def watch(self, region: BBox, callback: Callable[[str], None]) -> None:
        pass
        
    @abstractmethod
    def replay(self, scene_paths: List[str], callback: Callable[[str], None], delay_seconds: float = 5.0) -> None:
        pass
        
    @abstractmethod
    def stop(self) -> None:
        pass
        
    @property
    @abstractmethod
    def is_running(self) -> bool:
        pass
        
    @abstractmethod
    def schedule(self, cron_expr: str, callback: Callable[[], None]) -> str:
        """Schedule a task and return job ID."""
        pass
        
    @abstractmethod
    def cancel(self, job_id: str) -> None:
        """Cancel a scheduled job."""
        pass
