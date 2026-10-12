"""图表 visual_id 协议与生成：单一来源（single source of truth）。

``[[chart:<visual_id>]]`` 占位符协议要求 ID 只能包含 ``A-Za-z0-9_.-`` 且
长度 ≤ 100。该约束的**唯一定义**在本模块（``VISUAL_ID_PATTERN``），所有：

- ID 生成器（``new_visual_id``、image_cache、business_chart 等）
- 占位符匹配正则（前端 inlineChartBlocks/inlineChartImages/replyOutcomes、
  后端 social/inline_charts、安卓 InlineChart.kt）

都必须与之保持一致；后端契约测试
``backend/tests/test_visual_id_protocol.py`` 负责钉住这一不变式。

历史教训：ID 曾使用 19 位纳秒时间戳（模型照抄经常出错），且
``sanitize_image_id`` 曾允许点号与中文进入 ID（占位符匹配失败导致
Web/App 不渲染）。新增或修改 ID 生成逻辑时，先跑契约测试。
"""

import re
import time

_BASE36 = "0123456789abcdefghijklmnopqrstuvwxyz"

# 协议字符集的唯一定义：[[chart:<visual_id>]] 中 visual_id 的合法形式。
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
