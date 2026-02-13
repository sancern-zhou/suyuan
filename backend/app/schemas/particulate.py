from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, Field

from .common import Unit


class ParticulateSample(BaseModel):
    """Standardized particulate component record."""

    station_code: str = Field(..., alias="stationCode")
    station_name: str = Field(..., alias="stationName")
    timestamp: datetime = Field(..., alias="time")
    unit: Unit = Field(default=Unit.UG_M3)
    components: Dict[str, float] = Field(
        ...,
        description="Component concentration map (SO4, NO3, NH4, OC, EC ...).",
    )
    qc_flag: Optional[str] = None
    metadata: Optional[Dict[str, str]] = None

    class Config:
        populate_by_name = True


class UnifiedParticulateData(BaseModel):
    """Unified particulate data format for global converter output.

    数据已在DataStandardizer.standardize()中完成标准化（组分聚合到components）。
    如果数据中组分作为顶层字段，验证器会自动将其聚合到components字典中。
    """
    station_code: str = Field(..., description="Station code (e.g., ZX001)")
    station_name: str = Field(..., description="Station name (e.g., 肇庆莲花山)")
    timestamp: str = Field(
        ...,
        description="Timestamp in YYYY-MM-DD HH:MM:SS format"
    )
    unit: str = Field(
        default="ug/m3",
        description="Concentration unit (e.g., ug/m3)"
    )
    components: Dict[str, float] = Field(
        default_factory=dict,
        description="Component concentration map (SO4, NO3, NH4, OC, EC, calcium, potassium ...)"
    )
    PM2_5: Optional[float] = Field(
        default=None,
        description="PM2.5 concentration (μg/m³)"
    )
    qc_flag: Optional[str] = Field(
        default=None,
        description="Quality control flag"
    )
    metadata: Optional[Dict[str, str]] = Field(
        default=None,
        description="Additional metadata such as instrument, remark"
    )

    @classmethod
    def from_raw_data(cls, data: dict):
        """从原始数据创建模型，自动处理组件字段聚合

        如果原始数据中组件作为顶层字段（如 '铝': 1.949），
        自动将其聚合到 components 字典中。
        """
        # 已知的非组件字段
        known_fields = {
            'station_code', 'station_name', 'timestamp', 'unit',
            'qc_flag', 'metadata', 'stationCode', 'stationName',
            'time', 'quality', 'data_time', 'mtime', 'record_id',
            'PM2_5', 'PM2.5', 'PM₂.₅', 'pm25'  # PM2.5 字段变体
        }

        # 提取组件数据
        components = {}
        remaining = {}
        for key, value in data.items():
            if key in known_fields:
                remaining[key] = value
            elif isinstance(value, (int, float)):
                components[key] = float(value)
            else:
                remaining[key] = value

        # 合并数据
        if 'components' not in remaining and components:
            remaining['components'] = components

        # 【新增】碳组分字段标准化：将 elemental_carbon → EC, organic_carbon → OC
        # 便于分析工具直接使用简短字段名
        if 'components' in remaining:
            carbon_field_mapping = {
                "elemental_carbon": "EC",
                "organic_carbon": "OC"
            }
            for old_key, new_key in carbon_field_mapping.items():
                if old_key in remaining['components']:
                    remaining['components'][new_key] = remaining['components'].pop(old_key)

        return cls(**remaining)

    class Config:
        populate_by_name = True
        use_enum_values = True
