"""
Workflow Tool - 工作流工具抽象基类

工作流工具是封装了多个原子工具调用的高级工具，用于实现复杂的分析流程。
工作流工具作为ReAct工具注册到全局工具注册表，可以被LLM直接调用。

设计原则：
1. 最小侵入：不修改现有执行器核心，通过适配器封装
2. 渐进式迁移：允许工作流工具与原有系统并存
3. 保持灵活性：工作流可独立调用，也可被LLM选择
4. 统一数据格式：所有工作流返回标准UDF v2.0格式
5. 可观测性：完整记录执行步骤、数据流转、性能指标
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum
import structlog

logger = structlog.get_logger()


class WorkflowStatus(Enum):
    """工作流状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class WorkflowTool(ABC):
    """
    工作流工具抽象基类

    所有工作流工具必须继承此类并实现抽象方法。

    类属性：
        name: 工具名称（用于工具注册和LLM调用）
        description: 工具描述（用于LLM理解工具功能）
        version: 工具版本号
        category: 工具分类（默认为"workflow"）
        requires_context: 是否需要ExecutionContext（数据分析工具需要）

    实例属性：
        _start_time: 工作流开始时间
        _executed_steps: 已执行步骤列表
    """

    # 类属性（子类必须覆盖）
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    category: str = "workflow"
    requires_context: bool = False

    def __init__(self):
        """初始化工作流工具"""
        self._start_time: Optional[datetime] = None
        self._executed_steps: List[Dict[str, Any]] = []

    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行工作流，返回标准UDF v2.0格式

        Args:
            **kwargs: 工作流参数

        Returns:
            标准UDF v2.0格式：
            {
                "status": "success|failed|partial|empty",
                "success": bool,
                "data": Any,
                "visuals": List[Dict],  # 可选
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": self.name,
                    "scenario": "...",
                    "record_count": int,
                    "execution_steps": List[Dict],
                    "execution_time_ms": int
                },
                "summary": str
            }
        """
        pass

    @abstractmethod
    def get_function_schema(self) -> Dict[str, Any]:
        """
        生成OpenAI Function Schema

        用于LLM理解工具的参数格式和调用方式。

        Returns:
            OpenAI Function Schema格式：
            {
                "name": str,
                "description": str,
                "parameters": {
                    "type": "object",
                    "properties": Dict[str, Any],
                    "required": List[str]
                }
            }
        """
        pass

    def _record_step(self, step_name: str, status: str, data: Optional[Dict] = None):
        """
        记录执行步骤

        Args:
            step_name: 步骤名称
            status: 步骤状态（success/failed/pending）
            data: 步骤数据（可选）
        """
        step = {
            "step": step_name,
            "status": status,
            "timestamp": datetime.now().isoformat()
        }
        if data:
            step["data"] = data

        self._executed_steps.append(step)
        logger.debug(
            "workflow_step_recorded",
            workflow=self.name,
            step=step_name,
            status=status
        )

    def _start_timer(self):
        """开始计时"""
        self._start_time = datetime.now()
        logger.debug(
            "workflow_timer_started",
            workflow=self.name
        )

    def _get_elapsed_ms(self) -> Optional[int]:
        """
        获取已消耗时间（毫秒）

        Returns:
            已消耗时间（毫秒），如果未开始计时则返回None
        """
        if self._start_time:
            return int((datetime.now() - self._start_time).total_seconds() * 1000)
        return None

    def _build_udf_v2_result(
        self,
        status: str,
        success: bool,
        data: Any = None,
        visuals: Optional[List[Dict]] = None,
        summary: str = "",
        extra_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        构建标准UDF v2.0格式结果

        Args:
            status: 状态（success/failed/partial/empty）
            success: 是否成功
            data: 数据内容
            visuals: 可视化图表列表（可选）
            summary: 摘要信息
            extra_metadata: 额外的metadata（可选）

        Returns:
            标准UDF v2.0格式字典
        """
        metadata = {
            "schema_version": "v2.0",
            "generator": self.name,
            "scenario": f"{self.category}_analysis",
            "record_count": 1 if data else 0,
            "execution_steps": self._executed_steps,
            "execution_time_ms": self._get_elapsed_ms()
        }

        # 合并额外的metadata
        if extra_metadata:
            metadata.update(extra_metadata)

        return {
            "status": status,
            "success": success,
            "data": data,
            "visuals": visuals or [],
            "metadata": metadata,
            "summary": summary
        }

    def get_executed_steps(self) -> List[Dict[str, Any]]:
        """
        获取已执行步骤列表

        Returns:
            已执行步骤列表
        """
        return self._executed_steps.copy()

    def get_execution_summary(self) -> Dict[str, Any]:
        """
        获取执行摘要

        Returns:
            执行摘要字典
        """
        total_steps = len(self._executed_steps)
        success_steps = sum(1 for step in self._executed_steps if step["status"] == "success")
        failed_steps = sum(1 for step in self._executed_steps if step["status"] == "failed")

        return {
            "workflow": self.name,
            "version": self.version,
            "total_steps": total_steps,
            "success_steps": success_steps,
            "failed_steps": failed_steps,
            "execution_time_ms": self._get_elapsed_ms(),
            "steps": self._executed_steps
        }

    def is_available(self) -> bool:
        """
        检查工具是否可用

        工作流工具默认始终可用。

        Returns:
            True
        """
        return True
