"""
定时任务系统测试脚本
测试核心功能：数据模型、存储层、调度器、执行器
"""
import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.scheduled_tasks.models import ScheduledTask, ScheduleType
from app.scheduled_tasks.storage import TaskStorage, ExecutionStorage, EventClaimStorage
from app.scheduled_tasks.scheduler import SimpleScheduler
from app.scheduled_tasks.executor import ScheduledTaskExecutor
from app.scheduled_tasks.service import ScheduledTaskService


def test_models():
    """测试数据模型"""
    print("\n=== 测试数据模型 ===")

    # 创建任务：一次完整的 Agent 执行
    task = ScheduledTask(
        task_id="task_test_001",
        name="每日O3污染分析",
        description="每天早上8点分析广州昨天的O3污染情况",
        schedule_type=ScheduleType.DAILY_8AM,
        enabled=True,
        prompt="查询广州昨天的O3浓度数据并生成O3污染分析报告",
        timeout_seconds=1800,
        tags=["O3", "广州", "日报"]
    )

    print(f"任务ID: {task.task_id}")
    print(f"任务名称: {task.name}")
    print(f"调度类型: {task.schedule_type}")
    print(f"任务超时: {task.timeout_seconds}s")
    print("[OK] 数据模型测试通过")


def test_storage():
    """测试存储层"""
    print("\n=== 测试存储层 ===")

    # 创建存储实例
    task_storage = TaskStorage(storage_dir="backend_data_registry/scheduled_tasks_test")
    execution_storage = ExecutionStorage(storage_dir="backend_data_registry/scheduled_tasks_test")

    # 创建测试任务
    task = ScheduledTask(
        task_id="task_storage_test",
        name="存储测试任务",
        description="测试任务存储功能",
        schedule_type=ScheduleType.EVERY_30MIN,
        enabled=True,
        prompt="测试提示词",
        timeout_seconds=300,
    )

    # 测试创建
    created_task = task_storage.create(task)
    print(f"[OK] 创建任务: {created_task.task_id}")

    # 测试读取
    retrieved_task = task_storage.get(task.task_id)
    assert retrieved_task is not None
    assert retrieved_task.task_id == task.task_id
    print(f"[OK] 读取任务: {retrieved_task.name}")

    # 测试列表
    tasks = task_storage.list()
    print(f"[OK] 任务列表: {len(tasks)} 个任务")

    # 测试更新
    task.description = "更新后的描述"
    updated_task = task_storage.update(task)
    assert updated_task.description == "更新后的描述"
    print(f"[OK] 更新任务: {updated_task.description}")

    # 测试删除
    success = task_storage.delete(task.task_id)
    assert success
    print(f"[OK] 删除任务: {task.task_id}")

    print("[OK] 存储层测试通过")


def test_scheduler():
    """测试调度器"""
    print("\n=== 测试调度器 ===")

    # 创建存储和调度器
    task_storage = TaskStorage(storage_dir="backend_data_registry/scheduled_tasks_test")
    scheduler = SimpleScheduler(task_storage=task_storage)

    # 创建测试任务
    task = ScheduledTask(
        task_id="task_scheduler_test",
        name="调度器测试任务",
        description="测试调度器功能",
        schedule_type=ScheduleType.EVERY_2H,
        enabled=True,
        prompt="测试提示词",
        timeout_seconds=300,
    )

    task_storage.create(task)

    # 测试调度
    print(f"[OK] Cron模板: {scheduler.CRON_TEMPLATES}")
    print(f"[OK] 最大并发: {scheduler.MAX_CONCURRENT_TASKS}")

    # 清理
    task_storage.delete(task.task_id)
    print("[OK] 调度器测试通过")


async def test_executor():
    """测试执行器"""
    print("\n=== 测试执行器 ===")

    # 创建存储
    task_storage = TaskStorage(storage_dir="backend_data_registry/scheduled_tasks_test")
    execution_storage = ExecutionStorage(storage_dir="backend_data_registry/scheduled_tasks_test")

    # 模拟Agent工厂
    def mock_agent_factory():
        class MockAgent:
            async def analyze(self, prompt, **kwargs):
                print(f"  模拟Agent执行: {prompt[:50]}...")
                await asyncio.sleep(0.5)
                yield {"type": "data_saved", "data_id": "test_data_001"}
                yield {"type": "visual_generated", "visual": {"id": "viz_001", "type": "chart"}}
                yield {"type": "final_response", "content": "分析完成"}
        return MockAgent()

    # 创建执行器
    executor = ScheduledTaskExecutor(
        task_storage=task_storage,
        execution_storage=execution_storage,
        agent_factory=mock_agent_factory
    )

    # 创建测试任务
    task = ScheduledTask(
        task_id="task_executor_test",
        name="执行器测试任务",
        description="测试执行器功能",
        schedule_type=ScheduleType.DAILY_8AM,
        enabled=True,
        prompt="执行测试任务",
        timeout_seconds=10,
    )

    task_storage.create(task)

    # 执行任务
    print(f"开始执行任务: {task.name}")
    execution = await executor.execute_task(task)

    print(f"[OK] 执行ID: {execution.execution_id}")
    print(f"[OK] 执行状态: {execution.status}")
    print(f"[OK] 总步骤: {execution.total_steps}")
    print(f"[OK] 完成步骤: {execution.completed_steps}")
    print(f"[OK] 执行时长: {execution.duration_seconds:.2f}s")

    # 清理
    task_storage.delete(task.task_id)
    print("[OK] 执行器测试通过")


def test_service():
    """测试服务类"""
    print("\n=== 测试服务类 ===")

    # 模拟Agent工厂
    def mock_agent_factory():
        class MockAgent:
            async def analyze(self, prompt, **kwargs):
                await asyncio.sleep(0.1)
                yield {"type": "final_response", "content": "完成"}
        return MockAgent()

    # 创建服务（使用独立的测试存储目录，避免触碰真实任务数据）
    test_storage_dir = "backend_data_registry/scheduled_tasks_test"
    service = ScheduledTaskService(
        agent_factory=mock_agent_factory,
        task_storage=TaskStorage(storage_dir=test_storage_dir),
        execution_storage=ExecutionStorage(storage_dir=test_storage_dir),
        claim_storage=EventClaimStorage(storage_dir=test_storage_dir),
    )

    # 创建任务
    task = ScheduledTask(
        task_id="task_service_test",
        name="服务测试任务",
        description="测试服务功能",
        schedule_type=ScheduleType.EVERY_30MIN,
        enabled=True,
        prompt="测试提示词",
        timeout_seconds=300,
    )

    created_task = service.create_task(task)
    print(f"[OK] 创建任务: {created_task.name}")

    # 列出任务
    tasks = service.list_tasks()
    print(f"[OK] 任务列表: {len(tasks)} 个任务")

    # 获取调度器状态
    status = service.get_scheduler_status()
    print(f"[OK] 调度器状态: {status}")

    # 删除任务
    service.delete_task(task.task_id)
    print(f"[OK] 删除任务: {task.task_id}")

    print("[OK] 服务类测试通过")


def main():
    """运行所有测试"""
    print("=" * 60)
    print("定时任务系统测试")
    print("=" * 60)

    try:
        # 测试数据模型
        test_models()

        # 测试存储层
        test_storage()

        # 测试调度器
        test_scheduler()

        # 测试执行器
        asyncio.run(test_executor())

        # 测试服务类
        test_service()

        print("\n" + "=" * 60)
        print("所有测试通过")
        print("=" * 60)

    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
