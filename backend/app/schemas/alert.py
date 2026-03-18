"""
告警相关Schema (Alert Schemas)

用于污染高值告警快速溯源API的请求和响应定义
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
import re


class AlertRequest(BaseModel):
    """污染高值告警请求"""

    city: str = Field(
        ...,
        description="城市名称",
        example="济宁市",
        min_length=2,
        max_length=20
    )

    alert_time: str = Field(
        ...,
        description="告警时间，格式: YYYY-MM-DD HH:MM:SS",
        example="2026-02-02 12:00:00"
    )

    pollutant: str = Field(
        ...,
        description="告警污染物类型",
        example="PM2.5"
    )

    alert_value: float = Field(
        ...,
        description="告警浓度值",
        example=180.5,
        gt=0
    )

    unit: str = Field(
        default="μg/m³",
        description="浓度单位",
        example="μg/m³"
    )

    @validator('alert_time')
    def validate_alert_time(cls, v):
        """验证告警时间格式"""
        pattern = r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$'
        if not re.match(pattern, v):
            raise ValueError(
                f"告警时间格式错误，正确格式为: YYYY-MM-DD HH:MM:SS，当前值: {v}"
            )

        # 验证是否为有效日期时间
        try:
            dt = datetime.strptime(v, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            raise ValueError(
                f"告警时间不是有效的日期时间: {v}"
            )

        # 可选：验证时间不能是未来时间
        # if dt > datetime.now():
        #     raise ValueError(f"告警时间不能是未来时间: {v}")

        return v

    @validator('pollutant')
    def validate_pollutant(cls, v):
        """验证污染物类型"""
        valid_pollutants = {
            "PM2.5", "PM10", "O3", "NO2", "SO2", "CO", "AQI",
            "pm2.5", "pm10", "o3", "no2", "so2", "co", "aqi"  # 大小写兼容
        }

        if v not in valid_pollutants:
            raise ValueError(
                f"不支持的污染物类型: {v}，支持的类型: {', '.join(sorted(valid_pollutants))}"
            )

        # 统一为大写格式
        return v.upper()

    @validator('city')
    def validate_city(cls, v):
        """验证城市名称"""
        if not v or not v.strip():
            raise ValueError("城市名称不能为空")

        # 去除首尾空格
        city = v.strip()

        # 可选：检查是否为支持的城市
        # supported_cities = ["济宁市"]
        # if city not in supported_cities:
        #     raise ValueError(f"暂不支持的城市: {city}，支持的城市: {', '.join(supported_cities)}")

        return city

    class Config:
        """Pydantic配置"""
        schema_extra = {
            "example": {
                "city": "济宁市",
                "alert_time": "2026-02-02 12:00:00",
                "pollutant": "PM2.5",
                "alert_value": 180.5,
                "unit": "μg/m³"
            }
        }


class AlertResponse(BaseModel):
    """快速溯源分析响应"""

    summary_text: str = Field(
        ...,
        description="Markdown格式的总结文字"
    )

    visuals: List[dict] = Field(
        default_factory=list,
        description="可视化图表列表 (轨迹图、气象图等)"
    )

    execution_time_seconds: float = Field(
        ...,
        description="执行耗时(秒)",
        gt=0
    )

    data_ids: List[str] = Field(
        default_factory=list,
        description="生成的数据ID列表"
    )

    has_trajectory: bool = Field(
        default=False,
        description="是否成功获取轨迹分析"
    )

    warning_message: Optional[str] = Field(
        default=None,
        description="警告信息 (如轨迹分析超时)"
    )

    city: str = Field(
        ...,
        description="城市名称"
    )

    alert_time: str = Field(
        ...,
        description="告警时间"
    )

    pollutant: str = Field(
        ...,
        description="告警污染物"
    )

    alert_value: float = Field(
        ...,
        description="告警浓度值"
    )

    class Config:
        """Pydantic配置"""
        schema_extra = {
            "example": {
                "summary_text": "# 济宁市污染高值快速溯源报告\n\n## 1. 污染来源轨迹分析\n...",
                "visuals": [
                    {
                        "id": "trajectory_map_001",
                        "type": "map",
                        "payload": {
                            "map_url": "https://gaode.com/..."
                        }
                    }
                ],
                "execution_time_seconds": 120.5,
                "data_ids": [
                    "weather_data:xxx",
                    "air_quality:yyy"
                ],
                "has_trajectory": True,
                "warning_message": None,
                "city": "济宁市",
                "alert_time": "2026-02-02 12:00:00",
                "pollutant": "PM2.5",
                "alert_value": 180.5
            }
        }


class HealthResponse(BaseModel):
    """健康检查响应"""

    status: str = Field(
        ...,
        description="服务状态",
        example="healthy"
    )

    service: str = Field(
        ...,
        description="服务名称",
        example="quick_trace_alert"
    )

    version: str = Field(
        ...,
        description="服务版本",
        example="1.0.0"
    )

    supported_cities: List[str] = Field(
        default_factory=lambda: ["济宁市"],
        description="支持的城市列表"
    )

    class Config:
        """Pydantic配置"""
        schema_extra = {
            "example": {
                "status": "healthy",
                "service": "quick_trace_alert",
                "version": "1.0.0",
                "supported_cities": ["济宁市"]
            }
        }
