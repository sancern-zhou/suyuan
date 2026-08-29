"""Exception handlers extracted from app/main.py."""

import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import structlog

logger = structlog.get_logger()


def register_exception_handlers(app: FastAPI) -> None:
    """Register global application exception handlers."""

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Return sanitized validation errors for malformed requests."""
        errors = exc.errors()
        logger.error(
            "request_validation_failed",
            path=request.url.path,
            method=request.method,
            errors=errors,
            error_count=len(errors),
        )
        # 回给客户端的错误不包含原始输入值（可能含口令等敏感字段）
        safe_errors = [
            {
                key: value
                for key, value in error.items()
                if key in {"type", "loc", "msg"}
            }
            for error in errors
        ]
        return JSONResponse(
            status_code=422,
            content={
                "detail": safe_errors,
                "message": "请求数据验证失败，请检查数据格式",
            },
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Return a consistent response for unhandled exceptions."""
        error_id = uuid.uuid4().hex[:12]
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            error_id=error_id,
            error=str(exc),
            exc_info=True,
        )

        # 异常原文可能包含内部路径/SQL/依赖细节，不回显给客户端
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Internal server error",
                "error_id": error_id,
            },
        )

