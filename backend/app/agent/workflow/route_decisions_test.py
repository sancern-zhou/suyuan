"""阶段 A 回归：describe_target_mode 契约查询与路由决策审计（route_decisions）。"""

import asyncio

from app.agent.workflow import route_decisions
from app.agent.workflow.target_mode_contract import describe_target_mode


def test_describe_modes_lists_delegatable_child_modes():
    text = describe_target_mode("modes")
    for mode in ("query_monitoring_station", "expert_meteorology", "office"):
        assert mode in text


def test_describe_mode_detail_has_full_contract():
    text = describe_target_mode("expert_meteorology")
    assert "能做" in text
    assert "边界" in text
    assert "产出" in text


def test_describe_mode_fuzzy_correction():
    text = describe_target_mode("expert_meterology")
    assert "expert_meteorology" in text


def test_describe_mode_primary_only_query_keeps_contract():
    text = describe_target_mode("query")
    assert "主模式" in text
    assert "能做" in text


def test_describe_mode_report_primary_only():
    text = describe_target_mode("report")
    assert "主模式" in text


def test_describe_mode_unknown_gives_candidates():
    text = describe_target_mode("nonsense_mode")
    assert "未知模式" in text


def test_describe_mode_blank_gives_usage():
    text = describe_target_mode("  ")
    assert "describe_mode" in text


def test_build_decision_row_rejects_empty_and_unknown_reason():
    row = route_decisions.build_decision_row(
        session_id="s1",
        user_identifier="u1",
        parent_mode="assistant",
        target_modes=["expert_analysis"],
        reason_code=route_decisions.REASON_ASSISTANT_JUDGMENT,
        reason_values={"goal_chars": 10},
    )
    assert row is not None
    assert row["target_modes"] == ["expert_analysis"]
    assert row["reason_values"] == {"goal_chars": 10}
    # 空目标模式与未知 reason_code 都不入账
    assert (
        route_decisions.build_decision_row(
            session_id="s1", target_modes=["", None], reason_code="assistant_judgment"
        )
        is None
    )
    assert (
        route_decisions.build_decision_row(
            session_id="s1", target_modes=["office"], reason_code="bogus"
        )
        is None
    )


def test_record_route_decision_without_loop_is_noop():
    # 无事件循环时放弃记录且不抛异常（fail-soft）。
    route_decisions.record_route_decision(
        session_id="s", target_modes=["office"], reason_code="assistant_judgment"
    )


def test_insert_failure_is_swallowed(monkeypatch):
    async def boom(row):
        raise RuntimeError("db down")

    monkeypatch.setattr(route_decisions, "_insert_row", boom)
    asyncio.run(
        route_decisions._insert_row_checked({"reason_code": "assistant_judgment"})
    )
