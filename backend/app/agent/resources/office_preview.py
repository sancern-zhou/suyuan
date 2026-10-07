"""Office 交付物发布时自动生成 PDF 预览衍生。

App 端没有 docx/pptx 渲染能力，预览依赖 `relation="preview"` 的 PDF 子资源。
此前 `generated_file_products` 对 docx/pptx 只登记 download 能力，导致
App 端对话里生成的 Office 报告点预览时提示"暂无可用预览"。本模块在资源
发布管线中补齐：primary 为 Office 文档且组内尚无 preview 时，用 LibreOffice
(soffice) 离线转换为 PDF，并追加 preview 声明，与 primary 同组发布。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import structlog

from .contracts import (
    ResourceCapability,
    ResourceDeclaration,
    ResourceKind,
    ResourceLocator,
    ResourceRelation,
    ResourceRenderer,
)

logger = structlog.get_logger()

_OFFICE_SUFFIXES = {".docx", ".doc", ".pptx", ".ppt"}
_CONVERT_TIMEOUT_SECONDS = 120
_PREVIEW_DIRNAME = "__previews"


def _convert_to_pdf(source: Path) -> Path | None:
    """Convert one Office file to PDF under a dedicated preview directory."""
    try:
        from app.tools.office.soffice import run_soffice

        out_dir = source.parent / _PREVIEW_DIRNAME
        out_dir.mkdir(parents=True, exist_ok=True)
        expected = out_dir / f"{source.stem}.pdf"
        if expected.is_file() and expected.stat().st_size > 0:
            return expected
        completed = run_soffice(
            [
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(out_dir),
                str(source),
            ],
            timeout=_CONVERT_TIMEOUT_SECONDS,
        )
        if completed.returncode == 0 and expected.is_file() and expected.stat().st_size > 0:
            return expected
        logger.warning(
            "office_preview_convert_failed",
            source=str(source),
            returncode=getattr(completed, "returncode", None),
            stderr=str(getattr(completed, "stderr", ""))[:200],
        )
        return None
    except Exception as exc:  # noqa: BLE001 - 预览失败不能阻断资源发布
        logger.warning("office_preview_convert_error", source=str(source), error=str(exc))
        return None


def _preview_declaration(parent: ResourceDeclaration, pdf_path: Path) -> ResourceDeclaration:
    return ResourceDeclaration(
        kind=ResourceKind.FILE,
        group_key=parent.group_key,
        resource_key=f"{parent.resource_key}-pdf-preview",
        parent_key=parent.resource_key,
        relation=ResourceRelation.PREVIEW,
        role=parent.role,
        label=f"{pdf_path.stem}.pdf",
        locator=ResourceLocator(path=str(pdf_path)),
        format="pdf",
        media_type="application/pdf",
        renderer=ResourceRenderer.PDF,
        capabilities={ResourceCapability.PREVIEW, ResourceCapability.DOWNLOAD},
        metadata={"generator": "soffice", "preview_for": parent.resource_key},
        tool_name=parent.tool_name,
    )


async def attach_office_preview_declarations(
    declarations: list[ResourceDeclaration],
) -> list[ResourceDeclaration]:
    """Return declarations with PDF preview siblings for Office primaries."""
    try:
        pending: list[tuple[ResourceDeclaration, Path]] = []
        existing_previews = {
            item.parent_key for item in declarations if item.relation is ResourceRelation.PREVIEW
        }
        for item in declarations:
            if item.relation is not ResourceRelation.PRIMARY:
                continue
            if item.resource_key in existing_previews:
                continue
            locator = item.locator.path
            if not locator or item.kind not in {ResourceKind.FILE, ResourceKind.ARTIFACT}:
                continue
            source = Path(locator)
            if source.suffix.lower() not in _OFFICE_SUFFIXES or not source.is_file():
                continue
            pending.append((item, source))
        if not pending:
            return declarations

        results = await asyncio.gather(
            *(asyncio.to_thread(_convert_to_pdf, source) for _, source in pending)
        )
        appended = list(declarations)
        for (parent, source), pdf_path in zip(pending, results):
            if pdf_path is None:
                continue
            try:
                appended.append(_preview_declaration(parent, pdf_path))
            except Exception as exc:  # noqa: BLE001 - 单条声明失败不影响其余资源
                logger.warning(
                    "office_preview_declaration_failed",
                    source=str(source),
                    error=str(exc),
                )
        if len(appended) != len(declarations):
            logger.info(
                "office_preview_attached",
                count=len(appended) - len(declarations),
            )
        return appended
    except Exception as exc:  # noqa: BLE001 - 预览失败不能阻断资源发布
        logger.warning("office_preview_attach_failed", error=str(exc))
        return declarations
