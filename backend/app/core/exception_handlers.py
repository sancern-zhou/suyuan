"""Exception handlers extracted from app/main.py."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import structlog

logger = structlog.get_logger()


def register_exception_handlers(app: FastAPI) -> None:
    """Register global application exception handlers."""

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Return detailed validation errors for malformed requests."""
        errors = exc.errors()
        logger.error(
            "request_validation_failed",
            path=request.url.path,
            method=request.method,
            errors=errors,
            error_count=len(errors),
        )
        return JSONResponse(
            status_code=422,
            content={
                "detail": errors,
                "message": "请求数据验证失败，请检查数据格式",
            },
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Return a consistent response for unhandled exceptions."""
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            exc_info=True,
        )

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"Internal server error: {str(exc)}",
            },
        )

