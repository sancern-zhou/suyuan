"""Create a contact-sheet montage from rendered slide PNG files."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Iterable, List

from PIL import Image, ImageDraw


def _normalize_pil_color(color: str) -> str:
    value = color.strip()
    if value.startswith("#"):
        return value
    if len(value) in (6, 8) and all(char in "0123456789abcdefABCDEF" for char in value):
        return f"#{value[:6]}"
    return value


def create_montage(
    image_paths: Iterable[Path],
    output_path: Path,
    thumb_width: int = 320,
    padding: int = 18,
    background: str = "#FFFFFF",
) -> Path:
    paths: List[Path] = [Path(path) for path in image_paths]
    bg_color = _normalize_pil_color(background)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not paths:
        image = Image.new("RGB", (thumb_width, thumb_width), bg_color)
        image.save(output_path)
        return output_path

    thumbs = []
    for index, path in enumerate(paths, start=1):
        image = Image.open(path).convert("RGB")
        ratio = thumb_width / image.width
        thumb_height = max(1, int(image.height * ratio))
        image = image.resize((thumb_width, thumb_height), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (thumb_width, thumb_height + 24), bg_color)
        canvas.paste(image, (0, 0))
        draw = ImageDraw.Draw(canvas)
        draw.text((6, thumb_height + 4), f"{index}", fill=(90, 90, 90))
        thumbs.append(canvas)

    cols = min(4, max(1, math.ceil(math.sqrt(len(thumbs)))))
    rows = math.ceil(len(thumbs) / cols)
    cell_w = thumb_width + padding
    cell_h = max(thumb.height for thumb in thumbs) + padding
    montage = Image.new("RGB", (cols * cell_w + padding, rows * cell_h + padding), bg_color)
    for idx, thumb in enumerate(thumbs):
        row = idx // cols
        col = idx % cols
        montage.paste(thumb, (padding + col * cell_w, padding + row * cell_h))

    montage.save(output_path)
    return output_path
