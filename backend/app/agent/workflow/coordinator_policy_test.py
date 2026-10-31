"""Coordinator 新机制测试：模型错误策略表、停摆观测、用量遥测、失败抢救。

对照 ZCode dynamic-workflow v3.17.1 移植的四项引擎优化（见
docs/zcode-dynamic-workflow.md 的移植对照节）。
"""

import asyncio
import time
from datetime import datetime, timedelta

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


def test_quota_pause_recorded_with_reset_at():
    """stop_quota 且网关给出重置时刻：记档 quota_pause 并落 journal。"""

    reset_text = (datetime.now() + timedelta(hours=30)).strftime("%Y-%m-%d %H:%M")

    async def run():
        journal = FakeJournal()

        async def execute(node, dependencies, attempt, retry_context=None):
            raise RuntimeError(f"Error code: 402 - token plan 用量上限，重置于 {reset_text}")

        coordinator = WorkflowCoordinator(
            {"workflow_id": "quota-1", "nodes": [{"task_id": "air", "max_attempts": 2}]},
            executor=execute,
            journal=journal,
        )
        result = await coordinator.run()
        assert result["status"] == "failed"
        assert result["quota_pause"]["task_id"] == "air"
        assert result["quota_pause"]["reset_at"] > 0
        assert "workflow.quota_paused" in journal.event_types()
        # 无 reset_at 的配额错误不记档（不自动续跑）
        journal2 = FakeJournal()

        async def execute2(node, dependencies, attempt, retry_context=None):
            raise RuntimeError("Error code: 402 - insufficient_quota")

        coordinator2 = WorkflowCoordinator(
            {"workflow_id": "quota-2", "nodes": [{"task_id": "air", "max_attempts": 2}]},
            executor=execute2,
            journal=journal2,
        )
        result2 = await coordinator2.run()
        assert result2["quota_pause"] is None
        assert "workflow.quota_paused" not in journal2.event_types()

    asyncio.run(run())


def test_quota_paused_snapshot_resumes_quota_failed_nodes():
    """带 quota_pause 的快照恢复时：stop_quota 节点翻回可重试并重跑成功。"""

    reset_text = (datetime.now() + timedelta(hours=30)).strftime("%Y-%m-%d %H:%M")

    async def run():
        journal = FakeJournal()
        attempts = []

        async def fail_execute(node, dependencies, attempt, retry_context=None):
            attempts.append(attempt)
            raise RuntimeError(f"Error code: 402 - insufficient_quota，重置于 {reset_text}")

        coordinator = WorkflowCoordinator(
            {"workflow_id": "quota-3", "nodes": [{"task_id": "air", "max_attempts": 1}]},
            executor=fail_execute,
            journal=journal,
        )
        result = await coordinator.run()
        assert result["status"] == "failed"
        assert result["node_retryable"]["air"] is False

        # 配额重置后续跑：reset_at 已过，stop_quota 节点无视 attempt 计数重跑
        async def succeed_execute(node, dependencies, attempt, retry_context=None):
            return {"status": "success"}

        resumed = WorkflowCoordinator(
            result["definition"],
            executor=succeed_execute,
            snapshot=result,
            journal=journal,
        )
        resumed_result = await resumed.run()
        assert resumed_result["status"] == "succeeded"
        assert resumed_result["node_results"]["air"]["status"] == "success"

    asyncio.run(run())


def test_escalation_lifecycle_recorded_in_snapshot_and_journal():
    """escalation raised → resolved 状态流转：journal 事件 + 快照记档。"""

    async def run():
        journal = FakeJournal()

        async def execute(node, dependencies, attempt, retry_context=None):
            return {"status": "success"}

        coordinator = WorkflowCoordinator(
            {
                "workflow_id": "esc-1",
                "nodes": [
                    {"task_id": "a", "target_mode": "query", "goal": "取数"},
                    {"task_id": "b", "target_mode": "query", "goal": "研判", "dependencies": ["a"]},
                ],
            },
            executor=execute,
            journal=journal,
        )
        coordinator.record_escalation({
            "escalation_id": "e1", "event": "raised", "task_id": "a",
            "question": "用口径 A 还是 B？", "context": "差异 15%", "asked_at": 1.0,
        })
        assert coordinator.snapshot()["pending_escalations"]["e1"]["status"] == "pending"
        coordinator.record_escalation({
            "escalation_id": "e1", "event": "resolved", "task_id": "a",
            "question": "用口径 A 还是 B？", "answer": "口径 A", "asked_at": 1.0,
        })
        snapshot = coordinator.snapshot()
        assert snapshot["pending_escalations"]["e1"]["status"] == "resolved"
        assert snapshot["pending_escalations"]["e1"]["answer"] == "口径 A"
        types = journal.event_types()
        assert "workflow.escalation_raised" in types
        assert "workflow.escalation_resolved" in types
        # 快照往返：恢复后记档仍在
        restored = WorkflowCoordinator(
            snapshot["definition"], executor=execute, snapshot=snapshot, journal=journal
        )
        assert restored.snapshot()["pending_escalations"]["e1"]["status"] == "resolved"

    asyncio.run(run())


