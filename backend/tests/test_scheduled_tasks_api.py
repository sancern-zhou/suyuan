"""
测试定时任务API和工具（使用隔离存储，不触碰真实数据与真实LLM）
"""
import asyncio
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.scheduled_tasks import (
    ScheduledTask,
    ScheduleType,
    ScheduledTaskService,
)
from app.scheduled_tasks.storage import TaskStorage, ExecutionStorage, EventClaimStorage


def _make_service(temp_dir):
    def mock_agent_factory():
        class MockAgent:
            async def analyze(self, prompt, **kwargs):
                await asyncio.sleep(0.1)
                yield {"type": "final_response", "content": "完成"}
        return MockAgent()

    return ScheduledTaskService(
        agent_factory=mock_agent_factory,
        task_storage=TaskStorage(storage_dir=temp_dir),
        execution_storage=ExecutionStorage(storage_dir=temp_dir),
        claim_storage=EventClaimStorage(storage_dir=temp_dir),
    )


async def test_create_scheduled_task_tool():
    """测试create_scheduled_task工具：只生成任务级 prompt，不生成 steps"""
    temp_dir = tempfile.mkdtemp()
    try:
        service = _make_service(temp_dir)

        from app.tools.scheduled_tasks import create_scheduled_task_tool

        parsed_config = {
            "name": "每日O3污染分析",
            "description": "每天早上8点分析广州昨天的O3污染情况",
            "execution_mode": "expert",
            "schedule_type": "daily_8am",
            "prompt": "查询广州昨天的O3浓度数据并生成分析报告",
            "timeout_seconds": 1800,
            "tags": ["O3"],
        }

        with patch(
            "app.tools.scheduled_tasks.create_scheduled_task.get_scheduled_task_service",
            lambda: service,
        ), patch.object(
            create_scheduled_task_tool, "_parse_user_request", return_value=parsed_config,
        ):
            result = await create_scheduled_task_tool.execute(
                user_request="每天早上8点分析广州昨天的O3污染情况"
            )

        assert result["success"] is True, result
        created = service.get_task(result["data"]["task_id"])
        assert created.prompt == parsed_config["prompt"]
        assert created.timeout_seconds == 1800
        assert not hasattr(created, "steps")
        print("[OK] create_scheduled_task工具测试通过")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


async def test_api_integration():
    """测试API集成"""
    temp_dir = tempfile.mkdtemp()
    try:
        service = _make_service(temp_dir)

        # 创建测试任务
        task = ScheduledTask(
            task_id="test_api_task",
            name="API测试任务",
            description="测试API集成",
            schedule_type=ScheduleType.EVERY_30MIN,
            enabled=True,
            prompt="测试提示词",
            timeout_seconds=300,
        )

        created_task = service.create_task(task)
        assert created_task.name == "API测试任务"

        assert service.get_task(task.task_id).task_id == task.task_id
        assert service.disable_task(task.task_id).enabled is False
        assert service.enable_task(task.task_id).enabled is True
        assert service.delete_task(task.task_id) is True
        print("[OK] API集成测试通过")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


async def main():
    """运行所有测试"""
    print("=" * 60)
    print("定时任务API和工具测试")
    print("=" * 60)

    try:
        await test_create_scheduled_task_tool()
        await test_api_integration()
        print("\n所有测试通过")
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
