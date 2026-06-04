"""
统一数据质量验证器 (DataQualityValidator)

为所有工具提供统一的数据质量检查机制
避免空数据、低质量数据导致的虚假分析结果
"""

from typing import Dict, List, Any, Optional
import structlog
from enum import Enum

logger = structlog.get_logger()


class DataQualityLevel(str, Enum):
    """数据质量等级"""
    EXCELLENT = "excellent"  # 优秀
    GOOD = "good"  # 良好
    ACCEPTABLE = "acceptable"  # 可接受
    POOR = "poor"  # 较差
    INVALID = "invalid"  # 无效


class DataQualityReport:
    """数据质量报告"""
    def __init__(
        self,
        is_valid: bool,
        quality_level: DataQualityLevel,
        record_count: int,
        null_percentage: float,
        issues: List[str],
        recommendations: List[str],
        metadata: Dict[str, Any]
    ):
        self.is_valid = is_valid
        self.quality_level = quality_level
        self.record_count = record_count
        self.null_percentage = null_percentage
        self.issues = issues
        self.recommendations = recommendations
        self.metadata = metadata

    def to_dict(self) -> Dict[str, Any]:
        """以字典形式返回质量报告内容（推荐使用）。"""
        return {
            "is_valid": self.is_valid,
            "quality_level": self.quality_level.value,
            "record_count": self.record_count,
            "null_percentage": self.null_percentage,
            "issues": self.issues,
            "recommendations": self.recommendations,
            "metadata": self.metadata,
        }

    def dict(self) -> Dict[str, Any]:
        """
        兼容Pydantic风格的 .dict() 调用。

        注意：内部直接复用 to_dict，避免重复维护字段逻辑。
        """
        return self.to_dict()


