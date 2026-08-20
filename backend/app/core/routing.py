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
    requires_scheduled_tasks: bool = False


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
    RouterSpec("app.api.admin", description="Admin interface"),
    RouterSpec("app.api.agent", description="ReAct Agent API"),
    RouterSpec("app.api.routes", prefix="/api", description="Basic API routes"),
    RouterSpec("app.api.query_dashboard_routes", prefix="/api", description="Query dashboard API"),
    RouterSpec("app.api.knowledge_base_routes", prefix="/api", description="Knowledge Base API"),
    RouterSpec("app.api.knowledge_graph_routes", prefix="/api", description="Knowledge Graph API"),
    RouterSpec("app.api.knowledge_scene_routes", prefix="/api", description="Knowledge Scene API"),
    RouterSpec("app.api.report_generation", prefix="/api", description="Report generation"),
    RouterSpec("app.api.expert_deliberation", prefix="/api", description="Expert deliberation"),
    RouterSpec("app.api.monitoring", description="LLM monitoring"),
    RouterSpec("app.api.image_routes", prefix="/api", description="Image cache API"),
    RouterSpec("app.api.session_routes", description="Session management"),
    RouterSpec(
        "app.api.session_resource_routes",
        description="Session resource delivery",
        owner="core",
    ),
    RouterSpec("app.boards.routes", description="Draw.io board versions"),
    RouterSpec("app.api.knowledge_qa", description="Knowledge QA"),
    RouterSpec(
        "app.api.scheduled_task_routes",
        description="Scheduled tasks",
        requires_scheduled_tasks=True,
    ),
    RouterSpec(
        "app.api.scheduled_task_ws",
        description="Scheduled task WebSocket",
        requires_scheduled_tasks=True,
    ),
    RouterSpec("app.api.upload_routes", prefix="/api/upload", description="File upload"),
    RouterSpec("app.api.voice_routes", prefix="/api", description="Voice ASR/TTS API"),
    RouterSpec("app.api.file_manager_routes", prefix="/api", description="File manager"),
    RouterSpec("app.api.social_routes", description="Social platform management"),
    RouterSpec("app.api.fetchers", description="Fetcher management"),
    RouterSpec(
        "app.api.social_account_routes",
        optional=True,
        description="Social account management",
    ),
    RouterSpec("app.api.skills_routes", optional=True, description="Skills management"),
    RouterSpec("app.api.exam_routes", optional=True, description="Exam question review"),
    RouterSpec(
        "app.api.xuchang_air_quality_routes",
        description="Xuchang hourly air quality forecast",
        owner="xuchang-air-quality",
    ),
    RouterSpec(
        "app.api.jiangsu_work_order_routes",
        optional=True,
        description="Jiangsu fault work-order confirmation",
        owner="legacy",
    ),
    # System routes are registered last to preserve app/main.py route ordering.
    RouterSpec("app.api.system", description="System routes", owner="core"),
]


def select_router_specs(
    specs: list[RouterSpec],
    enabled_modules: frozenset[str],
    *,
    scheduled_tasks_enabled: bool = True,
) -> list[RouterSpec]:
    return [
        spec
        for spec in specs
        if spec.owner in enabled_modules
        and (scheduled_tasks_enabled or not spec.requires_scheduled_tasks)
    ]


def include_routers(app: FastAPI) -> None:
    """Register routers enabled by the selected project manifest."""
    from app.api.project_config_routes import get_project_context

    context = get_project_context()
    for spec in select_router_specs(
        ROUTER_REGISTRY,
        context.enabled_modules,
        scheduled_tasks_enabled=context.manifest.scheduled_tasks_enabled,
    ):
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
