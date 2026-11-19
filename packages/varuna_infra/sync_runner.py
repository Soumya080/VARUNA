import uuid
import threading
from datetime import datetime, timezone
from typing import Callable, Dict, Any

from .task_runner import TaskRunner, TaskResult, TaskStatus
from .task_definition import TaskDefinition, TaskType

class SyncTaskRunner(TaskRunner):
    """
    Executes tasks inline, no Redis/Celery dependency.
    Used for laptop mode and unit tests.
    """
    def __init__(self):
        self._handlers: Dict[TaskType, Callable[[TaskDefinition], Any]] = {}
        self._results: Dict[str, TaskResult] = {}
        
    def register_handler(self, task_type: TaskType, handler: Callable[[TaskDefinition], Any]) -> None:
        self._handlers[task_type] = handler
        
    def submit(self, task: TaskDefinition) -> str:
        task_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc)
        
        if task.task_type not in self._handlers:
            self._results[task_id] = TaskResult(
                task_id=task_id,
                case_id=task.case_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILED,
                error=f"No handler registered for {task.task_type}",
                started_at=started_at,
                completed_at=datetime.now(timezone.utc)
            )
            return task_id
            
        handler = self._handlers[task.task_type]
        
        result_container = {}
        
        def _run():
            try:
                res = handler(task)
                result_container['result'] = res
            except Exception as e:
                result_container['error'] = str(e)
                
        thread = threading.Thread(target=_run)
        thread.start()
        # Timeout if positive, else wait indefinitely
        timeout = task.timeout_seconds if task.timeout_seconds > 0 else None
        thread.join(timeout=timeout)
        
        completed_at = datetime.now(timezone.utc)
        
        if thread.is_alive():
            # Timed out
            self._results[task_id] = TaskResult(
                task_id=task_id,
                case_id=task.case_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.TIMED_OUT,
                error="Task timed out",
                started_at=started_at,
                completed_at=completed_at
            )
        elif 'error' in result_container:
            # Failed
            self._results[task_id] = TaskResult(
                task_id=task_id,
                case_id=task.case_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILED,
                error=result_container['error'],
                started_at=started_at,
                completed_at=completed_at
            )
        else:
            # Completed
            self._results[task_id] = TaskResult(
                task_id=task_id,
                case_id=task.case_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.COMPLETED,
                result=result_container.get('result'),
                started_at=started_at,
                completed_at=completed_at
            )
            
        return task_id
        
    def get_result(self, task_id: str) -> TaskResult:
        if task_id not in self._results:
            raise KeyError(f"Task {task_id} not found")
        return self._results[task_id]
        
    def cancel(self, task_id: str) -> bool:
        # Sync runner runs immediately, cannot be cancelled easily once started
        return False
