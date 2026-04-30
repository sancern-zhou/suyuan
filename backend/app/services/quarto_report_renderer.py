"""
Quarto report rendering service.

Report packages live under backend_data_registry/reports/{report_id}.
The preview HTML keeps asset references external for fast in-app loading.
The share HTML embeds resources into a standalone file.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import structlog

logger = structlog.get_logger()


REPORT_ROOT = (Path(__file__).resolve().parents[3] / "backend_data_registry" / "reports").resolve()


class ReportRenderError(RuntimeError):
    """Raised when Quarto rendering fails."""


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
        qmd_path = self.get_report_dir(report_id) / "report.qmd"
        if not qmd_path.exists():
            raise FileNotFoundError(f"report.qmd not found for report_id={report_id}")
        return qmd_path

    def render_preview_html(self, report_id: str) -> Path:
        """Render lightweight preview HTML with external assets."""
        report_dir = self.get_report_dir(report_id)
        self.get_qmd_path(report_id)
        self._run_quarto(
            report_dir,
            ["render", "report.qmd", "--to", "html", "--output", "report.html"],
        )
        return report_dir / "report.html"

    def render_docx(self, report_id: str) -> Path:
        report_dir = self.get_report_dir(report_id)
        self.get_qmd_path(report_id)
        self._run_quarto(
            report_dir,
            ["render", "report.qmd", "--to", "docx", "--output", "report.docx"],
        )
        return report_dir / "report.docx"

    def render_pptx(self, report_id: str) -> Path:
        report_dir = self.get_report_dir(report_id)
        self.get_qmd_path(report_id)
        self._run_quarto(
            report_dir,
            ["render", "report.qmd", "--to", "pptx", "--output", "report.pptx"],
        )
        return report_dir / "report.pptx"

    def render_share_html(self, report_id: str) -> Dict[str, Any]:
        """Render standalone HTML and persist a share token in meta.json."""
        report_dir = self.get_report_dir(report_id)
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


quarto_report_renderer = QuartoReportRenderer()
