"""Runtime CRUD for coordinator quick prompts (常用问题).

Two surfaces are served from the same table:

- ``home``: coordinator home page quick prompts. Read by any authenticated
  user at ``GET /api/project/coordinator/quick-prompts``; seeded from the
  manifest's ``frontend.coordinator.quick_prompts`` when empty.
- ``input``: per-agent-mode suggestions above the chat input box. Read with
  ``?surface=input``; seeded from ``INPUT_QUICK_PROMPT_DEFAULTS`` (mirroring
  the lists that used to be hardcoded in ``InputBox.vue``) when empty.

Admin CRUD lives under ``/api/admin/coordinator/quick-prompts`` guarded by
``require_admin_user``. Modes must be declared in the project manifest's
``frontend.agent_modes``, mirroring the build-time validation in
``app.project_config.models``.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
import structlog

from app.api.project_config_routes import ProjectContextDependency
from app.auth.dependencies import require_admin_user, require_current_user
from app.auth.models import CurrentUser
from app.db.repositories.coordinator_quick_prompt_repo import (
    CoordinatorQuickPromptRepository,
    QuickPromptConflict,
)
from app.project_config.models import ProjectContext

logger = structlog.get_logger()

SURFACES = ("home", "input")
MAX_HOME_QUICK_PROMPTS = 10
MAX_INPUT_QUICK_PROMPTS_PER_MODE = 8
MAX_LABEL_LENGTH = 30
MAX_PROMPT_LENGTH = 500

# Formerly hardcoded in InputBox.vue per agent mode; seeded into the input
# surface when a project has no input-surface rows yet. label doubles as the
# composer fill text.
INPUT_QUICK_PROMPT_DEFAULTS: dict[str, list[str]] = {
    "smart_event_external": ["今日识别结果", "每周事件统计", "待办统计", "数据影响诊断"],
    "smart_event_instrument": ["今日故障识别结果", "故障原因研判", "历史故障查询", "故障响应跟踪"],
    "ops": ["查询本周的故障工单审核情况", "对今天的待审核故障工单进行审核", "对上周的例行工单进行审核"],
    "smart_inspection": ["执行全网巡检", "对高淳淳溪站点巡检"],
    "operations_analysis": ["运维风险监管分析", "日常运维监管分析"],
    "jiangsu_query": [
        "南京有哪些省控站点",
        "站点的运维单位和运维负责人",
        "苏力有运维哪些站点",
        "苏力的运维人员信息",
    ],
}

router = APIRouter(prefix="/api/project/coordinator", tags=["project-config"])
admin_router = APIRouter(
    prefix="/api/admin/coordinator",
    tags=["admin"],
    dependencies=[Depends(require_admin_user)],
)

repo = CoordinatorQuickPromptRepository()


class QuickPromptPayload(BaseModel):
    label: str = Field(min_length=1, max_length=MAX_LABEL_LENGTH)
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_LENGTH)
    mode: str | None = None
    surface: str = "home"


class QuickPromptPatch(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=MAX_LABEL_LENGTH)
    prompt: str | None = Field(default=None, min_length=1, max_length=MAX_PROMPT_LENGTH)
    mode: str | None = None
    enabled: bool | None = None


class QuickPromptReorder(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ordered_ids: list[int] = Field(min_length=1, alias="orderedIds")
    surface: str = "home"
    mode: str | None = None


def _normalize_mode(mode: str | None) -> str | None:
    normalized = (mode or "").strip()
    return normalized or None


def _validated_surface(surface: str) -> str:
    if surface not in SURFACES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown surface: {surface}",
        )
    return surface


async def _validated_mode(
    mode: str | None, context: ProjectContext, *, required: bool = False
) -> str | None:
    normalized = _normalize_mode(mode)
    if normalized is None:
        if required:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="mode is required for input-surface quick prompts",
            )
        return None
    declared = context.manifest.frontend.agent_modes
    if normalized not in declared:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown agent mode: {normalized}",
        )
    return normalized


def _serialize(row) -> dict:
    return {
        "id": row.id,
        "surface": row.surface,
        "label": row.label,
        "prompt": row.prompt,
        "mode": row.mode,
        "sortOrder": row.sort_order,
        "enabled": row.enabled,
        "updatedBy": row.updated_by,
        "updatedAt": row.updated_at.isoformat(timespec="seconds") if row.updated_at else None,
    }


def _manifest_modes(context: ProjectContext) -> list[dict]:
    frontend = context.manifest.frontend
    overrides = frontend.agent_mode_overrides or {}
    return [
        {
            "id": mode,
            "name": (overrides.get(mode) or {}).get("name") or mode,
            "shortName": (overrides.get(mode) or {}).get("short_name") or mode,
        }
        for mode in frontend.agent_modes
    ]


async def _ensure_seeded(context: ProjectContext, surface: str) -> None:
    project = context.manifest.project
    if surface == "home":
        coordinator = context.manifest.frontend.coordinator
        entries = [
            {"label": entry.label, "prompt": entry.prompt, "mode": entry.mode}
            for entry in (coordinator.quick_prompts if coordinator else [])
        ]
        await repo.seed_defaults(project, surface, entries)
        return
    entries = [
        {"label": text, "prompt": text, "mode": mode}
        for mode, texts in INPUT_QUICK_PROMPT_DEFAULTS.items()
        for text in texts
    ]
    await repo.seed_defaults(project, surface, entries)


@router.get("/quick-prompts")
async def get_quick_prompts(
    context: ProjectContextDependency,
    user: CurrentUser = Depends(require_current_user),
    surface: str = Query("home"),
) -> dict:
    _validated_surface(surface)
    await _ensure_seeded(context, surface)
    rows = await repo.list_prompts(
        context.manifest.project, surface=surface, enabled_only=True
    )
    return {"items": [_serialize(row) for row in rows]}


@admin_router.get("/quick-prompts")
async def admin_list_quick_prompts(context: ProjectContextDependency) -> dict:
    project = context.manifest.project
    for surface in SURFACES:
        await _ensure_seeded(context, surface)
    rows = await repo.list_prompts(project)
    return {"items": [_serialize(row) for row in rows], "modes": _manifest_modes(context)}


@admin_router.post("/quick-prompts", status_code=status.HTTP_201_CREATED)
async def admin_create_quick_prompt(
    payload: QuickPromptPayload,
    context: ProjectContextDependency,
    user: CurrentUser = Depends(require_admin_user),
) -> dict:
    project = context.manifest.project
    surface = _validated_surface(payload.surface)
    mode = await _validated_mode(payload.mode, context, required=surface == "input")
    if surface == "home":
        existing = await repo.list_prompts(project, surface=surface)
        if len(existing) >= MAX_HOME_QUICK_PROMPTS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"home quick prompts are limited to {MAX_HOME_QUICK_PROMPTS} entries",
            )
    else:
        existing = await repo.list_prompts(project, surface=surface, mode=mode)
        if len(existing) >= MAX_INPUT_QUICK_PROMPTS_PER_MODE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"input quick prompts per mode are limited to "
                    f"{MAX_INPUT_QUICK_PROMPTS_PER_MODE} entries"
                ),
            )
    try:
        row = await repo.create_prompt(
            project,
            surface=surface,
            label=payload.label.strip(),
            prompt=payload.prompt.strip(),
            mode=mode,
            updated_by=user.display_name or user.username,
        )
    except QuickPromptConflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"label already exists: {payload.label.strip()}",
        )
    logger.info(
        "coordinator_quick_prompt_created",
        project=project,
        surface=surface,
        prompt_id=row.id,
        by=user.username,
    )
    return {"item": _serialize(row)}


@admin_router.put("/quick-prompts/{prompt_id}")
async def admin_update_quick_prompt(
    prompt_id: int,
    payload: QuickPromptPatch,
    context: ProjectContextDependency,
    user: CurrentUser = Depends(require_admin_user),
) -> dict:
    project = context.manifest.project
    row_before = await repo.get_prompt(project, prompt_id)
    if row_before is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"quick prompt not found: {prompt_id}",
        )
    mode = await _validated_mode(
        payload.mode, context, required=row_before.surface == "input"
    )
    try:
        row = await repo.update_prompt(
            project,
            prompt_id,
            label=payload.label.strip() if payload.label is not None else None,
            prompt=payload.prompt.strip() if payload.prompt is not None else None,
            mode=mode,
            mode_changed="mode" in payload.model_fields_set,
            enabled=payload.enabled,
            updated_by=user.display_name or user.username,
        )
    except QuickPromptConflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"label already exists: {payload.label.strip()}",
        )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"quick prompt not found: {prompt_id}",
        )
    logger.info(
        "coordinator_quick_prompt_updated",
        project=project,
        prompt_id=prompt_id,
        by=user.username,
    )
    return {"item": _serialize(row)}


@admin_router.post("/quick-prompts/reorder")
async def admin_reorder_quick_prompts(
    payload: QuickPromptReorder,
    context: ProjectContextDependency,
    user: CurrentUser = Depends(require_admin_user),
) -> dict:
    project = context.manifest.project
    surface = _validated_surface(payload.surface)
    mode = _normalize_mode(payload.mode)
    if surface == "home" and mode is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="home quick prompts are ordered as one flat list",
        )
    if not await repo.reorder_prompts(
        project, payload.ordered_ids, surface=surface, mode=mode
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ordered_ids must exactly match the quick prompt ids in the scope",
        )
    logger.info(
        "coordinator_quick_prompts_reordered",
        project=project,
        surface=surface,
        mode=mode,
        by=user.username,
    )
    rows = await repo.list_prompts(project, surface=surface, mode=mode)
    return {"items": [_serialize(row) for row in rows]}


@admin_router.delete("/quick-prompts/{prompt_id}")
async def admin_delete_quick_prompt(
    prompt_id: int,
    context: ProjectContextDependency,
    user: CurrentUser = Depends(require_admin_user),
) -> dict:
    project = context.manifest.project
    if not await repo.delete_prompt(project, prompt_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"quick prompt not found: {prompt_id}",
        )
    logger.info(
        "coordinator_quick_prompt_deleted",
        project=project,
        prompt_id=prompt_id,
        by=user.username,
    )
    return {"success": True}
