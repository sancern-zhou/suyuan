"""渐进发现上报（report_finding）测试：上报/去重/上限/注入条件。"""

import asyncio

from app.tools.agent_tools.call_sub_agent import build_finding_tool
from app.tools.agent_tools.report_finding_tool import ReportFindingTool


def test_report_finding_accepts_and_counts():
    async def run():
        events = []
        tool = ReportFindingTool(task_id="wf-1:air", on_finding=events.append)
        result = await tool.execute(content="全市 PM2.5 均值 58 μg/m³，同比上升 12%", tag="数值")
        assert result["success"] is True
        assert result["data"]["accepted"] is True
        assert len(events) == 1
        assert events[0]["task_id"] == "wf-1:air"
        assert events[0]["tag"] == "数值"
        assert "58" in events[0]["content"]

    asyncio.run(run())


def test_report_finding_dedupes_by_content():
    async def run():
        findings = []

        class FakeCoordinator:
            def record_finding(self, info):
                # 模拟 coordinator 的去重行为
                if any(item["content"] == info["content"] for item in findings):
                    return
                findings.append(info)

        tool = ReportFindingTool(task_id="t", on_finding=FakeCoordinator().record_finding)
        await tool.execute(content="同一发现")
        await tool.execute(content="同一发现")
        assert len(findings) == 1
        assert tool.reported == 2  # 工具侧不重复计数拦截（去重归 coordinator）

    asyncio.run(run())


def test_report_finding_budget_rejects_gracefully():
    async def run():
        events = []
        tool = ReportFindingTool(task_id="t", on_finding=events.append, max_findings=2)
        await tool.execute(content="第一条")
        await tool.execute(content="第二条")
        result = await tool.execute(content="第三条")
        assert result["data"]["accepted"] is False
        assert result["data"]["reason"] == "budget_exhausted"
        assert "合并" in result["result"]
        assert len(events) == 2

    asyncio.run(run())


def test_report_finding_empty_content_fails():
    async def run():
        tool = ReportFindingTool(task_id="t", on_finding=lambda info: None)
        result = await tool.execute(content="   ")
        assert result["success"] is False

    asyncio.run(run())


def test_build_finding_tool_conditions():
    tool = build_finding_tool("wf-1:air", lambda info: None)
    assert tool is not None
    assert tool.task_id == "wf-1:air"
    assert build_finding_tool("wf-1:air", None) is None
