"""
统一数据共享Schema

为多专家协同系统提供标准化的数据交换格式：
- 统一的数据格式与版本控制
- 结构化的元数据管理
- 专家间的标准化数据传递
- 完整的审计追踪
"""

from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class DataType(str, Enum):
    """数据类型枚举"""
    WEATHER = "weather"
    COMPONENT = "component"
    VISUALIZATION = "visualization"
    REPORT = "report"
    METADATA = "metadata"
    FUSION = "fusion"


class DataStatus(str, Enum):
    """数据状态枚举"""
    RAW = "raw"
    PROCESSING = "processing"
    PROCESSED = "processed"
    VALIDATED = "validated"
    ARCHIVED = "archived"
    ERROR = "error"


class SharedDataMetadata(BaseModel):
    """共享数据元数据"""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    schema_version: str = Field(default="1.0.0", description="数据模式版本")
    generator: str = Field(description="生成此数据的专家或工具名称")
    source_expert: str = Field(description="源专家名称")
    target_experts: List[str] = Field(default_factory=list, description="目标专家列表")
    data_quality_score: float = Field(default=1.0, ge=0.0, le=1.0, description="数据质量评分")
    record_count: int = Field(default=0, description="数据记录数量")
    tags: List[str] = Field(default_factory=list, description="数据标签")
    dependencies: List[str] = Field(default_factory=list, description="依赖的数据ID列表")
    audit_trail: List[Dict[str, Any]] = Field(default_factory=list, description="审计追踪")


class SharedDataRecord(BaseModel):
    """统一数据共享记录"""
    data_id: str = Field(description="唯一数据标识符")
    data_type: DataType = Field(description="数据类型")
    status: DataStatus = Field(default=DataStatus.PROCESSED, description="数据状态")
    payload: Union[Dict[str, Any], List[Dict[str, Any]]] = Field(description="数据载荷")
    metadata: SharedDataMetadata = Field(description="元数据")
    parent_data_ids: List[str] = Field(default_factory=list, description="父数据ID列表")
    child_data_ids: List[str] = Field(default_factory=list, description="子数据ID列表")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SharedDataRecord':
        """从字典创建实例"""
        return cls(**data)

    def add_audit_entry(self, action: str, expert: str, details: Optional[Dict[str, Any]] = None):
        """添加审计追踪记录"""
        self.metadata.audit_trail.append({
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "expert": expert,
            "details": details or {}
        })

    def update_timestamp(self):
        """更新时间戳"""
        self.metadata.updated_at = datetime.utcnow()

    def get_summary(self) -> Dict[str, Any]:
        """获取数据摘要"""
        return {
            "data_id": self.data_id,
            "data_type": self.data_type.value,
            "status": self.status.value,
            "created_at": self.metadata.created_at.isoformat(),
            "updated_at": self.metadata.updated_at.isoformat(),
            "generator": self.metadata.generator,
            "record_count": self.metadata.record_count,
            "quality_score": self.metadata.data_quality_score,
            "parent_count": len(self.parent_data_ids),
            "child_count": len(self.child_data_ids),
            "audit_count": len(self.metadata.audit_trail)
        }


