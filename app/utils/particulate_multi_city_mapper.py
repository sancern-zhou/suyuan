"""
颗粒物多站点城市映射器

支持一个城市对应多个站点，用于并发查询
数据源：particulate_city_multi_station_mapping.json
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
import structlog

logger = structlog.get_logger()


class ParticulateMultiCityMapper:
    """颗粒物多站点城市映射器（单例模式）"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.city_to_stations: Dict[str, List[str]] = {}  # 城市 → 站点列表
        self._load_mappings()
        self._initialized = True

    def _load_mappings(self):
        """加载城市→多站点映射配置"""
        config_file = Path(__file__).parent.parent / "config" / "particulate_city_multi_station_mapping.json"

        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            mappings = data.get("mappings", {})

            for city, stations in mappings.items():
                if isinstance(stations, list):
                    self.city_to_stations[city] = stations

            logger.info(
                "particulate_multi_city_mapper_loaded",
                cities_count=len(self.city_to_stations),
                config_version=data.get("version", "unknown"),
                source=data.get("source", "unknown")
            )

        except Exception as e:
            logger.error(
                "particulate_multi_city_mapper_load_failed",
                error=str(e),
                exc_info=True
            )

    def city_to_station_list(self, city_name: str) -> List[str]:
        """
        城市名映射到站点列表（支持多站点）

        Args:
            city_name: 城市名称，如 "佛山"

        Returns:
            站点名称列表，如 ["综合观测点"] 或 ["公园前", "南沙科大"]

        说明:
            - 如果城市有多个站点，返回所有站点
            - 如果城市没有站点，返回空列表
        """
        return self.city_to_stations.get(city_name, [])

    def cities_to_station_lists(self, city_names: List[str]) -> Dict[str, List[str]]:
        """
        批量城市名映射到站点列表

        Args:
            city_names: 城市名称列表，如 ["佛山", "广州"]

        Returns:
            城市到站点列表的映射字典，如 {"佛山": ["综合观测点"], "广州": ["公园前", "南沙科大"]}
        """
        result = {}
        for city in city_names:
            stations = self.city_to_station_list(city)
            if stations:
                result[city] = stations
                logger.info("city_to_stations_mapped", city=city, stations=stations, count=len(stations))
            else:
                logger.warning("city_no_stations", city=city)
        return result

    def get_all_cities(self) -> List[str]:
        """获取所有已配置的城市名称"""
        return list(self.city_to_stations.keys())


# 全局单例
_particulate_multi_city_mapper_instance = None


def get_particulate_multi_city_mapper() -> ParticulateMultiCityMapper:
    """获取颗粒物多站点城市映射器单例"""
    global _particulate_multi_city_mapper_instance
    if _particulate_multi_city_mapper_instance is None:
        _particulate_multi_city_mapper_instance = ParticulateMultiCityMapper()
    return _particulate_multi_city_mapper_instance
