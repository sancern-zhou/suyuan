"""Authorized catalog and opaque content delivery for session resources."""
from __future__ import annotations

import asyncio
import mimetypes
import re
import tempfile
from pathlib import Path
from typing import Literal
from urllib.parse import quote
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from app.agent.resources.actions import (
    attach_rendered_file,
    resource_action_links,
    resource_content_base,
)
from app.agent.resources.resource_service import SessionResourceService, StoredResource
from app.auth.dependencies import optional_current_user, require_current_user
from app.auth.models import CurrentUser
from app.auth.share_access import (
    RESOURCE_PREVIEW_COOKIE,
    RESOURCE_PREVIEW_TICKET,
    RESOURCE_PREVIEW_TICKET_PATH_SEGMENT,
    external_api_path,
    get_share_access_service,
    resource_preview_identity,
)
from app.conversations.dependencies import get_conversation_catalog
from app.conversations.service import ConversationCatalogService
from app.services.html_preview_runtime import inject_html_runtime
from app.services.quarto_report_renderer import (
    ReportRenderError,
    quarto_report_renderer,
)
from app.utils.path_config import get_data_registry

logger = structlog.get_logger()
router = APIRouter(prefix="/api/sessions", tags=["session-resources"])
USER_VISIBLE_RESOURCE_ROLES = {"output", "report", "attachment"}
# 与移动端资源列表保持一致（social_app_routes._app_resource_descriptors）：
# 外置数据文件（save_data 落盘的查询/中间结果）同样对用户可见、可下载。
USER_VISIBLE_RESOURCE_KINDS = {"data", "file", "artifact", "visual"}


class RenderResourceRequest(BaseModel):
    format: Literal["docx", "html"]


def user_visible_resource(item: StoredResource) -> bool:
    return (
        item.role in USER_VISIBLE_RESOURCE_ROLES
        and item.kind in USER_VISIBLE_RESOURCE_KINDS
    )


_DRAWIO_BOARD_PATH_RE = re.compile(r"(?:^|/)drawio_boards/([0-9a-f-]{36})(?:/|$)", re.IGNORECASE)


def _board_id_from_resource(item: StoredResource) -> str | None:
    """Expose only the opaque board UUID needed by the board editor."""
    if item.renderer != "board":
        return None
    path = str((item.locator or {}).get("path") or "")
    match = _DRAWIO_BOARD_PATH_RE.search(path)
    return match.group(1) if match else None


def resource_dto(session_id: str, item: StoredResource) -> dict:
    """Project a resource without exposing server locators or tool metadata."""
    base = resource_content_base(session_id, item)
    directory = item.kind == "artifact" and bool(item.metadata.get("entrypoint"))
    actions = resource_action_links(session_id, item)
    preview_service = get_share_access_service()
    preview_ticket = preview_service.issue(
        "session-resource",
        resource_preview_identity(session_id, item.resource_id),
    )
    internal_content_url = f"{base}/" if directory else base
    if directory:
        # Relative asset URLs (report_files/, assets/, ...) resolve against the
        # document URL, so a path segment makes every subresource carry the
        # ticket even when the sandboxed iframe cannot send cookies.
        content_url = external_api_path(
            f"{base}/{RESOURCE_PREVIEW_TICKET_PATH_SEGMENT}/{quote(preview_ticket, safe='')}/"
        )
    else:
        content_url = external_api_path(internal_content_url)
        separator = "&" if "?" in content_url else "?"
        content_url = f"{content_url}{separator}{RESOURCE_PREVIEW_TICKET}={preview_ticket}"
    if "preview" in actions:
        actions["preview"] = content_url
    if "render" in actions:
        actions["render"] = external_api_path(actions["render"])
    if "save" in actions:
        actions["save"] = external_api_path(actions["save"])
    download_url = (
        external_api_path(actions["download"])
        if actions.get("download")
        else None
    )
    if download_url:
        separator = "&" if "?" in download_url else "?"
        download_url = (
            f"{download_url}{separator}{RESOURCE_PREVIEW_TICKET}={preview_ticket}"
        )
    dto = {
        "resource_id": item.resource_id,
        "ref_id": item.resource_id,
        "group_id": item.group_id,
        "run_id": item.run_id,
        "parent_resource_id": item.parent_resource_id,
        "resource_key": item.resource_key,
        "relation": item.relation,
        "kind": item.kind,
        "role": item.role,
        "label": item.label,
        "format": item.format,
        "media_type": item.media_type,
        "renderer": item.renderer,
        "capabilities": item.capabilities,
        "actions": actions,
        "version": item.version,
        "status": item.status,
        "content_url": content_url,
        "download_url": download_url,
        "size_bytes": int(item.metadata.get("size") or item.metadata.get("size_bytes") or 0),
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }
    if item.resource_key in {"chart-spec", "chart-image"}:
        dto["visual_id"] = item.metadata.get("visual_id")
    if item.resource_key == "chart-spec":
        dto["interactive"] = item.metadata.get("interactive", (
            item.metadata.get("type") != "image"
            and item.tool_name not in {"execute_python", "create_business_chart"}
        ))
    board_id = _board_id_from_resource(item)
    if board_id:
        dto["board_id"] = board_id
    return dto


