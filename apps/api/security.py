"""
VARUNA GRID — API authentication boundary (Phase 5 of the VARUNA_PRODUCT_READY
hardening session).

Prior state: `apps/api/middleware/auth.py::AuthMiddleware` was a no-op that
called through to the next handler unconditionally, and the four
state-changing case endpoints (`POST /v1/cases`, `/ingest`, `/reconstruct`,
`/attribute`) had NO authorization check at all — not even the header-based
interim mechanism `apps/api/routers/missions.py` already used. This module is
the single place identity is resolved for every state-changing route, so that
gap cannot recur endpoint-by-endpoint.

Two paths, in order of preference:

1. `Authorization: Bearer <jwt>` — verified via `varuna_infra.auth.verify_token`
   (real HS256 signature check, real expiry check). This is the durable path.
2. `X-User-Id` / `X-User-Role` headers — unsigned, spoofable by anything that
   can set an HTTP header. Accepted ONLY when `settings.demo_mode` is true.
   No login/token-issuing endpoint exists in this repo yet (there is no user
   store to issue a JWT against), so gating the spoofable path behind
   `demo_mode` is what makes the JWT path meaningful outside a demo: turning
   `demo_mode` off refuses every unsigned identity claim rather than silently
   accepting it.

This intentionally does not invent a login endpoint or a user store — doing
so convincingly (password hashing, session/refresh-token lifecycle, a real
identity backing store) is out of scope for this hardening pass and was
explicitly flagged as a known gap by the session that first wrote the header
path. What this module closes is the narrower, concrete gap: a production
deployment with `demo_mode=False` can no longer be driven by an unsigned
header, and a real token-issuing service (when one exists) has a verified
path to plug into today.
"""
from __future__ import annotations

from fastapi import Header, HTTPException

from apps.api.config import settings
from varuna_infra.auth import verify_token
from varuna_infra.authorization import Principal


def get_principal(
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
) -> Principal:
    """Resolve the calling principal for a state-changing request.

    Raises 401 rather than returning None so a router cannot forget to check
    a null return — every caller of this dependency either gets a real
    `Principal` or the request never reaches the route body.
    """
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(
                status_code=401,
                detail="Authorization header must be 'Bearer <token>'",
            )
        payload = verify_token(token, settings.jwt_secret_key, settings.jwt_algorithm)
        if payload is None:
            raise HTTPException(status_code=401, detail="invalid or expired token")
        return Principal(principal_id=payload.sub, role=payload.role)

    if settings.demo_mode and x_user_id and x_user_role:
        return Principal(principal_id=x_user_id, role=x_user_role)

    if settings.demo_mode:
        raise HTTPException(
            status_code=401,
            detail="Authorization: Bearer <jwt> is required, or both "
                   "X-User-Id and X-User-Role headers (demo_mode only)",
        )
    raise HTTPException(
        status_code=401,
        detail="Authorization: Bearer <jwt> is required. Unsigned identity "
               "headers (X-User-Id/X-User-Role) are accepted only when "
               "demo_mode=true.",
    )
