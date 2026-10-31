"""Coordinator 新机制测试：模型错误策略表、停摆观测、用量遥测、失败抢救。

对照 ZCode dynamic-workflow v3.17.1 移植的四项引擎优化（见
docs/zcode-dynamic-workflow.md 的移植对照节）。
"""

import asyncio
import time

from app.agent.workflow.coordinator import WorkflowCoordinator
from app.agent.workflow.stall_watch import WorkflowStallWatch


class FakeJournal:
    def __init__(self):
        self.events = []

    def append(self, *, workflow_id, event_type, task_id=None, payload=None):
        self.events.append({"event_type": event_type, "task_id": task_id, "payload": payload or {}})

    def event_types(self):
        return [e["event_type"] for e in self.events]


def test_stop_class_model_error_fails_node_without_retry():
    """配额类错误走策略表立即失败：不烧重试预算、不调度重试。"""

    async def run():
        attempts = []
        journal = FakeJournal()

        async def execute(node, dependencies, attempt, retry_context=None):
            attempts.append(attempt)
            raise RuntimeError("Error code: 402 - token plan 用量上限，请升级套餐")

        coordinator = WorkflowCoordinator(
            {"workflow_id": "policy-1", "nodes": [{"task_id": "air", "max_attempts": 3}]},
            executor=execute,
            journal=journal,
        )
        result = await coordinator.run()
        assert result["status"] == "failed"
        assert attempts == [1]
        assert result["node_failure_policies"]["air"]["action"] == "stop_quota"
        failed = next(e for e in journal.events if e["event_type"] == "node.failed")
        assert failed["payload"]["retrying"] is False
        assert failed["payload"]["failure_policy"]["action"] == "stop_quota"
        assert "node.retry_scheduled" not in journal.event_types()

    asyncio.run(run())


def test_transient_model_error_retries_and_journals_retry_scheduled():
    """限流类错误按瞬态重试，journal 记录 node.retry_scheduled 与退避秒数。"""

    async def run():
        attempts = []
        journal = FakeJournal()

        async def execute(node, dependencies, attempt, retry_context=None):
            attempts.append(attempt)
            if attempt == 1:
                raise RuntimeError("Error code: 429 - rate limit exceeded, please retry")
            return {"status": "success"}

        coordinator = WorkflowCoordinator(
            {"workflow_id": "policy-2", "nodes": [{"task_id": "air", "max_attempts": 2}]},
            executor=execute,
            journal=journal,
        )
        result = await coordinator.run()
        assert result["status"] == "succeeded"
        assert attempts == [1, 2]
        scheduled = next(e for e in journal.events if e["event_type"] == "node.retry_scheduled")
        assert scheduled["payload"]["action"] == "retry_transient"
        assert scheduled["payload"]["delay_seconds"] > 0

    asyncio.run(run())


def test_node_usage_accumulates_into_budget_state_and_journal():
    """节点信封携带 usage 时：node_usage 记账、spent_tokens 累计、journal 出用量事件。"""

    async def run():
        journal = FakeJournal()

        async def execute(node, dependencies, attempt, retry_context=None):
            return {
                "status": "success",
                "metadata": {"session_id": "s1", "usage": {"turns": 2, "total_tokens": 150}},
            }

        coordinator = WorkflowCoordinator(
            {
                "workflow_id": "usage-1",
                "nodes": [
                    {"task_id": "a", "target_mode": "query", "goal": "取数"},
                    {"task_id": "b", "target_mode": "query", "goal": "再取数"},
                ],
            },
            executor=execute,
            journal=journal,
        )
        result = await coordinator.run()
        assert result["status"] == "succeeded"
        assert result["node_usage"]["a"]["total_tokens"] == 150
        assert result["budget_state"]["spent_tokens"] == 300
        types = journal.event_types()
        assert types.count("workflow.usage") == 2
        # 顺序契约：节点成功事件先于对应用量事件
        success_index = types.index("node.succeeded")
        usage_index = types.index("workflow.usage")
        assert success_index < usage_index

    asyncio.run(run())


def test_delivery_salvage_lists_failed_node_intermediate_files():
    """失败节点倒下前已交付的中间产物进入 delivery.salvage（失败不丢工作量）。"""

    async def run():
        async def execute(node, dependencies, attempt, retry_context=None):
            return {
                "success": False,
                "summary": "校验未通过",
                "data": {"file_paths": ["/sessions/s1/data/partial.csv"]},
                "metadata": {"session_id": "s1"},
            }

        coordinator = WorkflowCoordinator(
            {"workflow_id": "salvage-1", "nodes": [{"task_id": "air", "max_attempts": 1}]},
            executor=execute,
        )
        result = await coordinator.run()
        assert result["status"] == "failed"
        salvage = result["delivery"]["salvage"]
        assert len(salvage) == 1
        assert salvage[0]["task_id"] == "air"
        assert salvage[0]["delivered_files"] == ["/sessions/s1/data/partial.csv"]

    asyncio.run(run())


def test_stalled_workflow_journals_single_notification_per_quiet_segment():
    """停摆观测：静默超阈值发一次 workflow.stalled，纯观察不改变结果。"""

    async def run():
        journal = FakeJournal()

        async def execute(node, dependencies, attempt, retry_context=None):
            await asyncio.sleep(1.6)
            return {"status": "success"}

        coordinator = WorkflowCoordinator(
            {
                "workflow_id": "stall-1",
                "nodes": [{"task_id": "slow", "timeout_seconds": 30}],
                "budget": {"stall_notify_seconds": 1},
            },
            executor=execute,
            journal=journal,
        )
        result = await coordinator.run()
        assert result["status"] == "succeeded"
        stalled = [e for e in journal.events if e["event_type"] == "workflow.stalled"]
        assert len(stalled) == 1
        assert stalled[0]["payload"]["reason"] == "no_journal_event"
        assert result["stall"]["since_ms"] >= 1000

    asyncio.run(run())


def test_stall_watch_notifies_once_per_quiet_segment_and_rearms():
    """单元级：静默段通知一次；note_progress 重新上膛后可再次通知。"""

    async def run():
        notifications = []
        watch = WorkflowStallWatch(
            threshold_seconds=1.0,
            on_stalled=notifications.append,
        )
        watch.note_progress()
        # 回拨最后进展时间，模拟长时间静默
        watch._last_progress = time.monotonic() - 5.0
        watch.start()
        await asyncio.sleep(0.6)
        assert len(notifications) == 1
        # 同一静默段不重复通知
        await asyncio.sleep(0.4)
        assert len(notifications) == 1
        # 新事件重新上膛
        watch.note_progress()
        watch._last_progress = time.monotonic() - 5.0
        await asyncio.sleep(0.6)
        assert len(notifications) == 2
        await watch.stop()

    asyncio.run(run())