MAX_SPREADSHEET_SAVE_BYTES = 50 * 1024 * 1024
# 浏览器端编辑回传的格式签名与渲染器映射（xlsx/xls 走 SheetJS，docx 走 docx-editor）
EDITABLE_RESOURCE_SIGNATURES = {
    "xlsx": b"PK\x03\x04",
    "xls": b"\xd0\xcf\x11\xe0",
    "docx": b"PK\x03\x04",
}
EDITABLE_RESOURCE_RENDERERS = {
    "xlsx": "spreadsheet",
    "xls": "spreadsheet",
    "docx": "docx",
}
# 兼容旧引用
SPREADSHEET_SIGNATURES = EDITABLE_RESOURCE_SIGNATURES


def _is_valid_spreadsheet(path: Path, format_name: str) -> bool:
    try:
        if format_name == "xlsx":
            from openpyxl import load_workbook

            workbook = load_workbook(path, read_only=True, data_only=False)
            workbook.close()
        elif format_name == "docx":
            from docx import Document

            Document(str(path))
        else:
            import xlrd

            workbook = xlrd.open_workbook(path, on_demand=True)
            workbook.release_resources()
        return True
    except Exception:
        return False


@router.post("/{session_id}/resources/{resource_id}/save")
async def save_session_resource(
    session_id: str,
    resource_id: str,
    file: UploadFile = File(...),
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
):
    """Publish a browser-edited document (xlsx/xls via SheetJS, docx via docx-editor) as the next version."""
    await catalog.require_write(session_id, user)
    service = SessionResourceService.database()
    resource = await service.get_resource(session_id, resource_id, status="active")
    if resource is None or not user_visible_resource(resource):
        raise HTTPException(status_code=404, detail="resource_not_found")
    if not (
        resource.relation == "primary"
        and resource.format in EDITABLE_RESOURCE_SIGNATURES
        and resource.renderer == EDITABLE_RESOURCE_RENDERERS.get(resource.format)
        and "edit" in resource.capabilities
    ):
        raise HTTPException(status_code=422, detail="resource_not_editable")

    with tempfile.TemporaryDirectory(prefix="suyuan-resource-edit-") as temp_dir:
        edited = Path(temp_dir) / f"edited.{resource.format}"
        size = 0
        signature = b""
        with edited.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                if not signature:
                    signature = chunk[:4]
                size += len(chunk)
                if size > MAX_SPREADSHEET_SAVE_BYTES:
                    raise HTTPException(status_code=413, detail="resource_edit_too_large")
                output.write(chunk)
        if (
            size == 0
            or signature != SPREADSHEET_SIGNATURES[resource.format]
            or not await asyncio.to_thread(
                _is_valid_spreadsheet, edited, resource.format
            )
        ):
            raise HTTPException(status_code=422, detail="invalid_spreadsheet_content")
        try:
            publication = await service.replace_primary_file(
                session_id,
                f"resource-edit-{uuid4().hex}",
                resource_id,
                edited,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "success": True,
        "resource_version": publication.catalog_version,
        "changed_resource_ids": [
            item.resource_id for item in publication.resources
        ],
    }


@router.get("/{session_id}/resources")
async def get_session_resources(
    session_id: str,
    kind: str | None = None,
    role: str | None = None,
    renderer: str | None = None,
    group_id: str | None = None,
    status: str | None = "active",
    limit: int = 100,
    cursor: str | None = None,
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
):
    await catalog.require_read(session_id, user)
    service = SessionResourceService.database()
    try:
        page = await service.list_resources(
            session_id,
            kind=kind,
            role=role,
            renderer=renderer,
            group_id=group_id,
            status=status,
            limit=min(max(limit, 1), 200),
            cursor=cursor,
        )
    except Exception as exc:
        logger.error(
            "session_resources_load_failed", session_id=session_id, error=str(exc)
        )
        raise HTTPException(
            status_code=503, detail="resource_catalog_unavailable"
        ) from exc
    resources = [
        resource_dto(session_id, item)
        for item in page.resources
        if user_visible_resource(item)
    ]
    return {
        "session_id": session_id,
        "resource_version": await service.catalog_version(session_id),
        "resources": resources,
        "total": len(resources),
        "next_cursor": page.next_cursor,
    }


