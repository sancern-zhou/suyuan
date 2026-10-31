"""升级提问工具（escalate）测试：预算、超时兜底、用户作答、注入条件。"""

import asyncio
import json
import time

from app.tools.agent_tools.escalate_tool import (
    TIMEOUT_GUIDANCE,
    EscalateTool,
    escalation_redis_key,
)
from app.tools.agent_tools.call_sub_agent import build_escalation_tool


class FakeRedis:
    def __init__(self):
        self.values = {}

    async def set(self, key, value, ex=None):
        self.values[key] = value

    async def get(self, key):
        return self.values.get(key)


def make_tool(**kwargs):
    fake = FakeRedis()
    events = []
    tool = EscalateTool(
        session_id="session-1",
        workflow_id="wf-1",
        task_id="wf-1:air",
        redis_client=fake,
        redis_prefix="test:steering",
        on_escalation=events.append,
        **kwargs,
    )
    return tool, fake, events


def test_budget_exhausted_returns_guidance_without_redis_roundtrip():
    async def run():
        tool, fake, events = make_tool(max_escalations=2, timeout_seconds=1)
        for _ in range(2):
            # 无用户回答 → 走超时路径（每次 1 秒）
            result = await tool.execute(question="口径 A 还是口径 B？")
            assert result["success"] is True
            assert "假设" in result["result"]
        assert len(events) == 4  # raised + timeout 各两次
        # 第 3 次调用：预算耗尽，直接返回指引，不再写 Redis
        before = dict(fake.values)
        result = await tool.execute(question="还能问吗？")
        assert "已达上限" in result["result"]
        assert fake.values == before

    asyncio.run(run())


def test_user_answer_unblocks_parked_tool():
    async def run():
        tool, fake, events = make_tool(timeout_seconds=10)
        escalation_key = escalation_redis_key("test:steering", tool.escalation_id)

        async def answer_soon():
            for _ in range(40):
                await asyncio.sleep(0.05)
                if escalation_key in fake.values:
                    record = json.loads(fake.values[escalation_key])
                    record["status"] = "answered"
                    record["answer"] = "使用口径 A，统计全市国控站"
                    fake.values[escalation_key] = json.dumps(record, ensure_ascii=False)
                    return

        answer_task = asyncio.create_task(answer_soon())
        result = await tool.execute(question="用口径 A 还是 B？", context="两个口径差异 15%")
        await answer_task
        assert result["success"] is True
        assert result["data"]["escalation_answer"] == "使用口径 A，统计全市国控站"
        assert "口径 A" in result["result"]
        kinds = [event["event"] for event in events]
        assert kinds == ["raised", "resolved"]
        assert events[1]["answer"].startswith("使用口径 A")

    asyncio.run(run())


def test_timeout_returns_guidance_and_records_event():
    async def run():
        tool, fake, events = make_tool(timeout_seconds=1)
        started = time.monotonic()
        result = await tool.execute(question="时间范围是本月还是本季度？")
        elapsed = time.monotonic() - started
        assert 0.9 <= elapsed <= 6
        assert result["data"]["escalation_guidance"] == TIMEOUT_GUIDANCE
        assert [event["event"] for event in events] == ["raised", "timeout"]
        # pending 记录已在 Redis（24h TTL，前端/用户离线时仍可查）
        record = json.loads(fake.values[escalation_redis_key("test:steering", tool.escalation_id)])
        assert record["status"] == "pending"
        assert record["session_id"] == "session-1"

    asyncio.run(run())


def test_build_escalation_tool_conditions():
    class FakeWorkflowRun:
        task_id = "wf-9"

    class FakeExecutor:
        session_id = "parent-session"

    tool = build_escalation_tool(FakeWorkflowRun(), "wf-9:air", FakeExecutor(), lambda info: None)
    assert tool is not None
    assert tool.session_id == "parent-session"
    assert tool.workflow_id == "wf-9"
    assert tool.task_id == "wf-9:air"
    # 非工作流上下文 / 无观察者 → 不注入
    assert build_escalation_tool(None, "t", FakeExecutor(), lambda info: None) is None
    assert build_escalation_tool(FakeWorkflowRun(), "t", FakeExecutor(), None) is None
