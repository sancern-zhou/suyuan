"""Business-facing scene discovery and confirmation APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.knowledge_base.chunk_repository import KnowledgeChunkRepository
from app.knowledge_base.models import KnowledgeBase
from app.knowledge_base.permissions import KnowledgeBasePermissions
from app.knowledge_base.scene_discovery import SceneDiscoveryError, SceneDiscoveryService
from app.knowledge_base.scene_repository import RepresentativeDocumentRequired, SceneRepository
from app.knowledge_base.scene_schemas import (
    SceneConfirmationRequest,
    SceneDiscoveryRequest,
    SceneDraft,
)
from app.knowledge_base.schema_compiler import SceneSchemaCompiler, SchemaCompilationError

router = APIRouter(prefix="/knowledge-base/{kb_id}/scene", tags=["Knowledge Scene"])


async def _manageable_kb(
    db: AsyncSession,
    kb_id: str,
    user_id: str | None,
    is_admin: bool,
) -> KnowledgeBase:
    kb = await db.get(KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    if not KnowledgeBasePermissions.can_manage(kb, user_id or "anonymous", is_admin):
        raise HTTPException(status_code=403, detail="No permission to manage this knowledge base")
    return kb


def _profile_data(profile) -> dict:
    return {
        "id": profile.id,
        "knowledge_base_id": profile.kb_id,
        "version": profile.version,
        "scene_goal": profile.scene_goal,
        "desired_questions": list(profile.desired_questions or []),
        "business_objects": list(profile.business_objects or []),
        "business_logic": list(profile.business_logic or []),
        "ignored_content": list(profile.ignored_content or []),
        "source_document_ids": list(profile.source_document_ids or []),
        "status": profile.status,
        "diagnostics": dict(profile.discovery_diagnostics or {}),
        "created_by": profile.created_by,
        "created_at": profile.created_at,
        "confirmed_at": profile.confirmed_at,
    }


def _scene_data(kb: KnowledgeBase, profile=None) -> dict:
    return {
        "knowledge_base_id": kb.id,
        "scene_status": kb.scene_status,
        "scene_profile_version": kb.scene_profile_version,
        "schema_version": kb.schema_version,
        "rule_version": kb.rule_version,
        "profile": _profile_data(profile) if profile else None,
    }


@router.get("")
async def get_scene(
    kb_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str | None = Header(default=None, alias="X-User-Id"),
    is_admin: bool = Header(default=False, alias="X-Is-Admin"),
):
    kb = await _manageable_kb(db, kb_id, user_id, is_admin)
    profile = await SceneRepository(db).get_current_profile(kb_id)
    return _scene_data(kb, profile)


@router.post("/discover")
async def discover_scene(
    kb_id: str,
    request: SceneDiscoveryRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str | None = Header(default=None, alias="X-User-Id"),
    is_admin: bool = Header(default=False, alias="X-Is-Admin"),
):
    await _manageable_kb(db, kb_id, user_id, is_admin)
    repository = SceneRepository(db)
    try:
        documents = await repository.require_representative_documents(kb_id)
        await repository.begin_discovery(kb_id, user_id or "anonymous")
        from app.services.llm_service import llm_service

        draft = await SceneDiscoveryService(
            llm=llm_service,
            chunk_repository=KnowledgeChunkRepository(db),
        ).discover(
            kb_id=kb_id,
            scene_goal=request.scene_goal,
            desired_questions=request.desired_questions,
            documents=documents,
        )
        profile = await repository.create_draft(kb_id, draft, user_id or "anonymous")
        return _profile_data(profile)
    except RepresentativeDocumentRequired as exc:
        raise HTTPException(status_code=409, detail="representative_document_required") from exc
    except SceneDiscoveryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/profiles/current")
async def get_current_profile(
    kb_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str | None = Header(default=None, alias="X-User-Id"),
    is_admin: bool = Header(default=False, alias="X-Is-Admin"),
):
    await _manageable_kb(db, kb_id, user_id, is_admin)
    profile = await SceneRepository(db).get_current_profile(kb_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Scene profile not found")
    return _profile_data(profile)


@router.post("/profiles/{profile_id}/confirm")
async def confirm_scene(
    kb_id: str,
    profile_id: str,
    request: SceneConfirmationRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str | None = Header(default=None, alias="X-User-Id"),
    is_admin: bool = Header(default=False, alias="X-Is-Admin"),
):
    kb = await _manageable_kb(db, kb_id, user_id, is_admin)
    repository = SceneRepository(db)
    profile = await repository.get_current_profile(kb_id)
    if profile is None or profile.id != profile_id:
        raise HTTPException(status_code=409, detail="stale_scene_profile")
    draft = SceneDraft(
        scene_goal=profile.scene_goal,
        desired_questions=list(profile.desired_questions or []),
        business_objects=request.business_objects,
        business_logic=request.business_logic,
        ignored_content=request.ignored_content,
        source_document_ids=list(profile.source_document_ids or []),
        diagnostics=dict(profile.discovery_diagnostics or {}),
    )
    try:
        schema = SceneSchemaCompiler().compile(draft)
        confirmed = await repository.confirm_profile(profile_id, schema)
    except SchemaCompilationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.refresh(kb)
    return {**_scene_data(kb, confirmed), **_profile_data(confirmed)}


@router.get("/suggestions")
async def list_suggestions(
    kb_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str | None = Header(default=None, alias="X-User-Id"),
    is_admin: bool = Header(default=False, alias="X-Is-Admin"),
):
    await _manageable_kb(db, kb_id, user_id, is_admin)
    suggestions = await SceneRepository(db).list_suggestions(kb_id)
    return {
        "suggestions": [
            {
                "id": item.id,
                "suggestion_type": item.suggestion_type,
                "payload": dict(item.payload or {}),
                "evidence": list(item.evidence or []),
                "status": item.status,
            }
            for item in suggestions
        ]
    }

