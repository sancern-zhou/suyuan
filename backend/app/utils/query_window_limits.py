"""API 查询时间窗限制：按数据粒度约束单次查询跨度，避免一次拉取过量数据堵死接口。

限制在多源监测接口的客户端层执行（VOCs / PM2.5 组分），所有调用这些客户端的
问数工具自动生效。超限时返回可执行的错误文案，引导调用方拆分为分段查询。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

# 单次查询允许的最大时间跨度（按数据粒度）
MAX_SPAN_BY_GRANULARITY: dict[str, timedelta] = {
    "hour": timedelta(days=31),
    "day": timedelta(days=92),
    "month": timedelta(days=366),
    "year": timedelta(days=3660),
}

_GRANULARITY_LABELS = {
    "hour": "小时",
    "day": "日",
    "month": "月",
    "year": "年",
}

# 接口约定的粒度编码：1=小时，2=日，3=月，5=年；0 在部分组分接口中同样表示小时数值
_GRANULARITY_ALIASES: dict[Any, str] = {
    0: "hour",
    1: "hour",
    2: "day",
    3: "month",
    5: "year",
    "0": "hour",
    "1": "hour",
    "2": "day",
    "3": "month",
    "5": "year",
    "hour": "hour",
    "hourly": "hour",
    "1h": "hour",
    "时": "hour",
    "小时": "hour",
    "day": "day",
    "daily": "day",
    "日": "day",
    "日均": "day",
    "month": "month",
    "monthly": "month",
    "月": "month",
    "year": "year",
    "yearly": "year",
    "年": "year",
}

_DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d",
)


def normalize_granularity(value: Any, default: str = "hour") -> str:
    """把接口粒度参数（整数编码或字符串）归一为 hour/day/month/year。"""
    if value is None:
        return default
    key: Any = value.strip().lower() if isinstance(value, str) else value
    if key in _GRANULARITY_ALIASES:
        return _GRANULARITY_ALIASES[key]
    try:
        return _GRANULARITY_ALIASES[int(key)]
    except (TypeError, ValueError, KeyError):
        return default


def parse_query_datetime(value: Any) -> Optional[datetime]:
    """解析查询时间参数；无法识别时返回 None（交由各工具原有格式校验处理）。"""
    if isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def check_query_window(
    start_time: Any,
    end_time: Any,
    granularity: Any,
    *,
    tool: str = "接口",
) -> Optional[str]:
    """检查单次查询跨度是否超过该粒度的上限。

    Returns:
        超限时返回面向调用方的中文错误文案；合法或时间无法解析时返回 None。
    """
    start = parse_query_datetime(start_time)
    end = parse_query_datetime(end_time)
    if start is None or end is None or end <= start:
        # 起止顺序与格式由各工具原有校验负责，这里不重复报错
        return None

    unit = normalize_granularity(granularity)
    limit = MAX_SPAN_BY_GRANULARITY.get(unit)
    if limit is None:
        return None

    span = end - start
    if span <= limit:
        return None

    label = _GRANULARITY_LABELS[unit]
    return (
        f"{tool}单次查询时间跨度为 {span.days} 天，超过{label}粒度上限 {limit.days} 天。"
        f"单次跨度过大会一次性拉取大量{label}数据，容易造成接口超时或拥堵；"
        "请谨慎全量获取长时间细粒度数据，优先圈定重点时段（如污染过程、超标日、高值时段）"
        f"做精细取数与分析，确需覆盖全时段时拆分为不超过 {limit.days} 天的分段查询后合并结果。"
    )
