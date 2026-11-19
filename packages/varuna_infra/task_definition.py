from typing import Any
from enum import StrEnum
from pydantic import BaseModel, ConfigDict
from .resilience import RetryPolicy

class TaskType(StrEnum):
    NETRA_DETECT = "netra_detect"
    CHHAYA_INVESTIGATE = "chhaya_investigate"
    PRATIVARTAN_RECONSTRUCT = "prativartan_reconstruct"
    NYAYA_ATTRIBUTE = "nyaya_attribute"
    PRAVAAH_FORECAST = "pravaah_forecast"
    ABHIYAN_PLAN = "abhiyan_plan"
    DATA_GUARD_EVALUATE = "data_guard_evaluate"
    TRAINING_NETRA = "training_netra"
    TRAINING_CHHAYA = "training_chhaya"
    EVALUATION_RUN = "evaluation_run"

class TaskDefinition(BaseModel):
    task_type: TaskType
    case_id: str
    correlation_id: str
    input_payload: dict[str, Any]
    timeout_seconds: int
    retry_policy: RetryPolicy
    idempotency_key: str
    priority: int = 0

    model_config = ConfigDict(extra="forbid")
