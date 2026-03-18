"""
任务数据模型

定义任务、任务状态、任务树等核心数据结构。
"""

from enum import Enum
from datetime import datetime
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"           # 待执行
    IN_PROGRESS = "in_progress"   # 执行中
    COMPLETED = "completed"       # 已完成
    FAILED = "failed"             # 失败
    SKIPPED = "skipped"           # 已跳过
    CANCELLED = "cancelled"       # 已取消


class Task(BaseModel):
    """任务数据模型"""

    # 基本信息
    id: str = Field(..., description="任务ID")
    session_id: str = Field(..., description="会话ID")
    subject: str = Field(..., description="任务标题")
    description: str = Field(..., description="任务详细描述")

    # 状态信息
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="任务状态")
    progress: int = Field(default=0, ge=0, le=100, description="进度百分比")

    # 依赖关系
    depends_on: List[str] = Field(default_factory=list, description="依赖任务ID列表")
    blocked_by: List[str] = Field(default_factory=list, description="阻塞任务ID列表（运行时计算）")

    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict, description="任务元数据")

    # 时间信息
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")
    started_at: Optional[datetime] = Field(default=None, description="开始执行时间")
    completed_at: Optional[datetime] = Field(default=None, description="完成时间")

    # 执行结果
    error_message: Optional[str] = Field(default=None, description="错误信息")
    result_data_id: Optional[str] = Field(default=None, description="结果数据ID")
    checkpoint_id: Optional[str] = Field(default=None, description="检查点ID")
    celery_task_id: Optional[str] = Field(default=None, description="Celery任务ID")

    # 专家信息
    expert_type: Optional[str] = Field(default=None, description="执行此任务的专家类型")
    tool_name: Optional[str] = Field(default=None, description="使用的工具名称")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }

    def get_duration(self) -> Optional[float]:
        """获取任务执行时长（秒）"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        elif self.started_at:
            return (datetime.now() - self.started_at).total_seconds()
        return None

    def is_ready_to_execute(self, all_tasks: Dict[str, 'Task']) -> bool:
        """
        检查任务是否可以执行

        条件：
        1. 状态为pending
        2. 所有依赖任务已完成
        """
        if self.status != TaskStatus.PENDING:
            return False

        for dep_id in self.depends_on:
            dep_task = all_tasks.get(dep_id)
            if not dep_task or dep_task.status != TaskStatus.COMPLETED:
                return False

        return True

    def mark_started(self):
        """标记任务开始"""
        self.status = TaskStatus.IN_PROGRESS
        self.started_at = datetime.now()
        self.updated_at = datetime.now()

    def mark_completed(self, result_data_id: Optional[str] = None):
        """标记任务完成"""
        self.status = TaskStatus.COMPLETED
        self.progress = 100
        self.completed_at = datetime.now()
        self.updated_at = datetime.now()
        if result_data_id:
            self.result_data_id = result_data_id

    def mark_failed(self, error_message: str):
        """标记任务失败"""
        self.status = TaskStatus.FAILED
        self.completed_at = datetime.now()
        self.updated_at = datetime.now()
        self.error_message = error_message

    def update_progress(self, progress: int):
        """更新任务进度"""
        self.progress = max(0, min(100, progress))
        self.updated_at = datetime.now()


class TaskTree(BaseModel):
    """
    任务树结构

    用于展示任务的层级依赖关系。
    """
    task: Task
    children: List['TaskTree'] = Field(default_factory=list)

    def to_graph(self) -> Dict[str, Any]:
        """
        转换为图结构（用于可视化）

        Returns:
            包含nodes和edges的字典
        """
        nodes = []
        edges = []

        def _traverse(tree_node: 'TaskTree', parent_id: Optional[str] = None):
            """递归遍历树"""
            task = tree_node.task

            # 添加节点
            nodes.append({
                "id": task.id,
                "label": task.subject,
                "status": task.status.value,
                "progress": task.progress,
                "expert_type": task.expert_type,
                "metadata": {
                    "created_at": task.created_at.isoformat(),
                    "duration": task.get_duration()
                }
            })

            # 添加边
            if parent_id:
                edges.append({
                    "source": parent_id,
                    "target": task.id
                })

            # 递归处理子节点
            for child in tree_node.children:
                _traverse(child, task.id)

        _traverse(self)

        return {
            "nodes": nodes,
            "edges": edges
        }

    def get_all_tasks(self) -> List[Task]:
        """获取树中所有任务"""
        tasks = [self.task]
        for child in self.children:
            tasks.extend(child.get_all_tasks())
        return tasks


class TaskSummary(BaseModel):
    """任务摘要（用于列表展示）"""
    id: str
    subject: str
    status: TaskStatus
    progress: int
    depends_on: List[str]
    expert_type: Optional[str]
    created_at: datetime
    duration: Optional[float]


# 更新前向引用
TaskTree.model_rebuild()
