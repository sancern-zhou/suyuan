"""
空气质量数据字段规范化模块

统一处理不同API返回的字段名差异，提供标准化的字段访问接口。
"""

from typing import Any, Dict, List, Optional, Union
import structlog

logger = structlog.get_logger()


class DistrictFieldNormalizer:
    """区县数据字段规范化器"""

    # 字段映射：API字段 -> 标准字段
    FIELD_MAPPING = {
        # 区县信息
        "districtName": "district",
        "district": "district",
        "area": "district",
        "name": "district",

        # 城市信息
        "cityName": "city",
        "city": "city",
        "cityCode": "city_code",

        # 污染物浓度 - PM2.5 (多种格式)
        "pM2_5": "pm25",
        "PM2.5": "pm25",  # 带点格式
        "PM2_5": "pm25",
        "pm25": "pm25",
        "pM2_5_Decimal": "pm25",  # 高精度格式（用于同比）
        "PM2_5_Decimal": "pm25",

        # 污染物浓度 - PM10
        "pM10": "pm10",
        "PM10": "pm10",
        "pm10": "pm10",
        "pM10_Decimal": "pm10",  # 高精度格式
        "PM10_Decimal": "pm10",

        # 污染物浓度 - NO2
        "nO2": "no2",
        "NO2": "no2",
        "no2": "no2",
        "nO2_Decimal": "no2",  # 高精度格式
        "NO2_Decimal": "no2",

        # 污染物浓度 - NOx
        "nOx": "nox",
        "NOx": "nox",

        # 污染物浓度 - NO
        "nO": "no",
        "NO": "no",

        # 污染物浓度 - O3
        "o3_8h": "o3",
        "O3-8h": "o3",
        "O3": "o3",
        "o3": "o3",

        # 污染物浓度 - AQI
        "AQI": "aqi",
        "aqi": "aqi",
        "AQI_Decimal": "aqi",  # 高精度格式

        # 污染物浓度 - CO
        "CO": "co",
        "co": "co",
        "cO_Decimal": "co",  # 高精度格式
        "CO_Decimal": "co",

        # 污染物浓度 - SO2
        "sO2": "so2",
        "SO2": "so2",
        "so2": "so2",
        "sO2_Decimal": "so2",  # 高精度格式
        "SO2_Decimal": "so2",
    }

    @classmethod
    def normalize_record(cls, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        规范化单条区县记录

        Args:
            record: API返回的原始记录

        Returns:
            规范化后的记录
        """
        normalized = {}

        for api_field, value in record.items():
            # 跳过None值和"—"
            if value is None or value == "" or value == "—":
                continue

            # 查找标准字段名
            standard_field = cls.FIELD_MAPPING.get(api_field)
            if not standard_field:
                # 保留未映射的字段（以防需要调试）
                continue

            # 转换数值
            if standard_field in ["pm25", "pm10", "no2", "o3", "aqi", "co", "so2"]:
                normalized[standard_field] = cls._safe_float(value)
            else:
                normalized[standard_field] = value

        return normalized

    @classmethod
    def _safe_float(cls, value: Any) -> Optional[float]:
        """安全转换为浮点数"""
        if value is None or value == "" or value == "—":
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            logger.warning("field_convert_failed", field=value, error="cannot_convert_to_float")
            return None

    @classmethod
    def extract_district(cls, record: Dict[str, Any]) -> Optional[str]:
        """提取区县名称"""
        for field in ["districtName", "district", "area", "name"]:
            value = record.get(field)
            if value:
                return str(value).strip()
        return None

    @classmethod
    def extract_city(cls, record: Dict[str, Any]) -> str:
        """提取城市名称"""
        for field in ["cityName", "city", "cityCode"]:
            value = record.get(field)
            if value:
                return str(value).strip()
        return ""


class StationFieldNormalizer:
    """站点数据字段规范化器"""

    # 字段映射：API字段 -> 标准字段
    FIELD_MAPPING = {
        # 站点信息
        "站点": "station",
        "stationName": "station",
        "StationName": "station",
        "station": "station",
        "name": "station",
        "站点编码": "station_code",
        "stationCode": "station_code",

        # 城市信息
        "城市编码": "city_code",
        "cityCode": "city_code",
        "cityName": "city",
        "city": "city",

        # 污染物浓度 - PM2.5 (多种格式)
        "PM2.5": "pm25",  # 带点格式
        "PM2_5": "pm25",  # 带下划线格式
        "pM2_5": "pm25",  # 混合大小写
        "pm25": "pm25",
        "pM2_5_Decimal": "pm25",  # 高精度格式（用于同比）
        "PM2_5_Decimal": "pm25",

        # 污染物浓度 - PM10
        "PM10": "pm10",
        "pM10": "pm10",
        "pm10": "pm10",
        "pM10_Decimal": "pm10",  # 高精度格式
        "PM10_Decimal": "pm10",

        # 污染物浓度 - NO2
        "NO2": "no2",
        "nO2": "no2",
        "no2": "no2",
        "nO2_Decimal": "no2",  # 高精度格式
        "NO2_Decimal": "no2",

        # 污染物浓度 - NOx
        "NOx": "nox",
        "nOx": "nox",

        # 污染物浓度 - NO
        "NO": "no",

        # 污染物浓度 - O3
        "O3-8h": "o3",
        "O3": "o3",
        "o3_8h": "o3",
        "o3": "o3",

        # 污染物浓度 - AQI
        "AQI": "aqi",
        "aqi": "aqi",
        "AQI_Decimal": "aqi",  # 高精度格式

        # 污染物浓度 - CO
        "CO": "co",
        "co": "co",
        "cO_Decimal": "co",  # 高精度格式
        "CO_Decimal": "co",

        # 污染物浓度 - SO2
        "SO2": "so2",
        "sO2": "so2",
        "so2": "so2",
        "sO2_Decimal": "so2",  # 高精度格式
        "SO2_Decimal": "so2",
    }

    @classmethod
    def normalize_record(cls, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        规范化单条站点记录

        Args:
            record: API返回的原始记录

        Returns:
            规范化后的记录
        """
        normalized = {}

        for api_field, value in record.items():
            # 跳过None值和"—"
            if value is None or value == "" or value == "—":
                continue

            # 查找标准字段名
            standard_field = cls.FIELD_MAPPING.get(api_field)
            if not standard_field:
                # 保留未映射的字段（以防需要调试）
                continue

            # 转换数值
            if standard_field in ["pm25", "pm10", "no2", "o3", "aqi", "co", "so2"]:
                normalized[standard_field] = cls._safe_float(value)
            else:
                normalized[standard_field] = value

        return normalized

    @classmethod
    def _safe_float(cls, value: Any) -> Optional[float]:
        """安全转换为浮点数"""
        if value is None or value == "" or value == "—":
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            logger.warning("field_convert_failed", field=value, error="cannot_convert_to_float")
            return None

    @classmethod
    def extract_station(cls, record: Dict[str, Any]) -> Optional[str]:
        """提取站点名称"""
        for field in ["站点", "stationName", "StationName", "station", "name"]:
            value = record.get(field)
            if value:
                return str(value).strip()
        return None

    @classmethod
    def extract_city(cls, record: Dict[str, Any]) -> str:
        """提取城市信息"""
        for field in ["城市编码", "cityCode", "cityName", "city"]:
            value = record.get(field)
            if value:
                return str(value).strip()
        return ""


class CityDayFieldNormalizer:
    """城市日报数据字段规范化器"""

    # 字段映射：API字段 -> 标准字段
    FIELD_MAPPING = {
        # 日期信息
        "timePoint": "date",
        "time": "date",
        "date": "date",
        "day": "date",

        # 城市信息
        "cityName": "city",
        "city": "city",

        # 污染物浓度 - PM2.5 (多种格式)
        "pM2_5": "pm25",
        "PM2.5": "pm25",  # 带点格式
        "pm25": "pm25",
        "pM2_5_Decimal": "pm25",  # 高精度格式（用于同比）
        "PM2_5_Decimal": "pm25",

        # 污染物浓度 - PM10
        "pM10": "pm10",
        "PM10": "pm10",
        "pm10": "pm10",
        "pM10_Decimal": "pm10",  # 高精度格式
        "PM10_Decimal": "pm10",

        # 污染物浓度 - NO2
        "nO2": "no2",
        "NO2": "no2",
        "no2": "no2",
        "nO2_Decimal": "no2",  # 高精度格式
        "NO2_Decimal": "no2",

        # 污染物浓度 - O3
        "o3_8h": "o3",
        "O3-8h": "o3",
        "O3": "o3",
        "o3": "o3",

        # 污染物浓度 - AQI (关键字段)
        "AQI": "aqi",
        "aqi": "aqi",
        "AQI_Decimal": "aqi",  # 高精度格式

        # 首要污染物
        "primaryPollutant": "primary_pollutant",
        "primary": "primary_pollutant",
        "primaryPollutant": "primary_pollutant",
        "首要污染物": "primary_pollutant",  # 中文格式
    }

    @classmethod
    def normalize_record(cls, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        规范化单条城市日报记录

        Args:
            record: API返回的原始记录

        Returns:
            规范化后的记录
        """
        normalized = {}

        for api_field, value in record.items():
            # 跳过None值和"—"
            if value is None or value == "" or value == "—":
                continue

            # 查找标准字段名
            standard_field = cls.FIELD_MAPPING.get(api_field)
            if not standard_field:
                continue

            # 转换数值
            if standard_field in ["pm25", "pm10", "no2", "o3", "aqi"]:
                normalized[standard_field] = cls._safe_float(value)
            else:
                normalized[standard_field] = str(value).strip() if value else None

        return normalized

    @classmethod
    def _safe_float(cls, value: Any) -> Optional[float]:
        """安全转换为浮点数"""
        if value is None or value == "" or value == "—":
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            logger.warning("field_convert_failed", field=value, error="cannot_convert_to_float")
            return None

    @classmethod
    def extract_date(cls, record: Dict[str, Any]) -> Optional[str]:
        """提取日期"""
        for field in ["timePoint", "time", "date", "day"]:
            value = record.get(field)
            if value:
                date_str = str(value).strip()
                # 处理日期范围 "2026-05-01~ 2026-05-31"
                if "~" in date_str:
                    date_str = date_str.split("~")[0].strip()
                return date_str
        return None

    @classmethod
    def extract_city(cls, record: Dict[str, Any]) -> str:
        """提取城市名称"""
        for field in ["cityName", "city"]:
            value = record.get(field)
            if value:
                return str(value).strip()
        return ""

    @classmethod
    def extract_aqi(cls, record: Dict[str, Any]) -> Optional[float]:
        """提取AQI值"""
        for field in ["AQI", "aqi"]:
            value = record.get(field)
            if value is not None:
                return cls._safe_float(value)
        return None
