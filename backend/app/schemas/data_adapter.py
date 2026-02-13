"""
Data Adapter - 数据格式适配器

将各种工具的输出格式统一转换为Unified Data Format (UDF v1.0)
支持工具间相互调用和数据传递

主要功能：
1. 自动识别工具输出格式
2. 转换为统一格式
3. 保留向后兼容性
4. 简化工具间数据传递
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
import structlog

from app.schemas.unified import (
    UnifiedData, DataType, DataStatus, DataMetadata,
    UnifiedDataRecord, create_unified_data
)

logger = structlog.get_logger()


class DataAdapter:
    """
    数据适配器

    将各种工具的输出格式转换为统一格式
    """

    @staticmethod
    def detect_format(data: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """
        自动检测数据格式

        Args:
            data: 工具输出数据

        Returns:
            Tuple[格式类型, 转换提示]
        """
        format_hints = {}

        # 检测VOCs组分数据
        if "registry_schema" in data and data.get("registry_schema") == "vocs":
            if "DisplayName" in str(data.get("data", [])):
                return "vocs_component", {"schema": "vocs", "source": "get_component_data"}

        # 检测PMF结果
        if "source_contributions" in data and "timeseries" in data:
            if isinstance(data.get("source_contributions"), dict):
                return "pmf_result", {"schema": "pmf_result", "source": "calculate_pmf"}

        # 检测OBM/OFP结果
        if "ofp_by_species" in data and "ofp_by_category" in data:
            return "obm_ofp_result", {"schema": "obm_result", "source": "calculate_obm_full_chemistry"}

        # 检测气象数据
        if "records" in data and "data_type" in data:
            if data.get("data_type") in ["era5", "observed"]:
                return "weather_data", {"schema": "weather", "source": "get_weather_data"}

        # 检测空气质量数据
        if "structured_data" in data or "data" in data:
            if "conversation_id" in data:
                return "air_quality", {"schema": "air_quality", "source": "get_air_quality"}

        # 检测图表配置
        if "chart_config" in data or "chart_id" in data:
            return "chart_config", {"schema": "chart_config", "source": "smart_chart_generator"}

        return "unknown", format_hints

    @staticmethod
    def convert_to_unified(
        data: Dict[str, Any],
        target_schema: Optional[str] = None
    ) -> UnifiedData:
        """
        将数据转换为统一格式

        Args:
            data: 原始工具输出
            target_schema: 目标数据Schema（可选）

        Returns:
            UnifiedData实例
        """
        format_type, hints = DataAdapter.detect_format(data)

        logger.info(
            "data_conversion_started",
            original_format=format_type,
            hints=hints,
            target_schema=target_schema
        )

        try:
            if format_type == "vocs_component":
                return DataAdapter._convert_vocs_component(data, hints)
            elif format_type == "pmf_result":
                return DataAdapter._convert_pmf_result(data, hints)
            elif format_type == "obm_ofp_result":
                return DataAdapter._convert_obm_result(data, hints)
            elif format_type == "weather_data":
                return DataAdapter._convert_weather_data(data, hints)
            elif format_type == "air_quality":
                return DataAdapter._convert_air_quality(data, hints)
            elif format_type == "chart_config":
                return DataAdapter._convert_chart_config(data, hints)
            else:
                # 未知格式，使用通用转换
                return DataAdapter._convert_generic(data, hints)

        except Exception as e:
            logger.error(
                "data_conversion_failed",
                format=format_type,
                error=str(e),
                exc_info=True
            )
            return UnifiedData(
                status=DataStatus.FAILED,
                success=False,
                error=f"数据转换失败: {str(e)}",
                data=[],
                metadata=DataMetadata(
                    data_id="conversion_failed",
                    data_type=DataType.CUSTOM
                ),
                summary=f"❌ 数据转换失败: {format_type}"
            )

    @staticmethod
    def _convert_vocs_component(data: Dict, hints: Dict) -> UnifiedData:
        """转换VOCs组分数据"""
        raw_data = data.get("data", [])
        station_name = data.get("question", "").split("站")[0] + "站" if "站" in str(data.get("question", "")) else None

        records = []
        for item in raw_data:
            if isinstance(item, dict):
                timestamp_str = item.get("time", "")
                try:
                    timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                except (ValueError, TypeError):
                    timestamp = datetime.now()

                # 提取测量值
                measurements = {}
                for key, value in item.items():
                    if key not in ["time", "station_name", "lat", "lon"] and isinstance(value, (int, float)):
                        measurements[key] = float(value)

                if measurements:
                    records.append(UnifiedDataRecord(
                        timestamp=timestamp,
                        station_name=station_name,
                        measurements=measurements
                    ))

        return create_unified_data(
            data_type=DataType.VOCs,
            records=records,
            station_name=station_name,
            source=hints.get("source", "unknown"),
            quality_score=1.0 - (len([r for r in records if not r.measurements]) / max(len(records), 1))
        )

    @staticmethod
    def _convert_pmf_result(data: Dict, hints: Dict) -> UnifiedData:
        """转换PMF分析结果"""
        # PMF结果需要特殊处理，因为格式是分析结果而非原始数据
        source_contributions = data.get("source_contributions", {})
        timeseries = data.get("timeseries", [])

        # 转换为UnifiedDataRecord
        records = []
        for point in timeseries:
            timestamp_str = point.get("time", "")
            try:
                timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                timestamp = datetime.now()

            # 提取源贡献信息
            measurements = {
                k: float(v) for k, v in point.items()
                if k != "time" and k in source_contributions.keys()
            }

            if measurements:
                records.append(UnifiedDataRecord(
                    timestamp=timestamp,
                    measurements=measurements
                ))

        # 如果没有时序数据，创建一个聚合记录
        if not records and source_contributions:
            records = [UnifiedDataRecord(
                timestamp=datetime.now(),
                measurements=source_contributions
            )]

        return UnifiedData(
            status=DataStatus.SUCCESS,
            success=data.get("success", True),
            data=records,
            metadata=DataMetadata(
                data_id=f"pmf_result:{id(data)}",
                data_type=DataType.PMF_RESULT,
                station_name=data.get("station_name"),
                quality_score=data.get("performance", {}).get("R2", 0.0),
                source=hints.get("source", "unknown")
            ),
            summary=data.get("summary", "PMF分析完成"),
            legacy_fields=data
        )

    @staticmethod
    def _convert_obm_result(data: Dict, hints: Dict) -> UnifiedData:
        """转换OBM/OFP分析结果"""
        ofp_by_species = data.get("ofp_by_species", {})
        key_species = data.get("key_species", [])

        # 转换为UnifiedDataRecord
        records = [UnifiedDataRecord(
            timestamp=datetime.now(),
            measurements=ofp_by_species
        )]

        return UnifiedData(
            status=DataStatus.SUCCESS,
            success=data.get("success", True),
            data=records,
            metadata=DataMetadata(
                data_id=f"obm_result:{id(data)}",
                data_type=DataType.OBM_RESULT,
                quality_score=0.9,
                source=hints.get("source", "unknown")
            ),
            summary=data.get("summary", "OBM/OFP分析完成"),
            validation_report={
                "key_species_count": len(key_species),
                "total_ofp": data.get("total_ofp", 0)
            },
            legacy_fields=data
        )

    @staticmethod
    def _convert_weather_data(data: Dict, hints: Dict) -> UnifiedData:
        """转换气象数据"""
        raw_records = data.get("records", [])
        station_name = data.get("station_id", data.get("location", {}).get("station_name"))

        records = []
        for item in raw_records:
            if isinstance(item, dict):
                timestamp_str = item.get("time", "")
                try:
                    timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    timestamp = datetime.now()

                # 提取气象测量值
                measurements = {
                    k: float(v) for k, v in item.items()
                    if k not in ["time", "station_id", "lat", "lon", "location", "data_source"]
                    and isinstance(v, (int, float))
                }

                lat = item.get("lat", data.get("location", {}).get("lat"))
                lon = item.get("lon", data.get("location", {}).get("lon"))

                records.append(UnifiedDataRecord(
                    timestamp=timestamp,
                    station_name=station_name,
                    lat=lat,
                    lon=lon,
                    measurements=measurements
                ))

        return create_unified_data(
            data_type=DataType.WEATHER,
            records=records,
            station_name=station_name,
            source=hints.get("source", "unknown"),
            quality_score=1.0 if data.get("has_data") else 0.0
        )

    @staticmethod
    def _convert_air_quality(data: Dict, hints: Dict) -> UnifiedData:
        """转换空气质量数据"""
        structured_data = data.get("structured_data", {})
        raw_data = data.get("data", structured_data.get("data", []))

        records = []
        for item in raw_data:
            if isinstance(item, dict):
                timestamp_str = item.get("time", "")
                try:
                    timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                except (ValueError, TypeError):
                    timestamp = datetime.now()

                # 提取空气质量测量值
                measurements = {
                    k: float(v) for k, v in item.items()
                    if k not in ["time", "station_name", "lat", "lon"]
                    and isinstance(v, (int, float))
                }

                if measurements:
                    records.append(UnifiedDataRecord(
                        timestamp=timestamp,
                        station_name=item.get("station_name"),
                        measurements=measurements
                    ))

        return create_unified_data(
            data_type=DataType.AIR_QUALITY,
            records=records,
            source=hints.get("source", "unknown"),
            quality_score=0.8
        )

    @staticmethod
    def _convert_chart_config(data: Dict, hints: Dict) -> UnifiedData:
        """转换图表配置"""
        # 图表配置是静态数据，创建一个特殊记录
        records = [UnifiedDataRecord(
            timestamp=datetime.now(),
            measurements={"chart_type": data.get("chart_type", "unknown")}
        )]

        return UnifiedData(
            status=DataStatus.SUCCESS,
            success=True,
            data=records,
            metadata=DataMetadata(
                data_id=data.get("data_id", f"chart:{id(data)}"),
                data_type=DataType.CHART_CONFIG,
                quality_score=1.0,
                source=hints.get("source", "unknown")
            ),
            summary="图表配置",
            legacy_fields=data
        )

    @staticmethod
    def _convert_generic(data: Dict, hints: Dict) -> UnifiedData:
        """通用转换（未知格式）"""
        logger.warning("using_generic_converter", data_keys=list(data.keys())[:5])

        # 尝试从数据中提取基本信息
        station_name = data.get("station_name") or data.get("question", "").split("站")[0] + "站"
        time_range = None

        if "time_range" in data:
            time_range = data["time_range"]

        return UnifiedData(
            status=DataStatus.SUCCESS if data.get("success", True) else DataStatus.FAILED,
            success=data.get("success", True),
            data=[],
            metadata=DataMetadata(
                data_id=f"generic:{id(data)}",
                data_type=DataType.CUSTOM,
                station_name=station_name,
                time_range=time_range,
                source=hints.get("source", "unknown")
            ),
            summary=data.get("summary", "通用数据"),
            legacy_fields=data
        )


# ============================================================================
# 便利函数
# ============================================================================

def auto_convert(data: Dict[str, Any]) -> UnifiedData:
    """自动检测并转换数据格式"""
    return DataAdapter.convert_to_unified(data)


def convert_with_schema(data: Dict[str, Any], schema: str) -> UnifiedData:
    """根据指定Schema转换数据"""
    return DataAdapter.convert_to_unified(data, target_schema=schema)


# ============================================================================
# 示例用法
# ============================================================================

"""
示例1: 转换VOCs数据
```python
from app.schemas.data_adapter import auto_convert

# 模拟get_component_data的输出
vocs_data = {
    "success": True,
    "data": [
        {"time": "2025-08-09 00:00:00", "乙烯": 12.5, "丙烯": 8.3, "苯": 5.2},
        {"time": "2025-08-09 01:00:00", "乙烯": 11.8, "丙烯": 7.9, "苯": 4.8}
    ],
    "registry_schema": "vocs",
    "count": 2
}

unified = auto_convert(vocs_data)
print(f"转换成功: {unified.success}")
print(f"数据记录数: {len(unified.data)}")
print(f"数据类型: {unified.metadata.data_type}")
```

示例2: 转换PMF结果
```python
# 模拟calculate_pmf的输出
pmf_data = {
    "success": True,
    "source_contributions": {
        "石油化工": 71.96,
        "燃料挥发": 14.80,
        "机动车排放": 6.22
    },
    "timeseries": [
        {"time": "2025-08-09 00:00:00", "石油化工": 75.2, "燃料挥发": 13.5, "机动车排放": 5.8}
    ],
    "summary": "PMF分析完成"
}

unified = auto_convert(pmf_data)
print(f"源解析结果: {unified.metadata.data_type}")
print(f"主要源: {list(unified.data[0].measurements.keys())[:3]}")
```
"""
