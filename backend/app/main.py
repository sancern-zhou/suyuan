"""Main FastAPI application for Atmospheric Environment Intelligent Analysis and Decision Support Platform."""

from contextlib import asynccontextmanager

import os
import structlog

from fastapi import FastAPI

from app.core.exception_handlers import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import configure_middleware
from app.core.routing import include_routers
from app.core.static_files import mount_static_files
from app.lifecycle.shutdown import run_shutdown
from app.lifecycle.startup import run_startup
from config.settings import settings


configure_logging()
logger = structlog.get_logger()

# LD_PRELOAD（由 restart_server.sh 注入）仅用于让本进程提前映射 torch 原生库，
# 规避 aarch64 静态 TLS 缺陷。主进程完成映射后必须从环境中移除，
# 否则会泄露到子进程：bubblewrap 沙箱、node 快照、quarto 等会因被迫加载
# CUDA 巨型库（如 libcublasLt.so.13）而启动失败。
if os.environ.pop("LD_PRELOAD", None):
    logger.info("ld_preload_cleared_for_child_processes")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    await run_startup(app)
    yield
    await run_shutdown(app)


# Create FastAPI app
app = FastAPI(
    title="Atmospheric Environment Intelligent Analysis and Decision Support API",
    description="Backend API for atmospheric environment analysis, source tracing, reporting, and decision support with LLM-powered insights",
    version="1.0.0",
    lifespan=lifespan,
    debug=settings.debug,
)

configure_middleware(app)
include_routers(app)
register_exception_handlers(app)
mount_static_files(app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
        proxy_headers=False,
    )
