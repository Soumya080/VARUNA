import jwt
from datetime import datetime, timezone, timedelta
from typing import Optional
from pydantic import BaseModel
import uuid

class TokenPayload(BaseModel):
    sub: str       # user_id
    role: str
    exp: int
    iat: int
    jti: str       # unique token ID for audit

def create_access_token(user_id: str, role: str, secret_key: str, expires_delta: timedelta, algorithm: str = "HS256") -> str:
    now = datetime.now(timezone.utc)
    expire = now + expires_delta
    to_encode = {
        "sub": user_id,
        "role": role,
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp()),
        "jti": str(uuid.uuid4())
    }
    encoded_jwt = jwt.encode(to_encode, secret_key, algorithm=algorithm)
    return encoded_jwt

def verify_token(token: str, secret_key: str, algorithm: str = "HS256") -> Optional[TokenPayload]:
    try:
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        return TokenPayload(**payload)
    except jwt.PyJWTError:
        return None
