"""
会话管理API路由

提供会话保存、恢复、列表、删除等API端点。
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from typing import Optional, Any, Dict, List
from datetime import datetime
import mimetypes
from pathlib import Path
import structlog

from app.agent.session import get_session_manager
from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser
from app.conversations import ConversationSource
from app.conversations.adapters import (
    ConversationAdapterRegistry,
    get_conversation_adapters,
)
from app.conversations.dependencies import get_conversation_catalog
from app.conversations.service import ConversationCatalogService
from app.boards.application import BoardApplicationService
from app.boards.service import BoardNotFound, BoardVersionNotFound
from app.db.database import async_session
from app.agent.resources.resource_service import SessionResourceService
from app.utils.path_config import get_data_registry

logger = structlog.get_logger()

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


ARTIFACT_KEYS = {"visuals", "pdf_preview", "markdown_preview", "html_preview", "svg_preview", "spreadsheet_preview"}
SESSION_LIST_DEFAULT_LIMIT = 200
SESSION_LIST_MAX_LIMIT = 200


def _strip_lazy_artifacts(obj: Any) -> Any:
    """Return a copy with heavyweight visualization/document preview payloads removed."""
    if isinstance(obj, list):
        return [_strip_lazy_artifacts(item) for item in obj]
    if isinstance(obj, dict):
        stripped = {}
        for key, value in obj.items():
            if key in ARTIFACT_KEYS:
                if key == "visuals" and isinstance(value, list):
                    stripped["visuals_count"] = len(value)
                elif key.endswith("_preview") and isinstance(value, dict):
                    stripped[f"{key}_available"] = True
                continue
            stripped[key] = _strip_lazy_artifacts(value)
        return stripped
    return obj


def _extract_visualizations_from_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    visuals: List[Dict[str, Any]] = []
    seen_ids = set()

    def add_visuals(items: Any) -> None:
        if not isinstance(items, list):
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            payload = item.get("payload")
            visual_id = item.get("id") or (payload.get("id") if isinstance(payload, dict) else None)
            if visual_id and visual_id in seen_ids:
                continue
            if visual_id:
                seen_ids.add(visual_id)
            visuals.append(item)

    for msg in messages:
        if msg.get("type") != "tool_result":
            continue
        data = msg.get("data") or {}
        result = data.get("result") or {}
        results = data.get("results") or []

        add_visuals(result.get("visuals"))
        inner_data = result.get("data") if isinstance(result, dict) else None
        if isinstance(inner_data, dict):
            add_visuals(inner_data.get("visuals"))
        tool_results = result.get("tool_results") if isinstance(result, dict) else None
        for tool_result in tool_results if isinstance(tool_results, list) else []:
            if not isinstance(tool_result, dict):
                continue
            tool_result_payload = tool_result.get("result")
            if isinstance(tool_result_payload, dict):
                add_visuals(tool_result_payload.get("visuals"))
                tool_result_data = tool_result_payload.get("data")
                if isinstance(tool_result_data, dict):
                    add_visuals(tool_result_data.get("visuals"))
        for item in results if isinstance(results, list) else []:
            if not isinstance(item, dict):
                continue
            add_visuals(item.get("visuals"))
            item_data = item.get("data")
            if isinstance(item_data, dict):
                add_visuals(item_data.get("visuals"))

    return visuals


def _extract_office_documents_from_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    documents: List[Dict[str, Any]] = []

    for msg in messages:
        if msg.get("type") != "tool_result":
            continue
        result = (msg.get("data") or {}).get("result") or {}
        result_data = result.get("data") if isinstance(result, dict) else None
        if not isinstance(result_data, dict):
            continue

        pdf_preview = result_data.get("pdf_preview")
        markdown_preview = result_data.get("markdown_preview")
        html_preview = result_data.get("html_preview")
        svg_preview = result_data.get("svg_preview")
        spreadsheet_preview = result_data.get("spreadsheet_preview")
        if not (pdf_preview or markdown_preview or html_preview or svg_preview or spreadsheet_preview):
            continue

        document = {
            "file_name": result_data.get("file_name"),
            "file_path": result_data.get("file_path")
                or result_data.get("path")
                or (pdf_preview or {}).get("pdf_path")
                or (svg_preview or {}).get("svg_path")
                or (html_preview or {}).get("html_id"),
            "file_type": result_data.get("file_type")
                or (html_preview or {}).get("file_type")
                or (svg_preview or {}).get("file_type")
                or (spreadsheet_preview or {}).get("file_type"),
            "generator": result_data.get("generator")
                or (result.get("metadata") or {}).get("generator")
                or "document",
            "summary": result.get("summary"),
            "timestamp": msg.get("timestamp"),
        }
        if pdf_preview:
            document["pdf_preview"] = pdf_preview
        if markdown_preview:
            document["markdown_preview"] = markdown_preview
        if html_preview:
            document["html_preview"] = html_preview
        if svg_preview:
            document["svg_preview"] = svg_preview
        if spreadsheet_preview:
            document["spreadsheet_preview"] = spreadsheet_preview
        for key in ("related_files", "artifacts", "refs", "assets"):
            value = result_data.get(key)
            if value:
                document[key] = value
        documents.append(document)

    return documents


@router.get("/")
@router.get("")  # 同时支持不带斜杠的请求
async def list_sessions(
    limit: Optional[int] = None,
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
):
    """
    列出所有会话

    Args:
        limit: 限制数量

    Returns:
        会话列表
    """
    effective_limit = min(limit or SESSION_LIST_DEFAULT_LIMIT, SESSION_LIST_MAX_LIMIT)

    rows = await catalog.list_visible(user, limit=effective_limit)
    web_session_ids = [
        row.session_id
        for row in rows
        if row.source == ConversationSource.WEB
    ]
    web_metadata = {}
    if web_session_ids:
        from app.db.session_repository import get_session_repository

        web_metadata = await get_session_repository().get_session_summary_metadata(
            web_session_ids
        )

    sessions = []
    for row in rows:
        metadata = dict(web_metadata.get(row.session_id, {}))
        if row.mode:
            metadata["mode"] = row.mode
        sessions.append({
            "session_id": row.session_id,
            "query": row.title or "",
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
            "data_count": 0,
            "visual_count": 0,
            "has_error": False,
            "metadata": metadata,
            **row.model_dump(mode="json"),
        })

    return {
        "sessions": sessions,
        "total": len(sessions)
    }


@router.get("/stats")
async def get_session_stats(
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
):
    """
    获取会话统计信息

    Returns:
        统计信息
    """
    rows = await catalog.list_visible(user, limit=10000)
    return {
        "total": len(rows),
        "total_data_count": 0,
        "total_visual_count": 0,
        "error_count": 0,
    }


@router.get("/active")
async def get_active_sessions(
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
):
    """
    获取所有活跃会话

    Returns:
        活跃会话列表
    """
    session_manager = get_session_manager()
    sessions = await session_manager.get_active_sessions()
    visible = {
        row.session_id: row
        for row in await catalog.list_visible(user, limit=10000)
    }
    sessions = [session for session in sessions if session.session_id in visible]

    return {
        "sessions": [
            {
                **session.model_dump(mode="json"),
                **visible[session.session_id].model_dump(mode="json"),
            }
            for session in sessions
        ],
        "total": len(sessions)
    }


@router.get("/{session_id}")
async def get_session(
    session_id: str,
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
    adapters: ConversationAdapterRegistry = Depends(get_conversation_adapters),
):
    """
    获取会话详情

    Args:
        session_id: 会话ID

    Returns:
        会话详情
    """
    row = await catalog.require_read(session_id, user)
    session = await adapters.get(row.source).get(row)

    if not session:
        raise HTTPException(status_code=404, detail="session_not_found")

    return session


@router.post("/{session_id}/save")
async def save_session(
    session_id: str,
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
):
    """
    手动保存会话

    Args:
        session_id: 会话ID

    Returns:
        保存结果
    """
    await catalog.require_write(session_id, user)
    session_manager = get_session_manager()
    session = await session_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    success = await session_manager.save_session_metadata(session)

    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to save session: {session_id}")

    return {"message": f"Session {session_id} saved successfully"}


@router.post("/{session_id}/case")
async def mark_session_case(
    session_id: str,
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
):
    """Mark a session as a demo case."""
    await catalog.require_write(session_id, user)
    session_manager = get_session_manager()
    session = await session_manager.load_session(session_id, include_messages=False)

    if not session:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    session.metadata = {
        **(session.metadata or {}),
        "is_case": True,
        "case_marked_at": datetime.now().isoformat()
    }

    success = await session_manager.save_session_metadata(session, update_timestamp=False)
    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to mark session case: {session_id}")

    logger.info("session_marked_as_case", session_id=session_id)
    return {
        "message": f"Session {session_id} marked as case",
        "session": session.model_dump(mode='json')
    }


@router.delete("/{session_id}/case")
async def unmark_session_case(
    session_id: str,
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
):
    """Remove a session from the demo case library."""
    await catalog.require_write(session_id, user)
    session_manager = get_session_manager()
    session = await session_manager.load_session(session_id, include_messages=False)

    if not session:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    metadata = dict(session.metadata or {})
    metadata["is_case"] = False
    metadata.pop("case_marked_at", None)
    session.metadata = metadata

    success = await session_manager.save_session_metadata(session, update_timestamp=False)
    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to unmark session case: {session_id}")

    logger.info("session_unmarked_as_case", session_id=session_id)
    return {
        "message": f"Session {session_id} removed from case library",
        "session": session.model_dump(mode='json')
    }


@router.get("/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    before: Optional[int] = None,
    limit: int = 30,
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
    adapters: ConversationAdapterRegistry = Depends(get_conversation_adapters),
):
    """
    分页获取会话消息

    Args:
        session_id: 会话ID
        before: 游标，加载 sequence_number < before 的消息（不传则返回最新消息）
        limit: 每次加载数量，默认30

    Returns:
        消息列表、是否还有更多、总消息数
    """
    row = await catalog.require_read(session_id, user)
    if row.source != ConversationSource.WEB:
        restored = await adapters.get(row.source).restore(
            row, message_limit=limit, lazy_artifacts=True
        )
        if not restored:
            raise HTTPException(status_code=404, detail="session_not_found")
        payload = restored.get("normalized_session") or {}
        messages = payload.get("conversation_history") or []
        return {
            "messages": messages,
            "has_more": bool(payload.get("has_more_messages")),
            "total_count": payload.get("total_message_count", len(messages)),
            "oldest_sequence": payload.get("oldest_sequence"),
        }
    from app.db.session_repository import get_session_repository

    repo = get_session_repository()

    # 先验证会话是否存在
    session = await repo.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    result = await repo.get_messages_before(
        session_id=session_id,
        before_sequence=before,
        limit=limit
    )

    return result


@router.get("/{session_id}/resources")
async def get_session_resources(
    session_id: str,
    kind: Optional[str] = None,
    presentation_type: Optional[str] = None,
    role: Optional[str] = None,
    status: str = "active",
    limit: int = 100,
    cursor: Optional[str] = None,
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
):
    """List the single authoritative resource collection for a session."""
    await catalog.require_read(session_id, user)
    try:
        page = await SessionResourceService.database().list_resources(
            session_id,
            kind=kind,
            presentation_type=presentation_type,
            role=role,
            status=status,
            limit=min(max(limit, 1), 200),
            cursor=cursor,
        )
        resources = [
            {
                "ref_id": item.resource_id,
                "resource_id": item.resource_id,
                "resource_key": item.resource_key,
                "kind": item.kind,
                "role": item.role,
                "label": item.label,
                "locator": item.locator,
                "presentation_type": item.presentation_type,
                "presentation": item.presentation,
                "metadata": item.metadata,
                "tool_name": item.tool_name,
                "run_id": item.run_id,
                "turn_sequence": item.turn_sequence,
                "status": item.status,
                "created_at": item.created_at.isoformat(),
                "updated_at": item.updated_at.isoformat(),
            }
            for item in page.resources
        ]
    except Exception as exc:
        logger.error("session_resources_load_failed", session_id=session_id, error=str(exc))
        raise HTTPException(status_code=503, detail="resource_manifest_unavailable") from exc
    return {
        "session_id": session_id,
        "resources": resources,
        "total": len(resources),
        "next_cursor": page.next_cursor,
    }


@router.get("/{session_id}/resources/{resource_id}/content")
async def get_session_resource_content(
    session_id: str,
    resource_id: str,
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
):
    """Serve one authorized file resource without exposing its storage locator."""
    await catalog.require_read(session_id, user)
    resource = await SessionResourceService.database().get_resource(
        session_id,
        resource_id,
        status="active",
    )
    if resource is None or resource.kind not in {"file", "artifact"}:
        raise HTTPException(status_code=404, detail="resource_not_found")

    path_value = (resource.locator or {}).get("path")
    if not path_value:
        raise HTTPException(status_code=404, detail="resource_content_unavailable")
    path = Path(str(path_value)).expanduser().resolve()
    registry_root = get_data_registry().resolve()
    if not path.is_relative_to(registry_root):
        raise HTTPException(status_code=403, detail="resource_path_forbidden")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="resource_content_missing")

    media_type = str((resource.metadata or {}).get("mime_type") or "")
    if not media_type:
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    inline = (
        media_type.startswith(("image/", "audio/", "video/"))
        or media_type == "application/pdf"
    )
    response_options = {
        "path": path,
        "media_type": media_type,
        "headers": {
            "Cache-Control": "private, max-age=300, immutable",
            "X-Content-Type-Options": "nosniff",
        },
    }
    if not inline:
        response_options["filename"] = resource.label or path.name
    return FileResponse(**response_options)


@router.get("/{session_id}/drawio-board")
async def get_session_drawio_board(
    session_id: str,
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
):
    """
    按需获取会话 Draw.io 画板状态。

    restore 接口默认不返回画板 XML，避免首屏携带大块可编辑画布数据。
    """
    row = await catalog.require_read(session_id, user)
    if row.source != ConversationSource.WEB:
        return {
            "session_id": session_id,
            "drawio_board": None,
            "has_drawio_board": False,
        }
    from app.db.session_repository import get_session_repository

    repo = get_session_repository()
    metadata = await repo.get_session_metadata(session_id)
    if metadata is None:
        session = await repo.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
        metadata = {}

    drawio_board = metadata.get("drawio_board") if isinstance(metadata, dict) else None
    if not isinstance(drawio_board, dict):
        drawio_board = None

    try:
        legacy_xml = (
            drawio_board.get("current_xml")
            or drawio_board.get("currentXml")
            or drawio_board.get("xml")
            if isinstance(drawio_board, dict)
            else None
        )
        snapshot = await BoardApplicationService(async_session).load_session_board(
            session_id,
            legacy_title=(drawio_board or {}).get("title"),
            legacy_xml=legacy_xml,
        )
        if snapshot is None and drawio_board:
            raise BoardNotFound(str(drawio_board.get("board_id") or session_id))
        if snapshot is not None:
            is_candidate = snapshot.lifecycle_status == "candidate"
            drawio_board = {
                "artifact_kind": "drawio_board",
                "board_id": snapshot.board_id,
                "active_board_id": snapshot.board_id,
                "title": snapshot.title,
                "current_xml": snapshot.xml,
                "version": snapshot.version_number,
                "revision": snapshot.revision,
                "lifecycle_status": snapshot.lifecycle_status,
                "preview_candidate": is_candidate,
                "requires_visual_review": is_candidate,
                "candidate_version_id": snapshot.version_id if is_candidate else None,
                "current_version_id": snapshot.current_version_id,
                "base_version_id": snapshot.current_version_id,
                "xml_sha256": snapshot.xml_sha256,
                "quality_status": snapshot.quality_status,
                "quality_report": snapshot.quality_report,
                "screenshot_ref": snapshot.screenshot_ref,
                "selected_cells": (drawio_board or {}).get("selected_cells") or [],
                "dirty": False,
                "updated_at": snapshot.updated_at,
                "has_board_versions": True,
            }
            lightweight_metadata = dict(metadata or {})
            lightweight_metadata["drawio_board"] = {
                key: drawio_board[key]
                for key in (
                    "artifact_kind", "board_id", "active_board_id", "title",
                    "version", "revision", "lifecycle_status", "preview_candidate",
                    "requires_visual_review", "candidate_version_id",
                    "current_version_id", "updated_at",
                )
            }
            if lightweight_metadata != metadata:
                await repo.update_session(session_id, metadata=lightweight_metadata)
    except (FileNotFoundError, BoardNotFound, BoardVersionNotFound) as exc:
        logger.warning("drawio_board_version_restore_missing", session_id=session_id, error=str(exc))
        raise HTTPException(status_code=409, detail="board_version_restore_failed") from exc
    except Exception as exc:
        logger.exception("drawio_board_version_restore_failed", session_id=session_id, error=str(exc))
        raise HTTPException(status_code=503, detail="board_version_restore_failed") from exc

    return {
        "session_id": session_id,
        "drawio_board": _sanitize_floats(drawio_board),
        "has_drawio_board": bool(drawio_board)
    }


def _sanitize_floats(obj):
    """
    清理数据中的特殊浮点值（inf, -inf, nan），转换为 None

    防止 JSON 序列化时出现 "Out of range float values are not JSON compliant" 错误
    """
    import math

    if isinstance(obj, float):
        if math.isinf(obj) or math.isnan(obj):
            return None
        return obj
    elif isinstance(obj, dict):
        return {k: _sanitize_floats(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_sanitize_floats(item) for item in obj]
    return obj


@router.post("/{session_id}/restore")
async def restore_session(
    session_id: str,
    message_limit: int = 100,
    lazy_artifacts: bool = False,
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
    adapters: ConversationAdapterRegistry = Depends(get_conversation_adapters),
):
    """
    恢复会话（数据库层分页加载：只返回最新N条消息）

    Args:
        session_id: 会话ID
        message_limit: 首次加载的最新消息数量，默认100

    Returns:
        会话元数据 + 最新N条消息 + 分页状态
    """
    row = await catalog.require_read(session_id, user)
    logger.info(
        "[会话恢复] 开始恢复会话",
        session_id=session_id,
        message_limit=message_limit,
        lazy_artifacts=lazy_artifacts
    )

    result = await adapters.get(row.source).restore(
        row,
        message_limit=message_limit,
        lazy_artifacts=lazy_artifacts,
    )

    if not result:
        logger.error("[会话恢复] 会话未找到", session_id=session_id)
        raise HTTPException(status_code=404, detail="session_not_found")

    normalized_session = result.get("normalized_session")
    if normalized_session is not None:
        resource_counts = {"total": 0, "documents": 0, "visualizations": 0, "files": 0}
        try:
            counts = await SessionResourceService.database().resource_counts(session_id)
            resource_counts = {
                "total": counts.total,
                "documents": counts.documents,
                "visualizations": counts.visualizations,
                "files": counts.files,
            }
        except Exception as exc:
            logger.warning(
                "normalized_session_resource_counts_failed",
                session_id=session_id,
                error=str(exc),
            )
        normalized_session["resource_counts"] = resource_counts
        normalized_session["has_lazy_files"] = resource_counts["files"] > 0
        normalized_session["has_lazy_office_documents"] = resource_counts["documents"] > 0
        normalized_session["has_lazy_visualizations"] = resource_counts["visualizations"] > 0
        return {
            "message": f"Session {session_id} restored successfully",
            "session": normalized_session,
        }

    session = result["session"]
    pagination = result["pagination"]

    logger.info("[会话恢复] 会话加载成功（数据库层分页）",
                session_id=session_id,
                loaded_messages=len(session.conversation_history),
                total_messages=pagination["total_count"],
                has_more=pagination["has_more"])

    # 使用 mode='json' 确保 float 特殊值（inf, -inf, NaN）被正确处理
    session_data = session.model_dump(mode='json')

    resource_counts = {"total": 0, "documents": 0, "visualizations": 0, "files": 0}
    try:
        counts = await SessionResourceService.database().resource_counts(session_id)
        resource_counts = {
            "total": counts.total,
            "documents": counts.documents,
            "visualizations": counts.visualizations,
            "files": counts.files,
        }
    except Exception as exc:
        logger.warning("session_resource_counts_unavailable", session_id=session_id, error=str(exc))

    # 分页状态（从数据库查询结果获取）
    session_data["has_more_messages"] = pagination["has_more"]
    session_data["total_message_count"] = pagination["total_count"]
    session_data["oldest_sequence"] = pagination["oldest_sequence"]
    session_data["resource_counts"] = resource_counts
    # 轻量恢复 deliberately 不加载 artifacts，因而 session_data 中可能没有
    # session_metadata。画板仍按需从 metadata 读取；不能因为首屏省略 metadata
    # 就把已有画板错误标记为不存在，否则前端不会调度 /drawio-board。
    drawio_metadata = session_data.get("metadata")
    if not isinstance(drawio_metadata, dict):
        try:
            from app.db.session_repository import get_session_repository

            drawio_metadata = await get_session_repository().get_session_metadata(session_id)
        except Exception as exc:
            logger.warning("session_drawio_board_flag_unavailable", session_id=session_id, error=str(exc))
            drawio_metadata = None
    session_data["has_lazy_drawio_board"] = bool(
        isinstance(drawio_metadata, dict)
        and isinstance(drawio_metadata.get("drawio_board"), dict)
    )

    if lazy_artifacts:
        session_data["conversation_history"] = _strip_lazy_artifacts(
            session_data.get("conversation_history", [])
        )

    # 清理特殊浮点值，防止 JSON 序列化错误
    session_data = _sanitize_floats(session_data)

    return {
        "message": f"Session {session_id} restored successfully",
        "session": {**session_data, **row.model_dump(mode="json")}
    }


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
    adapters: ConversationAdapterRegistry = Depends(get_conversation_adapters),
):
    """
    删除会话

    Args:
        session_id: 会话ID

    Returns:
        删除结果
    """
    row = await catalog.require_write(session_id, user)
    success = await adapters.get(row.source).delete(row)

    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Session not found or failed to delete: {session_id}"
        )

    logger.info("session_deleted", session_id=session_id)
    await catalog.delete(session_id)

    return {"message": f"Session {session_id} deleted successfully"}


@router.post("/cleanup")
async def cleanup_expired_sessions(
    user: CurrentUser = Depends(require_current_user),
):
    """
    清理过期会话

    删除超过保留天数的会话。

    Returns:
        清理结果
    """
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="admin_required")
    session_manager = get_session_manager()
    deleted_count = await session_manager.cleanup_expired_sessions()

    return {
        "message": f"Cleaned up {deleted_count} expired sessions",
        "deleted_count": deleted_count
    }


@router.post("/auto-save")
async def auto_save_session(
    request: Request,
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
):
    """
    自动保存会话消息（每次AI回复完成时调用）

    Args:
        request: 包含 session_id, messages, state 的请求体

    Returns:
        保存结果
    """
    from app.agent.session import get_session_manager
    from app.agent.session.models import Session

    data = await request.json()
    session_id = data.get("session_id")
    messages = data.get("messages", [])
    state = data.get("state", "active")

    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    await catalog.require_write(session_id, user)

    logger.info(
        "[autoSave] 自动保存会话",
        session_id=session_id,
        message_count=len(messages),
        state=state
    )

    session_manager = get_session_manager()

    # 加载现有会话
    session = await session_manager.load_session(session_id)

    if session:
        # 更新对话历史
        session.conversation_history = messages
        session.updated_at = datetime.now()

        # Frontend auto-save submits a full message snapshot, so replace the
        # transcript explicitly instead of relying on append-only semantics.
        success = await session_manager.replace_session_transcript(session)

        if success:
            logger.info(
                "[autoSave] 会话保存成功",
                session_id=session_id,
                message_count=len(messages)
            )
            return {
                "status": "ok",
                "message": f"Session {session_id} auto-saved with {len(messages)} messages"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to save session")
    else:
        # 会话不存在，创建新会话
        logger.warning("[autoSave] 会话不存在，跳过保存", session_id=session_id)
        return {
            "status": "skipped",
            "message": f"Session {session_id} does not exist"
        }


@router.post("/{session_id}/export")
async def export_session(
    session_id: str,
    output_path: Optional[str] = None,
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
):
    """
    导出会话

    Args:
        session_id: 会话ID
        output_path: 导出路径（可选）

    Returns:
        导出结果
    """
    await catalog.require_write(session_id, user)
    session_manager = get_session_manager()

    # 如果未提供路径，使用默认路径
    if not output_path:
        output_path = f"backend_data_registry/exports/{session_id}.json"

    success = await session_manager.export_session(session_id, output_path)

    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Session not found or failed to export: {session_id}"
        )

    return {
        "message": f"Session {session_id} exported successfully",
        "output_path": output_path
    }


@router.post("/import")
async def import_session(
    input_path: str,
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
):
    """
    导入会话

    Args:
        input_path: 导入路径

    Returns:
        导入的会话信息
    """
    session_manager = get_session_manager()
    session = await session_manager.import_session(input_path)

    if not session:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to import session from: {input_path}"
        )

    try:
        await catalog.register(
            session_id=session.session_id,
            user=user,
            source=ConversationSource.WEB,
            mode=(session.metadata or {}).get("mode") or "assistant",
            title=session.query[:256],
        )
    except Exception:
        await session_manager.delete_session(session.session_id)
        raise

    return {
        "message": "Session imported successfully",
        "session": session.to_summary().model_dump(mode='json')
    }