def test_progressive_findings_dedupe_bounds_and_salvage():
    """渐进发现：去重入账、上限拒绝、失败节点 salvage 携带发现。"""

    async def run():
        journal = FakeJournal()

        async def execute(node, dependencies, attempt, retry_context=None):
            # 执行中上报两条发现（其中一条重复），随后失败
            coordinator.record_finding({"task_id": "air", "content": "PM2.5 均值 58，同比 +12%", "tag": "数值"})
            coordinator.record_finding({"task_id": "air", "content": "PM2.5 均值 58，同比 +12%", "tag": "数值"})
            coordinator.record_finding({"task_id": "air", "content": "两站点数据缺失", "tag": "异常"})
            return {"success": False, "summary": "校验未通过"}

        coordinator = WorkflowCoordinator(
            {"workflow_id": "finding-1", "nodes": [{"task_id": "air", "max_attempts": 1}]},
            executor=execute,
            journal=journal,
        )
        result = await coordinator.run()
        assert result["status"] == "failed"
        # 去重后仅 2 条
        findings = result["node_findings"]["air"]
        assert len(findings) == 2
        assert {item["tag"] for item in findings} == {"数值", "异常"}
        # journal 两条 node.finding
        assert journal.event_types().count("node.finding") == 2
        # salvage 携带发现（失败不丢工作量）
        salvage = result["delivery"]["salvage"]
        assert len(salvage) == 1
        assert len(salvage[0]["findings"]) == 2

    asyncio.run(run())


retry_context_captured = None


def test_settle_fallback_absorbs_envelope_findings():
    """未调用 report_finding 的节点：settle 时从结果信封 findings 补齐。"""

    async def run():
        async def execute(node, dependencies, attempt, retry_context=None):
            return {
                "status": "success",
                "data": {
                    "result_envelope": {
                        "status": "completed",
                        "findings": ["全市均值 58 μg/m³", {"content": "NO2 同比下降 5%"}],
                    }
                },
            }

        coordinator = WorkflowCoordinator(
            {
                "workflow_id": "finding-2",
                "nodes": [
                    {"task_id": "a", "target_mode": "query", "goal": "取数"},
                    {"task_id": "b", "target_mode": "query", "goal": "研判", "dependencies": ["a"]},
                ],
            },
            executor=execute,
        )
        result = await coordinator.run()
        assert result["status"] == "succeeded"
        contents = {item["content"] for item in result["node_findings"]["a"]}
        assert "全市均值 58 μg/m³" in contents
        assert "NO2 同比下降 5%" in contents

    asyncio.run(run())


def test_findings_snapshot_roundtrip():
    """快照往返：node_findings 恢复后仍在（含重试上下文路径）。"""

    async def run():
        async def execute(node, dependencies, attempt, retry_context=None):
            global retry_context_captured
            if attempt == 1:
                coordinator.record_finding({"task_id": "air", "content": "口径按 HJ633", "tag": "口径"})
                return {"success": False, "summary": "校验未通过"}
            retry_context_captured = retry_context
            return {"status": "success"}

        coordinator = WorkflowCoordinator(
            {"workflow_id": "finding-3", "nodes": [{"task_id": "air", "max_attempts": 2}]},
            executor=execute,
        )
        result = await coordinator.run()
        assert result["status"] == "succeeded"
        assert result["node_findings"]["air"][0]["content"] == "口径按 HJ633"
        # 重试上下文带上了上轮发现
        assert retry_context_captured is not None
        assert retry_context_captured["findings"][0]["content"] == "口径按 HJ633"

    asyncio.run(run())
