"""
Structured ReportPackage tools.

These tools make the Quarto report path a first-class Agent action:
create/validate a standard reports/{report_id}/ package and render all
deliverable formats from the same report.qmd source.
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import structlog

from app.services.quarto_report_renderer import (
    ReportRenderError,
    format_report_image_validation_error,
    inspect_report_image_refs,
    normalize_chinese_ascii_quotes,
    quarto_report_renderer,
)
from app.services.report_preview_refresh import (
    build_html_preview as build_report_html_preview,
)
from app.services.report_preview_refresh import (
    record_report_update,
)
from app.tools.artifact_utils import (
    attach_document_resources,
    build_artifact_resume_context,
    preview_output_path,
)
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.path_config import get_images_dir

logger = structlog.get_logger()


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
TABLE_EXTENSIONS = {".csv", ".json", ".xlsx", ".xls"}
REPORT_ID_PATTERN = re.compile(r"[^A-Za-z0-9_-]+")
MARKDOWN_IMAGE_PATTERN = re.compile(r"!\[[^\]]*\]\((?P<src>[^)]+)\)")
RESERVED_REPORT_META_KEYS = {
    "report_id",
    "created_at",
    "updated_at",
    "source",
    "files",
    "assets",
    "validation",
    "version",
    "history",
    "preview_version",
}


def _safe_report_id(raw_id: str) -> str:
    report_id = REPORT_ID_PATTERN.sub("_", str(raw_id or "").strip()).strip("_")
    if not report_id:
        report_id = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    return report_id


def _copy_file_to_dir(source: str, target_dir: Path, *, preferred_name: str | None = None) -> Dict[str, Any]:
    src = Path(source).expanduser().resolve()
    if not src.exists() or not src.is_file():
        return {"source": source, "success": False, "error": "file not found"}

    target_dir.mkdir(parents=True, exist_ok=True)
    target_name = preferred_name or src.name
    target = target_dir / Path(target_name).name
    if target.exists() and target.resolve() != src:
        stem, suffix = target.stem, target.suffix
        target = target_dir / f"{stem}_{datetime.now().strftime('%H%M%S')}{suffix}"

    if target.resolve() != src:
        shutil.copy2(src, target)
    return {
        "source": str(src),
        "success": True,
        "path": str(target),
        "relative_path": str(target.relative_to(target_dir.parents[1])),
    }


def _asset_target_dir(report_dir: Path, source: str, asset_type: str | None = None) -> Path:
    suffix = Path(source).suffix.lower()
    if asset_type == "table" or suffix in TABLE_EXTENSIONS:
        return report_dir / "tables"
    if asset_type == "image" or suffix in IMAGE_EXTENSIONS:
        return report_dir / "assets" / "charts"
    return report_dir / "assets"


def _normalize_asset_specs(assets: Optional[List[Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for item in assets or []:
        if isinstance(item, str):
            normalized.append({"path": item})
        elif isinstance(item, dict) and item.get("path"):
            normalized.append(item)
    return normalized


def _validate_image_refs(report_dir: Path, qmd_content: str) -> Dict[str, Any]:
    return inspect_report_image_refs(
        report_dir,
        qmd_content,
        qmd_path=report_dir / "report.qmd",
    )


def _copied_asset_ref_map(copied_assets: Iterable[Dict[str, Any]]) -> Dict[str, str]:
    ref_map: Dict[str, str] = {}
    for item in copied_assets:
        if not item.get("success") or not item.get("relative_path"):
            continue
        relative_path = str(item["relative_path"]).replace("\\", "/")
        keys = {relative_path, Path(relative_path).name}
        for field in ("source", "path"):
            value = item.get(field)
            if value:
                normalized = str(value).replace("\\", "/")
                keys.add(normalized)
                keys.add(Path(normalized).name)
        for key in keys:
            if key:
                ref_map[key] = relative_path
    return ref_map


def _rewrite_image_refs_to_copied_assets(
    report_dir: Path,
    qmd_content: str,
    copied_assets: Iterable[Dict[str, Any]],
) -> str:
    ref_map = _copied_asset_ref_map(copied_assets)
    if not ref_map:
        return qmd_content

    report_root = report_dir.resolve()

    def replace(match: re.Match[str]) -> str:
        src = match.group("src").strip()
        if not src or src.startswith(("http://", "https://", "data:")):
            return match.group(0)

        if src.startswith("/api/image/"):
            image_key = src[len("/api/image/") :].split("#", 1)[0].split("?", 1)[0]
            rewritten = ref_map.get(image_key) or ref_map.get(Path(image_key).name)
            if not rewritten and not Path(image_key).suffix:
                matching_assets = {
                    relative_path
                    for key, relative_path in ref_map.items()
                    if Path(key).stem == Path(image_key).name
                }
                if len(matching_assets) == 1:
                    rewritten = matching_assets.pop()
            if not rewritten:
                return match.group(0)
            return match.group(0).replace(match.group("src"), rewritten, 1)

        candidate = (report_dir / src).resolve()
        try:
            candidate.relative_to(report_root)
        except ValueError:
            pass
        else:
            if candidate.exists():
                return match.group(0)

        rewritten = ref_map.get(src.replace("\\", "/")) or ref_map.get(Path(src).name)
        if not rewritten:
            return match.group(0)
        return match.group(0).replace(match.group("src"), rewritten, 1)

    return MARKDOWN_IMAGE_PATTERN.sub(replace, qmd_content)


def _rewrite_missing_image_refs_to_copied_assets(
    report_dir: Path,
    qmd_content: str,
    copied_assets: Iterable[Dict[str, Any]],
) -> str:
    """
    Last-mile normalization for LLM-generated QMD.

    Agents sometimes infer a report-local path from an image cache id, such as
    assets/charts/matplotlib_*.png, while the actual copied asset keeps its real
    filename from execute_python. If the inferred refs are missing and copied
    image assets are available, rewrite missing refs to copied asset paths in
    document order.
    """
    image_assets = [
        item
        for item in copied_assets
        if item.get("success")
        and item.get("relative_path")
        and Path(str(item.get("relative_path"))).suffix.lower() in IMAGE_EXTENSIONS
    ]
    if not image_assets:
        return qmd_content

    missing_refs = _validate_image_refs(report_dir, qmd_content).get("missing") or []
    missing_image_refs = [
        ref
        for ref in missing_refs
        if ref.startswith(("assets/charts/", "assets/images/"))
        and Path(ref).suffix.lower() in IMAGE_EXTENSIONS
    ]
    if not missing_image_refs or len(missing_image_refs) != len(image_assets):
        return qmd_content

    ref_map = {
        missing_ref: str(asset["relative_path"]).replace("\\", "/")
        for missing_ref, asset in zip(missing_image_refs, image_assets)
    }

    def replace(match: re.Match[str]) -> str:
        src = match.group("src").strip()
        rewritten = ref_map.get(src)
        if not rewritten:
            return match.group(0)
        return match.group(0).replace(match.group("src"), rewritten, 1)

    logger.info(
        "create_report_package_missing_image_refs_normalized",
        rewritten=ref_map,
    )
    return MARKDOWN_IMAGE_PATTERN.sub(replace, qmd_content)


def _download_and_copy_api_images(
    report_dir: Path,
    qmd_content: str,
) -> tuple[str, List[Dict[str, Any]]]:
    """自动处理 /api/image/ 引用"""
    api_image_refs = []
    for match in MARKDOWN_IMAGE_PATTERN.finditer(qmd_content or ""):
        src = match.group("src").strip()
        if src.startswith("/api/image/"):
            image_id = src[len("/api/image/"):].split("?")[0].split("#")[0]
            api_image_refs.append({
                "original_ref": src,
                "image_id": image_id,
                "markdown_match": match.group(0)
            })

    if not api_image_refs:
        return qmd_content, []

    logger.info(
        "auto_processing_api_image_refs",
        count=len(api_image_refs),
        refs=[ref["original_ref"] for ref in api_image_refs]
    )

    image_cache_dir = get_images_dir()
    charts_dir = report_dir / "assets" / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    copied_assets = []
    rewritten_qmd = qmd_content

    for ref_info in api_image_refs:
        image_id = ref_info["image_id"]
        original_ref = ref_info["original_ref"]

        image_file = None
        for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"]:
            candidate = image_cache_dir / f"{image_id}{ext}"
            if candidate.exists():
                image_file = candidate
                break

        if not image_file:
            logger.warning(
                "api_image_file_not_found",
                image_id=image_id,
                searched_dir=str(image_cache_dir)
            )
            continue

        target_name = f"{image_id}{image_file.suffix}"
        target_path = charts_dir / target_name

        try:
            shutil.copy2(image_file, target_path)
            relative_path = f"assets/charts/{target_name}"
            rewritten_qmd = rewritten_qmd.replace(
                ref_info["markdown_match"],
                ref_info["markdown_match"].replace(original_ref, relative_path)
            )
            copied_assets.append({
                "source": str(image_file),
                "success": True,
                "path": str(target_path),
                "relative_path": relative_path,
                "original_api_ref": original_ref
            })
            logger.info(
                "api_image_copied_and_rewritten",
                image_id=image_id,
                original_ref=original_ref,
                new_ref=relative_path
            )
        except Exception as exc:
            logger.error(
                "api_image_copy_failed",
                image_id=image_id,
                error=str(exc)
            )

    return rewritten_qmd, copied_assets

def _read_qmd(report_dir: Path) -> str:
    qmd_path = report_dir / "report.qmd"
    if not qmd_path.exists():
        return ""
    return qmd_path.read_text(encoding="utf-8", errors="replace")


def _disable_quarto_docx_auto_structure(qmd_content: str) -> str:
    """Keep Word TOC and heading numbering ownership in DOCX finalization."""
    if not qmd_content.startswith("---"):
        return qmd_content

    end_match = re.search(r"(?m)^---\s*$", qmd_content[3:])
    if not end_match:
        return qmd_content

    header_end = 3 + end_match.end()
    header = qmd_content[:header_end]
    body = qmd_content[header_end:]
    lines = header.splitlines(keepends=True)
    in_docx_block = False
    docx_indent = -1
    changed = False

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(line.lstrip(" "))
        if in_docx_block and indent <= docx_indent and stripped != "docx:":
            in_docx_block = False

        if stripped == "docx:":
            in_docx_block = True
            docx_indent = indent
            continue

        if in_docx_block and re.match(r"(toc|number-sections):\s*true\s*(#.*)?$", stripped):
            key = stripped.split(":", 1)[0]
            newline = "\n" if line.endswith("\n") else ""
            comment = ""
            if "#" in stripped:
                comment = " " + stripped[stripped.index("#") :]
            lines[index] = f"{' ' * indent}{key}: false{comment}{newline}"
            changed = True

    if not changed:
        return qmd_content

    return "".join(lines) + body


def _normalize_static_qmd(qmd_content: str) -> str:
    """
    Remove RMarkdown template leftovers from static report QMD.

    Reports generated by the agent are static Markdown plus assets. Leaving
    inline R dates or knitr setup chunks makes Quarto require R/Rscript even
    when no computation is needed.
    """
    if not qmd_content:
        return qmd_content

    today = datetime.now().strftime("%Y-%m-%d")
    normalized = re.sub(
        r"(?m)^date:\s*['\"]?`r\s+Sys\.Date\(\)`['\"]?\s*$",
        f'date: "{today}"',
        qmd_content,
    )
    normalized = re.sub(
        r"\n?```{r\s+setup[^}]*}\s*\n\s*knitr::opts_chunk\$set\([^`]*?\)\s*\n```\s*\n?",
        "\n\n",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = normalize_chinese_ascii_quotes(normalized)
    return normalized


def _find_unsupported_r_qmd_features(qmd_content: str) -> List[str]:
    """Detect R/knitr constructs that make static report packages require R."""
    if not qmd_content:
        return []

    checks = [
        ("R code chunk", r"(?im)^(?:`{3,}|~{3,})\s*\{\s*r(?:[\s,}].*)?$"),
        ("inline R expression", r"`r\s+[^`]+`"),
        ("knitr::", r"\bknitr::"),
        ("rmarkdown::", r"\brmarkdown::"),
    ]
    return [label for label, pattern in checks if re.search(pattern, qmd_content)]


def _unsupported_r_qmd_result(report_id: str, unsupported_r_features: List[str]) -> Dict[str, Any]:
    detail = (
        "report.qmd contains unsupported R/knitr content. "
        "Use static Markdown image links and pre-generated assets instead."
    )
    return {
        "success": False,
        "data": {
            "error": detail,
            "report_id": report_id,
            "unsupported_r_features": unsupported_r_features,
        },
        "metadata": {"generator": "create_report_package", "schema_version": "report_package.v1"},
        "summary": "报告包创建失败：QMD 包含不支持的 R/knitr 内容。",
    }


class CreateReportPackageTool(LLMTool):
    """Create a standard ReportPackage and optionally render HTML preview."""

    def __init__(self):
        super().__init__(
            name="create_report_package",
            description=(
                "创建正式 Quarto ReportPackage；调用前读 "
                "backend/app/tools/report/report_package/references/index.md。"
                "禁止 R 和 /api/image；资源传真实路径到 assets。"
            ),
            category=ToolCategory.REPORTING,
            version="1.0.0",
        )
        self.function_schema = {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "report_id": {
                        "type": "string",
                        "description": "报告ID，会安全转义。",
                    },
                    "qmd_content": {
                        "type": "string",
                        "description": "完整 report.qmd；规则见 references/index.md。",
                    },
                    "source_qmd_path": {
                        "type": "string",
                        "description": (
                            "可编辑的原始 QMD 文件路径，仅作为来源元数据记录；不会直接覆盖"
                            "报告包内 report.qmd。HTML、DOCX 和 QMD 下载始终使用经 assets "
                            "复制及路径规范化后的报告包发布稿。"
                        ),
                    },
                    "title": {"type": "string", "description": "报告标题，可选。"},
                    "report_type": {
                        "type": "string",
                        "enum": ["government", "analysis", "briefing", "research", "custom"],
                        "description": "报告类型。",
                    },
                    "design_profile": {
                        "type": "string",
                        "enum": ["formal", "executive", "technical", "visual", "custom"],
                        "description": "报告呈现风格。",
                    },
                    "design_intent": {
                        "type": "string",
                        "description": "报告设计意图。",
                    },
                    "assets": {
                        "type": "array",
                        "description": "真实文件路径或 {path,type,name}；见 references/index.md。",
                        "items": {
                            "oneOf": [
                                {
                                    "type": "string",
                                },
                                {
                                    "type": "object",
                                    "properties": {
                                        "path": {
                                            "type": "string",
                                        },
                                        "type": {"type": "string", "enum": ["image", "table", "asset"]},
                                        "name": {
                                            "type": "string",
                                        },
                                    },
                                    "required": ["path"],
                                },
                            ]
                        },
                    },
                    "report_data": {
                        "type": "object",
                        "description": "写入 report_data.json。",
                    },
                    "metadata": {
                        "type": "object",
                        "description": "写入 meta.json。",
                    },
                    "render_html": {
                        "type": "boolean",
                        "description": "渲染 HTML 预览。",
                        "default": True,
                    },
                },
                "required": ["report_id", "qmd_content"],
            },
        }

    async def execute(
        self,
        report_id: str,
        qmd_content: str,
        source_qmd_path: str | None = None,
        title: str | None = None,
        report_type: str | None = None,
        design_profile: str | None = None,
        design_intent: str | None = None,
        assets: Optional[List[Any]] = None,
        report_data: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        render_html: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        safe_id = _safe_report_id(report_id)
        unsupported_r_features = _find_unsupported_r_qmd_features(qmd_content)
        if unsupported_r_features:
            return _unsupported_r_qmd_result(safe_id, unsupported_r_features)

        report_dir = quarto_report_renderer.get_report_dir(safe_id)
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "assets" / "charts").mkdir(parents=True, exist_ok=True)
        (report_dir / "assets" / "images").mkdir(parents=True, exist_ok=True)
        (report_dir / "tables").mkdir(parents=True, exist_ok=True)

        # Create _quarto.yml project configuration (Quarto official recommendation)
        # This ensures Quarto can find images in assets/charts and assets/images
        # and properly embed them in DOCX media/ folder during export
        _quarto_yml = report_dir / "_quarto.yml"
        quarto_config = """project:
  type: default

