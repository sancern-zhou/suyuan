"""Router registration extracted from app/main.py."""

from dataclasses import dataclass
from importlib import import_module

import structlog
from fastapi import FastAPI

logger = structlog.get_logger()


@dataclass(frozen=True)
class RouterSpec:
    """Declarative router registration entry."""

    module: str
    attr: str = "router"
    prefix: str | None = None
    optional: bool = False
    description: str = ""
    owner: str = "legacy"


ROUTER_REGISTRY = [
    RouterSpec(
        "app.api.project_config_routes",
        description="Project runtime configuration",
        owner="core",
    ),
    RouterSpec(
        "app.auth.routes",
        prefix="/api",
        description="Authentication support",
        owner="core",
    ),
    RouterSpec("app.routers.admin", description="Admin interface"),
    RouterSpec("app.routers.agent", description="ReAct Agent API"),
    RouterSpec("app.api.routes", prefix="/api", description="Basic API routes"),
    RouterSpec("app.api.query_dashboard_routes", prefix="/api", description="Query dashboard API"),
    RouterSpec("app.api.knowledge_base_routes", prefix="/api", description="Knowledge Base API"),
    RouterSpec("app.api.knowledge_graph_routes", prefix="/api", description="Knowledge Graph API"),
    RouterSpec("app.api.knowledge_scene_routes", prefix="/api", description="Knowledge Scene API"),
    RouterSpec("app.routers.report_generation", prefix="/api", description="Report generation"),
    RouterSpec("app.routers.expert_deliberation", prefix="/api", description="Expert deliberation"),
    RouterSpec("app.routers.monitoring", description="LLM monitoring"),
    RouterSpec("app.api.image_routes", prefix="/api", description="Image cache API"),
    RouterSpec("app.api.session_routes", description="Session management"),
    RouterSpec(
        "app.api.session_resource_routes",
        description="Session resource delivery",
        owner="core",
    ),
    RouterSpec("app.boards.routes", description="Draw.io board versions"),
    RouterSpec("app.routers.knowledge_qa", description="Knowledge QA"),
    RouterSpec("app.api.scheduled_task_routes", description="Scheduled tasks"),
    RouterSpec("app.api.scheduled_task_ws", description="Scheduled task WebSocket"),
    RouterSpec("app.api.upload_routes", prefix="/api/upload", description="File upload"),
    RouterSpec("app.api.voice_routes", prefix="/api", description="Voice ASR/TTS API"),
    RouterSpec("app.api.file_manager_routes", prefix="/api", description="File manager"),
    RouterSpec("app.routers.social_routes", description="Social platform management"),
    RouterSpec("app.routers.fetchers", description="Fetcher management"),
    RouterSpec(
        "app.api.social_account_routes",
        optional=True,
        description="Social account management",
    ),
    RouterSpec("app.api.skills_routes", optional=True, description="Skills management"),
    RouterSpec(
        "app.api.xuchang_air_quality_routes",
        description="Xuchang hourly air quality forecast",
        owner="xuchang-air-quality",
    ),
    # System routes are registered last to preserve app/main.py route ordering.
    RouterSpec("app.routers.system", description="System routes", owner="core"),
]


def select_router_specs(
    specs: list[RouterSpec],
    enabled_modules: frozenset[str],
) -> list[RouterSpec]:
    return [spec for spec in specs if spec.owner in enabled_modules]


def include_routers(app: FastAPI) -> None:
    """Register routers enabled by the selected project manifest."""
    from app.api.project_config_routes import get_project_context

    context = get_project_context()
    for spec in select_router_specs(ROUTER_REGISTRY, context.enabled_modules):
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
                owner=spec.owner,
                project=context.manifest.project,
                prefix=spec.prefix,
                description=spec.description,
            )
        except Exception as exc:
            if spec.optional:
                logger.warning(
                    "optional_router_registration_failed",
                    module=spec.module,
                    owner=spec.owner,
                    error=str(exc),
                )
                continue
            raise