class DataSchemaManager:
    """数据Schema管理器"""

    SCHEMA_VERSION = "1.0.0"

    @staticmethod
    def create_shared_data_record(
        data_id: str,
        data_type: DataType,
        payload: Union[Dict[str, Any], List[Dict[str, Any]]],
        generator: str,
        source_expert: str,
        target_experts: Optional[List[str]] = None,
        parent_data_ids: Optional[List[str]] = None,
        data_quality_score: float = 1.0,
        record_count: Optional[int] = None,
        tags: Optional[List[str]] = None
    ) -> SharedDataRecord:
        """
        创建标准化的数据共享记录

        Args:
            data_id: 唯一数据标识符
            data_type: 数据类型
            payload: 数据载荷
            generator: 生成工具/专家名称
            source_expert: 源专家名称
            target_experts: 目标专家列表
            parent_data_ids: 父数据ID列表
            data_quality_score: 数据质量评分 (0-1)
            record_count: 数据记录数量
            tags: 数据标签

        Returns:
            标准化的数据共享记录
        """
        metadata = SharedDataMetadata(
            schema_version=DataSchemaManager.SCHEMA_VERSION,
            generator=generator,
            source_expert=source_expert,
            target_experts=target_experts or [],
            data_quality_score=data_quality_score,
            record_count=record_count or (len(payload) if isinstance(payload, list) else 1),
            tags=tags or []
        )

        record = SharedDataRecord(
            data_id=data_id,
            data_type=data_type,
            payload=payload,
            metadata=metadata,
            parent_data_ids=parent_data_ids or []
        )

        # 添加创建审计记录
        record.add_audit_entry(
            action="created",
            expert=source_expert,
            details={
                "schema_version": DataSchemaManager.SCHEMA_VERSION,
                "data_type": data_type.value
            }
        )

        return record

    @staticmethod
    def validate_schema(record: SharedDataRecord) -> Dict[str, Any]:
        """
        验证数据记录是否符合Schema

        Args:
            record: 数据记录

        Returns:
            验证结果字典
        """
        issues = []

        # 检查必填字段
        if not record.data_id:
            issues.append("缺少data_id字段")

        if not record.data_type:
            issues.append("缺少data_type字段")

        if not record.metadata.generator:
            issues.append("缺少generator元数据")

        if not record.metadata.source_expert:
            issues.append("缺少source_expert元数据")

        # 检查数据载荷
        if record.payload is None:
            issues.append("payload为空")

        # 检查版本兼容性
        if record.metadata.schema_version != DataSchemaManager.SCHEMA_VERSION:
            issues.append(f"Schema版本不匹配: 期望{DataSchemaManager.SCHEMA_VERSION}, 实际{record.metadata.schema_version}")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "schema_version": DataSchemaManager.SCHEMA_VERSION
        }

    @staticmethod
    def create_weather_data_record(
        data_id: str,
        weather_data: Dict[str, Any],
        generator: str = "WeatherExpert",
        source_expert: str = "weather"
    ) -> SharedDataRecord:
        """创建气象数据记录"""
        return DataSchemaManager.create_shared_data_record(
            data_id=data_id,
            data_type=DataType.WEATHER,
            payload=weather_data,
            generator=generator,
            source_expert=source_expert,
            tags=["meteorology", "weather"]
        )

    @staticmethod
    def create_component_data_record(
        data_id: str,
        component_data: Dict[str, Any],
        generator: str = "ComponentExpert",
        source_expert: str = "component",
        parent_data_ids: Optional[List[str]] = None
    ) -> SharedDataRecord:
        """创建组分数据记录"""
        return DataSchemaManager.create_shared_data_record(
            data_id=data_id,
            data_type=DataType.COMPONENT,
            payload=component_data,
            generator=generator,
            source_expert=source_expert,
            parent_data_ids=parent_data_ids,
            tags=["component", "pollutants"]
        )

    @staticmethod
    def create_visualization_data_record(
        data_id: str,
        chart_data: Dict[str, Any],
        generator: str = "VizExpert",
        source_expert: str = "viz",
        parent_data_ids: Optional[List[str]] = None
    ) -> SharedDataRecord:
        """创建可视化数据记录"""
        return DataSchemaManager.create_shared_data_record(
            data_id=data_id,
            data_type=DataType.VISUALIZATION,
            payload=chart_data,
            generator=generator,
            source_expert=source_expert,
            parent_data_ids=parent_data_ids,
            tags=["visualization", "charts"]
        )

    @staticmethod
    def create_report_data_record(
        data_id: str,
        report_data: Dict[str, Any],
        generator: str = "ReportExpert",
        source_expert: str = "report",
        parent_data_ids: Optional[List[str]] = None
    ) -> SharedDataRecord:
        """创建报告数据记录"""
        return DataSchemaManager.create_shared_data_record(
            data_id=data_id,
            data_type=DataType.REPORT,
            payload=report_data,
            generator=generator,
            source_expert=source_expert,
            parent_data_ids=parent_data_ids,
            tags=["report", "analysis"]
        )

    @staticmethod
    def create_fusion_data_record(
        data_id: str,
        fusion_data: Dict[str, Any],
        source_data_ids: List[str],
        generator: str = "DataFusion",
        source_expert: str = "router"
    ) -> SharedDataRecord:
        """创建数据融合记录"""
        record = DataSchemaManager.create_shared_data_record(
            data_id=data_id,
            data_type=DataType.FUSION,
            payload=fusion_data,
            generator=generator,
            source_expert=source_expert,
            parent_data_ids=source_data_ids,
            tags=["fusion", "multi-source"]
        )
        record.metadata.dependencies = source_data_ids
        return record

    @staticmethod
    def extract_weather_payload(record: SharedDataRecord) -> Dict[str, Any]:
        """从气象数据记录中提取载荷"""
        if record.data_type != DataType.WEATHER:
            raise ValueError(f"数据类型不匹配: 期望{DataType.WEATHER}, 实际{record.data_type}")
        return record.payload

    @staticmethod
    def extract_component_payload(record: SharedDataRecord) -> Dict[str, Any]:
        """从组分数据记录中提取载荷"""
        if record.data_type != DataType.COMPONENT:
            raise ValueError(f"数据类型不匹配: 期望{DataType.COMPONENT}, 实际{record.data_type}")
        return record.payload

    @staticmethod
    def extract_visualization_payload(record: SharedDataRecord) -> Dict[str, Any]:
        """从可视化数据记录中提取载荷"""
        if record.data_type != DataType.VISUALIZATION:
            raise ValueError(f"数据类型不匹配: 期望{DataType.VISUALIZATION}, 实际{record.data_type}")
        return record.payload

    @staticmethod
    def extract_report_payload(record: SharedDataRecord) -> Dict[str, Any]:
        """从报告数据记录中提取载荷"""
        if record.data_type != DataType.REPORT:
            raise ValueError(f"数据类型不匹配: 期望{DataType.REPORT}, 实际{record.data_type}")
        return record.payload

    @staticmethod
    def get_data_lineage(record: SharedDataRecord) -> Dict[str, Any]:
        """获取数据血缘关系"""
        return {
            "data_id": record.data_id,
            "parents": record.parent_data_ids,
            "children": record.child_data_ids,
            "dependencies": record.metadata.dependencies,
            "generation_path": [
                entry["expert"]
                for entry in record.metadata.audit_trail
                if entry["action"] == "created"
            ]
        }


# 预定义的Schema模板
SCHEMA_TEMPLATES = {
    "weather_analysis": {
        "required_fields": ["latitude", "longitude", "time_range", "meteorological_data"],
        "optional_fields": ["trajectory_data", "upwind_analysis"],
        "data_type": DataType.WEATHER
    },
    "component_analysis": {
        "required_fields": ["station_id", "pollutant_type", "component_data"],
        "optional_fields": ["pmf_result", "obm_result", "source_apportionment"],
        "data_type": DataType.COMPONENT
    },
    "visualization": {
        "required_fields": ["chart_configs", "visuals"],
        "optional_fields": ["layout_config", "interaction_config"],
        "data_type": DataType.VISUALIZATION
    },
    "comprehensive_report": {
        "required_fields": ["conclusions", "recommendations"],
        "optional_fields": ["confidence_score", "data_sources", "limitations"],
        "data_type": DataType.REPORT
    }
}
