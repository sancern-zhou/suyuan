"""
定时任务数据模型
"""
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ScheduleType(str, Enum):
    """调度类型"""
    # 预设类型
    DAILY_8AM = "daily_8am"      # 每天早上8点
    EVERY_2H = "every_2h"        # 每2小时
    EVERY_30MIN = "every_30min"  # 每30分钟

    # 灵活类型
    ONCE = "once"                # 一次性任务（需指定run_at）
    INTERVAL = "interval"        # 自定义间隔（需指定interval_minutes）
    DAILY_CUSTOM = "daily_custom"  # 每天自定义时间（需指定hour和minute）


class TaskStep(BaseModel):
    """任务步骤"""
    step_id: str = Field(..., description="步骤ID")
    description: str = Field(..., description="步骤描述")
    agent_prompt: str = Field(..., description="发送给Agent的提示词")
    timeout_seconds: int = Field(default=300, description="超时时间（秒）")
    retry_on_failure: bool = Field(default=False, description="失败时是否重试")

    class Config:
        json_schema_extra = {
            "example": {
                "step_id": "step_1",
                "description": "获取昨日O3数据",
                "agent_prompt": "查询广州昨天的O3浓度数据",
                "timeout_seconds": 300,
                "retry_on_failure": False
            }
        }


class ScheduledTask(BaseModel):
    """定时任务"""
    task_id: str = Field(..., description="任务ID")
    name: str = Field(..., description="任务名称")
    description: str = Field(..., description="任务描述")

    # 调度配置
    schedule_type: ScheduleType = Field(..., description="调度类型")
    enabled: bool = Field(default=True, description="是否启用")

    # 灵活调度参数（根据schedule_type使用）
    run_at: Optional[datetime] = Field(default=None, description="一次性任务的执行时间（schedule_type=once时必填）")
    interval_minutes: Optional[int] = Field(default=None, description="自定义间隔分钟数（schedule_type=interval时必填）")
    hour: Optional[int] = Field(default=None, description="每天执行的小时（schedule_type=daily_custom时必填，0-23）")
    minute: Optional[int] = Field(default=None, description="每天执行的分钟（schedule_type=daily_custom时必填，0-59）")

    # 执行步骤
    steps: List[TaskStep] = Field(..., description="任务步骤列表")

    # 元数据
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")
    last_run_at: Optional[datetime] = Field(default=None, description="上次运行时间")
    next_run_at: Optional[datetime] = Field(default=None, description="下次运行时间")

    # 统计信息
    total_runs: int = Field(default=0, description="总运行次数")
    success_runs: int = Field(default=0, description="成功次数")
    failed_runs: int = Field(default=0, description="失败次数")

    # 创建者信息
    created_by: str = Field(default="user", description="创建者")
    tags: List[str] = Field(default_factory=list, description="标签")

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "task_001",
                "name": "每日O3污染分析",
                "description": "每天早上8点分析广州昨天的O3污染情况",
                "schedule_type": "daily_8am",
                "enabled": True,
                "steps": [
                    {
                        "step_id": "step_1",
                        "description": "获取昨日O3数据",
                        "agent_prompt": "查询广州昨天的O3浓度数据",
                        "timeout_seconds": 300
                    },
                    {
                        "step_id": "step_2",
                        "description": "生成分析报告",
                        "agent_prompt": "基于上一步的数据，生成O3污染分析报告",
                        "timeout_seconds": 600
                    }
                ],
                "tags": ["O3", "广州", "日报"]
            }
        }
