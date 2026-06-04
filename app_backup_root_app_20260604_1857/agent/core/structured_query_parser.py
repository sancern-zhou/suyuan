"""
结构化查询解析器 (StructuredQueryParser)

职责：将用户自然语言查询解析为结构化参数

解析流程：
1. LLM提取关键信息（地点、时间、污染物、分析类型）
2. 地点名称 → 经纬度映射（通过站点库）
3. 时间表达式 → 标准时间格式
4. 返回结构化结果
"""

from typing import Optional, List, Tuple, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import json
import re
import os
import structlog

from app.services.llm_service import llm_service

logger = structlog.get_logger()

# 站点信息文件路径（使用绝对路径，backend/data/station_info.json）
import pathlib
# __file__ = backend/app/agent/core/xxx.py, 需要向上4级到backend目录
STATION_INFO_FILE = str(pathlib.Path(__file__).resolve().parents[3] / "data" / "station_info.json")


class StructuredQuery(BaseModel):
    """结构化查询结果"""
    # 地理信息
    location: Optional[str] = Field(None, description="地点名称")
    lat: Optional[float] = Field(None, description="纬度")
    lon: Optional[float] = Field(None, description="经度")
    station_code: Optional[str] = Field(None, description="站点编码")

    # 时间信息
    start_time: Optional[str] = Field(None, description="开始时间 YYYY-MM-DD HH:mm:ss")
    end_time: Optional[str] = Field(None, description="结束时间 YYYY-MM-DD HH:mm:ss")
    time_granularity: str = Field("hourly", description="时间粒度: hourly/daily")

    # 分析目标
    pollutants: List[str] = Field(default_factory=list, description="污染物列表")

    # 原始查询
    original_query: str = Field("", description="原始查询文本")

    # 解析置信度
    parse_confidence: float = Field(0.0, description="解析置信度 0-1")

    # EKMA分析精度模式
    precision: str = Field('standard', description="EKMA分析精度模式: fast(快速筛查,约18秒), standard(标准分析,约3分钟), full(完整分析,约7-10分钟)")

    # 查询级别（城市级 vs 站点级）
    is_city_level_query: bool = Field(False, description="是否为城市级查询：true表示查询整个城市，false表示查询具体站点")


# 城市坐标映射表（常用城市）
CITY_COORDINATES = {
    "北京": (39.9042, 116.4074),
    "上海": (31.2304, 121.4737),
    "广州": (23.1291, 113.2644),
    "深圳": (22.5431, 114.0579),
    "肇庆": (23.0469, 112.4651),
    "佛山": (23.0218, 113.1219),
    "东莞": (23.0430, 113.7633),
    "珠海": (22.2710, 113.5767),
    "中山": (22.5176, 113.3926),
    "惠州": (23.1116, 114.4158),
    "江门": (22.5789, 113.0815),
    "清远": (23.6820, 113.0560),
    "韶关": (24.8108, 113.5975),
    "河源": (23.7463, 114.7007),
    "梅州": (24.2886, 116.1226),
    "汕头": (23.3535, 116.6819),
    "潮州": (23.6567, 116.6224),
    "揭阳": (23.5499, 116.3728),
    "汕尾": (22.7745, 115.3643),
    "阳江": (21.8579, 111.9822),
    "茂名": (21.6632, 110.9254),
    "湛江": (21.2707, 110.3594),
    "云浮": (22.9379, 112.0444),
}

# 污染物别名映射
POLLUTANT_ALIASES = {
    "臭氧": "O3",
    "ozone": "O3",
    "pm2.5": "PM2.5",
    "pm25": "PM2.5",
    "细颗粒物": "PM2.5",
    "pm10": "PM10",
    "可吸入颗粒物": "PM10",
    "二氧化氮": "NO2",
    "no2": "NO2",
    "二氧化硫": "SO2",
    "so2": "SO2",
    "一氧化碳": "CO",
    "co": "CO",
    "vocs": "VOCs",
    "挥发性有机物": "VOCs",
}


