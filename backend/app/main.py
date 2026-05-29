"""Main FastAPI application for Atmospheric Environment Intelligent Analysis and Decision Support Platform."""

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

# Create FastAPI app
app = FastAPI(
    title="Atmospheric Environment Intelligent Analysis and Decision Support API",
    description="Backend API for atmospheric environment analysis, source tracing, reporting, and decision support with LLM-powered insights",
    version="1.0.0",
    debug=settings.debug,
)

configure_middleware(app)
include_routers(app)
register_exception_handlers(app)
mount_static_files(app)


@app.on_event("startup")
async def startup_event():
    """Startup event handler."""
    await run_startup(app)


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler."""
    await run_shutdown(app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
