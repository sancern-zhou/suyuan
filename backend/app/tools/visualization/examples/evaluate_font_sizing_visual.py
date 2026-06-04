"""Generate visual samples for chart font sizing review.

This script is intentionally manual: it writes PNGs under
html_artifacts/font_eval so reviewers can compare output sizes visually.
"""

from __future__ import annotations

import base64
import math
from pathlib import Path

from app.tools.visualization.create_report_chart.domain.pollutant_wind_rose import generate_pollution_rose_contour


def main() -> None:
    out_dir = Path("html_artifacts/font_eval")
    out_dir.mkdir(parents=True, exist_ok=True)

    wind_dirs = [i * 10 % 360 for i in range(72)]
    wind_speeds = [1.0 + (i % 8) * 0.45 for i in range(72)]
    concentrations = [
        60 + 25 * math.sin(math.radians(direction)) + 8 * (speed - 2.5)
        for direction, speed in zip(wind_dirs, wind_speeds)
    ]

    cases = [
        ("polar_100dpi_auto.png", 100, None),
        ("polar_150dpi_auto.png", 150, None),
        ("polar_220dpi_auto.png", 220, None),
        ("polar_150dpi_large.png", 150, "large"),
    ]

    for filename, dpi, font_scale in cases:
        image_base64 = generate_pollution_rose_contour(
            wind_directions=wind_dirs,
            wind_speeds=wind_speeds,
            concentrations=concentrations,
            title=f"字号策略测试 dpi={dpi} scale={font_scale or 'auto'}",
            pollutant_name="PM10",
            use_six_level=False,
            dpi=dpi,
            font_scale=font_scale,
        )
        (out_dir / filename).write_bytes(base64.b64decode(image_base64))

    print(out_dir.resolve())


if __name__ == "__main__":
    main()
