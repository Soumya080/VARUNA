from pydantic import BaseModel, ConfigDict
from typing import Optional, Any, Protocol
from datetime import datetime, timezone
import uuid

class AuditEntry(BaseModel):
    audit_id: str
    timestamp: datetime
    user_id: Optional[str]
    role: Optional[str]
    action: str
    resource: str
    resource_id: Optional[str]
    request_id: Optional[str]
    ip: Optional[str]
    outcome: str
    details: dict[str, Any]
    
    model_config = ConfigDict(extra="forbid")
    
class AuditLogger(Protocol):
    def log(self, entry: AuditEntry) -> None:
        ...

class InMemoryAuditLogger(AuditLogger):
    def __init__(self):
        self.entries: list[AuditEntry] = []
        
    def log(self, entry: AuditEntry) -> None:
        self.entries.append(entry)

def create_audit_entry(
    action: str, 
    resource: str, 
    outcome: str, 
    user_id: Optional[str] = None,
    role: Optional[str] = None,
    resource_id: Optional[str] = None,
    request_id: Optional[str] = None,
    ip: Optional[str] = None,
    details: dict[str, Any] = None
) -> AuditEntry:
    return AuditEntry(
        audit_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        user_id=user_id,
        role=role,
        action=action,
        resource=resource,
        resource_id=resource_id,
        request_id=request_id,
        ip=ip,
        outcome=outcome,
        details=details or {}
    )
