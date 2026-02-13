import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from app.agent.react_agent import ReActAgent


@pytest.mark.asyncio
async def test_multi_expert_full_pipeline():
    """完整触发主Agent -> 多专家 -> 最终报告的链路。"""
    query = (
        "请对广州天河站在2025-08-01到2025-08-09期间的PM2.5污染做一次完整溯源分析，"
        "需要包含气象背景、组分源解析、可视化图表以及综合报告。"
    )

    agent = ReActAgent(max_iterations=12, enable_multi_expert=True)

    final_result = None
    async for event in agent.analyze(query):
        if event["type"] == "complete":
            final_result = event["data"]

    assert final_result is not None, "未返回最终结果"
    assert (
        final_result.get("pipeline_status") == "completed"
    ), f"多专家流程失败: {final_result}"

    expert_results = final_result.get("expert_results", {})
    for name in ("weather", "component", "viz", "report"):
        assert name in expert_results, f"缺少 {name} 专家输出"
        assert expert_results[name].get("has_data"), f"{name} 专家未产生有效数据"

    report = final_result.get("final_report")
    assert report, "缺少最终报告"
    assert report.get("comprehensive_report"), "综合报告为空"
    assert report.get("confidence", 0) > 0, "综合报告置信度为0"


@pytest.mark.asyncio
async def test_expert_router_direct_flow():
    """直接调用 ExpertRouter，验证 pipeline 执行。"""
    from app.agent.context.data_context_manager import DataContextManager
    from app.agent.experts.expert_router import ExpertRouter

    data_context = DataContextManager(session_id="test_e2e_router")
    router = ExpertRouter(data_context)

    task = {
        "description": "广州天河站多维度PM2.5溯源分析",
        "lat": 23.13,
        "lon": 113.28,
        "station_id": "天河站",
        "pollutant_type": "PM2.5",
        "time_range": {
            "start": "2025-08-01T00:00:00",
            "end": "2025-08-09T23:59:59",
        },
        "require_full_pipeline": True,
    }

    result = await router.route_and_execute(task, metadata={})

    assert result["pipeline_status"] == "completed", f"专家路由失败: {result}"
    assert result["final_report"], "缺少最终报告"
    assert result["final_report"].get("confidence", 0) > 0, "报告置信度过低"
