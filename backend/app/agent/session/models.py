"""
会话数据模型

定义会话、会话状态、会话信息等核心数据结构。
"""

from enum import Enum
from datetime import datetime
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field


class Session(BaseModel):
    """
    会话数据模型

    存储完整的会话状态，用于断点恢复。
    """

    # 基本信息
    session_id: str = Field(..., description="会话ID")
    query: str = Field(..., description="用户原始查询")

    # 时间信息
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")

    # 对话历史
    conversation_history: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="对话历史（LLM消息列表）"
    )

    # 执行上下文
    execution_context: Dict[str, Any] = Field(
        default_factory=dict,
        description="执行上下文数据"
    )

    # 任务列表引用
    task_list_file: Optional[str] = Field(
        default=None,
        description="任务列表文件路径"
    )

    # 当前执行状态
    current_step: Optional[str] = Field(default=None, description="当前执行步骤")
    current_expert: Optional[str] = Field(default=None, description="当前执行的专家")

    # 结果数据
    data_ids: List[str] = Field(default_factory=list, description="生成的数据ID列表")
    visual_ids: List[str] = Field(default_factory=list, description="生成的可视化ID列表")

    # Office文档预览数据（用于历史对话恢复PDF预览）
    office_documents: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Office文档PDF预览元数据列表"
    )

    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict, description="会话元数据")

    # 错误信息
    error: Optional[Dict[str, Any]] = Field(default=None, description="错误信息")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }

    def to_summary(self) -> 'SessionInfo':
        """转换为摘要信息"""
        return SessionInfo(
            session_id=self.session_id,
            query=self.query,
            created_at=self.created_at,
            updated_at=self.updated_at,
            data_count=len(self.data_ids),
            visual_count=len(self.visual_ids),
            has_error=self.error is not None
        )

    def get_duration(self) -> float:
        """获取会话持续时间（秒）"""
        return (datetime.now() - self.created_at).total_seconds()


class SessionInfo(BaseModel):
    """
    会话摘要信息

    用于会话列表展示，不包含完整数据。
    """
    session_id: str = Field(..., description="会话ID")
    query: str = Field(..., description="用户查询（前100字符）")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    data_count: int = Field(default=0, description="数据数量")
    visual_count: int = Field(default=0, description="可视化数量")
    has_error: bool = Field(default=False, description="是否有错误")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class SessionRestoreOptions(BaseModel):
    """会话恢复选项"""
    restore_conversation_history: bool = Field(
        default=True,
        description="是否恢复对话历史"
    )
    restore_execution_context: bool = Field(
        default=True,
        description="是否恢复执行上下文"
    )
    restore_task_list: bool = Field(
        default=True,
        description="是否恢复任务列表"
    )
    continue_from_checkpoint: bool = Field(
        default=True,
        description="是否从检查点继续"
    )
