"""SSE/JSON 序列化前的非有限数值清洗。

Python ``json.dumps`` 默认 ``allow_nan=True``，会把 NaN/±Inf 输出成字面量，
而那是非法 JSON：浏览器端逐事件容错尚可继续渲染，Android ``org.json``
则直接抛 ``Forbidden numeric value: NAN`` 断流——表现为 App 端报错、
不再更新进展，而后端分析仍在正常进行。

所有面向客户端的 SSE 输出统一走 :func:`dumps_safe`：先把非有限浮点
递归替换为 ``null``，再以 ``allow_nan=False`` 兜底（宁可抛错在服务端
日志里，也不把非法 JSON 推给客户端）。
"""
from __future__ import annotations

import json
import math
from typing import Any


def sanitize_json_values(value: Any) -> Any:
    """递归把非有限浮点（NaN/±Inf）替换为 None；其余结构原样拷贝。"""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: sanitize_json_values(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_json_values(item) for item in value]
    return value


def dumps_safe(
    value: Any,
    *,
    ensure_ascii: bool = False,
    default: Any = None,
) -> str:
    """清洗后序列化；allow_nan=False 保证输出一定是合法 JSON。"""
    kwargs: dict[str, Any] = {"ensure_ascii": ensure_ascii, "allow_nan": False}
    if default is not None:
        kwargs["default"] = default
    return json.dumps(sanitize_json_values(value), **kwargs)
