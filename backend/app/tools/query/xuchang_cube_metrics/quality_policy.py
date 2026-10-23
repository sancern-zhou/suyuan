"""Decision guidance based on source coverage and freshness state."""

POLICY = {
    "ok": {"decision": "可用于定量判断", "guidance": "数据覆盖和时效满足当前查询范围。"},
    "degraded": {"decision": "仅可作谨慎判断", "guidance": "应说明缺失、滞后或原始口径限制，不跨范围外推。"},
    "blocked": {"decision": "不可形成业务结论", "guidance": "只能报告数据问题和待核实事项。"},
    "unknown": {"decision": "质量未知", "guidance": "不得默认数据完整可靠，必要时补查数据覆盖。"},
}


def quality_guidance(status: str) -> dict[str, str]:
    return dict(POLICY.get(status, POLICY["unknown"]))
