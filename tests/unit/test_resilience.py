import pytest
import time
from varuna_infra.resilience import CircuitBreaker, CircuitState

def test_circuit_breaker_flow():
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=0.1, half_open_max=2)
    
    # Initially closed
    assert cb.can_execute() == True
    
    # Record 3 failures to open it
    cb.record_failure()
    cb.record_failure()
    cb.record_failure()
    
    assert cb.state == CircuitState.OPEN
    assert cb.can_execute() == False
    
    # Wait for recovery timeout
    time.sleep(0.15)
    
    # Now should transition to half open when we try to execute
    assert cb.can_execute() == True
    assert cb.state == CircuitState.HALF_OPEN
    
    # Record successes to close it
    cb.record_success()
    assert cb.state == CircuitState.HALF_OPEN
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    
    # Verify reset
    assert cb.failures == 0
