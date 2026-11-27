"""Generate and normalize names for visualization payloads and files."""

import re
import time

_BASE36 = "0123456789abcdefghijklmnopqrstuvwxyz"

VISUAL_ID_PATTERN = r"[A-Za-z0-9_.-]{1,100}"

_VISUAL_ID_UNSAFE_RE = re.compile(r"[^0-9A-Za-z._-]+")


def _base36(value: int) -> str:
    if value <= 0:
        return "0"
    digits = []
    while value:
        value, rem = divmod(value, 36)
        digits.append(_BASE36[rem])
    return "".join(reversed(digits))


def new_visual_id(prefix: str, index: int | None = None) -> str:
    """生成短 visual_id，例如 ``echarts_m3k7x2q9f_0`` / ``matplotlib_m3k7x2q9f``。"""
    token = _base36(time.time_ns() // 1000)
    return f"{prefix}_{token}" if index is None else f"{prefix}_{token}_{index}"


def sanitize_visual_id(value: str) -> str:
    """把任意输入归一化为协议安全 ID（中文名、mathtext、标点等一律收敛）。

    输出保证完整匹配 ``VISUAL_ID_PATTERN`` 或为空串（由调用方提供兜底）。
    """
    text = _VISUAL_ID_UNSAFE_RE.sub("_", str(value))
    text = re.sub(r"_+", "_", text).strip("_")
    text = text.strip("-.")
    return text[:100]
