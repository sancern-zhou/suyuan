"""
全局数据标准化器 (Data Standardizer)

根据UDF v2.0标准字段规范，将所有外部API的多样化字段
统一转换为内部标准字段，确保工具间数据格式一致性

设计原则：
- 宽进严出：接受多种字段格式，输出标准格式
- 性能优化：使用缓存减少重复映射
- 易于扩展：支持动态添加字段映射规则
- 异常处理：优雅处理异常值和缺失字段
"""
from typing import Any, Dict, List, Optional, Union, Set
from datetime import datetime
import re
import structlog
from functools import lru_cache

logger = structlog.get_logger()


def _safe_for_logging(value):
    """
    将值转换为日志安全的格式，避免Windows GBK编码错误

    Args:
        value: 任意值（字符串、列表、字典等）

    Returns:
        日志安全的值（Unicode字符转换为repr格式）
    """
    if isinstance(value, str):
        # 检查是否包含非ASCII字符
        try:
            value.encode('ascii')
            return value
        except UnicodeEncodeError:
            return repr(value)
    elif isinstance(value, (list, tuple)):
        return [_safe_for_logging(item) for item in value]
    elif isinstance(value, dict):
        return {_safe_for_logging(k): _safe_for_logging(v) for k, v in value.items()}
    else:
        return value


