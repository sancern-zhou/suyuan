"""
Observed Weather Data Tool Interface.

工具化设计原则:
1. 每个数据源独立实现
2. 统一的接口规范
3. 工具注册表管理
4. 互不干扰、可插拔
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
import structlog

logger = structlog.get_logger()


class DataQuality(Enum):
    """数据质量等级"""
    EXCELLENT = "excellent"  # 官方站点观测
    GOOD = "good"           # 可靠第三方API
    FAIR = "fair"           # 模型推算
    POOR = "poor"           # 数据可疑
    UNKNOWN = "unknown"     # 未知质量


@dataclass
class ObservedDataPoint:
    """
    标准化的观测数据点

    所有工具必须输出此格式
    """
    # 时空信息
    time: datetime
    station_id: str
    station_name: Optional[str]
    lat: float
    lon: float

    # 气象要素（可选，None表示缺失）
    temperature_2m: Optional[float] = None          # 温度 (°C)
    relative_humidity_2m: Optional[float] = None    # 相对湿度 (%)
    dew_point_2m: Optional[float] = None            # 露点 (°C)
    wind_speed_10m: Optional[float] = None          # 风速 (km/h)
    wind_direction_10m: Optional[float] = None      # 风向 (°)
    surface_pressure: Optional[float] = None        # 气压 (hPa)
    precipitation: Optional[float] = None           # 降水 (mm)
    cloud_cover: Optional[float] = None             # 云量 (%)
    visibility: Optional[float] = None              # 能见度 (m)

    # 元数据
    data_source: str = "unknown"                    # 数据来源
    data_quality: DataQuality = DataQuality.UNKNOWN # 数据质量
    raw_data: Optional[Dict[str, Any]] = None       # 原始数据（调试用）

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（用于数据库存储）"""
        return {
            "time": self.time,
            "station_id": self.station_id,
            "station_name": self.station_name,
            "lat": self.lat,
            "lon": self.lon,
            "temperature_2m": self.temperature_2m,
            "relative_humidity_2m": self.relative_humidity_2m,
            "dew_point_2m": self.dew_point_2m,
            "wind_speed_10m": self.wind_speed_10m,
            "wind_direction_10m": self.wind_direction_10m,
            "surface_pressure": self.surface_pressure,
            "precipitation": self.precipitation,
            "cloud_cover": self.cloud_cover,
            "visibility": self.visibility,
            "data_source": self.data_source,
            "data_quality": self.data_quality.value,
        }


class ObservedWeatherTool(ABC):
    """
    观测数据工具基类

    所有观测数据源必须继承此类并实现接口
    """

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.enabled = True
        self.api_key = None

    @abstractmethod
    async def fetch_current(
        self,
        lat: float,
        lon: float,
        station_id: Optional[str] = None
    ) -> Optional[ObservedDataPoint]:
        """
        获取实时观测数据

        Args:
            lat: 纬度
            lon: 经度
            station_id: 站点ID（可选）

        Returns:
            ObservedDataPoint 或 None（失败时）
        """
        pass

    @abstractmethod
    async def fetch_historical(
        self,
        lat: float,
        lon: float,
        date: str,  # YYYY-MM-DD
        station_id: Optional[str] = None
    ) -> List[ObservedDataPoint]:
        """
        获取历史观测数据（小时级）

        Args:
            lat: 纬度
            lon: 经度
            date: 日期
            station_id: 站点ID（可选）

        Returns:
            ObservedDataPoint列表（24小时）
        """
        pass

    @abstractmethod
    def get_metadata(self) -> Dict[str, Any]:
        """
        获取工具元数据

        Returns:
            {
                "name": "工具名称",
                "version": "版本",
                "api_limit": "API限额",
                "requires_key": True/False,
                "data_quality": "数据质量",
                "supported_variables": ["temp", "wind", ...],
                "coverage": "覆盖范围"
            }
        """
        pass

    def set_api_key(self, api_key: str):
        """设置API密钥"""
        self.api_key = api_key

    def enable(self):
        """启用工具"""
        self.enabled = True
        logger.info("tool_enabled", tool=self.name)

    def disable(self):
        """禁用工具"""
        self.enabled = False
        logger.info("tool_disabled", tool=self.name)

    def is_available(self) -> bool:
        """检查工具是否可用"""
        return self.enabled

    async def health_check(self) -> bool:
        """
        健康检查

        Returns:
            True if healthy, False otherwise
        """
        try:
            # 简单测试：获取一个已知位置的当前数据
            result = await self.fetch_current(23.13, 113.26)
            return result is not None
        except Exception as e:
            logger.error("tool_health_check_failed", tool=self.name, error=str(e))
            return False


