"""
TaskCheckpointManager 单元测试

测试任务检查点管理器的核心功能：
1. 检查点保存
2. 检查点加载
3. 断点恢复
4. 未完成任务检测
"""

import pytest
import asyncio
import json
import shutil
from pathlib import Path
from datetime import datetime

from app.agent.task.checkpoint_manager import TaskCheckpointManager
from app.agent.task.task_list import TaskList
from app.agent.task.models import Task, TaskStatus


@pytest.fixture
def temp_checkpoint_dir(tmp_path):
    """创建临时检查点目录"""
    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir()
    yield str(checkpoint_dir)
    # 清理
    if checkpoint_dir.exists():
        shutil.rmtree(checkpoint_dir)


@pytest.fixture
def task_list():
    """创建任务列表实例"""
    return TaskList()


@pytest.fixture
def checkpoint_manager(task_list, temp_checkpoint_dir):
    """创建检查点管理器实例"""
    session_id = "test_session_001"
    return TaskCheckpointManager(
        session_id=session_id,
        task_list=task_list,
        base_dir=temp_checkpoint_dir
    )


@pytest.fixture
def sample_tasks(task_list):
    """创建示例任务"""
    session_id = "test_session_001"

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
            subject="生成可视化图表",
            description="生成时序图和风向玫瑰图",
            depends_on=["task_001", "task_002"],
            expert_type="viz"
        )
    ]

    # 模拟任务状态
    task_list.update_task("task_001", status=TaskStatus.COMPLETED, progress=100)
    task_list.update_task("task_002", status=TaskStatus.IN_PROGRESS, progress=60)

    return tasks