class DataStandardizer:
    """
    全局数据标准化器

    将外部API返回的各种字段格式统一转换为UDF v2.0标准格式
    """

    def __init__(self, cache_size: int = 1000):
        """
        初始化数据标准化器

        Args:
            cache_size: LRU缓存大小，默认1000
        """
        self.cache_size = cache_size
        self._initialize_field_mappings()
        self._initialize_normalization_rules()

    def _initialize_field_mappings(self):
        """初始化所有字段映射规则"""

        # === 1. 时间字段映射 ===
        self.time_field_mapping = {
            "timestamp": "timestamp",
            "timePoint": "timestamp",
            "time_point": "timestamp",
            "TimePoint": "timestamp",
            "time": "timestamp",
            "DataTime": "timestamp",
            "datetime": "timestamp",
            "时间点": "timestamp",
            "时间": "timestamp",
            "TimePoint": "timestamp",
            "data_time": "timestamp"
        }

        # === 2. 地理字段映射 ===
        self.station_field_mapping = {
            # 站点名称
            "station_name": "station_name",
            "stationName": "station_name",
            "StationName": "station_name",
            "name": "station_name",
            "站点名称": "station_name",
            "监测点": "station_name",
            "城市名称": "city",
            "city_name": "city",
            "市区名称": "district",
            "地区": "city",

            # 站点编码
            "station_code": "station_code",
            "stationCode": "station_code",
            "StationCode": "station_code",
            "uniqueCode": "station_code",
            "unique_code": "station_code",
            "StationCode": "station_code",
            "code": "station_code",
            "city_code": "city_code",
            "cityCode": "city_code",
            "CityCode": "city_code",
            "Code": "station_code",  # VOCs API 返回的站点编码字段
        }

        self.coordinate_field_mapping = {
            # 纬度
            "lat": "lat",
            "latitude": "lat",
            "Latitude": "lat",
            "纬度": "lat",

            # 经度
            "lon": "lon",
            "lng": "lon",
            "longitude": "lon",
            "Longitude": "lon",
            "经度": "lon"
        }

        # === 3. 污染物字段映射 ===
        self.pollutant_field_mapping = {
            # PM2.5
            "PM2_5": "PM2_5",
            "PM2.5": "PM2_5",
            "PM25": "PM2_5",
            "pm2_5": "PM2_5",
            "pm2.5": "PM2_5",
            "pM2_5": "PM2_5",
            "PM2_5_24h": "PM2_5",
            "细颗粒物": "PM2_5",  # 新增：中文
            "细颗粒物(PM2.5)": "PM2_5",  # 新增：中文带括号
            "PM2.5浓度": "PM2_5",  # 新增：带浓度字样
            "PM₂.₅": "PM2_5",  # Unicode下标形式

            # PM10
            "PM10": "PM10",
            "pm10": "PM10",
            "pM10": "PM10",
            "PM10_24h": "PM10",
            "可吸入颗粒物": "PM10",  # 新增：中文
            "可吸入颗粒物(PM10)": "PM10",  # 新增：中文带括号
            "PM10浓度": "PM10",  # 新增：带浓度字样

            # O3
            "O3": "O3",
            "o3": "O3",
            "臭氧": "O3",
            "臭氧(O₃)": "O3",
            "臭氧(o3)": "O3",
            "臭氧(O3)": "O3",  # 新增：无下标版本
            "O₃": "O3",  # 新增：单独符号

            # O3_8H - 8小时臭氧平均值（单独指标）
            "O3_8h": "O3_8h",
            "O3_8H": "O3_8h",
            "O38H": "O3_8h",
            "O38h": "O3_8h",
            "臭氧8小时": "O3_8h",  # 新增：中文
            "臭氧(O₃) - 8小时平均": "O3_8h",  # 新增：完整中文

            # NO2
            "NO2": "NO2",
            "no2": "NO2",
            "nO2": "NO2",
            "二氧化氮": "NO2",  # 新增：中文
            "二氧化氮(NO₂)": "NO2",  # 新增：带下标中文
            "二氧化氮(NO2)": "NO2",  # 新增：无下标中文
            "NO₂": "NO2",  # 新增：单独符号

            # SO2
            "SO2": "SO2",
            "so2": "SO2",
            "sO2": "SO2",
            "二氧化硫": "SO2",  # 新增：中文
            "二氧化硫(SO₂)": "SO2",  # 新增：带下标中文
            "二氧化硫(SO2)": "SO2",  # 新增：无下标中文
            "SO₂": "SO2",  # 新增：单独符号

            # CO
            "CO": "CO",
            "co": "CO",
            "一氧化碳": "CO",  # 新增：中文
            "一氧化碳(CO)": "CO",  # 新增：中文带括号

            # NOx
            "NOx": "NOx",
            "nox": "NOx",
            "nOx": "NOx",

            # NO
            "NO": "NO",
            "no": "NO",
        }

        # === 4. AQI字段映射 ===
        self.aqi_field_mapping = {
            # AQI指数
            "AQI": "AQI",
            "aqi": "AQI",
            "空气质量指数": "AQI",
            "compositeindex": "AQI",
            "compositeIndex": "AQI",
            "综合指数": "AQI",

            # 首要污染物
            "primary_pollutant": "primary_pollutant",
            "primaryPollutant": "primary_pollutant",
            "首要污染物": "primary_pollutant",

            # 空气质量等级
            "air_quality_level": "air_quality_level",
            "quality_type": "air_quality_level",
            "qualityType": "air_quality_level",
            "空气质量等级": "air_quality_level",
            "quality_type": "air_quality_level"
        }

        # === 5. IAQI分指数映射 ===
        self.iaqi_field_mapping = {
            "SO2_IAQI": "SO2_IAQI",
            "sO2_IAQI": "SO2_IAQI",
            "NO2_IAQI": "NO2_IAQI",
            "nO2_IAQI": "NO2_IAQI",
            "PM10_IAQI": "PM10_IAQI",
            "pM10_IAQI": "PM10_IAQI",
            "CO_IAQI": "CO_IAQI",
            "cO_IAQI": "CO_IAQI",
            "O3_IAQI": "O3_IAQI",
            "o3_IAQI": "O3_IAQI",
            "O3_8h_IAQI": "O3_8h_IAQI",
            "O3_8H_IAQI": "O3_8h_IAQI",
            "PM2_5_IAQI": "PM2_5_IAQI",
            "pM2_5_IAQI": "PM2_5_IAQI"
        }

        # === 6. VOCs字段映射 ===
        # 基于广东省VOCs监测站实际监测物种（约100+种）
        self.vocs_field_mapping = {
            # ==========================================
            # 烷烃类 (Alkanes) - C2-C12
            # ==========================================
            # 低碳烷烃
            "Ethane": "C2H6",
            "Propane": "C3H8",
            "n-Butane": "n-C4H10",
            "Isobutane": "i-C4H10",
            "n-Pentane": "n-C5H12",
            "Isopentane": "i-C5H12",
            "n-Hexane": "n-C6H14",
            "n-Heptane": "n-C7H16",
            "n-Octane": "n-C8H18",
            "n-Nonane": "n-C9H20",
            "n-Decane": "n-C10H22",
            "n-Undecane": "n-C11H24",
            "n-Dodecane": "n-C12H26",
            # 中文烷烃
            "乙烷": "C2H6",
            "丙烷": "C3H8",
            "正丁烷": "n-C4H10",
            "异丁烷": "i-C4H10",
            "正戊烷": "n-C5H12",
            "异戊烷": "i-C5H12",
            "正己烷": "n-C6H14",
            "正庚烷": "n-C7H16",
            "正辛烷": "n-C8H18",
            "正壬烷": "n-C9H20",
            "正癸烷": "n-C10H22",
            "十一烷": "n-C11H24",
            "十二烷": "n-C12H26",
            # 支链/环状烷烃
            "Cyclopentane": "c-C5H10",
            "Cyclohexane": "c-C6H12",
            "Methylcyclopentane": "c-C5H9-CH3",
            "Methylcyclohexane": "c-C6H11-CH3",
            "2,2-Dimethylbutane": "2,2-DMB",
            "2,3-Dimethylbutane": "2,3-DMB",
            "2-Methylpentane": "2-MP",
            "3-Methylpentane": "3-MP",
            "2,4-Dimethylpentane": "2,4-DMP",
            "2,3-Dimethylpentane": "2,3-DMP",
            "2-Methylhexane": "2-MH",
            "3-Methylhexane": "3-MH",
            "2-Methylheptane": "2-MHpt",
            "3-Methylheptane": "3-MHpt",
            "2,2,4-Trimethylpentane": "2,2,4-TMP",
            "2,3,4-Trimethylpentane": "2,3,4-TMP",
            # 中文支链/环状烷烃
            "环戊烷": "c-C5H10",
            "环己烷": "c-C6H12",
            "甲基环戊烷": "c-C5H9-CH3",
            "甲基环己烷": "c-C6H11-CH3",
            "2,2-二甲基丁烷": "2,2-DMB",
            "2,3-二甲基丁烷": "2,3-DMB",
            "2-甲基戊烷": "2-MP",
            "3-甲基戊烷": "3-MP",
            "2,4-二甲基戊烷": "2,4-DMP",
            "2,3-二甲基戊烷": "2,3-DMP",
            "2-甲基己烷": "2-MH",
            "3-甲基己烷": "3-MH",
            "2-甲基庚烷": "2-MHpt",
            "3-甲基庚烷": "3-MHpt",
            "2,2,4-三甲基戊烷": "2,2,4-TMP",
            "2,3,4-三甲基戊烷": "2,3,4-TMP",

            # ==========================================
            # 烯烃类 (Alkenes)
            # ==========================================
            "Ethylene": "C2H4",
            "Propene": "C3H6",
            "1-Butene": "1-C4H8",
            "Isobutene": "i-C4H8",
            "1-Pentene": "1-C5H10",
            "cis-2-Butene": "cis-2-C4H8",
            "trans-2-Butene": "trans-2-C4H8",
            "cis-2-Pentene": "cis-2-C5H10",
            "trans-2-Pentene": "trans-2-C5H10",
            "1-Hexene": "1-C6H12",
            "Isoprene": "C5H8",
            "1,3-Butadiene": "C4H6",
            # 中文烯烃
            "乙烯": "C2H4",
            "丙烯": "C3H6",
            "1-丁烯": "1-C4H8",
            "异丁烯": "i-C4H8",
            "1-戊烯": "1-C5H10",
            "顺-2-丁烯": "cis-2-C4H8",
            "反-2-丁烯": "trans-2-C4H8",
            "顺-2-戊烯": "cis-2-C5H10",
            "反-2-戊烯": "trans-2-C5H10",
            "1-己烯": "1-C6H12",
            "异戊二烯": "C5H8",
            "1,3-丁二烯": "C4H6",

            # ==========================================
            # 芳香烃类 (Aromatics)
            # ==========================================
            "Benzene": "C6H6",
            "Toluene": "C7H8",
            "Ethylbenzene": "C8H10",
            "m-Xylene": "m-C8H10",
            "p-Xylene": "p-C8H10",
            "o-Xylene": "o-C8H10",
            "Styrene": "C8H8",
            "Isopropylbenzene": "i-C9H12",
            "n-Propylbenzene": "n-C9H12",
            "1,3,5-Trimethylbenzene": "1,3,5-TMB",
            "1,2,4-Trimethylbenzene": "1,2,4-TMB",
            "1,2,3-Trimethylbenzene": "1,2,3-TMB",
            "o-Ethyltoluene": "o-ECT",
            "m-Ethyltoluene": "m-ECT",
            "p-Ethyltoluene": "p-ECT",
            "m-Diethylbenzene": "m-DEB",
            "p-Diethylbenzene": "p-DEB",
            "Naphthalene": "C10H8",
            # 中文芳香烃
            "苯": "C6H6",
            "甲苯": "C7H8",
            "乙苯": "C8H10",
            "间-二甲苯": "m-C8H10",
            "对-二甲苯": "p-C8H10",
            "邻-二甲苯": "o-C8H10",
            "间/对-二甲苯": "m+p-C8H10",
            "苯乙烯": "C8H8",
            "异丙苯": "i-C9H12",
            "正丙苯": "n-C9H12",
            "1,3,5-三甲基苯": "1,3,5-TMB",
            "1,2,4-三甲基苯": "1,2,4-TMB",
            "1,2,3-三甲基苯": "1,2,3-TMB",
            "邻-乙基甲苯": "o-ECT",
            "间-乙基甲苯": "m-ECT",
            "对-乙基甲苯": "p-ECT",
            "间-二乙苯": "m-DEB",
            "对-二乙苯": "p-DEB",
            "萘": "C10H8",

            # ==========================================
            # 含氧化合物 (Oxygenated VOCs - OVOCs)
            # ==========================================
            # 醛类
            "Formaldehyde": "HCHO",
            "Acetaldehyde": "CH3CHO",
            "Propionaldehyde": "C2H5CHO",
            "n-Butyraldehyde": "n-C3H7CHO",
            "Valeraldehyde": "n-C4H9CHO",
            "Hexaldehyde": "C5H11CHO",
            "Acrolein": "C2H3CHO",
            "Crotonaldehyde": "C3H5CHO",
            "Methacrolein": "MA",
            "Benzaldehyde": "C6H5CHO",
            "m-Tolualdehyde": "m-CH3-C6H4CHO",
            # 中文醛类
            "甲醛": "HCHO",
            "乙醛": "CH3CHO",
            "丙醛": "C2H5CHO",
            "正丁醛": "n-C3H7CHO",
            "戊醛": "n-C4H9CHO",
            "己醛": "C5H11CHO",
            "丙烯醛": "C2H3CHO",
            "丁烯醛": "C3H5CHO",
            "甲基丙烯醛": "MA",
            "苯甲醛": "C6H5CHO",
            "间甲基苯甲醛": "m-CH3-C6H4CHO",
            # 酮类
            "Acetone": "C3H6O",
            "2-Butanone": "MEK",
            "4-Methyl-2-pentanone": "MIBK",
            "2-Hexanone": "MAK",
            "Methyl isobutyl ketone": "MIBK",
            # 中文酮类
            "丙酮": "C3H6O",
            "2-丁酮": "MEK",
            "4-甲基-2-戊酮": "MIBK",
            "2-己酮": "MAK",
            # 其他
            "Acetylene": "C2H2",
            "Carbon disulfide": "CS2",
            "Benzyl chloride": "C6H5CH2Cl",
            # 中文其他
            "乙炔": "C2H2",
            "二硫化碳": "CS2",
            "氯化苄": "C6H5CH2Cl",

            # ==========================================
            # 卤代烃类 (Halogenated hydrocarbons)
            # ==========================================
            # 氯甲烷类
            "Chloromethane": "CH3Cl",
            "Dichloromethane": "CH2Cl2",
            "Chloroform": "CHCl3",
            "Carbon tetrachloride": "CCl4",
            "Chlorodifluoromethane": "CHClF2",  # HCFC-22
            "Trichlorofluoromethane": "CCl3F",  # CFC-11
            "Dichlorodifluoromethane": "CCl2F2",  # CFC-12
            "Bromomethane": "CH3Br",
            "Chloroethane": "C2H5Cl",
            "1,1-Dichloroethane": "1,1-C2H4Cl2",
            "1,2-Dichloroethane": "1,2-C2H4Cl2",
            "1,1,1-Trichloroethane": "1,1,1-C2H3Cl3",
            "1,1,2-Trichloroethane": "1,1,2-C2H3Cl3",
            "Vinyl chloride": "C2H3Cl",
            "1,1-Dichloroethylene": "C2H2Cl2",
            "cis-1,2-Dichloroethylene": "cis-C2H2Cl2",
            "trans-1,2-Dichloroethylene": "trans-C2H2Cl2",
            "Trichloroethylene": "C2HCl3",
            "Tetrachloroethylene": "C2Cl4",
            # 溴代烃
            "Bromoform": "CHBr3",
            "Dibromochloromethane": "CHBr2Cl",
            "1,2-Dibromoethane": "C2H4Br2",
            # 氯苯类
            "Chlorobenzene": "C6H5Cl",
            "1,2-Dichlorobenzene": "1,2-C6H4Cl2",
            "1,3-Dichlorobenzene": "1,3-C6H4Cl2",
            "1,4-Dichlorobenzene": "1,4-C6H4Cl2",
            "1,2,4-Trichlorobenzene": "1,2,4-C6H3Cl3",
            "Hexachlorobutadiene": "C4Cl6",
            # 氯代丙烯类
            "cis-1,3-Dichloropropene": "cis-C3H4Cl2",
            "trans-1,3-Dichloropropene": "trans-C3H4Cl2",
            "1,2-Dichloropropane": "C3H6Cl2",
            # 中文卤代烃
            "氯甲烷": "CH3Cl",
            "二氯甲烷": "CH2Cl2",
            "三氯甲烷": "CHCl3",
            "四氯化碳": "CCl4",
            "氟利昂-12": "CCl2F2",
            "氟利昂-11": "CCl3F",
            "氟利昂-113": "C2F3Cl3",
            "氟利昂-114": "C2F4Cl2",
            "溴甲烷": "CH3Br",
            "氯乙烷": "C2H5Cl",
            "1,1-二氯乙烷": "1,1-C2H4Cl2",
            "1,2-二氯乙烷": "1,2-C2H4Cl2",
            "1,1,1-三氯乙烷": "1,1,1-C2H3Cl3",
            "1,1,2-三氯乙烷": "1,1,2-C2H3Cl3",
            "1,2-二氯丙烷": "C3H6Cl2",
            "氯乙烯": "C2H3Cl",
            "1,1-二氯乙烯": "C2H2Cl2",
            "顺-1,2-二氯乙烯": "cis-C2H2Cl2",
            "反-1,2-二氯乙烯": "trans-C2H2Cl2",
            "三氯乙烯": "C2HCl3",
            "四氯乙烯": "C2Cl4",
            "三溴甲烷": "CHBr3",
            "一溴二氯甲烷": "CHBr2Cl",
            "二溴一氯甲烷": "CHBrCl2",
            "二溴二氯甲烷": "CBr2Cl2",
            "1,2-二溴乙烷": "C2H4Br2",
            "四氯乙烷": "C2H2Cl4",
            "反-1,3-二氯丙烯": "trans-C3H4Cl2",
            "顺-1,3-二氯丙烯": "cis-C3H4Cl2",
            "六氯-1,3-丁二烯": "C4Cl6",
            "氯苯": "C6H5Cl",
            "1,2-二氯苯": "1,2-C6H4Cl2",
            "1,3-二氯苯": "1,3-C6H4Cl2",
            "1,4-二氯苯": "1,4-C6H4Cl2",
            "1,2,4-三氯苯": "1,2,4-C6H3Cl3",

            # ==========================================
            # 含氧化合物补充 (Oxygenated VOCs - OVOCs)
            # ==========================================
            # 醇类
            "Isopropanol": "i-C3H7OH",
            # 中文醇类
            "异丙醇": "i-C3H7OH",
            # 酯类
            "Vinyl acetate": "C4H6O2",
            "Ethyl acetate": "C4H8O2",
            "Methyl methacrylate": "C5H8O2",
            # 中文酯类
            "乙酸乙烯酯": "C4H6O2",
            "乙酸乙酯": "C4H8O2",
            "甲基丙烯酸甲酯": "C5H8O2",
            # 醚类
            "Tetrahydrofuran": "THF",
            "1,4-Dioxane": "C4H8O2",
            "Methyl tert-butyl ether": "MTBE",
            "Diethyl ether": "C2H5OC2H5",
            # 中文醚类
            "四氢呋喃": "THF",
            "1,4-二氧六环": "C4H8O2",
            "甲基叔丁基醚": "MTBE",
            "乙醚": "C2H5OC2H5"
        }

        # === 7. 颗粒物组分映射 ===
        self.pm_component_field_mapping = {
            # 无机离子
            "SO4": "SO4",
            "SO4^2-": "SO4",
            "Sulfate": "SO4",
            "SO₄²⁻": "SO4",  # Unicode上标形式
            "SO₄": "SO4",
            "sulfate": "SO4",
            "NO3": "NO3",
            "NO3^-": "NO3",
            "Nitrate": "NO3",
            "NO₃⁻": "NO3",  # Unicode上标形式
            "NO₃": "NO3",
            "nitrate": "NO3",
            "NH4": "NH4",
            "NH4^+": "NH4",
            "Ammonium": "NH4",
            "NH₄⁺": "NH4",  # Unicode上标形式
            "NH₄": "NH4",
            "ammonium": "NH4",

            # 元素碳
            "EC": "EC",
            "EC1": "EC",
            "EC2": "EC",
            "Elemental Carbon": "EC",
            "elemental_carbon": "EC",
            "EC（TOT）": "EC",  # 全角括号格式
            "OC": "OC",
            "OC1": "OC",
            "OC2": "OC",
            "Organic Carbon": "OC",
            "organic_carbon": "OC",
            "OC（TOT）": "OC",  # 全角括号格式

            # 地壳元素（小写形式）
            "Al": "Al",
            "aluminum": "Al",
            "Aluminum": "Al",
            "铝": "Al",  # 中文
            "Si": "Si",
            "silicon": "Si",
            "Silicon": "Si",
            "硅": "Si",  # 中文
            "K": "K",
            "K⁺": "K",  # Unicode上标形式
            "K+": "K",  # ASCII形式
            "potassium": "K",
            "Potassium": "K",
            "钾": "K",  # 中文
            "Ca": "Ca",
            "Ca²⁺": "Ca",  # Unicode上标形式
            "Ca2+": "Ca",  # ASCII形式
            "calcium": "Ca",
            "Calcium": "Ca",
            "钙": "Ca",  # 中文
            "Ti": "Ti",
            "titanium": "Ti",
            "Titanium": "Ti",
            "钛": "Ti",  # 中文
            "Fe": "Fe",
            "iron": "Fe",
            "Iron": "Fe",
            "铁": "Fe",  # 中文
            "Cu": "Cu",
            "copper": "Cu",
            "Copper": "Cu",
            "铜": "Cu",  # 中文
            "Zn": "Zn",
            "zinc": "Zn",
            "Zinc": "Zn",
            "锌": "Zn",  # 中文
            "Pb": "Pb",
            "lead": "Pb",
            "Lead": "Pb",
            "铅": "Pb",  # 中文

            # 其他常见元素
            "Mg": "Mg",
            "magnesium": "Mg",
            "Magnesium": "Mg",
            "Mg²⁺": "Mg",  # Unicode上标形式
            "镁": "Mg",  # 中文
            "Na": "Na",
            "sodium": "Na",
            "Sodium": "Na",
            "Na⁺": "Na",  # Unicode上标形式
            "钠": "Na",  # 中文
            "K": "K",
            "钾": "K",  # 中文（重复确保覆盖）
            "Cl": "Cl",
            "chloride": "Cl",
            "Chloride": "Cl",
            "Cl⁻": "Cl",  # Unicode上标形式
            "氯": "Cl",  # 中文

            # 其他离子（API返回格式）
            "Li⁺": "Li",  # 锂离子
            "Li": "Li",
            "lithium": "Li",
            "锂": "Li",  # 中文
            "Al3+": "Al",  # 铝离子（带电荷）
            "PO₄³⁻": "PO4",  # 磷酸根
            "PO4^3-": "PO4",
            "phosphate": "PO4",
            "PO43-": "PO4",
            "F⁻": "F",  # 氟离子
            "F-": "F",
            "fluoride": "F",
            "氟": "F",  # 中文
            "Br⁻": "Br",  # 溴离子
            "Br-": "Br",
            "bromide": "Br",
            "溴": "Br",  # 中文
            "NO₂⁻": "NO2",  # 亚硝酸根（不同于硝酸根 NO3-）
            "NO2^-": "NO2",
            "nitrite": "NO2",
            "亚硝酸盐": "NO2",  # 中文
            "NO3-": "NO3",  # 硝酸根
            "NO₃⁻": "NO3",  # 已在上面定义
            "硝酸盐": "NO3"  # 中文
        }

        # === 8. 气象字段映射 ===
        self.meteorological_field_mapping = {
            # === 温度相关 ===
            # 2米温度
            "temperature_2m": "temperature_2m",
            "temperature_2M": "temperature_2m",
            "temp_2m": "temperature_2m",
            "temp2m": "temperature_2m",
            "气温": "temperature_2m",
            "温度": "temperature_2m",

            # 露点温度
            "dew_point_2m": "dew_point_2m",
            "dewPoint_2m": "dew_point_2m",
            "dew_2m": "dew_point_2m",
            "dewpoint": "dew_point_2m",
            "露点": "dew_point_2m",

            # 体感温度
            "apparent_temperature": "apparent_temperature",
            "apparentTemp": "apparent_temperature",
            "feels_like": "apparent_temperature",
            "体感温度": "apparent_temperature",

            # 日最高温度
            "daily_temperature_max": "daily_temperature_max",
            "daily_temp_max": "daily_temperature_max",
            "temp_max": "daily_temperature_max",
            "日最高温度": "daily_temperature_max",

            # 日最低温度
            "daily_temperature_min": "daily_temperature_min",
            "daily_temp_min": "daily_temperature_min",
            "temp_min": "daily_temperature_min",
            "日最低温度": "daily_temperature_min",

            # === 湿度相关 ===
            # 2米相对湿度
            "relative_humidity_2m": "relative_humidity_2m",
            "relativeHumidity_2m": "relative_humidity_2m",
            "rh_2m": "relative_humidity_2m",
            "humidity_2m": "relative_humidity_2m",
            "相对湿度": "relative_humidity_2m",
            "湿度": "relative_humidity_2m",

            # === 风速相关 ===
            # 10米风速
            "wind_speed_10m": "wind_speed_10m",
            "windSpeed_10m": "wind_speed_10m",
            "ws_10m": "wind_speed_10m",
            "wind_speed": "wind_speed_10m",  # 兼容无高度标记
            "windSpeed": "wind_speed_10m",
            "ws": "wind_speed_10m",
            "WS": "wind_speed_10m",
            "风速": "wind_speed_10m",

            # 10米阵风
            "wind_gusts_10m": "wind_gusts_10m",
            "windGusts_10m": "wind_gusts_10m",
            "gusts_10m": "wind_gusts_10m",
            "wind_gusts": "wind_gusts_10m",
            "阵风": "wind_gusts_10m",

            # 日最大风速
            "daily_wind_speed_max": "daily_wind_speed_max",
            "daily_wind_max": "daily_wind_speed_max",
            "wind_max": "daily_wind_speed_max",
            "日最大风速": "daily_wind_speed_max",

            # 历史平均风速
            "historical_wind_speed_mean": "historical_wind_speed_mean",
            "hist_wind_mean": "historical_wind_speed_mean",
            "历史风速平均": "historical_wind_speed_mean",

            # === 风向相关 ===
            # 10米风向
            "wind_direction_10m": "wind_direction_10m",
            "windDirection_10m": "wind_direction_10m",
            "wd_10m": "wind_direction_10m",
            "wind_direction": "wind_direction_10m",  # 兼容无高度标记
            "windDirect": "wind_direction_10m",
            "wd": "wind_direction_10m",
            "WD": "wind_direction_10m",
            "风向": "wind_direction_10m",

            # === 气压相关 ===
            # 地表气压
            "surface_pressure": "surface_pressure",
            "surfacePressure": "surface_pressure",
            "pressure": "surface_pressure",  # 兼容无高度标记
            "press": "surface_pressure",
            "p": "surface_pressure",
            "气压": "surface_pressure",

            # === 降水相关 ===
            # 降水量
            "precipitation": "precipitation",
            "rainFall": "precipitation",
            "rain": "precipitation",
            "降水量": "precipitation",
            "降雨量": "precipitation",

            # 降水概率
            "precipitation_probability": "precipitation_probability",
            "precipProbability": "precipitation_probability",
            "pop": "precipitation_probability",
            "降水概率": "precipitation_probability",

            # 日累计降水量
            "daily_precipitation_sum": "daily_precipitation_sum",
            "daily_rain_sum": "daily_precipitation_sum",
            "rain_sum": "daily_precipitation_sum",
            "日降水量": "daily_precipitation_sum",

            # === 云量相关 ===
            # 云量
            "cloud_cover": "cloud_cover",
            "cloudCover": "cloud_cover",
            "cloud": "cloud_cover",
            "云量": "cloud_cover",
            "云": "cloud_cover",

            # === 辐射相关 ===
            # 短波太阳辐射
            "shortwave_radiation": "shortwave_radiation",
            "shortwaveRadiation": "shortwave_radiation",
            "solar_radiation": "shortwave_radiation",
            "solarRadiation": "shortwave_radiation",
            "辐射": "shortwave_radiation",
            "太阳辐射": "shortwave_radiation",

            # UV指数
            "uv_index": "uv_index",
            "uvIndex": "uv_index",
            "uv": "uv_index",
            "紫外线指数": "uv_index",

            # === 能见度 ===
            # 能见度
            "visibility": "visibility",
            "能见度": "visibility",

            # === 边界层相关 ===
            # 边界层高度
            "boundary_layer_height": "boundary_layer_height",
            "boundaryLayerHeight": "boundary_layer_height",
            "pbl_height": "boundary_layer_height",
            "pblh": "boundary_layer_height",
            "边界层高度": "boundary_layer_height",

            # 历史平均边界层高度
            "historical_boundary_layer_mean": "historical_boundary_layer_mean",
            "hist_pbl_mean": "historical_boundary_layer_mean",
            "历史边界层平均": "historical_boundary_layer_mean",

            # === 天气代码 ===
            # 天气代码
            "weather_code": "weather_code",
            "weatherCode": "weather_code",
            "weathercode": "weather_code",
            "weather": "weather_code",
            "天气代码": "weather_code",

            # === 兼容旧字段 ===
            # 温度（泛化）
            "temperature": "temperature_2m",
            "temp": "temperature_2m",

            # 湿度（泛化）
            "humidity": "relative_humidity_2m",
            "rh": "relative_humidity_2m",

            # 风速（泛化）
            "wind_speed": "wind_speed_10m",
            "windSpeed": "wind_speed_10m",

            # 风向（泛化）
            "wind_direction": "wind_direction_10m",
            "windDirect": "wind_direction_10m",

            # 气压（泛化）
            "pressure": "surface_pressure",
            "press": "surface_pressure",
            "p": "surface_pressure"
        }

        # === 9. 元数据字段映射 ===
        self.metadata_field_mapping = {
            # 数据ID
            "data_id": "data_id",
            "dataId": "data_id",

            # 来源
            "source": "source",
            "来源": "source",

            # 质量评分
            "quality_score": "quality_score",
            "qualityScore": "quality_score",
            "quality": "quality_score",

            # 记录ID
            "id": "record_id",
            "record_id": "record_id",
            "recordId": "record_id",
            "recordID": "record_id",

            # 创建时间
            "createTime": "created_time",
            "created_time": "created_time",
            "created": "created_time",

            # 修改时间
            "modifyTime": "modified_time",
            "modified_time": "modified_time",
            "updated": "modified_time",

            # 数据类型
            "dataType": "data_type",
            "data_type": "data_type"
        }

        # === 10. 空气质量等级和统计字段映射 ===
        self.quality_level_mapping = {
            # 等级相关字段
            "等级": "level",
            "优良天数": "good_days",
            "轻度污染天数": "light_pollution_days",
            "中度污染天数": "medium_pollution_days",
            "重度污染天数": "heavy_pollution_days",
            "优良率": "good_rate",
            "污染天数": "pollution_days",

            # 英文版本
            "fineRate": "good_rate",
            "finerate": "good_rate",
            "overRate": "over_rate",
            "overrate": "over_rate",
            "oneLevelDays": "one_level_days",
            "oneleveldays": "one_level_days",
            "twoLevelDays": "two_level_days",
            "twoleveldays": "two_level_days",
            "threeLevelDays": "three_level_days",
            "threeleveldays": "three_level_days",
            "fourLevelDays": "four_level_days",
            "fourleveldays": "four_level_days",
            "fiveLevelDays": "five_level_days",
            "fiveleveldays": "five_level_days",
            "sixLevelDays": "six_level_days",
            "sixleveldays": "six_level_days",
            "FineRate": "good_rate",

            # 数据类型标识
            "优良": "good",
            "良": "good",
            "优": "excellent"
        }

        # === 11. 排名相关字段映射 ===
        self.ranking_mapping = {
            # 排名相关
            "排名": "rank",
            "省内排名": "rank",
            "rank_compositeindex_168": "rank_168_composite",
            "rank_pm25_168": "rank_168_pm25",
            "rank_compositeindex_338": "rank_338_composite",
            "rank_pm25_338": "rank_338_pm25",
            "rank_compositeindex_gds": "rank_gds_composite",
            "rank_pm25_gds": "rank_gds_pm25",

            # 首要污染物
            "primary_pollutant": "primary_pollutant",
            "primaryPollutant": "primary_pollutant",
            "首要污染物": "primary_pollutant",

            # AQI指数
            "AQI": "AQI",
            "aqi": "AQI",
            "空气质量指数": "AQI",
            "compositeindex": "AQI",
            "compositeIndex": "AQI",
            "综合指数": "AQI"
        }

        # === 12. 通用字段映射（距离、地址等）===
        self.common_field_mapping = {
            # 距离
            "distance_km": "distance_km",
            "distance": "distance_km",
            "距离": "distance_km",
            "距离(km)": "distance_km",

            # 地址
            "address": "address",
            "详细地址": "address",
            "地址": "address",
            "addr": "address",

            # 区域
            "district": "district",
            "区": "district",
            "区县": "district",
            "所属区县": "district",
            "township": "township",
            "乡镇": "township",

            # 省份
            "province": "province",
            "省": "province",
            "省份": "province",

            # 城市
            "city": "city",
            "cityName": "city",
            "城市": "city",
            "城市名称": "city",
            "所属城市": "city"
        }

        # 合并所有映射规则
        self.all_field_mappings = {}
        self.all_field_mappings.update(self.time_field_mapping)
        self.all_field_mappings.update(self.station_field_mapping)
        self.all_field_mappings.update(self.coordinate_field_mapping)
        self.all_field_mappings.update(self.pollutant_field_mapping)
        self.all_field_mappings.update(self.aqi_field_mapping)
        self.all_field_mappings.update(self.iaqi_field_mapping)
        self.all_field_mappings.update(self.vocs_field_mapping)
        self.all_field_mappings.update(self.pm_component_field_mapping)
        self.all_field_mappings.update(self.meteorological_field_mapping)
        self.all_field_mappings.update(self.metadata_field_mapping)
        self.all_field_mappings.update(self.quality_level_mapping)  # 新增
        self.all_field_mappings.update(self.ranking_mapping)  # 新增
        self.all_field_mappings.update(self.common_field_mapping)

        logger.info(
            "data_standardizer_mappings_initialized",
            total_mappings=len(self.all_field_mappings),
            mapping_categories=13  # 更新为13个类别
        )

    def _initialize_normalization_rules(self):
        """初始化数据规范化规则"""

        # 空值标记
        self.null_values = {"—", "--", "-", "", "null", "None", "N/A", "n/a"}

        # 异常值标记
        self.invalid_markers = {"-99", "-99.000", "-999", "-999.0"}

        # 需要跳过的时间字段
        self.skip_time_fields = {
            "time", "timestamp", "时间", "时间点", "DataTime", "datetime"
        }

        # 需要跳过的地理字段
        self.skip_geo_fields = {
            "station_name", "name", "站点名称", "city_name", "city",
            "lat", "latitude", "纬度", "lon", "lng", "longitude", "经度"
        }

        # 特殊嵌套结构字段
        self.nested_structure_keys = {
            "aqi_indices", "air_quality_status", "meteorological_data"
        }

    @lru_cache(maxsize=1000)
    def _get_standard_field_name(self, field_name: str) -> Optional[str]:
        """
        获取字段的标准名称（带缓存）

        Args:
            field_name: 原始字段名

        Returns:
            标准字段名，如果未找到映射则返回None
        """
        if not field_name:
            return None

        # 直接映射
        if field_name in self.all_field_mappings:
            return self.all_field_mappings[field_name]

        # 大小写不敏感查找
        field_lower = field_name.lower()
        if field_lower in self.all_field_mappings:
            return self.all_field_mappings[field_lower]

        # 清理后的查找（移除特殊字符）
        cleaned = re.sub(r'[^a-zA-Z0-9_]', '', field_name)
        if cleaned in self.all_field_mappings:
            return self.all_field_mappings[cleaned]

        # 提取括号内容（处理特殊字符如"₃" → "3"）
        bracket_match = re.search(r'[(（]([^)）]+)[)）]', field_name)
        if bracket_match:
            bracket_content = bracket_match.group(1)
            # 处理下标字符
            bracket_content = bracket_content.replace('₃', '3').replace('₂', '2').replace('₁', '1')
            if bracket_content in self.all_field_mappings:
                return self.all_field_mappings[bracket_content]

        return None

    def _normalize_value(self, value: Any) -> Any:
        """
        规范化单个值

        Args:
            value: 原始值

        Returns:
            规范化后的值
        """
        if value is None:
            return None

        # 处理字符串类型
        if isinstance(value, str):
            # 检查空值标记
            if value.strip() in self.null_values:
                return None

            # 检查异常值标记
            if value.strip() in self.invalid_markers:
                return None

            # 尝试转换为数值
            try:
                # 移除逗号分隔符
                cleaned_value = value.replace(',', '').strip()
                if cleaned_value:
                    # 尝试转换为浮点数
                    return float(cleaned_value)
            except (ValueError, TypeError):
                pass

            # 返回清理后的字符串
            return value.strip()

        # 处理数值类型
        if isinstance(value, (int, float)):
            # 检查异常值
            if value in [-99, -99.0, -999, -999.0]:
                return None
            return value

        return value

    def _parse_timestamp(self, timestamp_value: Any) -> Optional[datetime]:
        """
        解析时间戳

        Args:
            timestamp_value: 时间戳值

        Returns:
            datetime对象，解析失败返回None
        """
        if not timestamp_value:
            return None

        try:
            if isinstance(timestamp_value, datetime):
                return timestamp_value

            if isinstance(timestamp_value, str):
                # 处理范围格式：提取开始时间
                if "~" in timestamp_value:
                    timestamp_value = timestamp_value.split("~")[0].strip()

                # 尝试多种时间格式
                formats = [
                    "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%d",
                    "%Y/%m/%d %H:%M:%S",
                    "%Y/%m/%d"
                ]

                for fmt in formats:
                    try:
                        return datetime.strptime(timestamp_value, fmt)
                    except ValueError:
                        continue

                # 尝试ISO格式
                try:
                    return datetime.fromisoformat(timestamp_value.replace('T', ' '))
                except ValueError:
                    pass

        except Exception as e:
            logger.debug(
                "timestamp_parse_failed",
                value=timestamp_value,
                error=str(e)
            )

        return None

    def _standardize_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准化单条记录

        Args:
            record: 原始记录

        Returns:
            标准化后的记录
        """
        if not isinstance(record, dict):
            return record

        standardized_record = {}
        nested_structures = {}
        vocs_species = {}  # 收集VOCs物种数据
        pm_components = {}  # 收集颗粒物组分数据

        for field_name, field_value in record.items():
            # 跳过None值
            if field_value is None:
                continue

            # 首先检查是否是嵌套结构字段（优先处理）
            if field_name in ["aqi_indices", "aqiIndices", "AQI_indices"]:
                nested_structures["aqi_indices"] = self._standardize_aqi_indices(field_value)
                continue

            if field_name in ["air_quality_status", "airQualityStatus", "Air_quality_status"]:
                nested_structures["air_quality_status"] = self._standardize_air_quality_status(field_value)
                continue

            if field_name in ["meteorological_data", "meteoData", " Meteorological data"]:
                nested_structures["meteorological_data"] = self._standardize_meteorological_data(field_value)
                continue

            # 特殊处理 measurements 字段（UnifiedDataRecord的测量值字段）
            if field_name == "measurements" and isinstance(field_value, dict):
                # 将 measurements 中的污染物字段展开并标准化
                for measurement_key, measurement_value in field_value.items():
                    standard_key = self._get_standard_field_name(measurement_key)
                    # 如果有标准映射，使用标准字段名；否则保留原字段名
                    final_key = standard_key if standard_key else measurement_key
                    normalized_value = self._normalize_value(measurement_value)
                    if normalized_value is not None:
                        standardized_record[final_key] = normalized_value
                continue

            # 特殊处理 metadata 字段（UnifiedDataRecord的元数据字段）
            if field_name == "metadata" and isinstance(field_value, dict):
                # metadata 通常包含非测量类的辅助信息，可以选择保留或标准化
                # 这里选择保留到嵌套结构中
                nested_structures["metadata"] = field_value
                continue

            # 特殊处理 species_data 字段（VOCs物种数据，直接保留不标准化）
            if field_name == "species_data" and isinstance(field_value, dict):
                # species_data 是VOCs特有的嵌套结构，包含物种名称到浓度值的映射
                # 直接保留原样，不进行字段映射或标准化
                standardized_record["species_data"] = field_value
                continue

            # 特殊处理 species 字段（原始VOCs数据格式，需要重命名为species_data）
            if field_name == "species" and isinstance(field_value, dict):
                # species 是原始VOCs数据格式，需要重命名为species_data以符合下游工具期望
                # 直接保留到species_data字段，不进行字段映射或标准化
                standardized_record["species_data"] = field_value
                continue

            # 【修复】特殊处理VOCs物种字段：收集到species字典中
            # VOCs物种字段（乙烷、丙烷、苯、甲苯等）需要聚合到species字典
            # vocs_field_mapping 的 key 是中文或英文名，value 是标准英文名
            # 需要同时检查 key（原始格式）和 value（标准化后格式）
            vocs_keys = set(self.vocs_field_mapping.keys())
            vocs_standard_names = set(self.vocs_field_mapping.values())
            if field_name in vocs_keys or field_name in vocs_standard_names:
                # 获取标准化后的字段名（优先使用映射的 value）
                if field_name in self.vocs_field_mapping:
                    final_key = self.vocs_field_mapping[field_name]
                else:
                    final_key = field_name  # 已经是标准名
                normalized_value = self._normalize_value(field_value)
                if normalized_value is not None:
                    vocs_species[final_key] = normalized_value
                continue

            # 【新增】特殊处理颗粒物组分字段：收集到components字典中
            # 颗粒物组分字段（SO4, NO3, NH4, OC, EC, calcium, potassium等）
            # pm_component_field_mapping 的 key 是中英文名，value 是标准英文名
            # 需要同时检查 key（原始格式）和 value（标准化后格式）
            pm_keys = set(self.pm_component_field_mapping.keys())
            pm_standard_names = set(self.pm_component_field_mapping.values())
            if field_name in pm_keys or field_name in pm_standard_names:
                # 获取标准化后的字段名（优先使用映射的 value）
                if field_name in self.pm_component_field_mapping:
                    final_key = self.pm_component_field_mapping[field_name]
                else:
                    final_key = field_name  # 已经是标准名
                normalized_value = self._normalize_value(field_value)
                if normalized_value is not None:
                    pm_components[final_key] = normalized_value
                continue

            # 获取标准字段名
            standard_field_name = self._get_standard_field_name(field_name)

            # 【调试】记录所有字段的映射情况
            if field_name in ['pM2_5', 'pM10', 'o3', 'nO2', 'co', 'aqi', 'no', 'nOx']:
                logger.debug(
                    "pollutant_field_processing",
                    field_name=field_name,
                    field_value=field_value,
                    standard_field_name=standard_field_name,
                    in_pollutant_mapping=field_name in self.pollutant_field_mapping,
                    in_all_mappings=field_name in self.all_field_mappings
                )

            # 如果找到标准映射，使用标准字段名
            if standard_field_name:
                # 处理特殊的时间字段（保持为字符串，不转换为datetime）
                if standard_field_name == "timestamp":
                    # 直接使用标准化的字符串时间戳，不转换为datetime对象
                    if isinstance(field_value, str):
                        # 清理时间格式：移除T分隔符，标准化为空格
                        cleaned_timestamp = field_value.replace("T", " ").strip()
                        standardized_record["timestamp"] = cleaned_timestamp
                    elif isinstance(field_value, datetime):
                        # 如果已经是datetime，转换为字符串格式
                        standardized_record["timestamp"] = field_value.strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        # 其他类型，尝试规范化
                        normalized_value = self._normalize_value(field_value)
                        if normalized_value is not None:
                            standardized_record["timestamp"] = str(normalized_value)
                    continue

                # 规范化值
                normalized_value = self._normalize_value(field_value)
                if normalized_value is not None:
                    standardized_record[standard_field_name] = normalized_value
                    # 【调试】记录成功标准化的污染物字段
                    if standard_field_name in ['PM2_5', 'PM10', 'O3', 'NO2', 'CO', 'AQI']:
                        logger.debug(
                            "pollutant_standardized_success",
                            original_field=_safe_for_logging(field_name),
                            standard_field=standard_field_name,
                            original_value=field_value,
                            normalized_value=normalized_value
                        )
                else:
                    # 【调试】记录被跳过的污染物字段
                    if field_name in self.pollutant_field_mapping:
                        logger.debug(
                            "pollutant_skipped_null",
                            field_name=_safe_for_logging(field_name),
                            standard_field_name=standard_field_name,
                            field_value=field_value
                        )

            # 【新增】VOCs物种字段兜底收集（当字段不在映射表但值是数值时）
            # VOCs API 返回的是扁平结构：元数据字段 + VOCs物种字段
            # 需要明确排除元数据字段，剩余字段作为VOCs物种收集到species_data
            elif field_name not in self.all_field_mappings:
                # VOCs API 的元数据字段（完整排除列表）
                vocs_metadata_fields = {"Code", "StationName", "TimePoint", "DataType", "TimeType"}
                if field_name in vocs_metadata_fields:
                    # 作为元数据保留在顶层，不收集到species_data
                    # 已经在上面的standard_field_name分支处理过，这里直接跳过
                    continue

                # 检查是否是VOCs物种字段（值可以转换为数字）
                normalized_value = self._normalize_value(field_value)
                if normalized_value is not None and isinstance(normalized_value, (int, float)):
                    # 认为是VOCs物种，保留原字段名（中文）
                    vocs_species[field_name] = normalized_value
                    continue

        # 添加嵌套结构
        if nested_structures:
            standardized_record.update(nested_structures)

        # 【修复】添加VOCs物种数据到species_data字段（符合UnifiedVOCsData规范）
        if vocs_species:
            standardized_record["species_data"] = vocs_species
            logger.debug(
                "vocs_species_aggregated",
                species_count=len(vocs_species),
                species_names=list(vocs_species.keys())[:5]  # 只记录前5个
            )
        else:
            # 【调试】如果没有收集到VOCs物种，减少重复警告
            # 通过实例变量控制，只打印前3条警告，然后打印汇总
            if not hasattr(self, '_vocs_warning_count'):
                self._vocs_warning_count = 0
                self._vocs_warning_total = 0

            self._vocs_warning_total += 1
            if self._vocs_warning_count < 3:
                # 跳过包含Unicode字符的日志，避免Windows GBK编码错误
                try:
                    safe_fields = _safe_for_logging(list(record.keys())[:10])
                    logger.warning(
                        "no_vocs_species_collected",
                        record_fields=safe_fields,
                        vocs_mapping_count=len(self.vocs_field_mapping),
                        warning_index=self._vocs_warning_count + 1
                    )
                except (UnicodeEncodeError, UnicodeDecodeError):
                    # 静默跳过编码错误
                    pass
                self._vocs_warning_count += 1
            elif self._vocs_warning_count == 3:
                # 只在达到阈值时打印一次汇总
                logger.warning(
                    "no_vocs_species_collected_summary",
                    total_empty_records=self._vocs_warning_total,
                    vocs_mapping_count=len(self.vocs_field_mapping),
                    message="后续空species_data记录不再逐条打印警告"
                )
                self._vocs_warning_count += 1  # 确保只打印一次汇总

        # 【新增】添加颗粒物组分数据到components字段（符合UnifiedParticulateData规范）
        if pm_components:
            standardized_record["components"] = pm_components
            logger.debug(
                "pm_components_aggregated",
                components_count=len(pm_components),
                component_names=list(pm_components.keys())[:5]  # 只记录前5个
            )
        else:
            # 【调试】记录为什么pm_components为空
            try:
                logger.debug(
                    "[DEBUG] pm_components为空，检查原始字段",
                    record_fields=_safe_for_logging(list(record.keys())[:20]),
                    pm_mapping_keys=_safe_for_logging(list(self.pm_component_field_mapping.keys())[:10])
                )
            except (UnicodeEncodeError, UnicodeDecodeError):
                # 静默跳过编码错误
                pass
            # 【新增】检测嵌套的测量值字典（颗粒物API返回的嵌套结构）
            # 例如：{station_code: 'xxx', 'a': {'PM₂.₅': 24.0, 'PM₁₀': 30.0}}
            # 需要检测并提取这些嵌套的测量值
            for key, value in record.items():
                if key in standardized_record:
                    continue  # 跳过已处理的字段
                if isinstance(value, dict):
                    # 检查这个嵌套字典是否包含测量值
                    measurement_count = 0
                    pm_measurement_count = 0
                    for nested_key, nested_value in value.items():
                        if nested_key in self.pollutant_field_mapping or \
                           nested_key in self.pm_component_field_mapping or \
                           self._get_standard_field_name(nested_key):
                            measurement_count += 1
                            if nested_key in self.pm_component_field_mapping:
                                pm_measurement_count += 1
                        # 检查 Unicode 下标格式
                        if '₅' in nested_key or '₁' in nested_key or '₂' in nested_key:
                            measurement_count += 1

                    # 如果嵌套字典包含多个测量值，认为是测量值字典
                    if measurement_count >= 2:
                        logger.debug(
                            "nested_measurement_dict_detected",
                            key=_safe_for_logging(key),
                            measurement_count=measurement_count,
                            pm_measurement_count=pm_measurement_count
                        )
                        # 提取测量值
                        for nested_key, nested_value in value.items():
                            # 标准化嵌套键名
                            standard_nested_key = self._get_standard_field_name(nested_key)
                            final_nested_key = standard_nested_key if standard_nested_key else nested_key
                            normalized_value = self._normalize_value(nested_value)
                            if normalized_value is not None:
                                if pm_measurement_count > 0 and nested_key in self.pm_component_field_mapping:
                                    # 颗粒物组分收集到components
                                    pm_final_key = self.pm_component_field_mapping.get(nested_key, final_nested_key)
                                    pm_components[pm_final_key] = normalized_value
                                else:
                                    # 其他测量值直接放到顶层
                                    standardized_record[final_nested_key] = normalized_value

                        # 如果提取了颗粒物组分，添加到components
                        if pm_components:
                            standardized_record["components"] = pm_components
                            logger.debug(
                                "pm_components_extracted_from_nested",
                                count=len(pm_components)
                            )
                        break  # 只处理第一个嵌套测量值字典

        # 【UDF v2.0格式转换】将扁平的污染物字段转换为measurements嵌套结构
        # 符合UnifiedDataRecord规范，确保污染物数据不丢失
        # logger.info(
        #     "udf_v2_conversion_start",
        #     input_fields=list(standardized_record.keys())[:20],
        #     has_PM2_5="PM2_5" in standardized_record,
        #     has_PM10="PM10" in standardized_record,
        #     has_measurements="measurements" in standardized_record
        # )
        standardized_record = self._convert_to_udf_v2_format(standardized_record)

        # logger.info(
        #     "udf_v2_conversion_complete",
        #     output_fields=list(standardized_record.keys())[:20],
        #     has_measurements="measurements" in standardized_record,
        #     measurements_count=len(standardized_record.get("measurements", {})),
        #     measurement_fields=list(standardized_record.get("measurements", {}).keys())[:15]
        # )

        return standardized_record

    def _convert_to_udf_v2_format(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        转换为UDF v2.0标准格式 (UnifiedDataRecord兼容)

        将扁平结构转换为UnifiedDataRecord期望的嵌套结构:
        - 污染物字段 → measurements
        - 元数据字段 → 保留在顶层
        - 原始字段 → original_fields (备份)

        这样可以确保在Pydantic反序列化时，污染物数据不会丢失到extra字段

        Args:
            record: 标准化后的记录（扁平结构）

        Returns:
            符合UDF v2.0规范的嵌套结构
        """
        # 定义顶层字段（不放入measurements，保留在顶层）
        TOP_LEVEL_FIELDS = {
            'timestamp', 'station_name', 'station_code', 'city', 'city_code',
            'lat', 'lon', 'latitude', 'longitude',
            'data_type', 'record_id', 'created_time', 'modified_time',
            'species_data', 'components', 'metadata', 'dimensions',
            'station_type', 'district', 'province', 'country'
        }

        # 定义污染物字段（应该放入measurements）
        # 包括常规污染物、AQI、IAQI等
        POLLUTANT_FIELDS = {
            # 常规污染物（标准字段名）
            'PM2_5', 'PM10', 'O3', 'NO2', 'SO2', 'CO', 'NO', 'NOx',
            # AQI和IAQI
            'AQI', 'IAQI', 'PM2_5_IAQI', 'PM10_IAQI', 'O3_IAQI',
            'SO2_IAQI', 'NO2_IAQI', 'CO_IAQI',
            # 气象要素（也放入measurements）
            'temperature', 'temperature_2m', 'humidity', 'relative_humidity_2m',
            'wind_speed', 'wind_speed_10m', 'wind_direction', 'wind_direction_10m',
            'pressure', 'surface_pressure', 'dew_point', 'dew_point_2m'
        }

        measurements = {}
        top_level_data = {}
        original_fields = {}

        logger.debug(
            "udf_v2_classifying_fields",
            total_fields=len(record),
            top_level_count=len(TOP_LEVEL_FIELDS),
            pollutant_count=len(POLLUTANT_FIELDS)
        )

        for field, value in record.items():
            # 备份原始字段（用于调试和向后兼容）
            if value is not None:
                original_fields[field] = value

            # 分类处理
            if field in TOP_LEVEL_FIELDS:
                # 顶层字段：直接保留
                top_level_data[field] = value
            elif field in POLLUTANT_FIELDS:
                # 污染物字段：放入measurements
                measurements[field] = value
                logger.debug(
                    "udf_v2_field_to_measurements",
                    field=field,
                    value=value
                )
            elif field.startswith('PM') or field in self.pollutant_field_mapping.values():
                # 动态检测其他污染物字段（如PM2_5_24h, O3_8h等）
                measurements[field] = value
                logger.debug(
                    "udf_v2_dynamic_pollutant_detected",
                    field=field,
                    value=value
                )
            else:
                # 其他字段：保留在顶层（兼容性考虑）
                top_level_data[field] = value

        # 构建v2.0格式记录
        v2_record = {**top_level_data}

        # 添加measurements字段（如果有污染物数据）
        if measurements:
            v2_record['measurements'] = measurements

            # logger.info(
            #     "udf_v2_measurements_created",
            #     measurements_count=len(measurements),
            #     measurement_fields=list(measurements.keys())[:15]  # 只记录前15个
            # )

        # 添加原始字段备份（可选，用于调试）
        # 为了节省空间，只在有extra字段时才备份
        extra_fields = set(record.keys()) - TOP_LEVEL_FIELDS - POLLUTANT_FIELDS
        if extra_fields and original_fields:
            v2_record['original_fields'] = {
                k: v for k, v in original_fields.items()
                if k in extra_fields
            }
            logger.debug(
                "udf_v2_original_fields_backup",
                backup_count=len(v2_record['original_fields'])
            )

        return v2_record

    def _standardize_aqi_indices(self, aqi_data: Any) -> Optional[Dict[str, Any]]:
        """标准化AQI分指数数据"""
        if not isinstance(aqi_data, dict):
            return None

        standardized = {}
        for key, value in aqi_data.items():
            standard_key = self._get_standard_field_name(key)
            if standard_key and standard_key.endswith("_IAQI"):
                normalized_value = self._normalize_value(value)
                if normalized_value is not None:
                    standardized[standard_key] = normalized_value

        return standardized if standardized else None

    def _standardize_air_quality_status(self, status_data: Any) -> Optional[Dict[str, Any]]:
        """标准化空气质量状态数据"""
        if not isinstance(status_data, dict):
            return None

        standardized = {}
        for key, value in status_data.items():
            standard_key = self._get_standard_field_name(key)
            if standard_key:
                normalized_value = self._normalize_value(value)
                if normalized_value is not None:
                    standardized[standard_key] = normalized_value

        return standardized if standardized else None

    def _standardize_meteorological_data(self, weather_data: Any) -> Optional[Dict[str, Any]]:
        """标准化气象数据"""
        if not isinstance(weather_data, dict):
            return None

        standardized = {}
        for key, value in weather_data.items():
            standard_key = self._get_standard_field_name(key)
            if standard_key:
                normalized_value = self._normalize_value(value)
                if normalized_value is not None:
                    standardized[standard_key] = normalized_value

        return standardized if standardized else None

    def standardize(self, data: Union[List[Dict[str, Any]], Dict[str, Any]]) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        """
        标准化数据

        Args:
            data: 输入数据（单条记录或记录列表）

        Returns:
            标准化后的数据
        """
        logger.debug(
            "data_standardization_start",
            input_type=type(data).__name__,
            is_list=isinstance(data, list)
        )

        try:
            # 处理单条记录
            if isinstance(data, dict):
                standardized = self._standardize_record(data)
                logger.debug(
                    "data_standardization_single_record_complete",
                    input_fields=len(data),
                    output_fields=len(standardized)
                )
                return standardized

            # 处理记录列表
            elif isinstance(data, list):
                standardized_list = []
                for i, record in enumerate(data):
                    if isinstance(record, dict):
                        standardized_record = self._standardize_record(record)
                        if standardized_record:  # 只保留非空记录
                            standardized_list.append(standardized_record)
                    else:
                        logger.warning(
                            "data_standardization_skip_invalid_record",
                            index=i,
                            record_type=type(record).__name__
                        )

                logger.info(
                    "data_standardization_list_complete",
                    input_count=len(data),
                    output_count=len(standardized_list)
                )
                return standardized_list

            else:
                logger.warning(
                    "data_standardization_unsupported_type",
                    data_type=type(data).__name__
                )
                return data

        except Exception as e:
            # 不使用exc_info=True，避免Unicode字符导致的编码错误
            logger.error(
                "data_standardization_failed",
                error=str(e),
                error_type=type(e).__name__
            )
            return data

    def get_field_mapping_info(self) -> Dict[str, int]:
        """
        获取字段映射信息

        Returns:
            各类型字段映射数量统计
        """
        return {
            "time_fields": len(self.time_field_mapping),
            "station_fields": len(self.station_field_mapping),
            "coordinate_fields": len(self.coordinate_field_mapping),
            "pollutant_fields": len(self.pollutant_field_mapping),
            "aqi_fields": len(self.aqi_field_mapping),
            "iaqi_fields": len(self.iaqi_field_mapping),
            "vocs_fields": len(self.vocs_field_mapping),
            "pm_component_fields": len(self.pm_component_field_mapping),
            "meteorological_fields": len(self.meteorological_field_mapping),
            "metadata_fields": len(self.metadata_field_mapping),
            "quality_level_fields": len(self.quality_level_mapping),  # 新增
            "ranking_fields": len(self.ranking_mapping),  # 新增
            "common_fields": len(self.common_field_mapping),
            "total_mappings": len(self.all_field_mappings)
        }

    def get_standard_field_name(self, field_name: str) -> Optional[str]:
        """
        获取字段的标准名称（公共方法）

        这是项目的统一字段名获取接口，所有代码都应该使用此方法
        来获取标准字段名，而不是硬编码字段名。

        Args:
            field_name: 原始字段名（任意格式：PM2.5, pm2.5, PM2_5等）

        Returns:
            标准字段名（如：PM2_5, PM10, O3等），如果未找到则返回None

        Examples:
            >>> standardizer = DataStandardizer()
            >>> standardizer.get_standard_field_name("PM2.5")
            'PM2_5'
            >>> standardizer.get_standard_field_name("pm2.5")
            'PM2_5'
            >>> standardizer.get_standard_field_name("臭氧(O₃)")
            'O3'
        """
        return self._get_standard_field_name(field_name)

    def get_measurement_value(self, measurements: Dict[str, Any], field_name: str) -> Optional[Any]:
        """
        从measurements字典中获取指定字段的值（自动处理字段映射）

        这是项目的统一数据获取接口，自动处理字段名映射。

        Args:
            measurements: measurements字典（已标准化的数据）
            field_name: 字段名（任意格式，会自动转换为标准字段名）

        Returns:
            字段值，如果字段不存在则返回None

        Examples:
            >>> measurements = {"PM2_5": 65.0, "O3": 45.0}
            >>> standardizer = DataStandardizer()
            >>> standardizer.get_measurement_value(measurements, "PM2.5")
            65.0
            >>> standardizer.get_measurement_value(measurements, "pm2.5")
            65.0
        """
        if not measurements or not field_name:
            return None

        # 获取标准字段名
        standard_field = self.get_standard_field_name(field_name)

        if standard_field:
            return measurements.get(standard_field)

        # 如果找不到映射，尝试直接查找
        return measurements.get(field_name)

    def add_custom_mapping(self, original_field: str, standard_field: str):
        """
        添加自定义字段映射

        Args:
            original_field: 原始字段名
            standard_field: 标准字段名
        """
        self.all_field_mappings[original_field] = standard_field
        logger.info(
            "custom_field_mapping_added",
            original=original_field,
            standard=standard_field
        )


