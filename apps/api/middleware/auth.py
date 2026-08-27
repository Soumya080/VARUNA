from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Stub for Auth
        response = await call_next(request)
        return response