def _qmd_report_id(resource: StoredResource) -> str:
    raw_path = (resource.locator or {}).get("path")
    if not raw_path:
        raise HTTPException(status_code=422, detail="report_source_unavailable")
    qmd_path = Path(str(raw_path)).expanduser().resolve()
    reports_root = quarto_report_renderer.report_root.resolve()
    try:
        relative = qmd_path.relative_to(reports_root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="report_source_forbidden") from exc
    if len(relative.parts) != 2 or relative.name != "report.qmd":
        raise HTTPException(status_code=422, detail="invalid_report_source")
    return relative.parts[0]


@router.post("/{session_id}/resources/{resource_id}/render")
async def render_session_resource(
    session_id: str,
    resource_id: str,
    payload: RenderResourceRequest,
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
):
    """Render a trusted QMD report into a downloadable same-group rendition."""
    await catalog.require_write(session_id, user)
    service = SessionResourceService.database()
    resource = await service.get_resource(session_id, resource_id, status="active")
    if resource is None or not user_visible_resource(resource):
        raise HTTPException(status_code=404, detail="resource_not_found")
    if not (
        resource.relation == "primary"
        and resource.role == "report"
        and resource.format == "qmd"
        and "render" in resource.capabilities
    ):
        raise HTTPException(status_code=422, detail="resource_not_renderable")

    report_id = _qmd_report_id(resource)
    try:
        if payload.format == "docx":
            path = await asyncio.to_thread(quarto_report_renderer.render_docx, report_id)
            renderer = "docx"
            label = "report.docx"
        else:
            path = await asyncio.to_thread(
                quarto_report_renderer.render_share_html, report_id
            )
            renderer = "html"
            label = "report.html"
        return await attach_rendered_file(
            service,
            session_id=session_id,
            run_id=f"resource-render-{uuid4().hex}",
            group_key=f"report:{report_id}",
            parent_resource_id=resource.resource_id,
            path=path,
            relation="rendition",
            renderer=renderer,
            tool_name=f"render_report_{payload.format}",
            capabilities=("download",),
            label=label,
        )
    except (FileNotFoundError, ValueError, ReportRenderError) as exc:
        logger.warning(
            "session_resource_render_failed",
            session_id=session_id,
            resource_id=resource_id,
            format=payload.format,
            error=str(exc),
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _require_within(candidate: Path, root: Path) -> Path:
    resolved = candidate.expanduser().resolve()
    if not resolved.is_relative_to(root):
        raise HTTPException(status_code=403, detail="resource_path_forbidden")
    return resolved


def _content_target(
    resource: StoredResource, registry_root: Path, asset_path: str | None
) -> tuple[Path, str]:
    raw_path = (resource.locator or {}).get("path")
    if not raw_path:
        raise HTTPException(status_code=404, detail="resource_content_unavailable")
    registered = _require_within(Path(str(raw_path)), registry_root)

    if resource.kind == "artifact" and resource.metadata.get("entrypoint"):
        if not registered.is_dir():
            raise HTTPException(status_code=404, detail="resource_content_missing")
        relative_target = asset_path
        if relative_target is None or relative_target == "":
            relative_target = str(resource.metadata["entrypoint"])
        candidate = _require_within(registered / relative_target, registered)
        candidate = _require_within(candidate, registry_root)
        media_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        return candidate, media_type

    if asset_path is not None:
        raise HTTPException(status_code=404, detail="resource_content_missing")
    media_type = resource.media_type or (
        mimetypes.guess_type(registered.name)[0] or "application/octet-stream"
    )
    return registered, media_type


# text/html 预览运行在 opaque sandbox origin：默认只放行同源资源与内联脚本/样式，
# 外链（fetch/XHR/WS/CDN）全部被拦。需要外部脚本的交互报告通过资源 metadata 的
# csp_profile 选择放宽档位；生成侧仍应坚持自包含（禁 CDN），放宽档位只服务
# 既有地图类报告的兼容。
HTML_CSP_PROFILES = {
    "default": (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; font-src 'self' data:; "
        "object-src 'none'; base-uri 'none'"
    ),
    "amap": (
        "default-src 'self'; img-src 'self' data: blob: https:; "
        "style-src 'self' 'unsafe-inline' https:; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' "
        "https://webapi.amap.com https://restapi.amap.com https://a.amap.com; "
        "connect-src 'self' https:; font-src 'self' data: https:; "
        "worker-src 'self' blob:; object-src 'none'; base-uri 'none'"
    ),
}
# 历史兼容：旧版日报生成器（xuchang 分支）不写 metadata，按文件名前缀识别。
LEGACY_AMAP_REPORT_PREFIX = "xuchang_air_quality_daily_review_"


def _html_content_security_policy(
    resource: StoredResource, filename: str
) -> tuple[str, bool]:
    """Return (CSP header value, no_store) for an inline HTML document."""
    profile_name = str((resource.metadata or {}).get("csp_profile") or "").strip()
    if not profile_name and filename.startswith(LEGACY_AMAP_REPORT_PREFIX):
        profile_name = "amap"
    if profile_name not in HTML_CSP_PROFILES:
        # 未知档位一律回落最严档，避免 metadata 注入放宽策略。
        profile_name = "default"
    return HTML_CSP_PROFILES[profile_name], profile_name == "amap"


def _read_html_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8", errors="replace")


@router.get("/{session_id}/resources/{resource_id}/content/{asset_path:path}")
@router.get("/{session_id}/resources/{resource_id}/content")
async def get_session_resource_content(
    session_id: str,
    resource_id: str,
    asset_path: str | None = None,
    disposition: Literal["inline", "attachment"] = "inline",
    request: Request = None,
    user: CurrentUser | None = Depends(optional_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
):
    """Serve authorized bytes while keeping the storage locator opaque."""
    path_ticket = ""
    if asset_path:
        segments = asset_path.split("/", 2)
        if segments[0] == RESOURCE_PREVIEW_TICKET_PATH_SEGMENT:
            path_ticket = segments[1] if len(segments) > 1 else ""
            asset_path = segments[2] if len(segments) > 2 and segments[2] else None
    preview_service = get_share_access_service()
    ticket = path_ticket
    if request is not None:
        ticket = (
            ticket
            or request.query_params.get(RESOURCE_PREVIEW_TICKET)
            or request.cookies.get(RESOURCE_PREVIEW_COOKIE, "")
        )
    ticket_valid = preview_service.verify(
        ticket,
        "session-resource",
        resource_preview_identity(session_id, resource_id),
    ) if ticket else False
    if user is not None:
        await catalog.require_read(session_id, user)
    elif not ticket_valid:
        raise HTTPException(status_code=401, detail="authentication_required")
    resource = await SessionResourceService.database().get_resource(
        session_id, resource_id, status="active"
    )
    if resource is None or not user_visible_resource(resource):
        raise HTTPException(status_code=404, detail="resource_not_found")
    required_capability = "download" if disposition == "attachment" else "preview"
    if required_capability not in resource.capabilities:
        raise HTTPException(status_code=404, detail="resource_content_unavailable")

    registry_root = get_data_registry().expanduser().resolve()
    target, media_type = _content_target(resource, registry_root, asset_path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="resource_content_missing")

    headers = {
        "Cache-Control": "private, max-age=300, immutable",
        "X-Content-Type-Options": "nosniff",
        # HTML previews run in an intentionally opaque sandbox origin. Quarto's
        # scripts, styles and fonts therefore require an explicit CORS grant.
        "Access-Control-Allow-Origin": "*",
    }
    if media_type == "text/html":
        csp, no_store = _html_content_security_policy(resource, target.name)
        headers["Content-Security-Policy"] = csp
        if no_store:
            headers["Cache-Control"] = "private, no-store"
    filename = target.name if asset_path is not None else (resource.label or target.name)
    if disposition == "inline" and media_type == "text/html":
        # Interactive HTML previews are sized by the host from content-reported
        # height, so inject the runtime that reports it (idempotent).
        html = await asyncio.to_thread(_read_html_text, target)
        response = Response(
            content=inject_html_runtime(html),
            media_type=media_type,
            headers={
                **headers,
                "Content-Disposition": f"inline; filename*=utf-8''{quote(filename, safe='')}",
            },
        )
    else:
        response = FileResponse(
            path=target,
            media_type=media_type,
            filename=filename,
            content_disposition_type=disposition,
            headers=headers,
        )
    if ticket_valid and request is not None:
        response.set_cookie(
            RESOURCE_PREVIEW_COOKIE,
            ticket,
            max_age=preview_service.ttl_seconds,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="strict",
            path=external_api_path(
                resource_content_base(session_id, resource)
            ),
        )
    return response