# 创建全局标准化器实例
_data_standardizer = None


def get_data_standardizer() -> DataStandardizer:
    """
    获取全局数据标准化器实例（单例模式）

    Returns:
        DataStandardizer实例
    """
    global _data_standardizer
    if _data_standardizer is None:
        _data_standardizer = DataStandardizer()
    return _data_standardizer


# 便利函数
def standardize_data(data: Union[List[Dict[str, Any]], Dict[str, Any]]) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    """
    标准化数据的便利函数

    Args:
        data: 输入数据

    Returns:
        标准化后的数据
    """
    standardizer = get_data_standardizer()
    return standardizer.standardize(data)


def add_field_mapping(original_field: str, standard_field: str):
    """
    添加字段映射的便利函数

    Args:
        original_field: 原始字段名
        standard_field: 标准字段名
    """
    standardizer = get_data_standardizer()
    standardizer.add_custom_mapping(original_field, standard_field)


# ============================================================================
# 便利函数 - 简化字段映射操作
# ============================================================================

def get_standard_field_name(field_name: str) -> Optional[str]:
    """
    获取字段的标准名称（便利函数）

    这是项目的统一字段名获取接口，所有代码都应该使用此函数
    来获取标准字段名，而不是硬编码字段名。

    Args:
        field_name: 原始字段名（任意格式：PM2.5, pm2.5, PM2_5等）

    Returns:
        标准字段名（如：PM2_5, PM10, O3等），如果未找到则返回None

    Examples:
        >>> from app.utils.data_standardizer import get_standard_field_name
        >>> get_standard_field_name("PM2.5")
        'PM2_5'
        >>> get_standard_field_name("pm2.5")
        'PM2_5'
        >>> get_standard_field_name("臭氧(O₃)")
        'O3'
    """
    standardizer = get_data_standardizer()
    return standardizer.get_standard_field_name(field_name)


