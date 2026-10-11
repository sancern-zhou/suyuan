"""Office 交付物发布时自动生成 PDF 预览衍生。

App 端没有 docx/xlsx/pptx 渲染能力，预览依赖 `relation="preview"` 的 PDF 子资源。
此前 `generated_file_products` 对 docx/pptx/xlsx 只登记 download 或表格能力，
导致 App 端对话里生成的 Office 报告/表格点预览时提示"暂无可用预览"。本模块在
资源发布管线中补齐：primary 为 Office 文档且组内尚无 preview 时，用 LibreOffice
(soffice) 离线转换为 PDF，并追加 preview 声明，与 primary 同组发布。
"""

from __future__ import annotations

import asyncio
import glob
import os
import shutil
import tempfile
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

_OFFICE_SUFFIXES = {".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls"}
_CONVERT_TIMEOUT_SECONDS = 120
_PREVIEW_DIRNAME = "__previews"


def _source_fingerprint(source: Path) -> str:
    """Identity of one source file revision (content changes => new value)."""
    stat = source.stat()
    return f"{stat.st_mtime_ns}-{stat.st_size}"


def _preview_pdf_path(out_dir: Path, source: Path) -> Path:
    """Fingerprinted preview name: rewrites of the same path get a new file.

    Keeping the source extension in the key also stops same-directory
    docx/xlsx pairs with identical stems from sharing one preview PDF.
    """
    extension = source.suffix.lower().lstrip(".")
    return out_dir / f"{source.stem}.{extension}-{_source_fingerprint(source)}.pdf"


def _prune_stale_previews(out_dir: Path, source: Path, keep: Path) -> None:
    """Remove preview PDFs of older revisions of the same source file."""
    extension = glob.escape(source.suffix.lower().lstrip("."))
    pattern = f"{glob.escape(source.stem)}.{extension}-*.pdf"
    try:
        for item in out_dir.glob(pattern):
            if item != keep:
                item.unlink(missing_ok=True)
        legacy = out_dir / f"{source.stem}.pdf"
        legacy.unlink(missing_ok=True)
    except OSError as exc:  # noqa: BLE001 - 清理失败不影响预览可用性
        logger.warning("office_preview_prune_failed", path=str(keep), error=str(exc))


def _convert_to_pdf(source: Path) -> Path | None:
    """Convert one Office file to PDF under a dedicated preview directory."""
    try:
        from app.tools.office.soffice import run_soffice

        out_dir = source.parent / _PREVIEW_DIRNAME
        out_dir.mkdir(parents=True, exist_ok=True)
        expected = _preview_pdf_path(out_dir, source)
        if expected.is_file() and expected.stat().st_size > 0:
            _prune_stale_previews(out_dir, source, expected)
            return expected
        # Convert in a private temp dir so concurrent conversions cannot
        # clobber each other's `<stem>.pdf` output, then move atomically.
        temp_dir = Path(tempfile.mkdtemp(prefix=".convert-", dir=out_dir))
        try:
            completed = run_soffice(
                [
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(temp_dir),
                    str(source),
                ],
                timeout=_CONVERT_TIMEOUT_SECONDS,
            )
            produced = temp_dir / f"{source.stem}.pdf"
            if (
                completed.returncode == 0
                and produced.is_file()
                and produced.stat().st_size > 0
            ):
                os.replace(produced, expected)
                _prune_stale_previews(out_dir, source, expected)
                return expected
            logger.warning(
                "office_preview_convert_failed",
                source=str(source),
                returncode=getattr(completed, "returncode", None),
                stderr=str(getattr(completed, "stderr", ""))[:200],
            )
            return None
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception as exc:  # noqa: BLE001 - 预览失败不能阻断资源发布
        logger.warning("office_preview_convert_error", source=str(source), error=str(exc))
        return None


def _preview_declaration(
    parent: ResourceDeclaration, source: Path, pdf_path: Path
) -> ResourceDeclaration:
    return ResourceDeclaration(
        kind=ResourceKind.FILE,
        group_key=parent.group_key,
        resource_key=f"{parent.resource_key}-pdf-preview",
        parent_key=parent.resource_key,
        relation=ResourceRelation.PREVIEW,
        role=parent.role,
        label=f"{source.stem}.pdf",
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
                appended.append(_preview_declaration(parent, source, pdf_path))
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
