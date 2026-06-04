"""
Centralized configuration manager for API endpoints and analysis parameters.
Allows runtime modification of configuration without restarting the service.
"""
import json
from pathlib import Path
from typing import Dict, Any, Optional
import structlog

logger = structlog.get_logger()

# Default configuration
DEFAULT_CONFIG = {
    "api_endpoints": {
        "name": "API接口配置",
        "description": "外部API接口地址配置",
        "config": {
            "station_api": {
                "name": "站点查询API",
                "url": "http://180.184.91.74:9095",
                "description": "查询站点信息、附近站点、企业数据"
            },
            "monitoring_data_api": {
                "name": "监测数据API",
                "url": "http://180.184.91.74:9091",
                "description": "查询污染物浓度监测数据"
            },
            "vocs_data_api": {
                "name": "VOCs组分数据API",
                "url": "http://180.184.91.74:9092",
                "description": "查询VOCs组分和OFP数据"
            },
            "particulate_data_api": {
                "name": "颗粒物组分数据API",
                "url": "http://180.184.91.74:9093",
                "description": "查询PM2.5/PM10组分数据"
            },
            "meteorological_api": {
                "name": "气象数据API",
                "url": "http://180.184.30.94/api/AiDataService/ReportApplication/UserReportDataQuery/Query",
                "description": "查询风速、风向、温度、湿度等气象数据",
                "api_key": "1882bb80-16a0-419a-ae3e-f442471909d3"
            },
            "upwind_analysis_api": {
                "name": "上风向分析API",
                "url": "http://180.184.91.74:9095",
                "description": "基于风向数据识别上风向企业"
            }
        }
    },

    "analysis_parameters": {
        "name": "分析参数配置",
        "description": "溯源分析流程的核心参数",
        "config": {
            "search_range_km": {
                "name": "搜索半径",
                "value": 5.0,
                "unit": "km",
                "description": "上风向企业搜索半径"
            },
            "max_enterprises": {
                "name": "最大企业数",
                "value": 30,
                "unit": "个",
                "description": "单次查询返回的最大企业数量"
            },
            "top_n_enterprises": {
                "name": "Top N企业数",
                "value": 8,
                "unit": "个",
                "description": "重点关注的Top N企业数量"
            },
            "wind_speed_low_threshold": {
                "name": "低风速阈值",
                "value": 1.5,
                "unit": "m/s",
                "description": "低于此风速视为静风或弱风"
            },
            "candidate_radius_km": {
                "name": "候选企业半径",
                "value": 25.0,
                "unit": "km",
                "description": "候选企业筛选半径"
            },
            "sector_half_angle": {
                "name": "扇区半角",
                "value": 11.25,
                "unit": "度",
                "description": "风向扇区的半角大小（22.5度扇区）"
            }
        }
    },

    "retry_configuration": {
        "name": "重试配置",
        "description": "API请求重试和超时设置",
        "config": {
            "max_retries": {
                "name": "最大重试次数",
                "value": 3,
                "unit": "次",
                "description": "API请求失败后的最大重试次数"
            },
            "retry_interval_ms": {
                "name": "重试间隔",
                "value": 100,
                "unit": "ms",
                "description": "重试之间的等待时间"
            },
            "request_timeout_seconds": {
                "name": "请求超时",
                "value": 120,
                "unit": "s",
                "description": "通用API请求超时时间"
            },
            "vocs_api_timeout_seconds": {
                "name": "VOCs API超时",
                "value": 90,
                "unit": "s",
                "description": "VOCs组分数据API专用超时时间"
            }
        }
    },

    "cache_configuration": {
        "name": "缓存配置",
        "description": "Redis缓存TTL设置",
        "config": {
            "cache_ttl_config": {
                "name": "配置缓存TTL",
                "value": 3600,
                "unit": "s",
                "description": "系统配置数据的缓存时间"
            },
            "cache_ttl_analysis": {
                "name": "分析结果缓存TTL",
                "value": 1800,
                "unit": "s",
                "description": "分析结果的缓存时间"
            },
            "cache_ttl_weather": {
                "name": "气象数据缓存TTL",
                "value": 600,
                "unit": "s",
                "description": "气象数据的缓存时间"
            }
        }
    },

    "station_query_templates": {
        "name": "站点级别查询模板",
        "description": "站点级别溯源分析的查询模板配置",
        "config": {
            "station_pollutant": {
                "name": "站点污染物查询模板",
                "value": "{station_name}站点的小时{pollutant}污染物浓度，时间为{start_time}至{end_time}",
                "description": "用于查询单个站点的污染物浓度数据（变量：station_name, pollutant, start_time, end_time）"
            },
            "station_vocs": {
                "name": "站点VOCs查询模板",
                "value": "查询{city}所有站点的OFP前十数据，时间周期为{start_time}至{end_time}，时间精度为小时",
                "description": "用于查询站点级别的VOCs组分数据（变量：city, start_time, end_time）"
            },
            "station_particulate": {
                "name": "站点颗粒物查询模板",
                "value": "查询{city}所有站点颗粒物组分重构数据，时间周期为{start_time}至{end_time}，时间精度为小时",
                "description": "用于查询站点级别的颗粒物组分数据（变量：city, start_time, end_time）"
            }
        }
    },

    "city_query_templates": {
        "name": "城市级别查询模板",
        "description": "城市级别溯源分析的查询模板配置",
        "config": {
            "city_pollutant": {
                "name": "城市污染物查询模板",
                "value": "{city}市{pollutant}小时平均浓度，时间为{start_time}至{end_time}",
                "description": "用于查询城市级别的污染物浓度数据（变量：city, pollutant, start_time, end_time）"
            },
            "city_vocs": {
                "name": "城市VOCs查询模板",
                "value": "查询{city}市的OFP前十数据，时间周期为{start_time}至{end_time}，时间精度为小时",
                "description": "用于查询城市级别的VOCs组分数据（变量：city, start_time, end_time）"
            },
            "city_particulate": {
                "name": "城市颗粒物查询模板",
                "value": "查询{city}市颗粒物组分重构数据，时间周期为{start_time}至{end_time}，时间精度为小时",
                "description": "用于查询城市级别的颗粒物组分数据（变量：city, start_time, end_time）"
            }
        }
    },

    "city_analysis_parameters": {
        "name": "城市级别分析参数",
        "description": "城市级别溯源分析的专属参数配置",
        "config": {
            "max_concurrent_stations": {
                "name": "最大并发站点数",
                "value": 5,
                "unit": "个",
                "description": "城市分析时同时处理的站点数量（Semaphore控制）"
            },
            "max_stations_display": {
                "name": "最大展示站点数",
                "value": 10,
                "unit": "个",
                "description": "综合报告中展示的最大站点数量"
            },
            "nearby_cities_count": {
                "name": "周边城市数量",
                "value": 3,
                "unit": "个",
                "description": "区域对比时获取的周边城市数量"
            },
            "max_enterprises_per_station": {
                "name": "每站点最大企业数",
                "value": 5,
                "unit": "个",
                "description": "每个站点在综合报告中展示的最大企业数量"
            }
        }
    }
}