class DataQualityValidator:
    """
    统一数据质量验证器

    提供全链路的数据质量检查,避免：
    - 空数据导致虚假分析
    - 低质量数据影响分析准确性
    - 缺少关键字段导致分析失败
    """

    # 质量阈值配置
    QUALITY_THRESHOLDS = {
        "min_records": 1,  # 最小记录数
        "null_threshold_excellent": 0.0,  # 优秀：0%空值
        "null_threshold_good": 0.1,  # 良好：<10%空值
        "null_threshold_acceptable": 0.3,  # 可接受：<30%空值
        "null_threshold_poor": 0.5,  # 较差：<50%空值
        # >50%空值视为无效
    }

    def __init__(self):
        logger.info("data_quality_validator_initialized")

    def validate_data(
        self,
        data: Any,
        schema_type: str,
        required_fields: Optional[List[str]] = None,
        min_records: Optional[int] = None
    ) -> DataQualityReport:
        """
        验证数据质量

        Args:
            data: 要验证的数据
            schema_type: 数据schema类型
            required_fields: 必需字段列表（可选）
            min_records: 最小记录数（可选,默认1）

        Returns:
            DataQualityReport: 数据质量报告
        """
        issues = []
        recommendations = []
        metadata = {"schema_type": schema_type}

        # Step 1: 基础验证
        if not data:
            return DataQualityReport(
                is_valid=False,
                quality_level=DataQualityLevel.INVALID,
                record_count=0,
                null_percentage=100.0,
                issues=["数据为空"],
                recommendations=["请检查数据源,确保数据获取成功"],
                metadata=metadata
            )

        # Step 2: 记录数量验证
        record_count = self._count_records(data)
        min_required = min_records or self.QUALITY_THRESHOLDS["min_records"]

        if record_count < min_required:
            issues.append(f"记录数不足（{record_count} < {min_required}）")
            recommendations.append("请扩大查询范围或检查数据源")

        metadata["record_count"] = record_count

        # Step 3: 空值比例检查
        null_percentage = self._calculate_null_percentage(data)
        metadata["null_percentage"] = null_percentage

        if null_percentage > 50:
            issues.append(f"空值比例过高（{null_percentage:.1f}%）")
            recommendations.append("请检查数据完整性,考虑更换数据源")
        elif null_percentage > 30:
            issues.append(f"空值比例较高（{null_percentage:.1f}%）")
            recommendations.append("建议使用数据填充或插值方法")

        # Step 4: 必需字段检查
        if required_fields:
            missing_fields = self._check_required_fields(data, required_fields)
            if missing_fields:
                issues.append(f"缺少必需字段: {', '.join(missing_fields)}")
                recommendations.append(f"请确保数据包含字段: {', '.join(missing_fields)}")
                metadata["missing_fields"] = missing_fields

        # Step 5: 确定质量等级
        if issues:
            is_valid = record_count >= min_required and null_percentage < 50
            quality_level = self._determine_quality_level(
                record_count, null_percentage, min_required, bool(issues)
            )
        else:
            is_valid = True
            quality_level = self._determine_quality_level(
                record_count, null_percentage, min_required, False
            )

        report = DataQualityReport(
            is_valid=is_valid,
            quality_level=quality_level,
            record_count=record_count,
            null_percentage=null_percentage,
            issues=issues,
            recommendations=recommendations,
            metadata=metadata
        )

        logger.info(
            "data_quality_validation_complete",
            schema_type=schema_type,
            is_valid=is_valid,
            quality_level=quality_level.value,
            record_count=record_count,
            null_percentage=f"{null_percentage:.1f}%",
            issue_count=len(issues)
        )

        return report

    def validate_before_analysis(
        self,
        data: Any,
        analysis_type: str,
        required_fields: Optional[List[str]] = None
    ) -> DataQualityReport:
        """
        分析前数据验证（便捷方法）

        Args:
            data: 要验证的数据
            analysis_type: 分析类型（如"trajectory_analysis", "source_contribution"等）
            required_fields: 必需字段列表

        Returns:
            DataQualityReport: 数据质量报告
        """
        # 根据分析类型设置最小记录数要求
        min_records_map = {
            "trajectory_analysis": 1,  # 轨迹分析至少需要1条记录
            "source_contribution": 10,  # 源区分析需要至少10条轨迹
            "clustering": 5,  # 聚类分析需要至少5条轨迹
            "statistical_analysis": 20,  # 统计分析需要足够样本量
        }

        min_records = min_records_map.get(analysis_type, 1)

        return self.validate_data(
            data=data,
            schema_type=analysis_type,
            required_fields=required_fields,
            min_records=min_records
        )

    def _count_records(self, data: Any) -> int:
        """统计记录数"""
        if isinstance(data, list):
            return len(data)
        elif isinstance(data, dict) and "data" in data:
            return len(data["data"]) if isinstance(data["data"], list) else 1
        return 1

    def _calculate_null_percentage(self, data: Any) -> float:
        """计算空值百分比"""
        if not data:
            return 100.0

        total_values = 0
        null_values = 0

        if isinstance(data, list):
            for record in data:
                if isinstance(record, dict):
                    for value in record.values():
                        total_values += 1
                        if value is None or value == "":
                            null_values += 1

        if total_values == 0:
            return 0.0

        return (null_values / total_values) * 100

    def _check_required_fields(
        self,
        data: Any,
        required_fields: List[str]
    ) -> List[str]:
        """检查必需字段,返回缺失的字段列表"""
        if not required_fields:
            return []

        missing = []

        # 获取第一条记录用于检查
        first_record = None
        if isinstance(data, list) and data:
            first_record = data[0]
        elif isinstance(data, dict) and "data" in data and data["data"]:
            first_record = data["data"][0]

        if not first_record or not isinstance(first_record, dict):
            return required_fields

        # 检查字段
        for field in required_fields:
            if field not in first_record:
                missing.append(field)

        return missing

    def _determine_quality_level(
        self,
        record_count: int,
        null_percentage: float,
        min_required: int,
        has_issues: bool
    ) -> DataQualityLevel:
        """确定质量等级"""
        # 无效数据
        if record_count < min_required or null_percentage > 50:
            return DataQualityLevel.INVALID

        # 较差数据
        if null_percentage > 30 or has_issues:
            return DataQualityLevel.POOR

        # 可接受数据
        if null_percentage > 10:
            return DataQualityLevel.ACCEPTABLE

        # 良好数据
        if null_percentage > 0:
            return DataQualityLevel.GOOD

        # 优秀数据
        return DataQualityLevel.EXCELLENT


# 全局单例
_validator_instance = None


def get_data_quality_validator() -> DataQualityValidator:
    """获取全局数据质量验证器实例"""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = DataQualityValidator()
    return _validator_instance
