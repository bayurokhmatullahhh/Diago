"""Error handling konsisten: semua error mengembalikan format JSON yang sama."""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


def _body(code: str, message: str, request: Request, details=None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": getattr(request.state, "request_id", None),
        }
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exc(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            _body("http_error", str(exc.detail), request), status_code=exc.status_code
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exc(request: Request, exc: RequestValidationError):
        details = [
            {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
            for e in exc.errors()
        ]
        return JSONResponse(
            _body("validation_error", "Input tidak valid", request, details),
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def unhandled_exc(request: Request, exc: Exception):
        logger.exception("Unhandled error pada %s %s", request.method, request.url.path)
        return JSONResponse(
            _body("internal_error", "Terjadi kesalahan internal", request),
            status_code=500,
        )
