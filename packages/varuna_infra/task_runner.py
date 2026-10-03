from __future__ import annotations
from typing import Any, Optional, Protocol
from datetime import datetime
from enum import StrEnum
from pydantic import BaseModel, ConfigDict

from .task_definition import TaskDefinition

class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"

class TaskResult(BaseModel):
    task_id: str
    case_id: str
    correlation_id: str
    status: TaskStatus
    result: Optional[Any] = None
    error: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

class TaskRunner(Protocol):
    def submit(self, task: TaskDefinition) -> str:
        """Submit a task for execution and return its task_id."""
        ...
        
    def get_result(self, task_id: str) -> TaskResult:
        """Retrieve the result of a task."""
        ...
        
    def cancel(self, task_id: str) -> bool:
        """Cancel a running or pending task."""
        ...
