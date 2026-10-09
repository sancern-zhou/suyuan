# -*- coding: utf-8 -*-
"""测试套件公共配置。

Windows 本地开发环境没有 fcntl（Unix 专用），而 app.services 等模块在
顶层无条件导入它；此处仅在真实 fcntl 不可用时注入无操作替身，
Linux/CI 上不受影响。
"""
from __future__ import annotations

import sys
import types

try:
    import fcntl  # noqa: F401
except ImportError:  # pragma: no cover - 仅 Windows 本地测试路径
    _fcntl_stub = types.ModuleType("fcntl")
    _fcntl_stub.LOCK_EX = 2
    _fcntl_stub.LOCK_SH = 1
    _fcntl_stub.LOCK_UN = 8
    _fcntl_stub.flock = lambda *args, **kwargs: None
    sys.modules["fcntl"] = _fcntl_stub
