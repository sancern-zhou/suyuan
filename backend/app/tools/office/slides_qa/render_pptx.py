"""Render PPTX decks to PDF and page PNG files."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Dict, List

from app.tools.office.soffice import run_soffice


def _convert_with_soffice(input_path: Path, output_dir: Path, target_format: str) -> Path:
    before = {path.resolve() for path in output_dir.glob(f"*.{target_format}")}
    result = run_soffice(
        [
            "--headless",
            "--invisible",
            "--norestore",
            "--convert-to",
            target_format,
            "--outdir",
            str(output_dir),
            str(input_path),
        ],
        timeout=120,
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout or f"LibreOffice {target_format} conversion failed")

    expected = output_dir / f"{input_path.stem}.{target_format}"
    if expected.exists():
        return expected

    candidates = [
        path for path in output_dir.glob(f"*.{target_format}")
        if path.resolve() not in before
    ]
    if not candidates:
        candidates = list(output_dir.glob(f"*.{target_format}"))
    if not candidates:
        raise RuntimeError(f"LibreOffice did not generate a {target_format.upper()} file")
    return max(candidates, key=lambda p: p.stat().st_mtime)


def render_pptx_to_pdf(pptx_path: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        generated = _convert_with_soffice(pptx_path, output_dir, "pdf")
    except Exception as first_error:
        with tempfile.TemporaryDirectory(prefix="pptx_qa_odp_") as tmp_name:
            tmp_dir = Path(tmp_name)
            odp_path = _convert_with_soffice(pptx_path, tmp_dir, "odp")
            try:
                generated = _convert_with_soffice(odp_path, tmp_dir, "pdf")
            except Exception as second_error:
                raise RuntimeError(
                    f"LibreOffice PDF conversion failed; direct={first_error}; odp_fallback={second_error}"
                ) from second_error
            copied = output_dir / f"{pptx_path.stem}.pdf"
            if copied.exists():
                copied.unlink()
            shutil.copy2(generated, copied)
            generated = copied

    pdf_path = output_dir / "deck.pdf"
    if generated.resolve() != pdf_path.resolve():
        if pdf_path.exists():
            pdf_path.unlink()
        shutil.move(str(generated), str(pdf_path))
    return pdf_path


def render_pdf_to_pngs(pdf_path: Path, output_dir: Path, dpi: int = 144) -> List[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF/fitz is required for PNG rendering") from exc

    doc = fitz.open(str(pdf_path))
    try:
        scale = dpi / 72.0
        matrix = fitz.Matrix(scale, scale)
        paths: List[Path] = []
        for index, page in enumerate(doc, start=1):
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            out_path = output_dir / f"page-{index:03d}.png"
            pix.save(str(out_path))
            paths.append(out_path)
        return paths
    finally:
        doc.close()


def render_deck(pptx_path: Path, qa_dir: Path, dpi: int = 144) -> Dict[str, object]:
    pdf_path = render_pptx_to_pdf(pptx_path, qa_dir)
    page_dir = qa_dir / "pages"
    png_paths = render_pdf_to_pngs(pdf_path, page_dir, dpi=dpi)
    return {
        "pdf_path": str(pdf_path),
        "page_pngs": [str(path) for path in png_paths],
        "page_count": len(png_paths),
    }
