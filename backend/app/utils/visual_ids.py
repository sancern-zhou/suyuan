"""图表 visual_id 协议与生成：单一来源（single source of truth）。

``[[chart:<visual_id>]]`` 占位符协议要求 ID 只能包含 ``A-Za-z0-9_.-`` 且
长度 ≤ 100。该约束的**唯一定义**在本模块（``VISUAL_ID_PATTERN``），所有：

- ID 生成器（``new_visual_id``、image_cache、business_chart 等）
- 占位符匹配正则（前端 inlineChartBlocks/inlineChartImages/replyOutcomes、
  后端 social/inline_charts、安卓 InlineChart.kt）
- 占位符修复（``repair_chart_reference_ids``：模型抄错 ID 时按编辑距离
  唯一近似匹配改写，agent 最终回复落库/下发前兜底）

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


def chart_reference_sub():
    """返回可对 ``[[chart:<id>]]`` 做 re.sub 的编译正则（单一定义复用）。"""
    return re.compile(r"\[\[chart:(" + VISUAL_ID_PATTERN + r")\]\]")


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


def _levenshtein_within(a: str, b: str, cap: int) -> int:
    """计算编辑距离；超过 cap 时提前返回 cap + 1（只需用于阈值比较）。"""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i]
        row_min = i
        for j, char_b in enumerate(b, start=1):
            cost = 0 if char_a == char_b else 1
            value = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
            current.append(value)
            row_min = min(row_min, value)
        if row_min > cap:
            return cap + 1
        previous = current
    return previous[-1]


def repair_chart_reference_ids(
    text: str,
    known_ids,
    max_distance: int = 3,
) -> str:
    """修复最终回复中被模型抄错的 ``[[chart:<visual_id>]]`` 占位符。

    模型引用图表时可能漏抄/错抄 ID 字符（历史教训见模块 docstring），
    前端按精确 visual_id 匹配资源，匹配不到就不渲染。本函数对每个
    占位符做一次兜底校对：

    - ID 精确存在于 ``known_ids``：原样保留；
    - 不存在但在已知 ID 中有唯一的最近似匹配（同前缀、编辑距离
      ≤ ``max_distance`` 且严格小于次优候选）：改写为正确 ID；
    - 无候选或存在歧义（多个同距候选）：保持原文，不做猜测。
    """
    if not isinstance(text, str) or "[[chart:" not in text:
        return text
    known = {str(vid) for vid in known_ids if isinstance(vid, str) and vid}
    if not known:
        return text

    def _repair(match: re.Match) -> str:
        marker_id = match.group(1)
        if marker_id in known:
            return match.group(0)
        prefix = marker_id.split("_", 1)[0]
        candidates = [vid for vid in known if vid.split("_", 1)[0] == prefix]
        best: list = []
        best_distance = max_distance + 1
        for candidate in candidates:
            distance = _levenshtein_within(marker_id, candidate, max_distance)
            if distance > max_distance:
                continue
            if distance < best_distance:
                best = [candidate]
                best_distance = distance
            elif distance == best_distance:
                best.append(candidate)
        if len(best) != 1:
            return match.group(0)
        return f"[[chart:{best[0]}]]"

    return chart_reference_sub().sub(_repair, text)
