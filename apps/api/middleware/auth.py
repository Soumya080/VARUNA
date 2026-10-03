from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class AuthMiddleware(BaseHTTPMiddleware):
    """Intentional pass-through, not a stub left unfinished.

    Authorization is enforced per-route via `apps.api.security.get_principal`
    + `varuna_infra.authorization.authorize(...)` as a FastAPI dependency on
    every state-changing endpoint (see `apps/api/routers/cases.py` and
    `missions.py`). That is where enforcement belongs: a dependency can
    require a `Permission` specific to the operation and raise 401/403 with
    the right detail, whereas an ASGI middleware only sees the raw request
    and would either duplicate that per-route logic or fall back to a coarse
    all-or-nothing gate. This middleware is kept as an explicit extension
    point (request-scoped logging/tracing of the resolved principal, global
    rate limiting by identity) rather than removed, but it deliberately does
    not perform authorization itself — do not read its presence as evidence
    that a route is protected.
    """
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        return response
