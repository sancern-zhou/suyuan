"""
Typed Data Handle for Type-Safe Data References

This module provides a type-safe wrapper around data references, ensuring that:
- Data schema is preserved and validated
- Quality reports are accessible without loading full data
- Field availability can be checked before tool execution
- Type information is carried throughout the data pipeline

This is inspired by LangChain's ToolMessage.artifact pattern and Google ADK's
ArtifactService, adapted for our multi-tool agent workflow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.schemas.common import DataQualityReport, FieldStats

import structlog

logger = structlog.get_logger()


@dataclass
class TypedDataHandle:
    """
    Type-safe data reference handle.

    This handle carries metadata about stored data without loading the full payload,
    enabling:
    - Schema validation before data loading
    - Field availability checks
    - Quality report access
    - Type-safe deserialization

    Attributes:
        data_id: Unique identifier (without schema prefix)
        schema: Data schema (e.g., "vocs", "particulate")
        version: Schema version (e.g., "v1")
        record_count: Number of records in dataset
        model_class: Pydantic model class for deserialization
        quality_report: Data validation quality report
        field_stats: Field-level statistics
        metadata: Additional metadata

    Example:
        handle = TypedDataHandle(
            data_id="abc123",
            schema="vocs",
            version="v1",
            record_count=48,
            model_class=VOCsSample,
            quality_report=report,
            field_stats=stats
        )

        # Check compatibility before loading
        if handle.is_compatible_with("vocs"):
            data = context.get_data(handle.full_id)
    """

    data_id: str
    schema: str
    version: str
    record_count: int
    model_class: Type[BaseModel]
    quality_report: DataQualityReport
    field_stats: List[FieldStats]
    metadata: Optional[Dict[str, Any]] = None

    @property
    def full_id(self) -> str:
        """
        Full data identifier with schema prefix.

        Returns:
            Formatted as "schema:version:data_id" (e.g., "vocs:v1:abc123")
        """
        return f"{self.schema}:{self.version}:{self.data_id}"

    def is_compatible_with(self, required_schema: str) -> bool:
        """
        Check if this handle's schema matches the required schema.

        Args:
            required_schema: Expected schema name

        Returns:
            True if schemas match

        Example:
            if not handle.is_compatible_with("vocs"):
                raise ValueError("Expected VOCs data")
        """
        return self.schema == required_schema

    def has_required_fields(
        self,
        fields: List[str]
    ) -> tuple[bool, List[str]]:
        """
        Check if dataset contains required fields.

        Args:
            fields: List of required field names

        Returns:
            Tuple of (all_present, missing_fields)

        Example:
            is_valid, missing = handle.has_required_fields(["乙烯", "丙烯", "苯"])
            if not is_valid:
                return {"error": f"Missing species: {', '.join(missing)}"}
        """
        available_fields = {stat.name for stat in self.field_stats}
        missing = [f for f in fields if f not in available_fields]
        return (len(missing) == 0, missing)

    def get_field_stats_by_name(self, field_name: str) -> Optional[FieldStats]:
        """
        Get statistics for a specific field.

        Args:
            field_name: Field name to look up

        Returns:
            FieldStats if found, None otherwise
        """
        for stat in self.field_stats:
            if stat.name == field_name:
                return stat
        return None

    def get_quality_summary(self) -> str:
        """
        Get human-readable quality summary.

        Returns:
            Formatted quality summary string

        Example:
            summary = handle.get_quality_summary()
            # "schema=vocs | count=48 | missing_rate=2.08% | issues=vocs.missing_required_species"
        """
        return self.quality_report.to_summary()

    def has_quality_errors(self) -> bool:
        """
        Check if quality report contains errors.

        Returns:
            True if there are validation errors

        Example:
            if handle.has_quality_errors():
                logger.warning("data_quality_issues", data_id=handle.full_id)
        """
        return self.quality_report.has_errors()

    def get_available_fields(self) -> List[str]:
        """
        Get list of all available field names.

        Returns:
            Sorted list of field names

        Example:
            fields = handle.get_available_fields()
            # ["乙烷", "丙烷", "苯", "甲苯", ...]
        """
        return sorted([stat.name for stat in self.field_stats])

    def get_field_coverage(self) -> Dict[str, float]:
        """
        Get field coverage (non-missing rate) for all fields.

        Returns:
            Dict mapping field name to coverage rate (0.0 to 1.0)

        Example:
            coverage = handle.get_field_coverage()
            # {"乙烯": 1.0, "丙烯": 0.98, "苯": 0.95, ...}
        """
        return {
            stat.name: 1.0 - stat.missing_rate
            for stat in self.field_stats
        }

    def validate_for_pmf(self) -> tuple[bool, Optional[str]]:
        """
        Validate if data is suitable for PMF analysis.

        PMF requirements:
        - VOCs: ≥20 samples, ≥3 species
        - Particulate: ≥20 samples, at least 3 core components present (flexible)

        Note: Core components may be split across multiple queries (e.g., water-soluble ions,
        carbon, crustal elements). This validator accepts data with at least 3 of the 5
        core components: SO4, NO3, NH4, OC, EC.

        Returns:
            Tuple of (is_valid, error_message)

        Example:
            is_valid, error = handle.validate_for_pmf()
            if not is_valid:
                return {"success": False, "error": error}
        """
        # 支持新旧两种格式
        if self.schema in ("vocs", "vocs_unified"):
            if self.record_count < 20:
                return (
                    False,
                    f"VOCs PMF需要≥20个样本，当前{self.record_count}个"
                )
            if len(self.field_stats) < 3:
                return (
                    False,
                    f"VOCs PMF需要≥3种物种，当前{len(self.field_stats)}种"
                )
        elif self.schema in ("particulate", "particulate_unified", "particulate_analysis"):
            if self.record_count < 20:
                return (
                    False,
                    f"颗粒物PMF需要≥20个样本，当前{self.record_count}个"
                )
            # 灵活的组分验证：接受至少3个核心组分（不要求全部5个）
            # 核心组分可能分散在多个查询中：水溶性离子(SO4,NO3,NH4)、碳组分(OC,EC)
            required = {"SO4", "NO3", "NH4", "OC", "EC"}
            available = {stat.name for stat in self.field_stats}
            # 也接受带后缀的字段名（兼容不同数据格式）
            extended_available = set()
            for field in available:
                extended_available.add(field)
                # 标准化：去除空格、下划线、转义字符
                normalized = field.replace(" ", "").replace("_", "").replace("⁻", "").replace("²", "").replace("+", "")
                extended_available.add(normalized)
            found = required & extended_available
            if len(found) < 3:
                return (
                    False,
                    f"缺少核心组分: 至少需要3个(当前找到{len(found)}个: {', '.join(found)})，要求: SO4、NO3、NH4、OC、EC"
                )
        else:
            return (False, f"PMF不支持{self.schema}数据")

        return (True, None)

    def validate_for_obm_ofp(self) -> tuple[bool, Optional[str]]:
        """
        Validate if data is suitable for OBM/OFP analysis.

        Requirements:
        - Must be VOCs data
        - ≥3 VOC species
        - At least one sample

        Returns:
            Tuple of (is_valid, error_message)
        """
        if self.schema != "vocs":
            return (False, "OBM/OFP分析只支持VOCs数据")

        if self.record_count == 0:
            return (False, "数据为空")

        if len(self.field_stats) < 3:
            return (
                False,
                f"OFP计算需要≥3种VOC物种，当前{len(self.field_stats)}种"
            )

        return (True, None)

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize handle to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "data_id": self.data_id,
            "full_id": self.full_id,
            "schema": self.schema,
            "version": self.version,
            "record_count": self.record_count,
            "model_class": self.model_class.__name__,
            "quality_summary": self.get_quality_summary(),
            "available_fields": self.get_available_fields(),
            "metadata": self.metadata
        }

    def __repr__(self) -> str:
        return (
            f"<TypedDataHandle {self.full_id} "
            f"records={self.record_count} "
            f"fields={len(self.field_stats)}>"
        )
