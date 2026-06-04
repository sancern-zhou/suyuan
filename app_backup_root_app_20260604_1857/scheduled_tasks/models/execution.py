"""
任务执行记录数据模型
"""
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ExecutionStatus(str, Enum):
    """执行状态"""
    PENDING = "pending"      # 等待执行
    RUNNING = "running"      # 执行中
    SUCCESS = "success"      # 成功
    FAILED = "failed"        # 失败
    TIMEOUT = "timeout"      # 超时
    CANCELLED = "cancelled"  # 已取消


class StepExecution(BaseModel):
    """步骤执行记录"""
    step_id: str = Field(..., description="步骤ID")
    status: ExecutionStatus = Field(..., description="执行状态")
    started_at: Optional[datetime] = Field(default=None, description="开始时间")
    completed_at: Optional[datetime] = Field(default=None, description="完成时间")
    duration_seconds: Optional[float] = Field(default=None, description="执行时长（秒）")

    # Agent交互记录
    agent_prompt: str = Field(..., description="发送给Agent的提示词")
    agent_response: Optional[str] = Field(default=None, description="Agent响应摘要")

    # Agent详细执行日志
    agent_thoughts: List[str] = Field(default_factory=list, description="Agent思考过程")
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list, description="工具调用记录")
    iterations: int = Field(default=0, description="迭代次数")

    # 结果数据
    result_data_ids: List[str] = Field(default_factory=list, description="生成的数据ID列表")
    result_visuals: List[Dict[str, Any]] = Field(default_factory=list, description="生成的可视化")

    # 错误信息
    error_message: Optional[str] = Field(default=None, description="错误信息")
    error_type: Optional[str] = Field(default=None, description="错误类型")

    class Config:
        json_schema_extra = {
            "example": {
                "step_id": "step_1",
                "status": "success",
                "started_at": "2024-01-15T08:00:00",
                "completed_at": "2024-01-15T08:02:30",
                "duration_seconds": 150.5,
                "agent_prompt": "查询广州昨天的O3浓度数据",
                "agent_response": "已获取广州2024-01-14的O3数据，共24条记录",
                "result_data_ids": ["air_quality_unified:abc123"]
            }
        }


class TaskExecution(BaseModel):
    """任务执行记录"""
    execution_id: str = Field(..., description="执行ID")
    task_id: str = Field(..., description="任务ID")
    task_name: str = Field(..., description="任务名称")

    # ReAct Agent 会话ID（整个任务共享，保持上下文连续）
    session_id: Optional[str] = Field(default=None, description="ReAct Agent会话ID")

    # 执行状态
    status: ExecutionStatus = Field(..., description="执行状态")
    started_at: datetime = Field(default_factory=datetime.now, description="开始时间")
    completed_at: Optional[datetime] = Field(default=None, description="完成时间")
    duration_seconds: Optional[float] = Field(default=None, description="总执行时长（秒）")

    # 步骤执行记录
    steps: List[StepExecution] = Field(default_factory=list, description="步骤执行列表")
    current_step_index: int = Field(default=0, description="当前步骤索引")

    # 触发信息
    trigger_type: str = Field(default="scheduled", description="触发类型")
    scheduled_time: Optional[datetime] = Field(default=None, description="计划执行时间")

    # 结果摘要
    total_steps: int = Field(..., description="总步骤数")
    completed_steps: int = Field(default=0, description="已完成步骤数")
    failed_steps: int = Field(default=0, description="失败步骤数")

    # 错误信息
    error_message: Optional[str] = Field(default=None, description="任务级错误信息")

    class Config:
        json_schema_extra = {
            "example": {
                "execution_id": "exec_20240115_080000_001",
                "task_id": "task_001",
                "task_name": "每日O3污染分析",
                "status": "success",
                "started_at": "2024-01-15T08:00:00",
                "completed_at": "2024-01-15T08:05:30",
                "duration_seconds": 330.5,
                "total_steps": 2,
                "completed_steps": 2,
                "failed_steps": 0,
                "trigger_type": "scheduled",
                "scheduled_time": "2024-01-15T08:00:00"
            }
        }
