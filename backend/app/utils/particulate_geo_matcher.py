"""
颗粒物组分站点地理映射器

专门用于 PM2.5 组分查询工具（get_pm25_ionic, get_pm25_carbon, get_pm25_crustal）

数据源：
- geo_mappings.json 的 stations 字段（包含组分站点编码）

与 GeoMatcher 的区别：
- GeoMatcher: 用于常规空气质量/气象站点，数据源是 station_district_results_with_type_id.json
- ParticulateGeoMatcher: 专门用于组分站点，数据源是 geo_mappings.json
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any
import structlog

logger = structlog.get_logger()


class ParticulateGeoMatcher:
    """颗粒物组分站点地理映射器（单例模式）"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # 核心数据结构
        self.station_codes: Dict[str, str] = {}  # 站点名称 -> 编码
        self.station_names: List[str] = []  # 站点名称列表（用于模糊匹配）

        self._load_data()
        self._initialized = True

    def _load_data(self):
        """从 geo_mappings.json 加载组分站点数据"""
        config_file = Path(__file__).parent.parent / "config" / "geo_mappings.json"

        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 只加载 stations 字段
            stations = data.get("stations", {})

            for station_name, station_code in stations.items():
                self.station_codes[station_name] = station_code
                self.station_names.append(station_name)

            # 按名称长度降序排序（优先匹配更具体的名称）
            self.station_names.sort(key=len, reverse=True)

            logger.info(
                "particulate_geo_matcher_initialized",
                stations_count=len(self.station_codes),
                sample_stations=list(self.station_codes.keys())[:10]
            )

        except Exception as e:
            logger.error(
                "particulate_geo_matcher_load_failed",
                error=str(e),
                exc_info=True
            )

    def stations_to_codes(self, names: List[str]) -> List[str]:
        """
        站点名称映射到编码（只支持精确匹配）

        Args:
            names: 站点名称列表，如 ["公园前", "东城"]

        Returns:
            站点编码列表，如 ["1006b", "1037b"]

        Raises:
            ValueError: 如果站点名称不存在
        """
        codes = []
        for name in names:
            if name in self.station_codes:
                codes.append(self.station_codes[name])
            else:
                raise ValueError(
                    f"组分站点 '{name}' 不在组分站点映射表中。"
                    f"可用站点: {', '.join(list(self.station_codes.keys())[:20])}..."
                )
        return codes

    def find_station_by_substring(self, query: str) -> Optional[str]:
        """
        通过子串匹配查找站点名称

        Args:
            query: 查询字符串（如"公园"、"观测"）

        Returns:
            匹配的站点名称，如果没找到返回 None
        """
        # 直接匹配
        if query in self.station_codes:
            return query

        # 子串匹配（优先匹配长名称）
        for station_name in self.station_names:
            if query in station_name or station_name in query:
                return station_name

        return None

    def get_all_station_names(self) -> List[str]:
        """获取所有组分站点名称"""
        return list(self.station_codes.keys())


# 全局单例
_particulate_geo_matcher_instance = None


def get_particulate_geo_matcher() -> ParticulateGeoMatcher:
    """获取颗粒物组分站点地理映射器单例"""
    global _particulate_geo_matcher_instance
    if _particulate_geo_matcher_instance is None:
        _particulate_geo_matcher_instance = ParticulateGeoMatcher()
    return _particulate_geo_matcher_instance