class StationInfo(BaseModel):
    """站点信息"""
    station_code: str = Field(..., description="站点唯一编码")
    station_name: str = Field(..., description="站点名称")
    lat: float = Field(..., description="纬度")
    lon: float = Field(..., description="经度")
    city: str = Field(..., description="城市名称")


# 广东省城市列表（用于周边城市查询）
GUANGDONG_CITIES = [
    "广州", "深圳", "佛山", "东莞", "惠州",
    "珠海", "中山", "江门", "肇庆",
    "汕头", "揭阳", "潮州", "汕尾",
    "湛江", "茂名", "阳江",
    "韶关", "清远", "河源", "梅州", "云浮"
]


def load_station_info() -> List[StationInfo]:
    """加载站点信息文件"""
    stations = []
    try:
        with open(STATION_INFO_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            results = data.get("results", [])
            for item in results:
                stations.append(StationInfo(
                    station_code=item.get("唯一编码", ""),
                    station_name=item.get("站点名称", ""),
                    lat=float(item.get("纬度", 0) or 0),
                    lon=float(item.get("经度", 0) or 0),
                    city=item.get("城市名称", "")
                ))
        logger.info("station_info_loaded", count=len(stations))
    except Exception as e:
        logger.error("station_info_load_failed", error=str(e))
    return stations


class StructuredQueryParser:
    """结构化查询解析器"""

    # 类级别缓存站点信息（所有实例共享）
    _station_cache: Optional[List[StationInfo]] = None

    def __init__(self):
        self.city_coords = CITY_COORDINATES
        self.pollutant_aliases = POLLUTANT_ALIASES
        # 加载站点信息（使用缓存）
        self.stations = self._get_station_info()
        logger.info("structured_query_parser_initialized", station_count=len(self.stations))

    @classmethod
    def _get_station_info(cls) -> List[StationInfo]:
        """获取站点信息（带缓存）"""
        if cls._station_cache is None:
            cls._station_cache = load_station_info()
        return cls._station_cache

    def get_stations_by_city(self, city: str) -> List[StationInfo]:
        """获取指定城市的所有站点"""
        city_clean = city.replace("市", "")
        return [s for s in self.stations if city_clean in s.city]

    def get_station_by_code(self, station_code: str) -> Optional[StationInfo]:
        """根据站点编码获取站点信息"""
        for station in self.stations:
            if station.station_code == station_code:
                return station
        return None

    def get_station_by_name(self, station_name: str) -> Optional[StationInfo]:
        """根据站点名称获取站点信息"""
        name_normalized = station_name.replace("站", "").replace("监测点", "")
        for station in self.stations:
            station_name_normalized = station.station_name.replace("站", "").replace("监测点", "")
            if station_name_normalized == name_normalized or station.station_name == station_name:
                return station
        return None

    def get_cities_with_stations(self) -> List[str]:
        """获取所有有站点的城市列表"""
        cities = set()
        for station in self.stations:
            cities.add(station.city)
        return sorted(list(cities))

    def _find_matching_stations(self, query: str) -> List[Dict[str, Any]]:
        """在查询中查找匹配的站点信息

        Args:
            query: 用户查询文本

        Returns:
            匹配的站点信息列表，每个包含station_code, station_name, lat, lon, city
        """
        matched = []
        query_normalized = query.replace("站", "").replace("监测点", "")

        for station in self.stations:
            # 匹配站点名称
            station_name_normalized = station.station_name.replace("站", "").replace("监测点", "")
            if (station_name_normalized in query_normalized or
                station.station_name in query or
                station_name_normalized in query):
                if station.station_code not in [s["station_code"] for s in matched]:
                    matched.append({
                        "station_code": station.station_code,
                        "station_name": station.station_name,
                        "lat": station.lat,
                        "lon": station.lon,
                        "city": station.city
                    })
                    logger.info(
                        "station_matched_by_name",
                        station_name=station.station_name,
                        station_code=station.station_code
                    )
                    continue

            # 匹配城市
            if station.city in query and station.station_code not in [s["station_code"] for s in matched]:
                matched.append({
                    "station_code": station.station_code,
                    "station_name": station.station_name,
                    "lat": station.lat,
                    "lon": station.lon,
                    "city": station.city
                })

        return matched

    async def parse(self, query: str) -> StructuredQuery:
        """
        解析用户查询为结构化格式

        Args:
            query: 用户自然语言查询

        Returns:
            StructuredQuery: 结构化查询结果
        """
        logger.info("parsing_query", query=query[:100])

        # 0. 预先匹配站点信息
        matched_stations = self._find_matching_stations(query)
        logger.info("pre_matched_stations", count=len(matched_stations))

        # 1. 使用LLM提取关键信息（传入匹配的站点信息）
        extracted = await self._llm_extract(query, matched_stations)

        # 2. 解析地点 → 经纬度和站点编码
        llm_station_code = extracted.get("station_code")
        lat, lon = None, None

        # 如果LLM返回了station_code，从matched_stations中获取对应坐标
        if llm_station_code:
            for s in matched_stations:
                if s["station_code"] == llm_station_code:
                    lat, lon = s["lat"], s["lon"]
                    logger.info(
                        "station_code_resolved",
                        station_code=llm_station_code,
                        station_name=s["station_name"],
                        lat=lat,
                        lon=lon
                    )
                    break
            if lat is None:
                logger.warning("station_code_not_in_matched", station_code=llm_station_code)

        # 如果没有找到站点坐标，尝试城市匹配
        if lat is None or lon is None:
            lat, lon, _ = self._resolve_location(extracted.get("location", ""))

        station_code = llm_station_code
        
        # 3. 解析时间表达式
        start_time, end_time = self._parse_time_expression(
            extracted.get("time_start"),
            extracted.get("time_end"),
            extracted.get("time_expression")
        )
        
        # 4. 标准化污染物名称
        pollutants = self._normalize_pollutants(extracted.get("pollutants", []))

        # 5. 计算解析置信度
        confidence = self._calculate_confidence(lat, lon, start_time, pollutants)

        result = StructuredQuery(
            location=extracted.get("location"),
            lat=lat,
            lon=lon,
            station_code=station_code,
            start_time=start_time,
            end_time=end_time,
            time_granularity=extracted.get("time_granularity", "hourly"),
            pollutants=pollutants,
            original_query=query,
            parse_confidence=confidence,
            is_city_level_query=extracted.get("is_city_level_query", False)
        )

        logger.info(
            "query_parsed",
            location=result.location,
            station_code=result.station_code,
            lat=result.lat,
            lon=result.lon,
            start_time=result.start_time,
            end_time=result.end_time,
            pollutants=result.pollutants,
            confidence=result.parse_confidence
        )

        return result
    
    async def _llm_extract(self, query: str, matched_stations: List[Dict] = None) -> Dict[str, Any]:
        """使用LLM提取查询中的关键信息

        Args:
            query: 用户查询文本
            matched_stations: 预先匹配到的站点信息列表
        """
        # 构建站点信息上下文
        stations_context = ""
        if matched_stations:
            stations_info = []
            for s in matched_stations:
                stations_info.append(
                    f"- 站点名称: {s['station_name']}, 编码: {s['station_code']}, "
                    f"经纬度: ({s['lat']}, {s['lon']}), 城市: {s['city']}"
                )
            stations_context = f"\n\n### 站点参考信息（用户查询中可能涉及的站点）:\n" + "\n".join(stations_info)

        prompt = f"""你是查询解析助手。请从用户查询中提取以下信息。

用户查询: {query}

当前时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}{stations_context}

请返回JSON格式:
{{
    "location": "地点名称（城市/站点），如：肇庆市、广州天河站，没有则为null",
    "station_code": "站点ID（唯一编码），如：1025b，只能从上面的站点参考信息中选择最匹配的站点编码，没有匹配站点则为null",
    "time_start": "开始时间，格式YYYY-MM-DD，如果是相对时间请转换为绝对时间，没有则为null",
    "time_end": "结束时间，格式YYYY-MM-DD，没有则为null",
    "time_expression": "原始时间表达式，如：昨天、最近三天、上周",
    "time_granularity": "时间粒度：hourly(小时)/daily(天)",
    "pollutants": ["污染物列表，如：O3, PM2.5, VOCs"],
    "is_city_level_query": true或false，true表示查询整个城市（如"阳江市"），false表示查询具体监测站点（如"阳江站"）
}}

重要时间计算规则（必须根据当前时间推算）：
- 当前时间是 {datetime.now().strftime("%Y-%m-%d")}
- 如果用户说"X月X日"（如"12月24日"），默认使用当前年份（如2025-12-24）
- 如果用户说"去年X月X日"或"前年X月X日"，才使用过去年份
- 如果用户说"昨天"，时间范围是 前一天00:00:00 到 前一天23:59:59
- 如果用户说"最近N天"，时间范围是 N天前00:00:00 到 今天现在时刻
- 如果没有明确时间，默认为最近1天（昨天到今天）

污染物使用标准名称：O3, PM2.5, PM10, NO2, SO2, CO, VOCs
station_id必须从上面的站点参考信息中选取精确匹配的编码
is_city_level_query判断规则：
- 用户查询的是城市名（如"阳江市"、"广州"）→ is_city_level_query=true
- 用户查询的是站点名（如"阳江站"、"广州天河站"）→ is_city_level_query=false

只返回JSON，不要其他内容。"""

        try:
            response = await llm_service.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            
            # 解析JSON响应
            extracted = self._parse_json_response(response)
            if extracted:
                return extracted
            
        except Exception as e:
            logger.error("llm_extract_failed", error=str(e))
        
        # 降级：使用正则提取
        return self._regex_extract(query)
    
    def _regex_extract(self, query: str) -> Dict[str, Any]:
        """正则提取（LLM失败时的降级方案）"""
        # 判断是否为城市级查询（location不包含"站"或"监测点"）
        is_city_level = "站" not in query and "监测点" not in query

        result = {
            "location": None,
            "station_code": None,
            "time_start": None,
            "time_end": None,
            "time_expression": None,
            "pollutants": [],
            "is_city_level_query": is_city_level
        }
        
        # 提取城市
        for city in self.city_coords.keys():
            if city in query:
                result["location"] = city
                break
        
        # 提取污染物
        query_lower = query.lower()
        for alias, standard in self.pollutant_aliases.items():
            if alias in query_lower:
                if standard not in result["pollutants"]:
                    result["pollutants"].append(standard)
        
        # 提取时间（简单模式）
        today = datetime.now()
        if "昨天" in query:
            yesterday = today - timedelta(days=1)
            result["time_start"] = yesterday.strftime("%Y-%m-%d")
            result["time_end"] = yesterday.strftime("%Y-%m-%d")
        elif "今天" in query:
            result["time_start"] = today.strftime("%Y-%m-%d")
            result["time_end"] = today.strftime("%Y-%m-%d")
        
        # 提取日期格式
        date_pattern = r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?)'
        dates = re.findall(date_pattern, query)
        if len(dates) >= 2:
            result["time_start"] = self._normalize_date(dates[0])
            result["time_end"] = self._normalize_date(dates[1])
        elif len(dates) == 1:
            result["time_start"] = self._normalize_date(dates[0])
            result["time_end"] = result["time_start"]

        return result
    
    def _normalize_date(self, date_str: str) -> str:
        """标准化日期格式"""
        # 替换中文分隔符
        date_str = date_str.replace("年", "-").replace("月", "-").replace("日", "")
        date_str = date_str.replace("/", "-")
        
        # 尝试解析
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return date_str
    
    def _resolve_location(self, location: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        """解析地点名称为经纬度和站点ID"""
        if not location:
            return None, None, None
        
        # 1. 尝试匹配城市
        for city, coords in self.city_coords.items():
            if city in location:
                return coords[0], coords[1], None
        
        # 2. TODO: 查询站点库获取站点坐标
        # 这里需要接入站点库
        
        logger.warning("location_not_resolved", location=location)
        return None, None, None
    
    def _parse_time_expression(
        self, 
        time_start: Optional[str], 
        time_end: Optional[str],
        time_expression: Optional[str]
    ) -> Tuple[Optional[str], Optional[str]]:
        """解析时间表达式"""
        
        today = datetime.now()
        
        # 如果已有明确的起止时间
        if time_start and time_end:
            formatted_start = self._format_datetime(time_start, is_start=True)
            formatted_end = self._format_datetime(time_end, is_start=False)
            return formatted_start, formatted_end
        
        # 解析相对时间表达式
        if time_expression:
            expr = time_expression.lower()
            
            if "昨天" in expr:
                yesterday = today - timedelta(days=1)
                return (
                    yesterday.strftime("%Y-%m-%d 00:00:00"),
                    yesterday.strftime("%Y-%m-%d 23:59:59")
                )
            
            if "今天" in expr:
                return (
                    today.strftime("%Y-%m-%d 00:00:00"),
                    today.strftime("%Y-%m-%d %H:%M:%S")
                )
            
            if "最近" in expr:
                # 提取天数
                match = re.search(r'(\d+)\s*[天日]', expr)
                if match:
                    days = int(match.group(1))
                    start = today - timedelta(days=days)
                    return (
                        start.strftime("%Y-%m-%d 00:00:00"),
                        today.strftime("%Y-%m-%d %H:%M:%S")
                    )
            
            if "上周" in expr:
                # 计算上周的起止日期
                days_since_monday = today.weekday()
                last_monday = today - timedelta(days=days_since_monday + 7)
                last_sunday = last_monday + timedelta(days=6)
                return (
                    last_monday.strftime("%Y-%m-%d 00:00:00"),
                    last_sunday.strftime("%Y-%m-%d 23:59:59")
                )
        
        # 默认：最近1天
        if not time_start:
            yesterday = today - timedelta(days=1)
            return (
                yesterday.strftime("%Y-%m-%d 00:00:00"),
                today.strftime("%Y-%m-%d %H:%M:%S")
            )
        
        return self._format_datetime(time_start, is_start=True), self._format_datetime(time_end, is_start=False)
    
    def _format_datetime(self, dt_str: Optional[str], is_start: bool = True) -> Optional[str]:
        """格式化日期时间字符串
        
        Args:
            dt_str: 日期时间字符串
            is_start: 是否为开始时间，用于确定只有日期时补充的时间部分
        """
        if not dt_str:
            return None
        
        # 如果只有日期，补充时间
        if len(dt_str) == 10:  # YYYY-MM-DD
            # 开始时间用00:00:00，结束时间用23:59:59
            time_suffix = "00:00:00" if is_start else "23:59:59"
            return f"{dt_str} {time_suffix}"
        
        return dt_str
    
    def _normalize_pollutants(self, pollutants: List[str]) -> List[str]:
        """标准化污染物名称"""
        result = []
        for p in pollutants:
            p_lower = p.lower().strip()
            if p_lower in self.pollutant_aliases:
                standard = self.pollutant_aliases[p_lower]
            else:
                standard = p.upper()
            
            if standard not in result:
                result.append(standard)
        
        return result
    
    def _calculate_confidence(
        self,
        lat: Optional[float],
        lon: Optional[float],
        start_time: Optional[str],
        pollutants: List[str]
    ) -> float:
        """计算解析置信度"""
        score = 0.0
        
        # 有经纬度 +0.3
        if lat is not None and lon is not None:
            score += 0.3
        
        # 有时间 +0.3
        if start_time:
            score += 0.3
        
        # 有污染物 +0.2
        if pollutants:
            score += 0.2
        
        # 基础分 +0.2
        score += 0.2
        
        return min(score, 1.0)
    
    def _parse_json_response(self, response: str) -> Optional[Dict]:
        """解析LLM的JSON响应"""
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        
        # 尝试提取JSON代码块
        if "```json" in response:
            start = response.find("```json") + 7
            end = response.find("```", start)
            if end > start:
                try:
                    return json.loads(response[start:end].strip())
                except json.JSONDecodeError:
                    pass
        
        # 尝试提取花括号内容
        start = response.find("{")
        end = response.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(response[start:end+1])
            except json.JSONDecodeError:
                pass
        
        return None
