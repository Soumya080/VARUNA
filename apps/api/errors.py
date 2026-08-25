"""
VARUNA GRID — API Error Handlers.
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

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

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": "http_error", "message": str(exc.detail)},
        )
