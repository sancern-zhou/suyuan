"""
Quarto report rendering service.

Report packages live under backend_data_registry/reports/{report_id}.
The preview HTML keeps asset references external for fast in-app loading.
The share HTML embeds resources into a standalone file.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import structlog

from app.auth.share_access import external_api_path
from app.services.report.government_docx_style import (
    ensure_government_reference_docx,
    finalize_government_docx,
    normalize_docx_image_paragraphs,
)
from app.utils.path_config import get_images_dir, get_reports_dir

logger = structlog.get_logger()

MARKDOWN_IMAGE_PATTERN = re.compile(r"!\[[^\]]*\]\((?P<src>[^)]+)\)")


# ✅ 使用统一路径配置（避免路径混乱）
REPORT_ROOT = get_reports_dir()


def _disable_docx_quarto_auto_structure(qmd_content: str) -> tuple[str, bool]:
    """Disable Quarto-owned TOC/numbering in the temporary DOCX render source."""
    if not qmd_content.startswith("---"):
        return qmd_content, False

    end_match = re.search(r"(?m)^---\s*$", qmd_content[3:])
    if not end_match:
        return qmd_content, False

    header_end = 3 + end_match.end()
    header = qmd_content[:header_end]
    body = qmd_content[header_end:]
    lines = header.splitlines(keepends=True)
    changed = False

    for index, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r"(toc|number-sections):\s*true\s*(#.*)?$", stripped):
            key = stripped.split(":", 1)[0]
            indent = len(line) - len(line.lstrip(" "))
            newline = "\n" if line.endswith("\n") else ""
            comment = ""
            if "#" in stripped:
                comment = " " + stripped[stripped.index("#") :]
            lines[index] = f"{' ' * indent}{key}: false{comment}{newline}"
            changed = True

    if not changed:
        return qmd_content, False
    return "".join(lines) + body, True


class ReportRenderError(RuntimeError):
    """Raised when Quarto rendering fails."""


def markdown_image_path(reference: str) -> str:
    """Return the path portion of a Markdown image destination."""
    value = reference.strip()
    if value.startswith("<"):
        closing = value.find(">")
        if closing > 0:
            return value[1:closing]
    match = re.match(
        r'''^(?P<path>\S+?)(?:\s+(?:"[^"]*"|'[^']*'|\([^)]*\)))?\s*$''',
        value,
    )
    return match.group("path") if match else value


def inspect_report_image_refs(
    report_dir: Path,
    qmd_content: str,
    *,
    qmd_path: Path | None = None,
) -> Dict[str, Any]:
    """Inspect package-local Markdown image references before rendering."""
    report_root = report_dir.resolve()
    refs: list[str] = []
    missing: list[str] = []
    api_refs: list[str] = []
    issues: list[Dict[str, str]] = []

    for match in MARKDOWN_IMAGE_PATTERN.finditer(qmd_content or ""):
        ref = match.group("src").strip()
        if not ref or re.match(r"^(?:https?://|data:)", ref, re.IGNORECASE):
            continue
        refs.append(ref)
        if ref.startswith("/api/image/"):
            api_refs.append(ref)
            continue

        clean_ref = markdown_image_path(ref).split("#", 1)[0].split("?", 1)[0].strip()
        candidate = (report_dir / clean_ref).resolve()
        reason = None
        try:
            candidate.relative_to(report_root)
        except ValueError:
            reason = "path escapes report package"
        else:
            if not candidate.exists():
                reason = "file does not exist"
            elif not candidate.is_file():
                reason = "path is not a file"

        if reason:
            missing.append(ref)
            filename = Path(clean_ref).name or "image.png"
            issues.append(
                {
                    "reference": ref,
                    "resolved_path": str(candidate),
                    "reason": reason,
                    "repair_hint": (
                        "Pass the real image path in create_report_package.assets and "
                        f"use the copied package path assets/charts/{filename}, "
                        "then validate again."
                    ),
                }
            )

    return {
        "qmd_path": str(qmd_path or report_dir / "report.qmd"),
        "refs": refs,
        "missing": missing,
        "api_image_refs": api_refs,
        "issues": issues,
    }


def format_report_image_validation_error(validation: Dict[str, Any]) -> str:
    """Build an actionable error that an Agent can use to repair a report."""
    lines = [f"Report image validation failed for {validation.get('qmd_path', 'report.qmd')}:"]
    for issue in validation.get("issues") or []:
        lines.extend(
            [
                f"- reference: {issue['reference']}",
                f"  resolved_path: {issue['resolved_path']}",
                f"  reason: {issue['reason']}",
            ]
        )
    if validation.get("issues"):
        lines.append(f"Repair: {validation['issues'][0]['repair_hint']}")
    return "\n".join(lines)


def _process_api_image_refs_in_qmd(
    qmd_path: Path,
    report_dir: Path,
) -> Dict[str, Any]:
    """
    处理 qmd 文件中的 /api/image/ 引用，将图片复制到报告包内并更新引用。

    这是为了确保 Quarto 渲染 DOCX 时能够找到图片文件。
    Quarto/Pandoc 不会通过 HTTP 请求获取图片，必须使用本地相对路径。
    """
    try:
        qmd_content = qmd_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        qmd_content = qmd_path.read_text(errors="ignore")

    api_image_refs = []
    for match in MARKDOWN_IMAGE_PATTERN.finditer(qmd_content):
        src = match.group("src").strip()
        if src.startswith("/api/image/"):
            image_id = src[len("/api/image/"):].split("?")[0].split("#")[0]
            api_image_refs.append({
                "original_ref": src,
                "image_id": image_id,
                "markdown_match": match.group(0)
            })

    if not api_image_refs:
        return {"processed": 0, "copied": [], "qmd_modified": False}

    logger.info(
        "quarto_docx_processing_api_image_refs",
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

        # 查找图片文件（支持多种扩展名）
        image_file = None
        for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"]:
            candidate = image_cache_dir / f"{image_id}{ext}"
            if candidate.exists():
                image_file = candidate
                break

        if not image_file:
            logger.warning(
                "quarto_docx_api_image_not_found",
                image_id=image_id,
                searched_dir=str(image_cache_dir)
            )
            continue

        target_name = f"{image_id}{image_file.suffix}"
        target_path = charts_dir / target_name
        relative_path = f"assets/charts/{target_name}"

        try:
            shutil.copy2(image_file, target_path)
            rewritten_qmd = rewritten_qmd.replace(
                ref_info["markdown_match"],
                ref_info["markdown_match"].replace(original_ref, relative_path)
            )
            copied_assets.append({
                "source": str(image_file),
                "target": str(target_path),
                "relative_path": relative_path,
                "original_api_ref": original_ref
            })
            logger.info(
                "quarto_docx_api_image_copied",
                image_id=image_id,
                original_ref=original_ref,
                new_ref=relative_path
            )
        except Exception as exc:
            logger.error(
                "quarto_docx_api_image_copy_failed",
                image_id=image_id,
                error=str(exc)
            )

    if copied_assets:
        qmd_path.write_text(rewritten_qmd, encoding="utf-8")
        logger.info(
            "quarto_docx_qmd_updated_with_local_refs",
            report_dir=str(report_dir),
            updated_count=len(copied_assets)
        )

    return {
        "processed": len(api_image_refs),
        "copied": copied_assets,
        "qmd_modified": len(copied_assets) > 0
    }


class QuartoReportRenderer:
    """Render and serve standardized Quarto report packages."""

    def __init__(self, report_root: Path = REPORT_ROOT) -> None:
        self.report_root = report_root.resolve()
        self.report_root.mkdir(parents=True, exist_ok=True)

    def get_report_dir(self, report_id: str) -> Path:
        if not report_id or any(sep in report_id for sep in ("/", "\\")) or ".." in report_id:
            raise ValueError("Invalid report_id")
        report_dir = (self.report_root / report_id).resolve()
        report_dir.relative_to(self.report_root)
        return report_dir

    def get_qmd_path(self, report_id: str) -> Path:
        report_dir = self.get_report_dir(report_id)
        qmd_path = report_dir / "report.qmd"
        if not qmd_path.exists():
            raise FileNotFoundError(f"report.qmd not found for report_id={report_id}")
        return qmd_path.resolve()

    def _validate_render_qmd(self, report_dir: Path, qmd_path: Path) -> Dict[str, Any]:
        text = qmd_path.read_text(encoding="utf-8", errors="replace")
        validation = inspect_report_image_refs(
            report_dir,
            text,
            qmd_path=qmd_path,
        )
        if validation["issues"]:
            raise ReportRenderError(format_report_image_validation_error(validation))
        return validation

    def render_preview_html(self, report_id: str) -> Path:
        """Render lightweight preview HTML with external assets."""
        report_dir = self.get_report_dir(report_id)
        output_path = report_dir / "report.html"
        qmd_path = self.get_qmd_path(report_id)
        self._validate_render_qmd(report_dir, qmd_path)
        self._run_quarto(
            report_dir,
            ["render", "report.qmd", "--to", "html", "--output", "report.html"],
        )
        return output_path

    def render_docx(self, report_id: str) -> Path:
        report_dir = self.get_report_dir(report_id)
        qmd_path = self.get_qmd_path(report_id)
        self._validate_render_qmd(report_dir, qmd_path)
        self._normalize_project_config_for_docx(report_dir)

        # 自动处理 /api/image/ 引用，确保 Quarto 能找到图片
        image_process_result = _process_api_image_refs_in_qmd(qmd_path, report_dir)
        if image_process_result.get("copied"):
            logger.info(
                "quarto_docx_auto_processed_images",
                report_id=report_id,
                copied_count=len(image_process_result["copied"])
            )

        qmd_for_render = self._prepare_docx_qmd(report_dir, qmd_path)
        args = ["render", qmd_for_render.name, "--to", "docx", "--output", "report.docx"]
        if not self._qmd_has_usable_reference_doc(qmd_path):
            reference_docx = ensure_government_reference_docx()
            args.extend(["-M", f"reference-doc:{reference_docx}"])

        try:
            self._run_quarto(report_dir, args)
            docx_path = report_dir / "report.docx"
            image_cleanup = normalize_docx_image_paragraphs(docx_path)
            logger.info("quarto_docx_image_paragraphs_normalized", **image_cleanup)
            style_cleanup = finalize_government_docx(docx_path)
            logger.info("quarto_docx_government_style_finalized", **style_cleanup)
            return docx_path
        except ReportRenderError:
            raise
        except Exception as exc:
            logger.error("quarto_docx_render_failed", error=str(exc), fallback="using_html_conversion")
            return self._render_docx_from_html_fallback(report_dir)
        finally:
            if qmd_for_render != qmd_path:
                qmd_for_render.unlink(missing_ok=True)

    def _render_docx_from_html_fallback(self, report_dir: Path) -> Path:
        """Fallback method: convert HTML to DOCX when Quarto fails to embed images."""
        from app.services.report.government_docx_style import convert_html_report_to_government_docx

        html_path = report_dir / "report.html"
        if not html_path.exists():
            raise FileNotFoundError(f"HTML report not found for fallback conversion: {html_path}")

        docx_path = report_dir / "report.docx"
        result = convert_html_report_to_government_docx(
            html_path=html_path,
            output_path=docx_path,
        )
        logger.info("docx_html_fallback_complete", **result)
        return docx_path

    def render_share_html(self, report_id: str) -> Dict[str, Any]:
        """Render standalone HTML and persist a share token in meta.json."""
        report_dir = self.get_report_dir(report_id)
        try:
            qmd_path = self.get_qmd_path(report_id)
            self._validate_render_qmd(report_dir, qmd_path)
            self._run_quarto(
                report_dir,
                [
                    "render",
                    "report.qmd",
                    "--to",
                    "html",
                    "--output",
                    "report_standalone.html",
                    "-M",
                    "embed-resources:true",
                ],
            )
        except FileNotFoundError:
            preview_html = report_dir / "report.html"
            if not preview_html.exists():
                raise
            standalone_html = report_dir / "report_standalone.html"
            html = preview_html.read_text(encoding="utf-8")
            html = self._inject_base_href(
                html, external_api_path(f"/api/reports/{report_id}/")
            )
            standalone_html.write_text(html, encoding="utf-8")

        token = uuid.uuid4().hex
        meta = self._read_meta(report_dir)
        shares = meta.setdefault("shares", [])
        shares.append(
            {
                "token": token,
                "file": "report_standalone.html",
                "created_at": datetime.now().isoformat(),
            }
        )
        self._write_meta(report_dir, meta)

        return {
            "token": token,
            "share_url": external_api_path(f"/api/reports/share/{token}"),
            "html_url": external_api_path(f"/api/reports/{report_id}/share/html"),
            "file_path": str(report_dir / "report_standalone.html"),
        }

    def find_shared_html(self, token: str) -> Path | None:
        if not token or "/" in token or "\\" in token or ".." in token:
            return None
        for meta_path in self.report_root.glob("*/meta.json"):
            try:
                meta = self._read_meta(meta_path.parent)
            except Exception:
                continue
            for share in meta.get("shares", []):
                if share.get("token") == token:
                    html_path = (meta_path.parent / share.get("file", "report_standalone.html")).resolve()
                    try:
                        html_path.relative_to(meta_path.parent.resolve())
                    except ValueError:
                        return None
                    return html_path if html_path.exists() else None
        return None

    def _inject_base_href(self, html: str, href: str) -> str:
        """Ensure copied HTML reports resolve relative assets through report routes."""
        base_tag = f'<base href="{href}">'
        lower_html = html.lower()
        if "<base " in lower_html:
            return html
        head_index = lower_html.find("<head>")
        if head_index >= 0:
            insert_at = head_index + len("<head>")
            return html[:insert_at] + "\n" + base_tag + html[insert_at:]
        return base_tag + "\n" + html

    def _read_qmd_front_matter(self, qmd_path: Path) -> str:
        try:
            text = qmd_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = qmd_path.read_text(errors="ignore")
        if not text.startswith("---"):
            return ""
        end_index = text.find("\n---", 3)
        if end_index < 0:
            return ""
        return text[3:end_index]

    def _qmd_reference_doc_values(self, qmd_path: Path) -> list[str]:
        """Return reference-doc values from qmd YAML front matter."""
        yaml_header = self._read_qmd_front_matter(qmd_path)
        if not yaml_header:
            return []
        values = []
        pattern = re.compile(r"^\s*reference[-_]doc\s*:\s*(?P<value>.*?)\s*$", re.IGNORECASE | re.MULTILINE)
        for match in pattern.finditer(yaml_header):
            value = match.group("value").split("#", 1)[0].strip().strip("\"'")
            values.append(value)
        return values

    def _qmd_has_usable_reference_doc(self, qmd_path: Path) -> bool:
        """Detect a concrete DOCX reference template in qmd YAML front matter."""
        values = self._qmd_reference_doc_values(qmd_path)
        if not values:
            return False
        placeholders = {"", "default", "none", "null", "~"}
        return any(value.lower() not in placeholders for value in values)

    def _prepare_docx_qmd(self, report_dir: Path, qmd_path: Path) -> Path:
        """Create a temporary qmd with DOCX-only render metadata normalized."""
        values = self._qmd_reference_doc_values(qmd_path)
        placeholders = {"default", "none", "null", "~"}
        has_placeholder_reference_doc = any(value.lower() in placeholders for value in values)

        try:
            text = qmd_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = qmd_path.read_text(errors="ignore")

        pattern = re.compile(
            r"^\s*reference[-_]doc\s*:\s*['\"]?(?:default|none|null|~)['\"]?\s*(?:#.*)?$\n?",
            re.IGNORECASE | re.MULTILINE,
        )
        sanitized = pattern.sub("", text) if has_placeholder_reference_doc else text
        sanitized, structure_changed = _disable_docx_quarto_auto_structure(sanitized)
        if has_placeholder_reference_doc:
            sanitized = re.sub(
                r"(?m)^(\s*)docx:\s*\n(?=(?:\1\S|\S|---))",
                "",
                sanitized,
            )

        if not has_placeholder_reference_doc and not structure_changed:
            return qmd_path

        temp_qmd = report_dir / "report_docx_render.qmd"
        temp_qmd.write_text(sanitized, encoding="utf-8")
        return temp_qmd

    def _normalize_project_config_for_docx(self, report_dir: Path) -> None:
        """Remove placeholder reference-doc values from project-level config."""
        quarto_yml = report_dir / "_quarto.yml"
        if not quarto_yml.exists():
            return
        try:
            text = quarto_yml.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = quarto_yml.read_text(errors="ignore")
        pattern = re.compile(
            r"^\s*reference[-_]doc\s*:\s*['\"]?(?:default|none|null|~)['\"]?\s*(?:#.*)?$\n?",
            re.IGNORECASE | re.MULTILINE,
        )
        normalized = pattern.sub("", text)
        if normalized != text:
            quarto_yml.write_text(normalized, encoding="utf-8")
            logger.info(
                "quarto_project_config_reference_doc_normalized",
                path=str(quarto_yml),
            )

    def _run_quarto(self, cwd: Path, args: list[str]) -> None:
        quarto = shutil.which("quarto") or "quarto"
        command = [quarto, *args]
        logger.info("quarto_render_start", cwd=str(cwd), command=command)
        try:
            completed = subprocess.run(
                command,
                cwd=str(cwd),
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise ReportRenderError("Quarto is not installed or not available on PATH") from exc
        except subprocess.CalledProcessError as exc:
            logger.error(
                "quarto_render_failed",
                returncode=exc.returncode,
                stdout=exc.stdout,
                stderr=exc.stderr,
            )
            detail = exc.stderr or exc.stdout or str(exc)
            raise ReportRenderError(detail) from exc
        combined_output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
        missing_resource_lines = [
            line.strip()
            for line in combined_output.splitlines()
            if "could not fetch resource" in line.lower()
        ]
        if missing_resource_lines:
            detail = "\n".join(missing_resource_lines)
            raise ReportRenderError(
                "Quarto rendered with unresolved image resources:\n"
                f"{detail}\n"
                "Repair: pass each real image path in create_report_package.assets, use its "
                "assets/charts/{filename} package path, and validate the report again."
            )
        logger.info("quarto_render_done", stdout=completed.stdout, stderr=completed.stderr)

    def _read_meta(self, report_dir: Path) -> Dict[str, Any]:
        meta_path = report_dir / "meta.json"
        if not meta_path.exists():
            return {}
        return json.loads(meta_path.read_text(encoding="utf-8"))

    def _write_meta(self, report_dir: Path, meta: Dict[str, Any]) -> None:
        meta_path = report_dir / "meta.json"
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

quarto_report_renderer = QuartoReportRenderer()
