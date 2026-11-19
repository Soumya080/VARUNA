"""
VARUNA GRID — API Error Handlers.
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from varuna_infra.authorization import AuthorizationError

class CaseNotFoundError(Exception):
    def __init__(self, case_id: str):
        self.case_id = case_id

class InvalidStateTransitionError(Exception):
    def __init__(self, message: str):
        self.message = message

def register_error_handlers(app):
    @app.exception_handler(CaseNotFoundError)
    async def case_not_found_handler(request: Request, exc: CaseNotFoundError):
        return JSONResponse(
            status_code=404,
            content={"error": "not_found", "message": f"Case {exc.case_id} not found"},
        )

    @app.exception_handler(InvalidStateTransitionError)
    async def invalid_state_handler(request: Request, exc: InvalidStateTransitionError):
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_state", "message": exc.message},
        )

    @app.exception_handler(AuthorizationError)
    async def authorization_error_handler(request: Request, exc: AuthorizationError):
        # 403, not 404 or a generic 400: the resource exists and the
        # authenticated caller is simply not permitted. A single global
        # handler means every route that calls `varuna_infra.authorization
        # .authorize()` gets this translation for free, rather than each
        # router needing its own try/except AuthorizationError block.
        return JSONResponse(
            status_code=403,
            content={"error": "forbidden", "message": str(exc)},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": "http_error", "message": str(exc.detail)},
        )