class TestCheckpointManager:
    """检查点管理器测试类"""

    @pytest.mark.asyncio
    async def test_save_checkpoint(self, checkpoint_manager, sample_tasks):
        """测试保存检查点"""
        # 保存检查点
        checkpoint_id = await checkpoint_manager.save_checkpoint(
            checkpoint_type="test",
            metadata={"test": "data"}
        )

        # 验证返回值
        assert checkpoint_id is not None
        assert checkpoint_id.startswith("ckpt_")

        # 验证文件存在
        assert checkpoint_manager.tasks_file.exists()

        # 验证文件内容
        with open(checkpoint_manager.tasks_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        assert data["checkpoint_id"] == checkpoint_id
        assert data["session_id"] == "test_session_001"
        assert data["type"] == "test"
        assert len(data["tasks"]) == 3
        assert len(data["completed_tasks"]) == 1
        assert len(data["in_progress_tasks"]) == 1
        assert len(data["pending_tasks"]) == 1

    @pytest.mark.asyncio
    async def test_load_checkpoint(self, checkpoint_manager, sample_tasks):
        """测试加载检查点"""
        # 先保存
        checkpoint_id = await checkpoint_manager.save_checkpoint("test")

        # 加载检查点
        checkpoint_data = await checkpoint_manager.load_checkpoint()

        # 验证数据
        assert checkpoint_data is not None
        assert checkpoint_data["checkpoint_id"] == checkpoint_id
        assert len(checkpoint_data["tasks"]) == 3
        assert checkpoint_data["completed_tasks"] == ["task_001"]
        assert checkpoint_data["in_progress_tasks"] == ["task_002"]
        assert checkpoint_data["pending_tasks"] == ["task_003"]

    @pytest.mark.asyncio
    async def test_load_specific_checkpoint(self, checkpoint_manager, sample_tasks):
        """测试加载指定检查点"""
        # 保存第一个检查点
        checkpoint_id_1 = await checkpoint_manager.save_checkpoint("checkpoint_1")

        # 修改任务状态
        checkpoint_manager.task_list.update_task(
            "task_002",
            status=TaskStatus.COMPLETED,
            progress=100
        )

        # 保存第二个检查点
        checkpoint_id_2 = await checkpoint_manager.save_checkpoint("checkpoint_2")

        # 加载第一个检查点
        checkpoint_data = await checkpoint_manager.load_checkpoint(checkpoint_id_1)

        # 验证是第一个检查点的数据
        assert checkpoint_data["checkpoint_id"] == checkpoint_id_1
        assert "task_002" in checkpoint_data["in_progress_tasks"]
        assert "task_002" not in checkpoint_data["completed_tasks"]

    @pytest.mark.asyncio
    async def test_restore_from_checkpoint(self, checkpoint_manager, sample_tasks):
        """测试从检查点恢复"""
        # 保存检查点
        checkpoint_id = await checkpoint_manager.save_checkpoint("test")

        # 清空内存任务列表
        checkpoint_manager.task_list.clear_session_tasks("test_session_001")
        assert len(checkpoint_manager.task_list.get_tasks("test_session_001")) == 0

        # 从检查点恢复
        success = await checkpoint_manager.restore_from_checkpoint()

        # 验证恢复成功
        assert success is True

        # 验证任务已恢复
        restored_tasks = checkpoint_manager.task_list.get_tasks("test_session_001")
        assert len(restored_tasks) == 3

        # 验证任务状态
        task_001 = checkpoint_manager.task_list.get_task("task_001")
        assert task_001.status == TaskStatus.COMPLETED
        assert task_001.progress == 100

        task_002 = checkpoint_manager.task_list.get_task("task_002")
        assert task_002.status == TaskStatus.IN_PROGRESS
        assert task_002.progress == 60

        task_003 = checkpoint_manager.task_list.get_task("task_003")
        assert task_003.status == TaskStatus.PENDING
        assert task_003.progress == 0

    @pytest.mark.asyncio
    async def test_has_unfinished_tasks(self, checkpoint_manager, sample_tasks):
        """测试检测未完成任务"""
        # 保存检查点（有未完成任务）
        await checkpoint_manager.save_checkpoint("test")

        # 检测未完成任务
        has_unfinished = await checkpoint_manager.has_unfinished_tasks()
        assert has_unfinished is True

        # 完成所有任务
        checkpoint_manager.task_list.update_task(
            "task_002",
            status=TaskStatus.COMPLETED,
            progress=100
        )
        checkpoint_manager.task_list.update_task(
            "task_003",
            status=TaskStatus.COMPLETED,
            progress=100
        )

        # 保存新检查点
        await checkpoint_manager.save_checkpoint("all_completed")

        # 再次检测
        has_unfinished = await checkpoint_manager.has_unfinished_tasks()
        assert has_unfinished is False

    @pytest.mark.asyncio
    async def test_get_unfinished_tasks(self, checkpoint_manager, sample_tasks):
        """测试获取未完成任务列表"""
        # 保存检查点
        await checkpoint_manager.save_checkpoint("test")

        # 获取未完成任务
        unfinished_tasks = await checkpoint_manager.get_unfinished_tasks()

        # 验证
        assert len(unfinished_tasks) == 2  # task_002 和 task_003

        task_ids = [t.id for t in unfinished_tasks]
        assert "task_002" in task_ids
        assert "task_003" in task_ids
        assert "task_001" not in task_ids  # 已完成

    @pytest.mark.asyncio
    async def test_clear_checkpoint(self, checkpoint_manager, sample_tasks):
        """测试清除检查点"""
        # 保存检查点
        await checkpoint_manager.save_checkpoint("test")

        # 验证文件存在
        assert checkpoint_manager.tasks_file.exists()

        # 清除检查点
        success = await checkpoint_manager.clear_checkpoint()
        assert success is True

        # 验证文件已删除
        assert not checkpoint_manager.tasks_file.exists()

        # 验证无法加载检查点
        checkpoint_data = await checkpoint_manager.load_checkpoint()
        assert checkpoint_data is None

    @pytest.mark.asyncio
    async def test_get_checkpoint_info(self, checkpoint_manager, sample_tasks):
        """测试获取检查点信息"""
        # 保存检查点
        checkpoint_id = await checkpoint_manager.save_checkpoint("test")

        # 获取检查点信息
        info = await checkpoint_manager.get_checkpoint_info()

        # 验证
        assert info is not None
        assert info["checkpoint_id"] == checkpoint_id
        assert info["type"] == "test"
        assert info["total_tasks"] == 3
        assert info["completed_tasks"] == 1
        assert info["in_progress_tasks"] == 1
        assert info["pending_tasks"] == 1
        assert info["failed_tasks"] == 0

    @pytest.mark.asyncio
    async def test_no_checkpoint_exists(self, checkpoint_manager):
        """测试不存在检查点的情况"""
        # 加载不存在的检查点
        checkpoint_data = await checkpoint_manager.load_checkpoint()
        assert checkpoint_data is None

        # 检测未完成任务
        has_unfinished = await checkpoint_manager.has_unfinished_tasks()
        assert has_unfinished is False

        # 获取未完成任务
        unfinished_tasks = await checkpoint_manager.get_unfinished_tasks()
        assert len(unfinished_tasks) == 0

        # 获取检查点信息
        info = await checkpoint_manager.get_checkpoint_info()
        assert info is None

    @pytest.mark.asyncio
    async def test_empty_task_list(self, checkpoint_manager):
        """测试空任务列表的情况"""
        # 保存空任务列表
        checkpoint_id = await checkpoint_manager.save_checkpoint("empty")

        # 应该返回 None（没有任务不保存）
        assert checkpoint_id is None

    @pytest.mark.asyncio
    async def test_task_serialization(self, checkpoint_manager, sample_tasks):
        """测试任务序列化和反序列化"""
        # 保存检查点
        await checkpoint_manager.save_checkpoint("test")

        # 清空并恢复
        checkpoint_manager.task_list.clear_session_tasks("test_session_001")
        await checkpoint_manager.restore_from_checkpoint()

        # 验证任务属性完整性
        task = checkpoint_manager.task_list.get_task("task_002")

        assert task.id == "task_002"
        assert task.subject == "分析VOCs组分"
        assert task.description == "分析VOCs组分特征"
        assert task.status == TaskStatus.IN_PROGRESS
        assert task.progress == 60
        assert task.depends_on == ["task_001"]
        assert task.expert_type == "component"
        assert task.created_at is not None
        assert task.updated_at is not None

    @pytest.mark.asyncio
    async def test_multiple_checkpoints_history(self, checkpoint_manager, sample_tasks):
        """测试多个检查点历史"""
        # 保存多个检查点
        checkpoint_ids = []
        for i in range(3):
            checkpoint_id = await checkpoint_manager.save_checkpoint(f"checkpoint_{i}")
            checkpoint_ids.append(checkpoint_id)
            await asyncio.sleep(0.1)  # 确保时间戳不同

        # 验证所有检查点文件都存在
        for checkpoint_id in checkpoint_ids:
            checkpoint_file = checkpoint_manager.checkpoints_dir / f"{checkpoint_id}.json"
            assert checkpoint_file.exists()

        # 验证可以加载任意检查点
        for checkpoint_id in checkpoint_ids:
            checkpoint_data = await checkpoint_manager.load_checkpoint(checkpoint_id)
            assert checkpoint_data is not None
            assert checkpoint_data["checkpoint_id"] == checkpoint_id


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
