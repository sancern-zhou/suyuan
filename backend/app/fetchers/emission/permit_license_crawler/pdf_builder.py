from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

from PIL import Image


def build_pdf(page_paths: Iterable[Path | str], output_path: Path | str) -> Path:
    pages = [Path(path) for path in page_paths]
    if not pages:
        raise ValueError("at least one page image is required")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.part")
    images: list[Image.Image] = []
    try:
        for page in pages:
            with Image.open(page) as source:
                images.append(source.convert("RGB"))
        first, *remaining = images
        first.save(temporary, format="PDF", save_all=True, append_images=remaining)
        os.replace(temporary, output)
    finally:
        for image in images:
            image.close()
        temporary.unlink(missing_ok=True)
    return output
