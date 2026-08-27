import pytest
from datetime import datetime
from varuna_infra.task_definition import TaskDefinition, TaskType
from varuna_infra.task_runner import TaskStatus
from varuna_infra.resilience import RetryPolicy
from varuna_infra.sync_runner import SyncTaskRunner

@pytest.fixture
def sync_runner():
    return SyncTaskRunner()

@pytest.fixture
def sample_task():
    return TaskDefinition(
        task_type=TaskType.NETRA_DETECT,
        case_id="case-123",
        correlation_id="corr-123",
        input_payload={"test": "data"},
        timeout_seconds=2,
        retry_policy=RetryPolicy(),
        idempotency_key="idemp-123"
    )

def test_sync_runner_success(sync_runner, sample_task):
    def success_handler(task: TaskDefinition):
        return {"status": "ok", "payload": task.input_payload}
        
    sync_runner.register_handler(TaskType.NETRA_DETECT, success_handler)
    
    task_id = sync_runner.submit(sample_task)
    result = sync_runner.get_result(task_id)
    
    assert result.status == TaskStatus.COMPLETED
    assert result.result == {"status": "ok", "payload": {"test": "data"}}
    assert result.case_id == "case-123"

def test_sync_runner_failure(sync_runner, sample_task):
    def failing_handler(task: TaskDefinition):
        raise ValueError("Simulated failure")
        
    sync_runner.register_handler(TaskType.NETRA_DETECT, failing_handler)
    
    task_id = sync_runner.submit(sample_task)
    result = sync_runner.get_result(task_id)
    
    assert result.status == TaskStatus.FAILED
    assert "Simulated failure" in result.error

def test_sync_runner_timeout(sync_runner, sample_task):
    import time
    def slow_handler(task: TaskDefinition):
        time.sleep(3)
        return "done"
        
    sync_runner.register_handler(TaskType.NETRA_DETECT, slow_handler)
    
    task_id = sync_runner.submit(sample_task)
    result = sync_runner.get_result(task_id)
    
    assert result.status == TaskStatus.TIMED_OUT
    assert result.error == "Task timed out"

def test_sync_runner_no_handler(sync_runner, sample_task):
    task_id = sync_runner.submit(sample_task)
    result = sync_runner.get_result(task_id)
    
    assert result.status == TaskStatus.FAILED
    assert "No handler registered" in result.error
