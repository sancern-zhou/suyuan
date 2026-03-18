"""
字段映射字典 - 集中管理所有数据字段映射

本模块统一管理系统中所有工具的字段映射逻辑，确保数据字段的一致性。

版本历史：
- v1.0: 初始版本，整合PMF、OBM、图表转换器等工具的字段映射
- v2.0: 分层架构重构，将静态配置与动态逻辑分离
"""

from typing import Dict, List, Optional, Any, Union


class FieldMappings:
    """
    字段映射管理器

    提供统一的字段映射接口，支持：
    - 污染物浓度字段映射
    - IAQI指数字段映射
    - 空气质量状态字段映射
    - 地理层级字段映射
    - 气象字段映射
    - 系统字段映射
    - VOCs相关字段映射
    - PMF/OBM结果字段映射

    架构设计：
    - 配置区域：静态字段映射定义
    - 解析器区域：动态字段解析逻辑
    - 工具方法区域：辅助方法
    """

    # ============================================
    # ========== 配置区域（静态）==========
    # ============================================

    # 1. 污染物浓度字段映射
    # 支持所有常见的PM2.5字段命名变体
    PM25_MAPPINGS = [
        "PM2.5", "pM2_5", "pM2.5", "pm2_5", "pm2.5", "PM25",
        "PM2_5", "PM2.5_Concentration", "PM2_5_Concentration",
        "细颗粒物", "PM2.5浓度",  # 中文字段支持
        "细颗粒物(PM2.5)", "PM2.5(细颗粒物)"  # 新增：带括号格式
    ]

    # PM10字段映映射
    PM10_MAPPINGS = [
        "PM10", "pM10", "pm10", "PM10_Concentration", "PM10_Concentration",
        "可吸入颗粒物", "PM10浓度",  # 中文字段支持
        "可吸入颗粒物(PM10)", "PM10(可吸入颗粒物)"  # 新增：带括号格式
    ]

    # O3字段映射（臭氧瞬时值）
    O3_MAPPINGS = [
        "O3", "o3", "pO3", "O3_Concentration", "O3_Concentration",
        "臭氧", "臭氧(O₃)", "臭氧(O3)", "ozone"  # 中文字段支持
    ]

    # O3_8H字段映射（8小时臭氧平均值）
    O3_8H_MAPPINGS = [
        "O3_8H", "o3_8h", "pO3_8H", "O3_8H_Concentration", "O3_8H_Concentration",
        "O3_8h", "O3_8h_Concentration",
        "8小时臭氧", "臭氧8小时", "O3_8小时", "O3_8h_avg"  # 中文字段支持
    ]

    # NO2字段映射
    NO2_MAPPINGS = [
        "NO2", "nO2", "pNO2", "no2", "NO2_Concentration", "NO2_Concentration",
        "二氧化氮", "nitrogen_dioxide",  # 中文字段支持
        "二氧化氮(NO2)", "NO2(二氧化氮)"  # 新增：带括号格式
    ]

    # SO2字段映射
    SO2_MAPPINGS = [
        "SO2", "sO2", "pSO2", "so2", "SO2_Concentration", "SO2_Concentration",
        "二氧化硫", "sulfur_dioxide",  # 中文字段支持
        "二氧化硫(SO2)", "SO2(二氧化硫)"  # 新增：带括号格式
    ]

    # CO字段映射
    CO_MAPPINGS = [
        "CO", "co", "pCO", "CO_Concentration", "CO_Concentration",
        "一氧化碳", "carbon_monoxide",  # 中文字段支持
        "一氧化碳(CO)", "CO(一氧化碳)"  # 新增：带括号格式
    ]

    # 合并所有污染物浓度字段
    POLLUTANT_CONCENTRATION_MAPPINGS = {
        "PM2.5": PM25_MAPPINGS,
        "PM10": PM10_MAPPINGS,
        "O3": O3_MAPPINGS,        # 臭氧瞬时值
        "O3_8H": O3_8H_MAPPINGS,  # 8小时臭氧平均值（独立指标）
        "NO2": NO2_MAPPINGS,
        "SO2": SO2_MAPPINGS,
        "CO": CO_MAPPINGS
    }

    # 2. IAQI指数字段映射
    AQI_INDEX_MAPPINGS = {
        "SO2_IAQI": ["sO2_IAQI", "SO2_IAQI"],
        "NO2_IAQI": ["nO2_IAQI", "NO2_IAQI"],
        "PM10_IAQI": ["pM10_IAQI", "PM10_IAQI"],
        "CO_IAQI": ["cO_IAQI", "CO_IAQI"],
        "O3_IAQI": ["o3_IAQI", "O3_IAQI"],
        "PM2.5_IAQI": ["pM2_5_IAQI", "PM2.5_IAQI"]
    }

    # 3. 空气质量状态字段映射
    AIR_QUALITY_STATUS_MAPPINGS = {
        "AQI": ["aqi", "AQI", "IAQI", "空气质量指数"],  # 添加中文支持
        "quality_type": ["quality_type", "qualityType", "quality", "AQ_Level", "质量等级", "空气质量"],
        "primary_pollutant": ["primary_pollutant", "primaryPollutant", "Primary_Pollutant", "首要污染物"]
    }

    # 4. 地理层级字段映射
    GEOGRAPHIC_MAPPINGS = {
        "city_code": ["cityCode", "city_code", "CityCode"],
        "city_name": ["cityName", "city_name", "CityName"],
        "district_code": ["districtCode", "district_code", "DistrictCode"],
        "district_name": ["districtName", "district_name", "DistrictName"],
        "station_code": ["stationCode", "station_code", "StationCode", "Code"],
        "unique_code": ["uniqueCode", "unique_code", "UniqueCode"],
        "station_name": ["stationName", "station_name", "StationName", "name", "Name"],
        "display_name": ["displayName", "display_name", "DisplayName"],
        "geo_level": ["geo_level", "geoLevel", "Geo_Level", "level", "Level"]
    }

    # 5. 气象字段映射
    METEOROLOGICAL_MAPPINGS = {
        "temperature": ["temperature", "temp", "气温", "Temperature"],
        "humidity": ["humidity", "rh", "湿度", "Humidity"],
        "windSpeed": ["windSpeed", "ws", "wind_speed", "风速", "WindSpeed", "Wind_Speed"],
        "windDirection": ["windDirection", "wd", "wind_direction", "风向", "WindDirection", "Wind_Direction"],
        "pressure": ["pressure", "press", "p", "气压", "Pressure"],
        "rainFall": ["rainFall", "rainfall", "降水", "RainFall"],
        "visibility": ["visibility", "能见度", "Visibility"],
        "precipitation": ["precipitation", "降水量", "Precipitation"]
    }

    # 6. 系统字段映射
    SYSTEM_MAPPINGS = {
        "create_time": ["createTime", "create_time", "CreateTime", "Create_Time"],
        "modify_time": ["modifyTime", "modify_time", "ModifyTime", "Modify_Time"],
        "data_type": ["dataType", "data_type", "DataType", "Data_Type"],
        "record_id": ["id", "record_id", "RecordId", "Record_Id"],
        "timestamp": ["timestamp", "time_point", "timePoint", "time", "TimePoint", "datetime", "DataTime", "时间点", "时间"]
    }

    # 7. VOCs相关字段映射
    VOCS_MAPPINGS = {
        # VOCs物种浓度
        "species_data": ["species_data", "SpeciesData", "species", "Species", "components", "Components"],
        "station_code": GEOGRAPHIC_MAPPINGS["station_code"],
        "station_name": GEOGRAPHIC_MAPPINGS["station_name"],
        "timestamp": SYSTEM_MAPPINGS["timestamp"],

        # VOCs分析结果
        "source_contributions": ["source_contributions", "SourceContributions", "source_contribution"],
        "source_name": ["source_name", "SourceName", "source"],
        "contribution_pct": ["contribution_pct", "ContributionPct", "contribution", "percentage"],
        "concentration": ["concentration", "Concentration", "conc"],
        "confidence": ["confidence", "Confidence", "conf"]
    }

    # 8. PMF/OBM结果字段映射
    PMF_OBM_MAPPINGS = {
        # PMF结果
        "sources": ["sources", "Sources", "source_list"],
        "timeseries": ["timeseries", "TimeSeries", "time_series"],
        "source_values": ["source_values", "SourceValues", "source_data"],
        "performance": ["performance", "Performance", "model_performance"],
        "R2": ["R2", "r2", "R_Squared"],

        # OBM/OFP结果
        "category_summary": ["category_summary", "CategorySummary", "categories"],
        "total_ofp": ["total_ofp", "TotalOFP", "total_ofp_value"],
        "species_ofp": ["species_ofp", "SpeciesOFP", "ofp_data"],
        "ofp": ["ofp", "OFP"],
        "primary_vocs": ["primary_vocs", "PrimaryVOCs", "primary_voc"],
        "sensitivity": ["sensitivity", "Sensitivity", "sensitivity_analysis"],
        "vocs_control_effectiveness": ["vocs_control_effectiveness", "VOCsControl", "voc_control"],
        "nox_control_effectiveness": ["nox_control_effectiveness", "NOxControl", "nox_control"],
        "sensitivity_type": ["sensitivity_type", "SensitivityType", "sensitivity_class"],
        "recommendation": ["recommendation", "Recommendation", "suggestion"]
    }

    # ============================================
    # ========== 解析器区域（动态）==========
    # ============================================

    @classmethod
    def get_pollutant_mappings(cls) -> Dict[str, List[str]]:
        """获取污染物浓度字段映射"""
        return cls.POLLUTANT_CONCENTRATION_MAPPINGS.copy()

    @classmethod
    def get_aqi_mappings(cls) -> Dict[str, List[str]]:
        """获取IAQI指数字段映射"""
        return cls.AQI_INDEX_MAPPINGS.copy()

    @classmethod
    def get_air_quality_status_mappings(cls) -> Dict[str, List[str]]:
        """获取空气质量状态字段映射"""
        return cls.AIR_QUALITY_STATUS_MAPPINGS.copy()

    @classmethod
    def get_geographic_mappings(cls) -> Dict[str, List[str]]:
        """获取地理层级字段映射"""
        return cls.GEOGRAPHIC_MAPPINGS.copy()

    @classmethod
    def get_meteorological_mappings(cls) -> Dict[str, List[str]]:
        """获取气象字段映射"""
        return cls.METEOROLOGICAL_MAPPINGS.copy()

    @classmethod
    def get_system_mappings(cls) -> Dict[str, List[str]]:
        """获取系统字段映射"""
        return cls.SYSTEM_MAPPINGS.copy()

    @classmethod
    def get_vocs_mappings(cls) -> Dict[str, List[str]]:
        """获取VOCs字段映射"""
        return cls.VOCS_MAPPINGS.copy()

    @classmethod
    def get_pmf_obm_mappings(cls) -> Dict[str, List[str]]:
        """获取PMF/OBM字段映射"""
        return cls.PMF_OBM_MAPPINGS.copy()

    @classmethod
    def get_all_mappings(cls) -> Dict[str, List[str]]:
        """获取所有字段映射的合并字典"""
        all_mappings = {}
        all_mappings.update(cls.POLLUTANT_CONCENTRATION_MAPPINGS)
        all_mappings.update(cls.AQI_INDEX_MAPPINGS)
        all_mappings.update(cls.AIR_QUALITY_STATUS_MAPPINGS)
        all_mappings.update(cls.GEOGRAPHIC_MAPPINGS)
        all_mappings.update(cls.METEOROLOGICAL_MAPPINGS)
        all_mappings.update(cls.SYSTEM_MAPPINGS)
        all_mappings.update(cls.VOCS_MAPPINGS)
        all_mappings.update(cls.PMF_OBM_MAPPINGS)
        return all_mappings

    @classmethod
    def find_field_value(
        cls,
        record: Dict[str, Any],
        field_key: str,
        mappings: Optional[Dict[str, List[str]]] = None
    ) -> Optional[Any]:
        """
        根据字段键在记录中查找值（大小写不敏感）

        解析流程：
        1. 直接查找字段键
        2. 在映射中查找字段键的所有变体
        3. 返回第一个找到的非None值

        Args:
            record: 数据记录字典
            field_key: 字段键（如"PM2.5"）
            mappings: 可选的映射字典，如果未提供则使用所有映射

        Returns:
            字段值，如果未找到则返回None
        """
        if mappings is None:
            mappings = cls.get_all_mappings()

        # Step 1: 直接查找字段键
        if field_key in record and record[field_key] is not None:
            return record[field_key]

        # Step 2: 在映射中查找字段键
        if field_key in mappings:
            for variant in mappings[field_key]:
                if variant in record and record[variant] is not None:
                    return record[variant]

        return None

    @classmethod
    def extract_measurements(
        cls,
        record: Dict[str, Any],
        measurement_type: str = "all"
    ) -> Dict[str, Any]:
        """
        从记录中提取测量值（支持多种类型）

        解析流程：
        1. 根据测量类型选择对应的映射
        2. 对每个字段使用find_field_value查找
        3. 过滤掉None值
        4. 组织成结构化的结果

        Args:
            record: 数据记录字典
            measurement_type: 测量类型（"pollutant", "aqi", "status", "meteo", "all"）

        Returns:
            提取的测量值字典
        """
        measurements = {}

        # 1. 提取污染物浓度
        if measurement_type in ["pollutant", "all"]:
            for pollutant, variants in cls.POLLUTANT_CONCENTRATION_MAPPINGS.items():
                value = cls.find_field_value(record, pollutant)
                normalized_value = cls._normalize_value(value)
                if normalized_value is not None:
                    measurements[pollutant] = normalized_value

        # 2. 提取IAQI指数
        if measurement_type in ["aqi", "all"]:
            aqi_data = {}
            for index, variants in cls.AQI_INDEX_MAPPINGS.items():
                value = cls.find_field_value(record, index)
                normalized_value = cls._normalize_value(value)
                if normalized_value is not None:
                    aqi_data[index] = normalized_value
            if aqi_data:
                measurements["aqi_indices"] = aqi_data

        # 3. 提取空气质量状态
        if measurement_type in ["status", "all"]:
            status_data = {}
            for status, variants in cls.AIR_QUALITY_STATUS_MAPPINGS.items():
                value = cls.find_field_value(record, status)
                if value is not None and value not in ["—", "--", ""]:
                    status_data[status] = value
            if status_data:
                measurements["air_quality_status"] = status_data

        # 4. 提取气象数据
        if measurement_type in ["meteo", "all"]:
            meteo_data = {}
            for meteo, variants in cls.METEOROLOGICAL_MAPPINGS.items():
                value = cls.find_field_value(record, meteo)
                normalized_value = cls._normalize_value(value)
                if normalized_value is not None:
                    meteo_data[meteo] = normalized_value
            if meteo_data:
                measurements["meteorological_data"] = meteo_data

        return measurements

    @classmethod
    def extract_geographic_info(cls, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        从记录中提取地理信息

        解析流程：
        1. 对每个地理字段使用find_field_value查找
        2. 过滤掉None值
        3. 返回结构化的地理信息

        Args:
            record: 数据记录字典

        Returns:
            地理信息字典
        """
        geo_info = {}
        for geo_key, variants in cls.GEOGRAPHIC_MAPPINGS.items():
            value = cls.find_field_value(record, geo_key)
            if value is not None:
                geo_info[geo_key] = value
        return geo_info

    @classmethod
    def extract_station_info(cls, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        提取站点信息（智能判断地理层级）

        解析流程：
        1. 提取基本地理信息（站点名、城市名等）
        2. 智能判断地理层级（站点/城市/未知）
        3. 返回结构化的站点信息

        Args:
            record: 数据记录字典

        Returns:
            站点信息字典
        """
        # Step 1: 提取基本地理信息
        station_name = cls.find_field_value(record, "station_name")
        city_name = cls.find_field_value(record, "city_name")
        unique_code = cls.find_field_value(record, "unique_code")
        district_name = cls.find_field_value(record, "district_name")

        # Step 2: 智能判断地理层级
        geo_level = "unknown"
        if unique_code:
            # 有唯一编码 → 站点层级
            geo_level = "station"
        elif city_name and station_name:
            # 有城市和站点名
            if station_name == city_name:
                # 站点名等于城市名 → 城市层级
                geo_level = "city"
            else:
                # 站点名不等于城市名 → 站点层级
                geo_level = "station"
        elif city_name:
            # 只有城市名 → 城市层级
            geo_level = "city"
        elif station_name:
            # 只有站点名 → 站点层级
            geo_level = "station"

        return {
            "station_name": station_name,
            "city_name": city_name,
            "district_name": district_name,
            "unique_code": unique_code,
            "geo_level": geo_level
        }

    @classmethod
    def extract_guangdong_measurement_value(
        cls,
        measurements: Dict[str, Any],
        pollutant: str
    ) -> Optional[float]:
        """
        从广东站点measurements中提取污染物值（支持嵌套结构）

        解析流程：
        1. 直接从measurements查找（兼容旧格式）
        2. 使用字段映射查找
        3. 处理嵌套在aqi_indices中的IAQI指数
        4. 处理嵌套在air_quality_status中的状态字段
        5. 应用标准化和类型转换

        Args:
            measurements: measurements字典
            pollutant: 污染物名称（PM2.5, PM10, O3, NO2, SO2, CO, AQI等）

        Returns:
            污染物浓度值，如果无法提取则返回None
        """
        # Step 1: 尝试直接从measurements中获取（兼容旧格式）
        direct_value = measurements.get(pollutant)
        normalized_value = cls._normalize_value(direct_value)
        if normalized_value is not None:
            try:
                return float(normalized_value)
            except (ValueError, TypeError):
                pass

        # Step 2: 使用字段映射查找污染物
        mappings = cls.get_all_mappings()
        if pollutant in mappings:
            for field_name in mappings[pollutant]:
                value = measurements.get(field_name)
                normalized_value = cls._normalize_value(value)
                if normalized_value is not None:
                    try:
                        return float(normalized_value)
                    except (ValueError, TypeError):
                        pass

        # Step 3: 处理嵌套在aqi_indices中的IAQI指数
        aqi_indices = measurements.get("aqi_indices", {})
        if aqi_indices and pollutant.endswith("_IAQI"):
            value = aqi_indices.get(pollutant)
            normalized_value = cls._normalize_value(value)
            if normalized_value is not None:
                try:
                    return float(normalized_value)
                except (ValueError, TypeError):
                    pass

        # Step 4: 处理嵌套在air_quality_status中的状态字段
        air_quality_status = measurements.get("air_quality_status", {})
        if air_quality_status:
            status_mappings = cls.AIR_QUALITY_STATUS_MAPPINGS
            if pollutant in status_mappings:
                for field_name in status_mappings[pollutant]:
                    value = air_quality_status.get(field_name)
                    normalized_value = cls._normalize_value(value)
                    if normalized_value is not None:
                        try:
                            # AQI转换为数值
                            if pollutant == "AQI":
                                return float(normalized_value)
                            # 其他状态字段直接返回字符串
                            return normalized_value
                        except (ValueError, TypeError):
                            pass

        return None

    # ============================================
    # ========== 工具方法区域（辅助）==========
    # ============================================

    @classmethod
    def _normalize_value(cls, value: Any) -> Any:
        """
        标准化数值，处理异常值

        标准化流程：
        1. 检查是否为None
        2. 字符串类型：处理无数据标记和异常值，尝试转换为数值
        3. 数值类型：检查异常值
        4. 其他类型：直接返回

        Args:
            value: 原始值

        Returns:
            标准化后的值
        """
        if value is None:
            return None

        if isinstance(value, str):
            # 无数据标记
            if value in ["—", "--", "-", "", "null", "NULL"]:
                return None
            # 异常值标记
            if value in ["-99.000", "-99", "-999", "-999.000"]:
                return None

            # 尝试转换为数值
            try:
                return float(value)
            except (ValueError, TypeError):
                return value

        # 数值类型直接返回（检查异常值）
        if isinstance(value, (int, float)):
            if value in [-99, -99.0, -999, -999.0]:
                return None
            return value

        return value

    @classmethod
    def _validate_value(cls, value: Any, allow_none: bool = True) -> bool:
        """
        验证值是否有效

        Args:
            value: 要验证的值
            allow_none: 是否允许None值

        Returns:
            验证是否通过
        """
        if value is None:
            return allow_none

        # 检查是否为异常值
        if isinstance(value, str) and value in ["—", "--", "", "null", "NULL"]:
            return False

        if isinstance(value, (int, float)) and value in [-99, -99.0, -999, -999.0]:
            return False

        return True

    @classmethod
    def _convert_type(cls, value: Any, target_type: type = float) -> Optional[Any]:
        """
        类型转换

        Args:
            value: 要转换的值
            target_type: 目标类型

        Returns:
            转换后的值，失败返回None
        """
        if value is None:
            return None

        try:
            if target_type == float:
                return float(value)
            elif target_type == int:
                return int(value)
            elif target_type == str:
                return str(value)
            else:
                return target_type(value)
        except (ValueError, TypeError):
            return None


# ============================================
# ========== 便捷函数接口（对外）==========
# ============================================

def get_pollutant_field_variants(pollutant: str) -> List[str]:
    """
    获取指定污染物的所有字段变体

    Args:
        pollutant: 污染物名称（如"PM2.5"）

    Returns:
        字段变体列表
    """
    return FieldMappings.POLLUTANT_CONCENTRATION_MAPPINGS.get(pollutant, [pollutant])


def extract_pollutant_value(record: Dict[str, Any], pollutant: str) -> Optional[float]:
    """
    从记录中提取污染物值（带异常值处理）

    解析流程：
    1. 使用find_field_value查找值
    2. 应用标准化处理
    3. 转换为float类型

    Args:
        record: 数据记录
        pollutant: 污染物名称

    Returns:
        污染物浓度值，如果无法提取或为异常值则返回None
    """
    value = FieldMappings.find_field_value(record, pollutant)
    normalized_value = FieldMappings._normalize_value(value)

    try:
        return float(normalized_value) if normalized_value is not None else None
    except (ValueError, TypeError):
        return None


def build_measurement_from_record(
    record: Dict[str, Any],
    include_types: List[str] = ["pollutant", "aqi", "status", "meteo"]
) -> Dict[str, Any]:
    """
    从记录构建完整的测量值字典

    Args:
        record: 数据记录
        include_types: 包含的测量类型列表

    Returns:
        完整的测量值字典
    """
    measurements = {}
    for measurement_type in include_types:
        type_measurements = FieldMappings.extract_measurements(record, measurement_type)
        measurements.update(type_measurements)
    return measurements


# ============================================
# ========== 示例用法和测试==========
# ============================================

if __name__ == "__main__":
    # 示例：使用字段映射
    sample_record = {
        "pM2_5": 35.6,
        "PM10": 52.3,
        "o3": 28.4,
        "aqi": 85,
        "stationName": "深圳莲花站",
        "cityName": "深圳",
        "windSpeed": 3.2,
        "temperature": 25.6
    }

    # 提取PM2.5值
    pm25_value = extract_pollutant_value(sample_record, "PM2.5")
    print(f"PM2.5: {pm25_value}")

    # 提取所有测量值
    measurements = build_measurement_from_record(sample_record)
    print(f"所有测量值: {measurements}")

    # 提取站点信息
    station_info = FieldMappings.extract_station_info(sample_record)
    print(f"站点信息: {station_info}")
