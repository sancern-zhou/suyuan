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


class ReportRenderError(RuntimeError):
    """Raised when Quarto rendering fails."""


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
        source_qmd = self._get_source_qmd_path(report_dir)
        qmd_path = source_qmd or report_dir / "report.qmd"
        if not qmd_path.exists():
            raise FileNotFoundError(f"report.qmd not found for report_id={report_id}")
        return qmd_path.resolve()

    def render_preview_html(self, report_id: str) -> Path:
        """Render lightweight preview HTML with external assets."""
        report_dir = self.get_report_dir(report_id)
        self._snapshot_source_qmd(report_dir)
        output_path = report_dir / "report.html"
        self.get_qmd_path(report_id)
        self._run_quarto(
            report_dir,
            ["render", "report.qmd", "--to", "html", "--output", "report.html"],
        )
        return output_path

    def render_docx(self, report_id: str) -> Path:
        report_dir = self.get_report_dir(report_id)
        qmd_path = self.get_qmd_path(report_id)
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
            self._snapshot_source_qmd(report_dir)
            self.get_qmd_path(report_id)
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
            html = self._inject_base_href(html, f"/api/reports/{report_id}/")
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
            "share_url": f"/api/reports/share/{token}",
            "html_url": f"/api/reports/{report_id}/share/html",
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
        """Create a temporary qmd without placeholder reference-doc values."""
        values = self._qmd_reference_doc_values(qmd_path)
        placeholders = {"default", "none", "null", "~"}
        if not any(value.lower() in placeholders for value in values):
            return qmd_path

        try:
            text = qmd_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = qmd_path.read_text(errors="ignore")

        pattern = re.compile(
            r"^\s*reference[-_]doc\s*:\s*['\"]?(?:default|none|null|~)['\"]?\s*(?:#.*)?$\n?",
            re.IGNORECASE | re.MULTILINE,
        )
        sanitized = pattern.sub("", text)
        sanitized = re.sub(
            r"(?m)^(\s*)docx:\s*\n(?=(?:\1\S|\S|---))",
            "",
            sanitized,
        )
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
        logger.info("quarto_render_done", stdout=completed.stdout, stderr=completed.stderr)

    def _read_meta(self, report_dir: Path) -> Dict[str, Any]:
        meta_path = report_dir / "meta.json"
        if not meta_path.exists():
            return {}
        return json.loads(meta_path.read_text(encoding="utf-8"))

    def _write_meta(self, report_dir: Path, meta: Dict[str, Any]) -> None:
        meta_path = report_dir / "meta.json"
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def _get_source_qmd_path(self, report_dir: Path) -> Path | None:
        meta = self._read_meta(report_dir)
        files = meta.get("files") if isinstance(meta.get("files"), dict) else {}
        raw_path = files.get("source_qmd") or meta.get("source_qmd")
        if not raw_path:
            return None
        source_qmd = Path(raw_path).expanduser().resolve()
        if source_qmd == (report_dir / "report.qmd").resolve():
            return None
        return source_qmd

    def _snapshot_source_qmd(self, report_dir: Path) -> Path | None:
        source_qmd = self._get_source_qmd_path(report_dir)
        if not source_qmd:
            return None
        if not source_qmd.exists():
            raise FileNotFoundError(f"source_qmd not found: {source_qmd}")
        snapshot_qmd = report_dir / "report.qmd"
        text = source_qmd.read_text(encoding="utf-8", errors="replace")
        snapshot_qmd.write_text(text, encoding="utf-8")
        self._copy_source_qmd_local_assets(source_qmd, report_dir, text)
        logger.info(
            "report_source_qmd_snapshotted",
            source_qmd=str(source_qmd),
            snapshot_qmd=str(snapshot_qmd),
        )
        return snapshot_qmd

    def _copy_source_qmd_local_assets(self, source_qmd: Path, report_dir: Path, qmd_text: str) -> None:
        source_dir = source_qmd.parent
        for match in MARKDOWN_IMAGE_PATTERN.finditer(qmd_text or ""):
            src = match.group("src").strip().split("#", 1)[0].split("?", 1)[0]
            if not src or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", src) or src.startswith("/api/"):
                continue
            source_asset = Path(src)
            if source_asset.is_absolute():
                continue
            source_asset = (source_dir / source_asset).resolve()
            try:
                source_asset.relative_to(source_dir.resolve())
            except ValueError:
                continue
            if not source_asset.exists() or not source_asset.is_file():
                continue
            target_asset = (report_dir / Path(src)).resolve()
            try:
                target_asset.relative_to(report_dir.resolve())
            except ValueError:
                continue
            target_asset.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_asset, target_asset)


quarto_report_renderer = QuartoReportRenderer()
