"""Router registration extracted from app/main.py."""

from dataclasses import dataclass
from importlib import import_module
from typing import Optional

from fastapi import FastAPI
import structlog

logger = structlog.get_logger()


@dataclass(frozen=True)
class RouterSpec:
    """Declarative router registration entry."""

    module: str
    attr: str = "router"
    prefix: Optional[str] = None
    optional: bool = False
    description: str = ""


ROUTER_REGISTRY = [
    RouterSpec("app.routers.admin", description="Admin interface"),
    RouterSpec("app.routers.agent", description="ReAct Agent API"),
    RouterSpec("app.api.routes", prefix="/api", description="Basic API routes"),
    RouterSpec("app.api.query_dashboard_routes", prefix="/api", description="Query dashboard API"),
    RouterSpec("app.api.knowledge_base_routes", prefix="/api", description="Knowledge Base API"),
    RouterSpec("app.api.knowledge_graph_routes", prefix="/api", description="Knowledge Graph API"),
    RouterSpec("app.api.cognitive_map_routes", description="Cognitive Map API"),
    RouterSpec("app.routers.report_generation", prefix="/api", description="Report generation"),
    RouterSpec("app.routers.expert_deliberation", prefix="/api", description="Expert deliberation"),
    RouterSpec("app.routers.monitoring", description="LLM monitoring"),
    RouterSpec("app.api.image_routes", prefix="/api", description="Image cache API"),
    RouterSpec("app.api.signed_media_routes", prefix="/api", description="Signed media API"),
    RouterSpec("app.api.utility_routes", prefix="/api", description="Utility API"),
    RouterSpec("app.api.session_routes", description="Session management"),
    RouterSpec("app.routers.knowledge_qa", description="Knowledge QA"),
    RouterSpec("app.api.scheduled_task_routes", description="Scheduled tasks"),
    RouterSpec("app.api.scheduled_task_ws", description="Scheduled task WebSocket"),
    RouterSpec("app.api.upload_routes", prefix="/api/upload", description="File upload"),
    RouterSpec("app.api.voice_routes", prefix="/api", description="Voice ASR/TTS API"),
    RouterSpec("app.api.office_routes", description="Office preview"),
    RouterSpec("app.api.report_routes", description="Quarto report preview/share"),
    RouterSpec("app.api.html_artifact_routes", description="HTML artifact preview/share"),
    RouterSpec("app.api.file_manager_routes", prefix="/api", description="File manager"),
    RouterSpec("app.routers.social_routes", description="Social platform management"),
    RouterSpec("app.routers.fetchers", description="Fetcher management"),
    RouterSpec(
        "app.api.social_account_routes",
        optional=True,
        description="Social account management",
    ),
    RouterSpec("app.api.skills_routes", optional=True, description="Skills management"),
    # System routes are registered last to preserve app/main.py route ordering.
    RouterSpec("app.routers.system", description="System routes"),
]


def include_routers(app: FastAPI) -> None:
    """Register all application routers from a centralized registry."""
    for spec in ROUTER_REGISTRY:
        try:
            module = import_module(spec.module)
            router = getattr(module, spec.attr)
            if spec.prefix:
                app.include_router(router, prefix=spec.prefix)
            else:
                app.include_router(router)
            logger.info(
                "router_registered",
                module=spec.module,
                prefix=spec.prefix,
                description=spec.description,
            )
        except Exception as e:
            if spec.optional:
                logger.warning(
                    "optional_router_registration_failed",
                    module=spec.module,
                    error=str(e),
                )
                continue
            raise
