"""
STEP 7: the minimal real login path this repository has never had (see
`apps.api.security`'s own long-standing docstring, and
docs/product/AUTH_OPERATIONAL_COMPLETION_REPORT.md's diagnosis). Issues a
genuinely signed JWT via the pre-existing, previously-unused-in-production
`varuna_infra.auth.create_access_token`. The role in the token comes ONLY
from `varuna_infra.demo_users`'s server-side registry — the request body
has no role field, so a client cannot name its own privileges.
"""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from apps.api.config import settings
from apps.api.security import get_principal
from varuna_infra.auth import create_access_token
from varuna_infra.authorization import Principal
from varuna_infra.demo_users import authenticate

router = APIRouter(prefix="/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    expires_in_seconds: int


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest) -> LoginResponse:
    """Demo/local login against `varuna_infra.demo_users` — see that
    module's docstring for why this is not a production credential store.
    Same 401 for unknown username and wrong password, so a failed attempt
    cannot be used to enumerate valid accounts."""
    user = authenticate(body.username, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid username or password")

    expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
    token = create_access_token(
        user_id=user.username, role=user.role,
        secret_key=settings.jwt_secret_key, expires_delta=expires_delta,
        algorithm=settings.jwt_algorithm,
    )
    return LoginResponse(
        access_token=token, role=user.role,
        expires_in_seconds=int(expires_delta.total_seconds()),
    )


@router.get("/me")
def me(principal: Principal = Depends(get_principal)):
    """Lets the frontend restore/validate a stored session on page load
    without guessing whether a token is still good — a 401 here is the
    same signal `get_principal` already gives every other route."""
    return {"principal_id": principal.principal_id, "role": principal.role}
