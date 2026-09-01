"""
定时任务数据模型
"""
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator


class ScheduleType(str, Enum):
    """调度类型"""
    # 预设类型
    DAILY_8AM = "daily_8am"      # 每天早上8点
    EVERY_2H = "every_2h"        # 每2小时
    EVERY_30MIN = "every_30min"  # 每30分钟
    MONTHLY_1ST_7AM = "monthly_1st_7am"  # 每月1日早上7点
    WEEKLY_MONDAY_8AM = "weekly_monday_8am"  # 每周一早上8点

    # 灵活类型
    ONCE = "once"                # 一次性任务（需指定run_at）
    INTERVAL = "interval"        # 自定义间隔（需指定interval_minutes）
    DAILY_CUSTOM = "daily_custom"  # 每天自定义时间（需指定hour和minute）


class TriggerType(str, Enum):
    """任务触发方式。"""

    SCHEDULE = "schedule"
    EVENT = "event"


class WorkspaceEntry(BaseModel):
    """Optional left-sidebar business entry for a scheduled task."""

    enabled: bool = False
    title: str = ""


class HistoryLearningConfig(BaseModel):
    """任务级历史执行记忆配置。

    案例库与长期记忆均绑定单个任务，不跨任务共享：
    - 案例 = 单次执行的回顾性总结（不含面向下次执行的建议）
    - 长期记忆 = 跨次积累的前瞻性知识（模式规律/经验教训/输出偏好/当前关注）
    """

    enabled: bool = Field(default=True, description="是否启用历史执行记忆")
    max_recent_cases: int = Field(
        default=3, ge=0, le=20, description="执行前注入的最近案例数量"
    )
    memory_char_budget: int = Field(
        default=4000, ge=200, description="长期记忆注入的字符上限"
    )
    consolidation_timeout_seconds: int = Field(
        default=120, ge=1, description="执行后巩固调用的超时时间（秒）"
    )


class ScheduledTask(BaseModel):
    """定时任务"""
    task_id: str = Field(..., description="任务ID")
    name: str = Field(..., description="任务名称")
    description: str = Field(..., description="任务描述")
    execution_mode: str = Field(
        default="expert",
        description="执行模式（assistant/expert/query/social/custom）"
    )
    tool_names: Optional[List[str]] = Field(
        default=None,
        description="custom 模式固定使用的工具名称列表",
    )
    skill_id: Optional[str] = Field(
        default=None,
        description="执行时注入的已发布 Skill ID",
    )
    knowledge_base_binding: Optional[str] = Field(
        default=None,
        description="项目知识库绑定键；由运行时解析为 knowledge_base_ids",
    )

    # 触发配置
    trigger_type: TriggerType = Field(default=TriggerType.SCHEDULE, description="触发方式")
    schedule_type: Optional[ScheduleType] = Field(default=None, description="调度类型")
    event_type: Optional[str] = Field(default=None, description="事件类型")
    event_filters: Dict[str, Any] = Field(default_factory=dict, description="事件属性过滤条件")
    target_user_ids: List[str] = Field(default_factory=list, description="后台社交用户ID")
    broadcast_enabled: bool = Field(default=False, description="是否广播执行结果")
    enabled: bool = Field(default=True, description="是否启用")

    # 灵活调度参数（根据schedule_type使用）
    run_at: Optional[datetime] = Field(default=None, description="一次性任务的执行时间（schedule_type=once时必填）")
    interval_minutes: Optional[int] = Field(default=None, description="自定义间隔分钟数（schedule_type=interval时必填）")
    hour: Optional[int] = Field(default=None, description="每天执行的小时（schedule_type=daily_custom时必填，0-23）")
    minute: Optional[int] = Field(default=None, description="每天执行的分钟（schedule_type=daily_custom时必填，0-59）")

    # 一个定时任务就是一次完整的 Agent 执行：Agent 自行规划工具调用，
    # 不存在预配置的多步骤机制（历史 steps 字段已彻底移除）。
    prompt: str = Field(..., min_length=1, description="任务提示词")
    timeout_seconds: int = Field(default=1800, ge=1, description="任务级总超时时间（秒）")

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
    owner_user_id: str = Field(default="system", description="会话归属用户ID")
    owner_username: str = Field(default="scheduled-task", description="会话归属用户名")
    owner_display_name: str = Field(default="定时任务", description="会话归属显示名")
    tags: List[str] = Field(default_factory=list, description="标签")
    workspace_entry: Optional[WorkspaceEntry] = Field(
        default=None,
        description="左侧业务入口配置",
    )
    history_learning: HistoryLearningConfig = Field(
        default_factory=HistoryLearningConfig,
        description="历史执行记忆配置（任务专属案例库 + 长期记忆）",
    )

    @field_validator("tool_names")
    @classmethod
    def normalize_tool_names(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return None
        normalized: List[str] = []
        seen = set()
        for raw_name in value:
            name = raw_name.strip()
            if not name or name in seen:
                continue
            seen.add(name)
            normalized.append(name)
        return normalized

    @model_validator(mode="after")
    def validate_trigger(self):
        self.prompt = (self.prompt or "").strip()
        if not self.prompt:
            raise ValueError("prompt is required")
        if self.execution_mode == "custom" and not self.tool_names:
            raise ValueError("tool_names is required for custom mode")
        if self.execution_mode != "custom" and self.tool_names is not None:
            raise ValueError("tool_names is only valid for custom mode")
        if self.skill_id is not None:
            skill_id = self.skill_id.strip()
            if not skill_id or any(part in skill_id for part in ("/", "\\", "..")):
                raise ValueError("skill_id must be a safe published skill id")
            self.skill_id = skill_id
        if self.knowledge_base_binding is not None:
            binding = self.knowledge_base_binding.strip()
            if not binding or any(part in binding for part in ("/", "\\", "..")):
                raise ValueError("knowledge_base_binding must be a safe binding key")
            self.knowledge_base_binding = binding
        if self.trigger_type == TriggerType.SCHEDULE and self.schedule_type is None:
            raise ValueError("schedule_type is required for schedule tasks")
        if self.trigger_type == TriggerType.EVENT and not (self.event_type or "").strip():
            raise ValueError("event_type is required for event tasks")
        if self.broadcast_enabled and not self.target_user_ids:
            raise ValueError("target_user_ids is required when broadcast_enabled=true")
        return self

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "task_001",
                "name": "每日O3污染分析",
                "description": "每天早上8点分析广州昨天的O3污染情况",
                "execution_mode": "expert",
                "schedule_type": "daily_8am",
                "enabled": True,
                "prompt": "查询广州昨天的O3浓度数据并生成污染分析报告",
                "timeout_seconds": 1800,
                "tags": ["O3", "广州", "日报"]
            }
        }
