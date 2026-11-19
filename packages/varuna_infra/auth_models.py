from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol

@dataclass
class User:
    user_id: str
    username: str
    password_hash: str
    role: str
    is_active: bool
    created_at: datetime

class UserRepository(Protocol):
    def create(self, username: str, password_hash: str, role: str) -> User:
        ...
        
    def get(self, user_id: str) -> Optional[User]:
        ...
        
    def get_by_username(self, username: str) -> Optional[User]:
        ...
