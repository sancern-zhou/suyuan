"""Load the committed demo datasets for the Jiangsu project."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATASET_PATH = Path(__file__).with_name("august_2026.json")
_DEVICE_CONTROL_PATH = Path(__file__).with_name("device_control_states.json")


@lru_cache(maxsize=1)
def load_demo_dataset() -> dict[str, Any]:
    if not _DATASET_PATH.exists():
        raise FileNotFoundError(
            "演示数据集不存在，请先运行 app.tools.jiangsu.demo_data.generate_august_dataset 生成"
        )
    return json.loads(_DATASET_PATH.read_text())


def demo_section(key: str) -> list[dict[str, Any]]:
    rows = load_demo_dataset().get(key) or []
    return [row for row in rows if isinstance(row, dict)]


def load_device_control_states() -> dict[str, Any]:
    """Seeded device-control states used by the simulated QC demo."""
    if not _DEVICE_CONTROL_PATH.exists():
        return {}
    return json.loads(_DEVICE_CONTROL_PATH.read_text())
