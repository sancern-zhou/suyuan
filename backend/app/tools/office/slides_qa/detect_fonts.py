"""Extract font names from rendered PDFs."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional


def _normalize_font_name(font_name: str) -> str:
    name = font_name.lower()
    if "+" in name:
        name = name.split("+", 1)[1]
    for suffix in ("-bold", "-regular", "-italic", "-light", "-medium", "-semibold"):
        name = name.replace(suffix, "")
    return "".join(char for char in name if char.isalnum())


def detect_pdf_fonts(pdf_path: Path, expected_fonts: Optional[List[str]] = None) -> Dict[str, object]:
    try:
        import fitz
    except ImportError:
        return {
            "fonts": [],
            "missing_expected_fonts": expected_fonts or [],
            "issues": [{"type": "font_detection_unavailable", "message": "PyMuPDF/fitz is not installed"}],
        }

    fonts = set()
    doc = fitz.open(str(pdf_path))
    try:
        for page in doc:
            for font in page.get_fonts(full=True):
                if len(font) >= 4 and font[3]:
                    fonts.add(str(font[3]))
    finally:
        doc.close()

    expected = [font for font in (expected_fonts or []) if font]
    normalized_fonts = {_normalize_font_name(font) for font in fonts}
    missing = [
        font
        for font in expected
        if _normalize_font_name(font) not in normalized_fonts
    ]
    issues = [
        {"type": "expected_font_missing", "font": font}
        for font in missing
    ]
    return {
        "fonts": sorted(fonts),
        "missing_expected_fonts": missing,
        "issues": issues,
    }