class ObservedWeatherToolRegistry:
    """
    观测数据工具注册表

    管理所有观测数据源工具，支持:
    - 注册/注销工具
    - 按优先级选择工具
    - 故障转移（fallback）
    - 统计和监控
    """

    def __init__(self):
        self._tools: Dict[str, ObservedWeatherTool] = {}
        self._priority_order: List[str] = []  # 工具优先级顺序
        self._stats: Dict[str, Dict[str, int]] = {}  # 统计信息

    def register(
        self,
        tool: ObservedWeatherTool,
        priority: int = 100
    ):
        """
        注册工具

        Args:
            tool: 工具实例
            priority: 优先级（数字越小优先级越高）
        """
        self._tools[tool.name] = tool
        self._stats[tool.name] = {
            "success": 0,
            "failed": 0,
            "total": 0
        }

        # 插入到优先级列表
        self._priority_order.append(tool.name)
        self._priority_order.sort(key=lambda name: priority)

        logger.info(
            "tool_registered",
            tool=tool.name,
            priority=priority,
            total_tools=len(self._tools)
        )

    def unregister(self, tool_name: str):
        """注销工具"""
        if tool_name in self._tools:
            del self._tools[tool_name]
            self._priority_order.remove(tool_name)
            del self._stats[tool_name]
            logger.info("tool_unregistered", tool=tool_name)

    def get_tool(self, tool_name: str) -> Optional[ObservedWeatherTool]:
        """获取指定工具"""
        return self._tools.get(tool_name)

    def list_tools(self) -> List[str]:
        """列出所有已注册工具（按优先级排序）"""
        return self._priority_order.copy()

    async def fetch_current(
        self,
        lat: float,
        lon: float,
        station_id: Optional[str] = None,
        preferred_tool: Optional[str] = None
    ) -> Optional[ObservedDataPoint]:
        """
        获取实时观测数据（带故障转移）

        Args:
            lat: 纬度
            lon: 经度
            station_id: 站点ID
            preferred_tool: 优先使用的工具名称

        Returns:
            ObservedDataPoint 或 None
        """
        # 如果指定了优先工具，先尝试
        if preferred_tool and preferred_tool in self._tools:
            tool = self._tools[preferred_tool]
            if tool.is_available():
                try:
                    result = await tool.fetch_current(lat, lon, station_id)
                    if result:
                        self._record_success(preferred_tool)
                        return result
                except Exception as e:
                    logger.error(
                        "tool_fetch_failed",
                        tool=preferred_tool,
                        error=str(e)
                    )
                    self._record_failure(preferred_tool)

        # 按优先级尝试所有可用工具
        for tool_name in self._priority_order:
            tool = self._tools[tool_name]

            if not tool.is_available():
                continue

            if tool_name == preferred_tool:
                continue  # 已尝试过

            try:
                logger.info("trying_tool", tool=tool_name)
                result = await tool.fetch_current(lat, lon, station_id)

                if result:
                    self._record_success(tool_name)
                    logger.info("tool_succeeded", tool=tool_name)
                    return result

            except Exception as e:
                logger.error(
                    "tool_fetch_failed",
                    tool=tool_name,
                    error=str(e)
                )
                self._record_failure(tool_name)

        # 所有工具都失败
        logger.error("all_tools_failed", lat=lat, lon=lon)
        return None

    async def fetch_historical(
        self,
        lat: float,
        lon: float,
        date: str,
        station_id: Optional[str] = None,
        preferred_tool: Optional[str] = None
    ) -> List[ObservedDataPoint]:
        """
        获取历史观测数据（带故障转移）
        """
        # 类似 fetch_current 的逻辑
        if preferred_tool and preferred_tool in self._tools:
            tool = self._tools[preferred_tool]
            if tool.is_available():
                try:
                    result = await tool.fetch_historical(lat, lon, date, station_id)
                    if result:
                        self._record_success(preferred_tool)
                        return result
                except Exception as e:
                    logger.error(
                        "tool_fetch_historical_failed",
                        tool=preferred_tool,
                        error=str(e)
                    )
                    self._record_failure(preferred_tool)

        # 按优先级尝试其他工具
        for tool_name in self._priority_order:
            tool = self._tools[tool_name]

            if not tool.is_available() or tool_name == preferred_tool:
                continue

            try:
                logger.info("trying_tool_historical", tool=tool_name)
                result = await tool.fetch_historical(lat, lon, date, station_id)

                if result:
                    self._record_success(tool_name)
                    logger.info("tool_historical_succeeded", tool=tool_name)
                    return result

            except Exception as e:
                logger.error(
                    "tool_fetch_historical_failed",
                    tool=tool_name,
                    error=str(e)
                )
                self._record_failure(tool_name)

        logger.error("all_tools_failed_historical", lat=lat, lon=lon, date=date)
        return []

    def _record_success(self, tool_name: str):
        """记录成功"""
        if tool_name in self._stats:
            self._stats[tool_name]["success"] += 1
            self._stats[tool_name]["total"] += 1

    def _record_failure(self, tool_name: str):
        """记录失败"""
        if tool_name in self._stats:
            self._stats[tool_name]["failed"] += 1
            self._stats[tool_name]["total"] += 1

    def get_stats(self) -> Dict[str, Dict[str, int]]:
        """获取统计信息"""
        return self._stats.copy()

    def get_metadata_all(self) -> Dict[str, Dict[str, Any]]:
        """获取所有工具的元数据"""
        return {
            name: tool.get_metadata()
            for name, tool in self._tools.items()
        }


# 全局注册表实例
observed_tool_registry = ObservedWeatherToolRegistry()
