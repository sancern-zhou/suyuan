"""
TaskCheckpointManager 集成测试

测试完整的任务执行和断点恢复流程
"""

import pytest
import asyncio
import shutil
from pathlib import Path

from app.agent.task.checkpoint_manager import TaskCheckpointManager
from app.agent.task.task_list import TaskList
from app.agent.task.models import TaskStatus


@pytest.fixture
def temp_checkpoint_dir(tmp_path):
    """创建临时检查点目录"""
    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir()
    yield str(checkpoint_dir)
    if checkpoint_dir.exists():
        shutil.rmtree(checkpoint_dir)


@pytest.mark.asyncio
async def test_complete_workflow(temp_checkpoint_dir):
    """
    测试完整的任务执行和断点恢复流程

    模拟场景：
    1. 创建任务清单
    2. 执行部分任务
    3. 保存检查点
    4. 模拟中断（清空内存）
    5. 恢复检查点
    6. 继续执行剩余任务
    """

    session_id = "integration_test_session"

    # ========================================
    # 阶段 1: 创建任务清单
    # ========================================
    print("\n=== 阶段 1: 创建任务清单 ===")

    task_list = TaskList()
    checkpoint_manager = TaskCheckpointManager(
        session_id=session_id,
        task_list=task_list,
        base_dir=temp_checkpoint_dir
    )

    # 创建5个任务（模拟复杂分析流程）
    tasks = [
        task_list.create_task(
            session_id=session_id,
            task_id="task_001",
            subject="获取气象数据",
            description="获取广州2024年气象数据",
            depends_on=[],
            expert_type="weather"
        ),
        task_list.create_task(
            session_id=session_id,
            task_id="task_002",
            subject="分析VOCs组分",
            description="分析VOCs组分特征",
            depends_on=["task_001"],
            expert_type="component"
        ),
        task_list.create_task(
            session_id=session_id,
            task_id="task_003",
            subject="计算PMF源解析",
            description="计算PMF源解析结果",
            depends_on=["task_002"],
            expert_type="component"
        ),
        task_list.create_task(
            session_id=session_id,
            task_id="task_004",
            subject="生成可视化图表",
            description="生成时序图和风向玫瑰图",
            depends_on=["task_001", "task_003"],
            expert_type="viz"
        ),
        task_list.create_task(
            session_id=session_id,
            task_id="task_005",
            subject="生成综合报告",
            description="生成完整的污染溯源报告",
            depends_on=["task_004"],
            expert_type="report"
        )
    ]

    print(f"[OK] 创建了 {len(tasks)} 个任务")

    # 保存初始检查点
    checkpoint_id = await checkpoint_manager.save_checkpoint("plan_created")
    print(f"[OK] 保存初始检查点: {checkpoint_id}")

    # ========================================
    # 阶段 2: 执行部分任务
    # ========================================
    print("\n=== 阶段 2: 执行部分任务 ===")

    # 执行 task_001
    task_list.update_task("task_001", status=TaskStatus.IN_PROGRESS)
    await checkpoint_manager.save_checkpoint("before_task")
    print("[->] 开始执行 task_001: 获取气象数据")

    await asyncio.sleep(0.1)  # 模拟执行时间

    task_list.update_task(
        "task_001",
        status=TaskStatus.COMPLETED,
        progress=100,
        result_data_id="weather_data:abc123"
    )
    await checkpoint_manager.save_checkpoint("after_task")
    print("[OK] task_001 完成")

    # 执行 task_002
    task_list.update_task("task_002", status=TaskStatus.IN_PROGRESS)
    await checkpoint_manager.save_checkpoint("before_task")
    print("[->] 开始执行 task_002: 分析VOCs组分")

    await asyncio.sleep(0.1)

    task_list.update_task(
        "task_002",
        status=TaskStatus.COMPLETED,
        progress=100,
        result_data_id="vocs_analysis:def456"
    )
    await checkpoint_manager.save_checkpoint("after_task")
    print("[OK] task_002 完成")

    # 开始执行 task_003，但执行到一半
    task_list.update_task("task_003", status=TaskStatus.IN_PROGRESS, progress=50)
    await checkpoint_manager.save_checkpoint("before_task")
    print("[->] 开始执行 task_003: 计算PMF源解析 (50%)")

    # ========================================
    # 阶段 3: 模拟中断
    # ========================================
    print("\n=== 阶段 3: 模拟中断（清空内存） ===")

    # 获取检查点信息
    info = await checkpoint_manager.get_checkpoint_info()
    print(f"检查点信息:")
    print(f"  - 总任务数: {info['total_tasks']}")
    print(f"  - 已完成: {info['completed_tasks']}")
    print(f"  - 进行中: {info['in_progress_tasks']}")
    print(f"  - 待执行: {info['pending_tasks']}")

    # 清空内存（模拟程序重启）
    task_list.clear_session_tasks(session_id)
    print("[OK] 内存已清空（模拟程序重启）")

    assert len(task_list.get_tasks(session_id)) == 0

    # ========================================
    # 阶段 4: 恢复检查点
    # ========================================
    print("\n=== 阶段 4: 恢复检查点 ===")

    # 检测是否有未完成的任务
    has_unfinished = await checkpoint_manager.has_unfinished_tasks()
    print(f"检测到未完成的任务: {has_unfinished}")
    assert has_unfinished is True

    # 恢复检查点
    success = await checkpoint_manager.restore_from_checkpoint()
    print(f"恢复检查点: {'成功' if success else '失败'}")
    assert success is True

    # 验证任务已恢复
    restored_tasks = task_list.get_tasks(session_id)
    print(f"[OK] 恢复了 {len(restored_tasks)} 个任务")
    assert len(restored_tasks) == 5

    # 验证任务状态
    task_001 = task_list.get_task("task_001")
    assert task_001.status == TaskStatus.COMPLETED
    print(f"  - task_001: {task_001.status.value} [OK]")

    task_002 = task_list.get_task("task_002")
    assert task_002.status == TaskStatus.COMPLETED
    print(f"  - task_002: {task_002.status.value} [OK]")

    task_003 = task_list.get_task("task_003")
    assert task_003.status == TaskStatus.IN_PROGRESS
    assert task_003.progress == 50
    print(f"  - task_003: {task_003.status.value} (50%) [OK]")

    task_004 = task_list.get_task("task_004")
    assert task_004.status == TaskStatus.PENDING
    print(f"  - task_004: {task_004.status.value} [OK]")

    task_005 = task_list.get_task("task_005")
    assert task_005.status == TaskStatus.PENDING
    print(f"  - task_005: {task_005.status.value} [OK]")

    # ========================================
    # 阶段 5: 继续执行剩余任务
    # ========================================
    print("\n=== 阶段 5: 继续执行剩余任务 ===")

    # 完成 task_003
    print("[->] 继续执行 task_003: 计算PMF源解析 (50% -> 100%)")
    task_list.update_task(
        "task_003",
        status=TaskStatus.COMPLETED,
        progress=100,
        result_data_id="pmf_result:ghi789"
    )
    await checkpoint_manager.save_checkpoint("after_task")
    print("[OK] task_003 完成")

    # 执行 task_004
    task_list.update_task("task_004", status=TaskStatus.IN_PROGRESS)
    await checkpoint_manager.save_checkpoint("before_task")
    print("[->] 开始执行 task_004: 生成可视化图表")

    await asyncio.sleep(0.1)

    task_list.update_task(
        "task_004",
        status=TaskStatus.COMPLETED,
        progress=100,
        result_data_id="viz_charts:jkl012"
    )
    await checkpoint_manager.save_checkpoint("after_task")
    print("[OK] task_004 完成")

    # 执行 task_005
    task_list.update_task("task_005", status=TaskStatus.IN_PROGRESS)
    await checkpoint_manager.save_checkpoint("before_task")
    print("[->] 开始执行 task_005: 生成综合报告")

    await asyncio.sleep(0.1)

    task_list.update_task(
        "task_005",
        status=TaskStatus.COMPLETED,
        progress=100,
        result_data_id="report:mno345"
    )
    await checkpoint_manager.save_checkpoint("after_task")
    print("[OK] task_005 完成")

    # ========================================
    # 阶段 6: 验证所有任务完成
    # ========================================
    print("\n=== 阶段 6: 验证所有任务完成 ===")

    # 检查是否还有未完成的任务
    has_unfinished = await checkpoint_manager.has_unfinished_tasks()
    print(f"是否有未完成的任务: {has_unfinished}")
    assert has_unfinished is False

    # 获取最终检查点信息
    final_info = await checkpoint_manager.get_checkpoint_info()
    print(f"\n最终统计:")
    print(f"  - 总任务数: {final_info['total_tasks']}")
    print(f"  - 已完成: {final_info['completed_tasks']}")
    print(f"  - 进行中: {final_info['in_progress_tasks']}")
    print(f"  - 待执行: {final_info['pending_tasks']}")
    print(f"  - 失败: {final_info['failed_tasks']}")

    assert final_info['completed_tasks'] == 5
    assert final_info['in_progress_tasks'] == 0
    assert final_info['pending_tasks'] == 0
    assert final_info['failed_tasks'] == 0

    print("\n[SUCCESS] 完整流程测试通过！")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
