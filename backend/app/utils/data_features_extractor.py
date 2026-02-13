"""
数据特征提取器 - 为Agent推荐图表提供数据特征摘要

根据LLM Agent驱动架构，数据工具需要输出data_features字段，
帮助Agent准确判断应该推荐哪种图表类型。
"""
from typing import Dict, Any, List, Optional, Set
import structlog

logger = structlog.get_logger()


class DataFeaturesExtractor:
    """
    数据特征提取器

    从数据中提取关键特征，帮助Agent推荐图表类型
    """

    # 时间字段候选名称
    TIME_FIELD_CANDIDATES = [
        "timestamp", "time", "datetime", "time_point", "timePoint",
        "DataTime", "dataTime", "date", "Date", "create_time", "modify_time"
    ]

    # 空间字段候选名称
    SPATIAL_FIELD_CANDIDATES = {
        "longitude": ["longitude", "lng", "lon", "经度"],
        "latitude": ["latitude", "lat", "纬度"]
    }

    # 气象字段候选名称
    METEOROLOGY_FIELD_CANDIDATES = [
        "temperature", "temperature_2m", "气温", "温度",
        "humidity", "relative_humidity_2m", "湿度",
        "wind_speed", "wind_speed_10m", "windSpeed", "风速",
        "wind_direction", "wind_direction_10m", "windDirection", "风向",
        "pressure", "surface_pressure", "气压",
        "precipitation", "降水", "降水量",
        "cloud_cover", "云量",
        "visibility", "能见度",
        "dew_point", "dew_point_2m", "露点温度",
        "boundary_layer_height", "pbl", "边界层高度",
        "altitude", "height", "高度"
    ]

    # 污染物字段候选名称
    POLLUTANT_FIELD_CANDIDATES = [
        "PM2.5", "PM2_5", "pm2.5", "pM2_5",
        "PM10", "pm10", "pM10",
        "O3", "o3", "pO3",
        "NO2", "no2", "pNO2",
        "SO2", "so2", "pSO2",
        "CO", "co", "pCO",
        "AQI", "aqi"
    ]

    @classmethod
    def extract_features(
        cls,
        data: List[Dict[str, Any]],
        schema_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        从数据中提取特征摘要

        Args:
            data: 数据记录列表
            schema_type: 数据schema类型（可选，用于优化提取）

        Returns:
            数据特征字典：
            {
                "has_time_field": bool,
                "time_count": int,
                "time_field_name": str,
                "has_spatial_fields": bool,
                "spatial_field_names": List[str],
                "has_meteorology_fields": bool,
                "meteorology_field_names": List[str],
                "pollutant_count": int,
                "pollutant_field_names": List[str],
                "has_altitude_field": bool,
                "record_count": int,
                "field_count": int
            }
        """
        if not data:
            return cls._empty_features()

        # 获取第一条记录用于字段检测
        first_record = data[0]

        # 展平嵌套字段（如measurements）
        flattened_fields = cls._flatten_record(first_record)

        # 【调试】打印展平后的关键字段
        logger.info(
            "data_features_flattened_fields",
            schema_type=schema_type,
            field_count=len(flattened_fields),
            # 只打印前20个字段名用于调试
            sample_fields=list(flattened_fields.keys())[:20],
            # 检查是否有常见污染物字段
            has_o3="o3" in flattened_fields or "O3" in flattened_fields,
            has_pm25="PM2_5" in flattened_fields or "pm2.5" in flattened_fields or "PM2.5" in flattened_fields,
            has_measurements="measurements" in first_record
        )

        # 提取各类特征
        features = {
            "record_count": len(data),
            "field_count": len(flattened_fields),
        }

        # 1. 时间特征
        time_features = cls._extract_time_features(data, flattened_fields)
        features.update(time_features)

        # 2. 空间特征
        spatial_features = cls._extract_spatial_features(flattened_fields)
        features.update(spatial_features)

        # 3. 气象特征
        meteo_features = cls._extract_meteorology_features(flattened_fields)
        features.update(meteo_features)

        # 4. 污染物特征
        pollutant_features = cls._extract_pollutant_features(flattened_fields)
        features.update(pollutant_features)

        # 5. 特殊字段检测（如高度字段）
        features["has_altitude_field"] = cls._has_altitude_field(flattened_fields)

        logger.info(
            "data_features_extracted",
            schema_type=schema_type,
            record_count=features["record_count"],
            has_time=features["has_time_field"],
            has_spatial=features["has_spatial_fields"],
            has_meteo=features["has_meteorology_fields"],
            pollutant_count=features["pollutant_count"]
        )

        return features

    @classmethod
    def _empty_features(cls) -> Dict[str, Any]:
        """返回空数据的特征"""
        return {
            "record_count": 0,
            "field_count": 0,
            "has_time_field": False,
            "time_count": 0,
            "time_field_name": None,
            "has_spatial_fields": False,
            "spatial_field_names": [],
            "has_meteorology_fields": False,
            "meteorology_field_names": [],
            "pollutant_count": 0,
            "pollutant_field_names": [],
            "has_altitude_field": False
        }

    @classmethod
    def _flatten_record(cls, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        展平嵌套记录（如measurements字段）

        Args:
            record: 原始记录

        Returns:
            展平后的字段字典
        """
        flattened = {}

        for key, value in record.items():
            if isinstance(value, dict):
                # 嵌套字典，展平
                for nested_key, nested_value in value.items():
                    flattened[nested_key] = nested_value
            else:
                flattened[key] = value

        return flattened

    @classmethod
    def _extract_time_features(
        cls,
        data: List[Dict[str, Any]],
        flattened_fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """提取时间特征"""
        # 查找时间字段
        time_field_name = None
        for candidate in cls.TIME_FIELD_CANDIDATES:
            if candidate in flattened_fields:
                time_field_name = candidate
                break

        if not time_field_name:
            return {
                "has_time_field": False,
                "time_count": 0,
                "time_field_name": None
            }

        # 统计唯一时间点数量
        time_values = set()
        for record in data:
            flattened = cls._flatten_record(record)
            if time_field_name in flattened and flattened[time_field_name]:
                time_values.add(str(flattened[time_field_name]))

        return {
            "has_time_field": True,
            "time_count": len(time_values),
            "time_field_name": time_field_name
        }

    @classmethod
    def _extract_spatial_features(cls, flattened_fields: Dict[str, Any]) -> Dict[str, Any]:
        """提取空间特征"""
        spatial_field_names = []

        # 检查经度字段
        for candidate in cls.SPATIAL_FIELD_CANDIDATES["longitude"]:
            if candidate in flattened_fields:
                spatial_field_names.append(candidate)
                break

        # 检查纬度字段
        for candidate in cls.SPATIAL_FIELD_CANDIDATES["latitude"]:
            if candidate in flattened_fields:
                spatial_field_names.append(candidate)
                break

        return {
            "has_spatial_fields": len(spatial_field_names) >= 2,
            "spatial_field_names": spatial_field_names
        }

    @classmethod
    def _extract_meteorology_features(cls, flattened_fields: Dict[str, Any]) -> Dict[str, Any]:
        """提取气象特征"""
        meteo_field_names = []

        for candidate in cls.METEOROLOGY_FIELD_CANDIDATES:
            if candidate in flattened_fields:
                meteo_field_names.append(candidate)

        return {
            "has_meteorology_fields": len(meteo_field_names) > 0,
            "meteorology_field_names": meteo_field_names
        }

    @classmethod
    def _extract_pollutant_features(cls, flattened_fields: Dict[str, Any]) -> Dict[str, Any]:
        """提取污染物特征"""
        from app.utils.data_standardizer import get_data_standardizer
        standardizer = get_data_standardizer()

        # 标准化字段名后进行匹配
        pollutant_field_names = []
        seen_pollutants = set()  # 避免重复检测相同污染物

        # 【调试】记录标准化后的字段名映射
        std_mapping_sample = {}
        for key in list(flattened_fields.keys())[:10]:
            std_mapping_sample[key] = standardizer._get_standard_field_name(key)

        for candidate in cls.POLLUTANT_FIELD_CANDIDATES:
            # 检查原始字段名
            if candidate in flattened_fields:
                # 标准化后确定污染物种类型
                normalized = standardizer._get_standard_field_name(candidate)
                base_pollutant = normalized or candidate

                # 提取基础污染物名（如 O3_8h → O3_8h）
                if base_pollutant not in seen_pollutants:
                    pollutant_field_names.append(candidate)
                    seen_pollutants.add(base_pollutant)
                continue

            # 检查标准化后的字段名
            std_field_name = standardizer._get_standard_field_name(candidate)
            if std_field_name and std_field_name in flattened_fields:
                if std_field_name not in seen_pollutants:
                    pollutant_field_names.append(candidate)
                    seen_pollutants.add(std_field_name)

        # 如果没有检测到，尝试模糊匹配（小写转换）
        if not pollutant_field_names:
            lower_fields = {k.lower(): k for k in flattened_fields.keys()}
            for candidate in cls.POLLUTANT_FIELD_CANDIDATES:
                if candidate.lower() in lower_fields:
                    original_field = lower_fields[candidate.lower()]
                    normalized = standardizer._get_standard_field_name(original_field)
                    if normalized and normalized not in seen_pollutants:
                        pollutant_field_names.append(candidate)
                        seen_pollutants.add(normalized)

        # 【调试】记录检测结果
        logger.debug(
            "pollutant_features_extracted",
            candidate_count=len(cls.POLLUTANT_FIELD_CANDIDATES),
            detected_count=len(pollutant_field_names),
            detected_pollutants=pollutant_field_names,
            std_mapping_sample=std_mapping_sample
        )

        return {
            "pollutant_count": len(pollutant_field_names),
            "pollutant_field_names": pollutant_field_names
        }

    @classmethod
    def _has_altitude_field(cls, flattened_fields: Dict[str, Any]) -> bool:
        """检测是否包含高度字段（用于profile图表推荐）"""
        altitude_candidates = ["altitude", "height", "高度"]
        return any(candidate in flattened_fields for candidate in altitude_candidates)


# 全局提取器实例
_extractor_instance = None


def get_data_features_extractor() -> DataFeaturesExtractor:
    """获取全局数据特征提取器实例"""
    global _extractor_instance
    if _extractor_instance is None:
        _extractor_instance = DataFeaturesExtractor()
    return _extractor_instance
