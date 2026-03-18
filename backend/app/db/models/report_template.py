"""
报告模板数据库模型
"""
from sqlalchemy import Column, String, Text, DateTime, Integer, JSON, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.db.database import Base


class ReportTemplate(Base):
    """报告模板模型"""
    __tablename__ = "report_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(255), nullable=False, comment="模板名称")
    description = Column(Text, comment="模板描述")
    content = Column(Text, nullable=False, comment="模板内容")

    # 模板类型
    template_type = Column(String(50), default="structured", comment="模板类型: structured(结构化)/annotated(标注)")

    # 模板元数据
    template_metadata = Column(JSON, comment="模板元数据，包括占位符、章节信息等")

    # 使用统计
    usage_count = Column(Integer, default=0, comment="使用次数")

    # 状态
    is_active = Column(Boolean, default=True, comment="是否启用")

    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")

    # 创建者（可选）
    created_by = Column(String(100), comment="创建者")

    def __repr__(self):
        return f"<ReportTemplate(id={self.id}, name='{self.name}', type='{self.template_type}')>"

    @property
    def placeholder_count(self) -> int:
        """获取占位符数量"""
        if not self.template_metadata:
            return 0
        return len(self.template_metadata.get("placeholders", []))

    @property
    def section_count(self) -> int:
        """获取章节数量"""
        if not self.template_metadata:
            return 0
        return len(self.template_metadata.get("sections", []))


class ReportGenerationHistory(Base):
    """报告生成历史模型"""
    __tablename__ = "report_generation_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    template_id = Column(UUID(as_uuid=True), nullable=False, comment="关联模板ID")

    # 生成参数
    target_time_range = Column(JSON, comment="目标时间范围")
    generation_options = Column(JSON, comment="生成选项")

    # 生成结果
    report_content = Column(Text, comment="生成的报告内容")
    generation_status = Column(String(50), default="completed", comment="生成状态: pending/completed/failed")

    # 执行统计
    execution_time = Column(Integer, comment="执行时间(秒)")
    data_fetch_count = Column(Integer, default=0, comment="数据获取次数")

    # 错误信息
    error_message = Column(Text, comment="错误信息")

    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="生成时间")

    def __repr__(self):
        return f"<ReportGenerationHistory(id={self.id}, template_id={self.template_id}, status='{self.generation_status}')>"
