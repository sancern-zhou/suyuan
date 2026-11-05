# -*- coding: utf-8 -*-
"""Translate DQ state into an explicit Agent decision boundary.

粤苏两分支的实现逐字节相同（2026-10-31 上移共享），项目工具直接 import 本模块。
"""
from typing import Dict


QUALITY_POLICY: Dict[str, Dict[str, str]] = {
    "ok": {"decision": "可用于定量判断", "guidance": "可以形成与查询范围一致的数量、趋势或比较结论。"},
    "degraded": {"decision": "仅可作谨慎判断", "guidance": "可以描述结果，但必须说明质量告警，不宜据此下强结论或跨范围外推。"},
    "blocked": {"decision": "不可形成业务结论", "guidance": "只能返回数据质量问题和待核实事项，需修复数据后再判断。"},
    "unknown": {"decision": "质量未知", "guidance": "可以展示取数结果，但应把质量状态作为不确定性，不得默认为完整可靠。"},
}


def quality_guidance(status: str) -> Dict[str, str]:
    return dict(QUALITY_POLICY.get(status, QUALITY_POLICY["unknown"]))
