import pytest
from varuna_infra.task_runner import TaskDefinition
from varuna_infra.sync_runner import SyncTaskRunner

def test_m5_production_pipeline_e2e():
    runner = SyncTaskRunner()
    
    def mock_task(task_def: TaskDefinition):
        return {"status": "success", "task_id": "test_id"}
        
    runner.register_handler("netra_detect", mock_task)
    
    task_def = TaskDefinition(
        task_type="netra_detect",
        case_id="c1",
        correlation_id="corr1",
        input_payload={"data": "test"},
        timeout_seconds=300,
        retry_policy={"max_retries": 3},
        idempotency_key="idemp1"
    )
    task_id = runner.submit(task_def)
    result = runner.get_result(task_id)
    
    assert result.status.value == "completed"
    assert result.result["task_id"] == "test_id"
