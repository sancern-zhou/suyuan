"""
颗粒物组分查询的城市→站点映射工具

职责：
- 将城市名称映射到该城市的代表监测站点
- 不涉及站点→编码的映射（由 geo_matcher 负责）
"""

import json
from pathlib import Path
from typing import Optional, Dict
import structlog

logger = structlog.get_logger()


class ParticulateCityMapper:
    """颗粒物组分查询的城市→站点映射器"""

    def __init__(self):
        self.city_to_station: Dict[str, str] = {}
        self._load_mappings()

    def _load_mappings(self):
        """加载城市→站点映射配置"""
        config_path = Path(__file__).parent.parent / "config" / "particulate_city_station_mapping.json"

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                self.city_to_station = config.get("mappings", {})
                logger.info(
                    "particulate_city_mapping_loaded",
                    city_count=len(self.city_to_station),
                    config_version=config.get("version", "unknown")
                )
        except FileNotFoundError:
            logger.error(
                "particulate_city_mapping_not_found",
                config_path=str(config_path)
            )
        except Exception as e:
            logger.error(
                "particulate_city_mapping_load_failed",
                error=str(e),
                config_path=str(config_path)
            )

    def city_to_station_name(self, city_name: str) -> Optional[str]:
        """
        将城市名称映射到代表站点名称

        Args:
            city_name: 城市名称（如"深圳"、"深圳市"）

        Returns:
            站点名称（如"深南中路"），如果映射失败返回 None
        """
        # 清理城市名称（去除"市"后缀）
        cleaned_city = city_name.replace("市", "").strip()

        # 1. 直接匹配
        if cleaned_city in self.city_to_station:
            station = self.city_to_station[cleaned_city]
            logger.info(
                "city_to_station_mapped",
                city=city_name,
                station=station
            )
            return station

        # 2. 尝试原始名称匹配
        if city_name in self.city_to_station:
            station = self.city_to_station[city_name]
            logger.info(
                "city_to_station_mapped",
                city=city_name,
                station=station
            )
            return station

        # 3. 映射失败
        logger.warning(
            "city_to_station_mapping_failed",
            city=city_name,
            available_cities=list(self.city_to_station.keys())[:10]
        )
        return None

    def get_available_cities(self) -> list:
        """获取所有支持的城市列表"""
        return list(self.city_to_station.keys())


# 单例模式
_particulate_city_mapper_instance = None


def get_particulate_city_mapper() -> ParticulateCityMapper:
    """获取颗粒物城市映射器单例"""
    global _particulate_city_mapper_instance
    if _particulate_city_mapper_instance is None:
        _particulate_city_mapper_instance = ParticulateCityMapper()
    return _particulate_city_mapper_instance
