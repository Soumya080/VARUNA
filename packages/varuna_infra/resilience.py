from enum import StrEnum
from typing import Protocol, Dict, Any, Optional, Type
from pydantic import BaseModel, ConfigDict
import time

class RetryPolicy(BaseModel):
    max_retries: int = 0
    backoff_base: float = 2.0
    backoff_max: float = 60.0
    # retryable_exceptions could be a list of exception class names or omitted for now
    
    model_config = ConfigDict(extra="forbid")

class TimeoutPolicy(BaseModel):
    connect_timeout: float = 5.0
    read_timeout: float = 15.0
    total_timeout: float = 30.0
    
    model_config = ConfigDict(extra="forbid")

class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0, half_open_max: int = 2):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max = half_open_max
        
        self.state = CircuitState.CLOSED
        self.failures = 0
        self.last_failure_time = 0.0
        self.half_open_successes = 0
        
    def record_failure(self):
        self.failures += 1
        self.last_failure_time = time.time()
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
        elif self.failures >= self.failure_threshold:
            self.state = CircuitState.OPEN

    def record_success(self):
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_successes += 1
            if self.half_open_successes >= self.half_open_max:
                self.reset()
        elif self.state == CircuitState.CLOSED:
            self.failures = 0

    def reset(self):
        self.state = CircuitState.CLOSED
        self.failures = 0
        self.half_open_successes = 0

    def can_execute(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_successes = 0
                return True
            return False
        # HALF_OPEN
        return True

class HealthStatus(BaseModel):
    healthy: bool
    details: Dict[str, Any]
    
    model_config = ConfigDict(extra="forbid")

class HealthCheck(Protocol):
    def check(self) -> HealthStatus:
        ...