class ConfigManager:
    """Manager for system configuration with persistence."""

    def __init__(self, config_file: str = "system_config.json"):
        self.config_file = Path(__file__).parent.parent.parent / config_file
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file, or use defaults."""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    logger.info("config_loaded", source="file", sections=len(loaded))
                    return loaded
            except Exception as e:
                logger.error("config_load_failed", error=str(e))
                return DEFAULT_CONFIG.copy()
        else:
            logger.info("config_initialized", source="defaults", sections=len(DEFAULT_CONFIG))
            return DEFAULT_CONFIG.copy()

    def save_config(self) -> bool:
        """Save current configuration to file."""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            logger.info("config_saved", file=str(self.config_file))
            return True
        except Exception as e:
            logger.error("config_save_failed", error=str(e))
            return False

    def get_all_config(self) -> Dict[str, Any]:
        """Get all configuration sections."""
        return self.config

    def get_section(self, section_name: str) -> Optional[Dict[str, Any]]:
        """Get a specific configuration section."""
        return self.config.get(section_name)

    def get_value(self, section_name: str, key: str) -> Any:
        """Get a specific configuration value."""
        section = self.get_section(section_name)
        if section and "config" in section:
            item = section["config"].get(key)
            if item and "value" in item:
                return item["value"]
            elif item and "url" in item:
                return item["url"]
        return None

    def update_value(self, section_name: str, key: str, value: Any) -> bool:
        """Update a specific configuration value."""
        if section_name not in self.config:
            return False

        section = self.config[section_name]
        if "config" not in section or key not in section["config"]:
            return False

        item = section["config"][key]
        if "value" in item:
            item["value"] = value
        elif "url" in item:
            item["url"] = value
        else:
            return False

        return self.save_config()

    def update_api_endpoint(self, api_name: str, url: str) -> bool:
        """Update an API endpoint URL."""
        return self.update_value("api_endpoints", api_name, url)

    def get_api_url(self, api_name: str) -> Optional[str]:
        """Get an API endpoint URL."""
        section = self.get_section("api_endpoints")
        if section and "config" in section:
            api = section["config"].get(api_name)
            if api and "url" in api:
                return api["url"]
        return None

    def reset_to_defaults(self) -> bool:
        """Reset all configuration to defaults."""
        self.config = DEFAULT_CONFIG.copy()
        return self.save_config()


# Global configuration manager instance
config_manager = ConfigManager()