format:
  docx:
    resource-path: ["assets/charts", "assets/images"]
  html:
    resource-path: ["assets/charts", "assets/images"]
"""
        if not _quarto_yml.exists():
            _quarto_yml.write_text(quarto_config.strip(), encoding="utf-8")
            logger.info(
                "quarto_project_config_created",
                report_id=safe_id,
                path=str(_quarto_yml),
            )
        else:
            try:
                existing_quarto_config = _quarto_yml.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                existing_quarto_config = _quarto_yml.read_text(errors="ignore")
            if "reference-doc: default" in existing_quarto_config:
                _quarto_yml.write_text(quarto_config.strip(), encoding="utf-8")
                logger.info(
                    "quarto_project_config_normalized",
                    report_id=safe_id,
                    path=str(_quarto_yml),
                    reason="removed_placeholder_reference_doc",
                )

        copied_assets = []
        for spec in _normalize_asset_specs(assets):
            target_dir = _asset_target_dir(report_dir, spec["path"], spec.get("type"))
            copied_assets.append(_copy_file_to_dir(spec["path"], target_dir, preferred_name=spec.get("name")))

        qmd_content = _rewrite_image_refs_to_copied_assets(report_dir, qmd_content, copied_assets)
        # 自动处理 /api/image/ 引用
        qmd_content, api_copied_assets = _download_and_copy_api_images(report_dir, qmd_content)
        copied_assets.extend(api_copied_assets)
        qmd_content = _rewrite_missing_image_refs_to_copied_assets(report_dir, qmd_content, copied_assets)
        qmd_content = _disable_quarto_docx_auto_structure(qmd_content)
        qmd_content = _normalize_static_qmd(qmd_content)
        qmd_path = report_dir / "report.qmd"
        source_qmd = None
        if source_qmd_path:
            try:
                candidate = Path(source_qmd_path).expanduser().resolve()
                if candidate.exists() and candidate.is_file() and candidate != qmd_path.resolve():
                    source_unsupported_r_features = _find_unsupported_r_qmd_features(
                        candidate.read_text(encoding="utf-8")
                    )
                    if source_unsupported_r_features:
                        return _unsupported_r_qmd_result(safe_id, source_unsupported_r_features)
                    source_qmd = candidate
            except (OSError, UnicodeDecodeError):
                source_qmd = None

        qmd_path.write_text(qmd_content, encoding="utf-8")

        if report_data is not None:
            (report_dir / "report_data.json").write_text(
                json.dumps(report_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        meta_path = report_dir / "meta.json"
        existing_meta: Dict[str, Any] = {}
        if meta_path.exists():
            try:
                existing_meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                existing_meta = {}

        validation = _validate_image_refs(report_dir, qmd_content)
        now = datetime.now().isoformat()
        history = list(existing_meta.get("history") or [])
        version = int(existing_meta.get("version") or 0) + 1
        history.append(
            {
                "version": version,
                "updated_at": now,
                "source": "create_report_package",
                "qmd_size": qmd_path.stat().st_size,
            }
        )
        files = {
            "qmd": str(qmd_path),
            "html": str(report_dir / "report.html"),
            "docx": str(report_dir / "report.docx"),
        }
        if source_qmd:
            files["source_qmd"] = str(source_qmd)

        meta = {
            "report_id": safe_id,
            "title": title or metadata.get("title") if isinstance(metadata, dict) else title,
            "created_at": existing_meta.get("created_at") or now,
            "updated_at": now,
            "source": "create_report_package",
            "files": files,
            "assets": copied_assets,
            "validation": validation,
            "version": version,
            "history": history[-20:],
        }
        if report_type:
            meta["report_type"] = report_type
        if design_profile:
            meta["design_profile"] = design_profile
        if design_intent:
            meta["design_intent"] = design_intent
        if metadata:
            for key, value in metadata.items():
                if key not in RESERVED_REPORT_META_KEYS:
                    meta[key] = value
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        if validation.get("issues"):
            validation_error = format_report_image_validation_error(validation)
            return {
                "success": False,
                "data": {
                    "error": validation_error,
                    "report_id": safe_id,
                    "report_dir": str(report_dir),
                    "validation": validation,
                    "copied_assets": copied_assets,
                },
                "metadata": {
                    "generator": "create_report_package",
                    "schema_version": "report_package.v1",
                },
                "summary": "报告包创建失败：图片引用无法解析，请按错误提示修复后重试。",
            }

        html_preview = None
        render_error = None
        if render_html:
            if validation.get("missing"):
                render_error = f"Missing local image refs: {', '.join(validation['missing'])}"
                logger.warning(
                    "create_report_package_image_refs_missing",
                    report_id=safe_id,
                    missing=validation.get("missing"),
                )
            else:
                try:
                    html_path = quarto_report_renderer.render_preview_html(safe_id)
                    html_preview = build_report_html_preview(safe_id, html_path)
                    meta = record_report_update(
                        safe_id,
                        source="create_report_package_render",
                        html_path=html_path,
                        increment_version=False,
                    )
                except Exception as exc:
                    render_error = str(exc)
                    logger.warning("create_report_package_html_render_failed", report_id=safe_id, error=render_error)

        data = {
            "report_id": safe_id,
            "file_path": str(source_qmd or qmd_path),
            "report_dir": str(report_dir),
            "file_type": "report",
            "generator": "create_report_package",
            "validation": validation,
            "copied_assets": copied_assets,
            "version": meta.get("version"),
        }
        if html_preview:
            data["html_preview"] = html_preview
        else:
            data["markdown_preview"] = {
                "content": qmd_content,
                "file_type": "report",
                "schema_version": "report_package.v1",
            }
        if render_error:
            data["render_error"] = render_error
            data["error"] = render_error

        attach_document_resources(
            data,
            qmd_path,
            kind="report",
            format="qmd",
            title=data.get("report_id"),
            preview_path=preview_output_path(html_preview),
            generator="create_report_package",
            metadata={"report_id": safe_id},
        )
        primary_artifact_path = str(html_path) if html_preview and html_path else str(qmd_path)
        resume_context = build_artifact_resume_context(
            data,
            qmd_path,
            tool_hint=(
                f"Use read_file(path='{qmd_path}') to inspect the report source, "
                f"or present_artifact(file_path='{primary_artifact_path}') to preview it."
            ),
            extra_resume={
                "report_id": safe_id,
                "report_dir": str(report_dir),
                "source_qmd_path": str(source_qmd) if source_qmd else None,
                "primary_artifact_path": primary_artifact_path,
            },
        )

        return {
            "success": not bool(render_error),
            "data": data,
            "resources": data.get("resources", []),
            **resume_context,
            "metadata": {"generator": "create_report_package", "schema_version": "report_package.v1"},
            "summary": (
                f"报告包创建失败：{render_error}。请按错误提示修复后重新打包。"
                if render_error
                else (
                    f"报告包已创建：{safe_id}。右侧预览已生成，预览和下载由右侧文档面板处理。"
                    if html_preview
                    else f"报告包已创建：{safe_id}。HTML预览尚未生成，右侧文档面板显示QMD预览。"
                )
            ),
        }


class RenderReportPackageTool(LLMTool):
    """Render a standard ReportPackage to requested formats."""

    def __init__(self):
        super().__init__(
            name="render_report_package",
            description="将标准 ReportPackage 的 report.qmd 渲染为 html/docx/share_html。HTML用于右侧面板预览，DOCX用于正式报告下载。",
            category=ToolCategory.REPORTING,
            version="1.0.0",
        )
        self.function_schema = {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "report_id": {"type": "string", "description": "报告ID。"},
                    "format": {
                        "type": "string",
                        "enum": ["html", "docx", "share_html"],
                        "description": "渲染格式。",
                        "default": "html",
                    },
                },
                "required": ["report_id"],
            },
        }

    async def execute(self, report_id: str, format: str = "html", **kwargs) -> Dict[str, Any]:
        safe_id = _safe_report_id(report_id)
        try:
            if format == "html":
                path = quarto_report_renderer.render_preview_html(safe_id)
                meta = record_report_update(safe_id, source="render_report_package_html", html_path=path)
                data = {
                    "report_id": safe_id,
                    "file_path": str(quarto_report_renderer.get_report_dir(safe_id) / "report.qmd"),
                    "path": str(path),
                    "file_type": "report",
                    "generator": "render_report_package",
                    "html_preview": build_report_html_preview(safe_id, path),
                    "version": meta.get("version"),
                }
                attach_document_resources(
                    data,
                    path,
                    kind="report",
                    format="html",
                    title=safe_id,
                    preview_path=path,
                    generator="render_report_package",
                    metadata={"report_id": safe_id},
                )
            elif format == "docx":
                path = quarto_report_renderer.render_docx(safe_id)
                data = {
                    "report_id": safe_id,
                    "file_path": str(path),
                    "file_type": "report",
                    "generator": "render_report_package",
                }
                attach_document_resources(
                    data,
                    path,
                    kind="report",
                    format="docx",
                    title=safe_id,
                    generator="render_report_package",
                    metadata={"report_id": safe_id},
                )
            elif format == "share_html":
                path = quarto_report_renderer.render_share_html(safe_id)
                data = {
                    "report_id": safe_id,
                    "file_path": str(path),
                    "file_type": "report",
                    "generator": "render_report_package",
                }
                attach_document_resources(
                    data,
                    path,
                    kind="report",
                    format="html",
                    title=safe_id,
                    generator="render_report_package",
                    metadata={"report_id": safe_id},
                )
            else:
                return {"success": False, "data": {"error": f"不支持的格式: {format}"}, "summary": "报告渲染格式不支持"}
        except (FileNotFoundError, ValueError, ReportRenderError) as exc:
            return {"success": False, "data": {"error": str(exc), "report_id": safe_id}, "summary": f"报告渲染失败：{exc}"}

        return {
            "success": True,
            "data": data,
            "resources": data.get("resources", []),
            "metadata": {"generator": "render_report_package", "schema_version": "report_package.v1"},
            "summary": f"报告 {safe_id} 已渲染为 {format}",
        }


class ValidateReportPackageTool(LLMTool):
    """Validate qmd, image refs, and generated deliverables."""

    def __init__(self):
        super().__init__(
            name="validate_report_package",
            description="验收标准 ReportPackage：检查 report.qmd、图片引用、meta/report_data、HTML预览和DOCX产物。",
            category=ToolCategory.REPORTING,
            version="1.0.0",
        )
        self.function_schema = {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "report_id": {"type": "string", "description": "报告ID。"},
                    "require_html": {"type": "boolean", "default": True},
                    "require_docx": {"type": "boolean", "default": False},
                },
                "required": ["report_id"],
            },
        }

    async def execute(
        self,
        report_id: str,
        require_html: bool = True,
        require_docx: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        safe_id = _safe_report_id(report_id)
        try:
            report_dir = quarto_report_renderer.get_report_dir(safe_id)
        except ValueError as exc:
            return {"success": False, "data": {"error": str(exc)}, "summary": "报告ID无效"}

        qmd_content = _read_qmd(report_dir)
        checks = {
            "report_id": safe_id,
            "report_dir": str(report_dir),
            "qmd_exists": (report_dir / "report.qmd").exists(),
            "meta_exists": (report_dir / "meta.json").exists(),
            "report_data_exists": (report_dir / "report_data.json").exists(),
            "html_exists": (report_dir / "report.html").exists(),
            "docx_exists": (report_dir / "report.docx").exists(),
            "image_refs": _validate_image_refs(report_dir, qmd_content),
        }
        errors = []
        if not checks["qmd_exists"]:
            errors.append("缺少 report.qmd")
        if require_html and not checks["html_exists"]:
            errors.append("缺少 report.html")
        if require_docx and not checks["docx_exists"]:
            errors.append("缺少 report.docx")
        if checks["image_refs"]["missing"]:
            errors.append(f"图片引用缺失: {', '.join(checks['image_refs']['missing'][:5])}")
        if checks["image_refs"]["api_image_refs"]:
            errors.append("qmd 包含 /api/image/ 引用，建议改为报告包内相对图片路径以保证 Word/PPT 导出")

        checks["errors"] = errors
        if checks["image_refs"]["issues"]:
            checks["error"] = format_report_image_validation_error(checks["image_refs"])
        return {
            "success": not errors,
            "data": checks,
            "metadata": {"generator": "validate_report_package", "schema_version": "report_package.v1"},
            "summary": "报告包验收通过" if not errors else "报告包验收发现问题：" + "；".join(errors),
        }