def get_measurement_value(measurements: Dict[str, Any], field_name: str) -> Optional[Any]:
    """
    从measurements字典中获取指定字段的值（自动处理字段映射）

    这是项目的统一数据获取接口，自动处理字段名映射。

    Args:
        measurements: measurements字典（已标准化的数据）
        field_name: 字段名（任意格式，会自动转换为标准字段名）

    Returns:
        字段值，如果字段不存在则返回None

    Examples:
        >>> from app.utils.data_standardizer import get_measurement_value
        >>> measurements = {"PM2_5": 65.0, "O3": 45.0}
        >>> get_measurement_value(measurements, "PM2.5")
        65.0
        >>> get_measurement_value(measurements, "pm2.5")
        65.0
    """
    standardizer = get_data_standardizer()
    return standardizer.get_measurement_value(measurements, field_name)


# 使用示例
if __name__ == "__main__":
    # 测试数据
    test_data = [
        {
            "时间点": "2025-11-01T00:00:00",
            "城市名称": "广州市",
            "pM2_5": "22",
            "PM10": "35",
            "o3": "93",
            "nO2": "18",
            "aqi": "25",
            "primaryPollutant": null
        },
        {
            "timePoint": "2025-11-01T01:00:00",
            "cityName": "深圳市",
            "PM2.5": "28",
            "PM10": "40",
            "O3": "88",
            "NO2": "22"
        }
    ]

    # 标准化数据
    standardized = standardize_data(test_data)

    print("标准化结果:")
    for record in standardized:
        print(f"  {record}")
