from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends

from app.project_config.loader import load_project_context
from app.project_config.models import ProjectContext
from config.settings import settings

router = APIRouter(prefix="/api/project", tags=["project-config"])


@lru_cache(maxsize=1)
def get_project_context() -> ProjectContext:
    return load_project_context(settings.project_id)


ProjectContextDependency = Annotated[ProjectContext, Depends(get_project_context)]


@router.get("/runtime-config")
def runtime_project_config(context: ProjectContextDependency) -> dict:
    manifest = context.manifest
    return {
        "schemaVersion": manifest.schema_version,
        "project": manifest.project,
        "modules": sorted(context.enabled_modules),
        "frontend": manifest.frontend.model_dump(),
    }
