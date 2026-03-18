"""
任务列表系统单元测试
"""

import pytest
from datetime import datetime
from pathlib import Path
import tempfile
import shutil

from app.agent.task import TaskList, Task, TaskStatus


@pytest.fixture
def temp_storage():
    """创建临时存储目录"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def task_list(temp_storage):
    """创建TaskList实例"""
    return TaskList(storage_base_path=temp_storage)


class TestTaskCreation:
    """测试任务创建"""

    def test_create_simple_task(self, task_list):
        """测试创建简单任务"""
        task = task_list.create_task(
            session_id="session_001",
            task_id="task_001",
            subject="测试任务",
            description="这是一个测试任务"
        )

        assert task.id == "task_001"
        assert task.session_id == "session_001"
        assert task.subject == "测试任务"
        assert task.status == TaskStatus.PENDING
        assert task.progress == 0

    def test_create_task_with_dependencies(self, task_list):
        """测试创建带依赖的任务"""
        # 创建任务1
        task1 = task_list.create_task(
            session_id="session_001",
            task_id="task_001",
            subject="任务1",
            description="第一个任务"
        )

        # 创建任务2，依赖任务1
        task2 = task_list.create_task(
            session_id="session_001",
            task_id="task_002",
            subject="任务2",
            description="第二个任务",
            depends_on=["task_001"]
        )

        assert task2.depends_on == ["task_001"]
        assert len(task_list.get_tasks("session_001")) == 2

    def test_create_task_with_metadata(self, task_list):
        """测试创建带元数据的任务"""
        task = task_list.create_task(
            session_id="session_001",
            task_id="task_001",
            subject="气象分析",
            description="分析气象数据",
            expert_type="weather",
            metadata={
                "location": "广州",
                "group_index": 0
            }
        )

        assert task.expert_type == "weather"
        assert task.metadata["location"] == "广州"
        assert task.metadata["group_index"] == 0


class TestTaskUpdate:
    """测试任务更新"""

    def test_update_task_status(self, task_list):
        """测试更新任务状态"""
        # 创建任务
        task = task_list.create_task(
            session_id="session_001",
            task_id="task_001",
            subject="测试任务",
            description="测试描述"
        )

        # 更新为进行中
        updated_task = task_list.update_task(
            "task_001",
            status=TaskStatus.IN_PROGRESS,
            progress=50
        )

        assert updated_task.status == TaskStatus.IN_PROGRESS
        assert updated_task.progress == 50
        assert updated_task.started_at is not None

    def test_update_task_to_completed(self, task_list):
        """测试标记任务完成"""
        task = task_list.create_task(
            session_id="session_001",
            task_id="task_001",
            subject="测试任务",
            description="测试描述"
        )

        # 标记完成
        updated_task = task_list.update_task(
            "task_001",
            status=TaskStatus.COMPLETED,
            result_data_id="result_001"
        )

        assert updated_task.status == TaskStatus.COMPLETED
        assert updated_task.progress == 100
        assert updated_task.result_data_id == "result_001"
        assert updated_task.completed_at is not None

    def test_update_task_to_failed(self, task_list):
        """测试标记任务失败"""
        task = task_list.create_task(
            session_id="session_001",
            task_id="task_001",
            subject="测试任务",
            description="测试描述"
        )

        # 标记失败
        updated_task = task_list.update_task(
            "task_001",
            status=TaskStatus.FAILED,
            error_message="执行失败"
        )

        assert updated_task.status == TaskStatus.FAILED
        assert updated_task.error_message == "执行失败"

    def test_update_nonexistent_task(self, task_list):
        """测试更新不存在的任务"""
        with pytest.raises(ValueError, match="Task not found"):
            task_list.update_task("nonexistent_task", status=TaskStatus.IN_PROGRESS)


class TestTaskQuery:
    """测试任务查询"""

    def test_get_task(self, task_list):
        """测试获取单个任务"""
        task = task_list.create_task(
            session_id="session_001",
            task_id="task_001",
            subject="测试任务",
            description="测试描述"
        )

        retrieved_task = task_list.get_task("task_001")
        assert retrieved_task is not None
        assert retrieved_task.id == "task_001"

    def test_get_tasks_by_session(self, task_list):
        """测试获取会话的所有任务"""
        # 创建多个任务
        for i in range(3):
            task_list.create_task(
                session_id="session_001",
                task_id=f"task_00{i+1}",
                subject=f"任务{i+1}",
                description=f"描述{i+1}"
            )

        tasks = task_list.get_tasks("session_001")
        assert len(tasks) == 3
        assert all(t.session_id == "session_001" for t in tasks)

    def test_get_tasks_by_status(self, task_list):
        """测试按状态获取任务"""
        # 创建不同状态的任务
        task1 = task_list.create_task(
            session_id="session_001",
            task_id="task_001",
            subject="任务1",
            description="描述1"
        )

        task2 = task_list.create_task(
            session_id="session_001",
            task_id="task_002",
            subject="任务2",
            description="描述2"
        )

        # 更新一个任务为进行中
        task_list.update_task("task_001", status=TaskStatus.IN_PROGRESS)

        # 查询pending任务
        pending_tasks = task_list.get_tasks_by_status("session_001", TaskStatus.PENDING)
        assert len(pending_tasks) == 1
        assert pending_tasks[0].id == "task_002"

        # 查询进行中任务
        in_progress_tasks = task_list.get_tasks_by_status("session_001", TaskStatus.IN_PROGRESS)
        assert len(in_progress_tasks) == 1
        assert in_progress_tasks[0].id == "task_001"

    def test_get_ready_tasks(self, task_list):
        """测试获取可执行任务"""
        # 创建任务链
        task1 = task_list.create_task(
            session_id="session_001",
            task_id="task_001",
            subject="任务1",
            description="无依赖"
        )

        task2 = task_list.create_task(
            session_id="session_001",
            task_id="task_002",
            subject="任务2",
            description="依赖任务1",
            depends_on=["task_001"]
        )

        # 初始状态：只有task1可执行
        ready_tasks = task_list.get_ready_tasks("session_001")
        assert len(ready_tasks) == 1
        assert ready_tasks[0].id == "task_001"

        # task1完成后，task2可执行
        task_list.update_task("task_001", status=TaskStatus.COMPLETED)
        ready_tasks = task_list.get_ready_tasks("session_001")
        assert len(ready_tasks) == 1
        assert ready_tasks[0].id == "task_002"


class TestTaskPersistence:
    """测试任务持久化"""

    def test_save_to_disk(self, task_list):
        """测试保存到磁盘"""
        # 创建任务
        task_list.create_task(
            session_id="session_001",
            task_id="task_001",
            subject="测试任务",
            description="测试描述"
        )

        # 验证文件存在
        session_file = Path(task_list.storage_path) / "session_001_tasks.json"
        assert session_file.exists()

    def test_load_from_disk(self, temp_storage):
        """测试从磁盘加载"""
        # 创建第一个TaskList实例并保存任务
        task_list1 = TaskList(storage_base_path=temp_storage)
        task_list1.create_task(
            session_id="session_001",
            task_id="task_001",
            subject="测试任务",
            description="测试描述"
        )

        # 创建第二个TaskList实例并加载
        task_list2 = TaskList(storage_base_path=temp_storage)
        loaded = task_list2.load_from_disk("session_001")

        assert loaded is True
        tasks = task_list2.get_tasks("session_001")
        assert len(tasks) == 1
        assert tasks[0].id == "task_001"

    def test_load_nonexistent_session(self, task_list):
        """测试加载不存在的会话"""
        loaded = task_list.load_from_disk("nonexistent_session")
        assert loaded is False


class TestTaskTree:
    """测试任务树"""

    def test_build_simple_tree(self, task_list):
        """测试构建简单任务树"""
        # 创建线性依赖链
        task1 = task_list.create_task(
            session_id="session_001",
            task_id="task_001",
            subject="任务1",
            description="根任务"
        )

        task2 = task_list.create_task(
            session_id="session_001",
            task_id="task_002",
            subject="任务2",
            description="依赖任务1",
            depends_on=["task_001"]
        )

        # 构建任务树
        tree = task_list.build_task_tree("session_001")
        assert tree is not None
        assert tree.task.id == "task_001"
        assert len(tree.children) == 1
        assert tree.children[0].task.id == "task_002"

    def test_build_parallel_tree(self, task_list):
        """测试构建并行任务树"""
        # 创建并行任务
        task1 = task_list.create_task(
            session_id="session_001",
            task_id="task_001",
            subject="任务1",
            description="并行任务1"
        )

        task2 = task_list.create_task(
            session_id="session_001",
            task_id="task_002",
            subject="任务2",
            description="并行任务2"
        )

        # 构建任务树（多个根节点）
        tree = task_list.build_task_tree("session_001")
        assert tree is not None
        # 应该创建虚拟根节点
        assert len(tree.children) == 2


class TestSessionProgress:
    """测试会话进度"""

    def test_calculate_progress(self, task_list):
        """测试计算会话进度"""
        # 创建3个任务
        for i in range(3):
            task_list.create_task(
                session_id="session_001",
                task_id=f"task_00{i+1}",
                subject=f"任务{i+1}",
                description=f"描述{i+1}"
            )

        # 完成1个
        task_list.update_task("task_001", status=TaskStatus.COMPLETED)
        # 进行中1个
        task_list.update_task("task_002", status=TaskStatus.IN_PROGRESS, progress=50)

        progress = task_list.get_session_progress("session_001")

        assert progress["total"] == 3
        assert progress["completed"] == 1
        assert progress["in_progress"] == 1
        assert progress["pending"] == 1
        assert progress["failed"] == 0
        # 整体进度 = (100 + 50 + 0) / 3 = 50
        assert progress["overall_progress"] == 50


class TestTaskClear:
    """测试任务清除"""

    def test_clear_session_tasks(self, task_list):
        """测试清除会话任务"""
        # 创建任务
        for i in range(3):
            task_list.create_task(
                session_id="session_001",
                task_id=f"task_00{i+1}",
                subject=f"任务{i+1}",
                description=f"描述{i+1}"
            )

        # 清除
        task_list.clear_session_tasks("session_001")

        # 验证
        tasks = task_list.get_tasks("session_001")
        assert len(tasks) == 0

        # 验证文件已删除
        session_file = Path(task_list.storage_path) / "session_001_tasks.json"
        assert not session_file.exists()


class TestListSessions:
    """测试会话列表"""

    def test_list_saved_sessions(self, task_list):
        """测试列出保存的会话"""
        # 创建多个会话
        for i in range(3):
            task_list.create_task(
                session_id=f"session_00{i+1}",
                task_id=f"task_00{i+1}",
                subject=f"任务{i+1}",
                description=f"描述{i+1}"
            )

        # 列出会话
        sessions = task_list.list_saved_sessions()

        assert len(sessions) == 3
        assert all("session_id" in s for s in sessions)
        assert all("updated_at" in s for s in sessions)
        assert all("task_count" in s for s in sessions)
