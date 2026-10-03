from enum import Enum
from pydantic import BaseModel, ConfigDict
from typing import List, Optional

class QualityVerdict(str, Enum):
    PASS = "pass"
    WARN = "warn"
    REJECT = "reject"

class DedupVerdict(str, Enum):
    KEEP = "keep"
    DUPLICATE = "duplicate"
    REVIEW = "review"

class QualityCheck(BaseModel):
    name: str
    passed: bool
    verdict: QualityVerdict
    message: Optional[str] = None

class QualityState(BaseModel):
    overall_verdict: QualityVerdict
    checks: List[QualityCheck] = []

    model_config = ConfigDict(extra="forbid")

class DedupState(BaseModel):
    verdict: DedupVerdict
    reason: Optional[str] = None
    duplicate_of: Optional[str] = None

    model_config = ConfigDict(extra="forbid")
