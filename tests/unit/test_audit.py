import pytest
from varuna_infra.audit import InMemoryAuditLogger, create_audit_entry

def test_audit_logger():
    logger = InMemoryAuditLogger()
    entry = create_audit_entry(
        action="login",
        resource="auth",
        outcome="success",
        user_id="user1",
        ip="127.0.0.1"
    )
    logger.log(entry)
    
    assert len(logger.entries) == 1
    assert logger.entries[0].action == "login"
    assert logger.entries[0].user_id == "user1"
    assert logger.entries[0].audit_id is not None
