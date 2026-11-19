import hashlib
from typing import Optional, Dict
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel

class IdempotencyKey(BaseModel):
    key: str
    created_at: datetime
    
    @classmethod
    def generate(cls, operation: str, resource_id: str, parameters: dict) -> 'IdempotencyKey':
        payload = f"{operation}:{resource_id}:{str(parameters)}".encode('utf-8')
        hashed = hashlib.sha256(payload).hexdigest()
        return cls(key=hashed, created_at=datetime.now(timezone.utc))

class IdempotencyStore:
    def __init__(self, ttl_hours: int = 24):
        self._store: Dict[str, datetime] = {}
        self.ttl = timedelta(hours=ttl_hours)
        
    def check_and_set(self, idempotency_key: str) -> bool:
        """Returns True if the key is new (operation should proceed), False if already processed."""
        now = datetime.now(timezone.utc)
        
        # Cleanup expired
        to_delete = [k for k, v in self._store.items() if now - v > self.ttl]
        for k in to_delete:
            del self._store[k]
            
        if idempotency_key in self._store:
            return False
            
        self._store[idempotency_key] = now
        return True
