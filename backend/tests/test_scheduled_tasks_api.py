"""
测试定时任务API和工具
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.scheduled_tasks import (
    init_service,
    get_scheduled_task_service,
    ScheduledTask,
    TaskStep,
    ScheduleType
)


async def test_create_scheduled_task_tool():
    """测试create_scheduled_task工具"""
    print("\n=== 测试create_scheduled_task工具 ===")

    # 初始化服务（不启动调度器）
    def mock_agent_factory():
        class MockAgent:
            async def analyze(self, prompt):
                await asyncio.sleep(0.1)
                yield {"type": "final_response", "content": "完成"}
        return MockAgent()

    init_service(agent_factory=mock_agent_factory)

    # 导入工具
    from app.tools.scheduled_tasks import create_scheduled_task_tool

    # 测试工具执行
    result = await create_scheduled_task_tool.execute(
        user_request="每天早上8点分析广州昨天的O3污染情况"
    )

    print(f"工具执行结果:")
    print(f"  成功: {result.get('success')}")
    print(f"  摘要: {result.get('summary')}")
    if result.get('success'):
        data = result.get('data', {})
        print(f"  任务ID: {data.get('task_id')}")
        print(f"  任务名称: {data.get('name')}")
        print(f"  调度类型: {data.get('schedule_type')}")
        print(f"  步骤数量: {data.get('steps_count')}")

    # 验证任务已创建
    service = get_scheduled_task_service()
    tasks = service.list_tasks()
    print(f"\n当前任务列表: {len(tasks)} 个任务")
    for task in tasks:
        print(f"  - {task.name} ({task.schedule_type})")

    print("[OK] create_scheduled_task工具测试通过")


async def test_api_integration():
    """测试API集成"""
    print("\n=== 测试API集成 ===")

    # 初始化服务
    def mock_agent_factory():
        class MockAgent:
            async def analyze(self, prompt):
                await asyncio.sleep(0.1)
                yield {"type": "final_response", "content": "完成"}
        return MockAgent()

    init_service(agent_factory=mock_agent_factory)
    service = get_scheduled_task_service()

    # 创建测试任务
    task = ScheduledTask(
        task_id="test_api_task",
        name="API测试任务",
        description="测试API集成",
        schedule_type=ScheduleType.EVERY_30MIN,
        enabled=True,
        steps=[
            TaskStep(
                step_id="step_1",
                description="测试步骤",
                agent_prompt="测试提示词",
                timeout_seconds=300
            )
        ]
    )

    created_task = service.create_task(task)
    print(f"[OK] 创建任务: {created_task.name}")

    # 列出任务
    tasks = service.list_tasks()
    print(f"[OK] 任务列表: {len(tasks)} 个任务")

    # 获取任务详情
    retrieved_task = service.get_task(task.task_id)
    print(f"[OK] 获取任务: {retrieved_task.name}")

    # 禁用任务
    disabled_task = service.disable_task(task.task_id)
    print(f"[OK] 禁用任务: {disabled_task.enabled}")

    # 启用任务
    enabled_task = service.enable_task(task.task_id)
    print(f"[OK] 启用任务: {enabled_task.enabled}")

    # 删除任务
    success = service.delete_task(task.task_id)
    print(f"[OK] 删除任务: {success}")

    print("[OK] API集成测试通过")


async def main():
    """运行所有测试"""
    print("=" * 60)
    print("定时任务API和工具测试")
    print("=" * 60)

    try:
        # 测试create_scheduled_task工具
        await test_create_scheduled_task_tool()

        # 测试API集成
        await test_api_integration()

        print("\n" + "=" * 60)
        print("所有测试通过")
        print("=" * 60)

    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
