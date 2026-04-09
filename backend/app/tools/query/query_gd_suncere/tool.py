"""
广东省 Suncere 常规数据查询工具

使用官方 API 查询广东省空气质量监测数据
支持城市日报、站点小时数据、统计报表等多种查询方式

参考 Vanna 项目实现：
- 城市/站点名称自动映射到编码
- LLM 驱动的结构化参数查询
"""
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
import structlog
import json
from pathlib import Path

from app.services.gd_suncere_api_client import get_gd_suncere_api_client
from app.agent.context.execution_context import ExecutionContext
from app.utils.data_standardizer import get_data_standardizer


logger = structlog.get_logger()


class GeoMappingResolver:
    """
    地理位置映射解析器

    提供：
    1. 城市名称 → 城市编码映射
    2. 站点名称 → 站点编码映射
    3. 区域名称 → 区域编码映射
    4. 城市名称 → 下辖站点编码列表映射
    5. 区县名称 → 下辖站点编码列表映射
    6. 站点类型过滤功能（国控/省控/市控等）

    站点数据来源：
    - station_district_results_with_type_id.json：376个站点，含城市/区县归属
    """

    # 站点类型映射常量
    STATION_TYPE_MAP = {
        "国控": 1.0,
        "省控": 2.0,
        "市控": 3.0,
        "1.0": 1.0, "2.0": 2.0, "3.0": 3.0,
        "4.0": 4.0, "5.0": 5.0, "6.0": 6.0,
        "7.0": 7.0, "8.0": 8.0, "9.0": 9.0, "15.0": 15.0,
    }

    # 类变量，用于缓存从 JSON 加载的站点数据
    _station_data_loaded = False
    _station_code_map_from_json: Dict[str, str] = {}           # 站点名 -> 站点编码
    _city_stations_map_from_json: Dict[str, List[str]] = {}    # 城市短名 -> 站点编码列表
    _district_stations_map_from_json: Dict[str, List[str]] = {}  # 区县名 -> 站点编码列表
    _station_meta_map: Dict[str, Dict] = {}                    # 站点编码 -> 元数据

    @classmethod
    def _load_station_data_from_json(cls):
        """从 station_district_results_with_type_id.json 加载站点数据（只加载一次）"""
        if cls._station_data_loaded:
            return

        try:
            possible_paths = [
                Path(__file__).parent.parent.parent.parent.parent / "config" / "station_district_results_with_type_id.json",
                Path(__file__).parent.parent.parent.parent / "config" / "station_district_results_with_type_id.json",
            ]

            station_file = None
            for path in possible_paths:
                if path.exists():
                    station_file = path
                    break

            if not station_file:
                logger.warning("station_district_json_not_found", message="station_district_results_with_type_id.json 文件未找到")
                cls._station_data_loaded = True
                return

            with open(station_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            records = data.get("data", [])

            for item in records:
                station_name = item.get("站点名称", "").strip()
                station_code = item.get("唯一编码", "").strip()
                # 城市短名（如"广州"），用于与 CITY_CODE_MAP 对齐
                city_short = item.get("城市名称", "").strip()
                # 区县名（str 或空 list）
                district_raw = item.get("区县", "")
                district = district_raw.strip() if isinstance(district_raw, str) else ""

                if not station_name or not station_code:
                    continue

                # 站点名 -> 编码
                cls._station_code_map_from_json[station_name] = station_code

                # 站点元数据
                cls._station_meta_map[station_code] = {
                    "name": station_name,
                    "city": city_short,
                    "district": district,
                    "lng": item.get("经度"),
                    "lat": item.get("纬度"),
                    "address": item.get("详细地址", ""),
                    "admin_code": item.get("行政区划代码", ""),
                    "type_id": item.get("站点类型ID"),
                }

                # 城市 -> 站点列表（按城市短名索引，同时索引去掉"市"后缀）
                if city_short:
                    for key in (city_short, city_short.rstrip("市")):
                        cls._city_stations_map_from_json.setdefault(key, [])
                        if station_code not in cls._city_stations_map_from_json[key]:
                            cls._city_stations_map_from_json[key].append(station_code)

                # 区县 -> 站点列表
                if district:
                    district_key = district.rstrip("区县市")  # 保留核心字，便于模糊匹配
                    for key in (district, district_key):
                        cls._district_stations_map_from_json.setdefault(key, [])
                        if station_code not in cls._district_stations_map_from_json[key]:
                            cls._district_stations_map_from_json[key].append(station_code)

            cls._station_data_loaded = True

            logger.info(
                "station_data_loaded_from_json",
                total_stations=len(cls._station_code_map_from_json),
                cities=len(cls._city_stations_map_from_json),
                districts=len(cls._district_stations_map_from_json),
                source=str(station_file)
            )

        except Exception as e:
            logger.error("station_data_load_failed", error=str(e), exc_info=True)
            cls._station_data_loaded = True

    # 广东省城市代码映射（完整版，支持别名）
    CITY_CODE_MAP = {
        # 标准名称
        "广州": "440100",
        "深圳": "440300",
        "珠海": "440400",
        "汕头": "440500",
        "佛山": "440600",
        "韶关": "440200",
        "湛江": "440800",
        "肇庆": "441200",
        "江门": "440700",
        "茂名": "440900",
        "惠州": "441300",
        "梅州": "441400",
        "汕尾": "441500",
        "河源": "441600",
        "阳江": "441700",
        "清远": "441800",
        "东莞": "441900",
        "中山": "442000",
        "潮州": "445100",
        "揭阳": "445200",
        "云浮": "445300",
        # 别名（带"市"后缀）
        "广州市": "440100",
        "深圳市": "440300",
        "珠海市": "440400",
        "汕头市": "440500",
        "佛山市": "440600",
        "韶关市": "440200",
        "湛江市": "440800",
        "肇庆市": "441200",
        "江门市": "440700",
        "茂名市": "440900",
        "惠州市": "441300",
        "梅州市": "441400",
        "汕尾市": "441500",
        "河源市": "441600",
        "阳江市": "441700",
        "清远市": "441800",
        "东莞市": "441900",
        "中山市": "442000",
        "潮州市": "445100",
        "揭阳市": "445200",
        "云浮市": "445300"
    }

    # 从 station_district_results_with_type_id.json 动态加载，以下为空占位
    STATION_CODE_MAP: Dict[str, str] = {}
    CODE_STATION_MAP: Dict[str, str] = {}
    CITY_STATIONS_MAP: Dict[str, List[str]] = {}

    @classmethod
    def _get_full_station_code_map(cls) -> Dict[str, str]:
        """获取站点名称 → 站点编码映射"""
        cls._load_station_data_from_json()
        return cls._station_code_map_from_json

    @classmethod
    def _get_full_city_stations_map(cls) -> Dict[str, List[str]]:
        """获取城市短名 → 站点编码列表映射"""
        cls._load_station_data_from_json()
        return cls._city_stations_map_from_json

    @classmethod
    def _get_full_district_stations_map(cls) -> Dict[str, List[str]]:
        """获取区县名 → 站点编码列表映射"""
        cls._load_station_data_from_json()
        return cls._district_stations_map_from_json

    @classmethod
    def resolve_station_name(cls, code: str) -> str:
        """站点编码→站点名称，找不到返回原编码"""
        # 确保已加载 JSON 数据
        cls._load_station_data_from_json()

        # 从 JSON 加载的数据中生成反向映射
        reverse_json_map = {v: k for k, v in cls._station_code_map_from_json.items()}
        return reverse_json_map.get(str(code), str(code))

    # 城市→站点代码列表映射（从 geo_mappings.json 动态加载）
    CITY_STATIONS_MAP = {}

    # 广东省区域代码映射
    REGION_CODE_MAP = {
        # 标准名称
        "广东省": "440001",
        "全省": "440001",
        "粤东": "440003",
        "粤西": "440004",
        "粤北": "440005",
        "珠三角": "440002",
        "非珠三角": "440006",
        "粤东西北": "440006",
        # 别名
        "广东": "440001",
        "广东省全省": "440001",
        "粤东地区": "440003",
        "粤西地区": "440004",
        "粤北地区": "440005",
        "珠三角地区": "440002",
        "非珠三角地区": "440006",
        "粤东西北地区": "440006",
    }

    @classmethod
    def resolve_city_codes(cls, city_names: List[str]) -> List[str]:
        """
        将城市名称列表转换为城市编码列表

        Args:
            city_names: 城市名称列表（LLM 输出）

        Returns:
            城市编码列表
        """
        city_codes = []

        for city_name in city_names:
            city_name = city_name.strip()

            # 优先查找区域编码
            if city_name in cls.REGION_CODE_MAP:
                city_codes.append(cls.REGION_CODE_MAP[city_name])
                continue

            # 直接查找城市编码
            if city_name in cls.CITY_CODE_MAP:
                city_codes.append(cls.CITY_CODE_MAP[city_name])
                continue

            # 模糊匹配（去除"市"后缀）
            city_clean = city_name.replace("市", "")
            if city_clean in cls.CITY_CODE_MAP:
                city_codes.append(cls.CITY_CODE_MAP[city_clean])
                continue

            # 检查是否已经是编码（6位数字）
            if city_name.isdigit() and len(city_name) == 6:
                city_codes.append(city_name)
                continue

            logger.warning(
                "city_code_not_found",
                city_name=city_name,
                available_cities=list(cls.CITY_CODE_MAP.keys()),
                available_regions=list(cls.REGION_CODE_MAP.keys())
            )

        logger.info(
            "city_names_resolved_to_codes",
            input_names=city_names,
            output_codes=city_codes
        )

        return city_codes

    @classmethod
    def resolve_station_codes(cls, station_names: List[str]) -> List[str]:
        """
        将站点名称列表转换为站点编码列表

        支持硬编码站点和从 station_info.json 加载的站点

        Args:
            station_names: 站点名称列表（LLM 输出）

        Returns:
            站点编码列表
        """
        # 获取完整的站点映射（硬编码 + JSON）
        full_station_map = cls._get_full_station_code_map()

        station_codes = []

        for station_name in station_names:
            station_name = station_name.strip()

            # 直接查找
            if station_name in full_station_map:
                station_codes.append(full_station_map[station_name])
                continue

            # 模糊匹配
            for mapped_name, code in full_station_map.items():
                if station_name in mapped_name or mapped_name in station_name:
                    station_codes.append(code)
                    break
            else:
                logger.warning(
                    "station_code_not_found",
                    station_name=station_name,
                    available_stations=list(full_station_map.keys())[:10]  # 只显示前10个
                )

        logger.info(
            "station_names_resolved_to_codes",
            input_names=station_names,
            output_codes=station_codes,
            total_available=len(full_station_map)
        )

        return station_codes

    @classmethod
    def resolve_station_codes_by_city(cls, city_names: List[str]) -> List[str]:
        """
        将城市名称列表展开为对应的所有站点代码列表

        LLM 只传城市名（如 ["广州"]），工具内部自动展开为该城市下所有站点代码。

        Args:
            city_names: 城市名称列表

        Returns:
            站点代码列表（去重）
        """
        full_city_stations_map = cls._get_full_city_stations_map()

        station_codes = []
        seen = set()

        for city_name in city_names:
            city_name = city_name.strip().replace("市", "")

            codes = full_city_stations_map.get(city_name, [])
            if not codes:
                logger.warning(
                    "city_stations_not_found",
                    city_name=city_name,
                    available_cities=list(full_city_stations_map.keys())
                )
                continue

            for code in codes:
                if code not in seen:
                    station_codes.append(code)
                    seen.add(code)

        logger.info(
            "city_names_resolved_to_station_codes",
            input_names=city_names,
            station_codes=station_codes,
            station_count=len(station_codes),
            total_cities=len(full_city_stations_map)
        )

        return station_codes

    @classmethod
    def resolve_station_codes_by_district(cls, district_names: List[str]) -> List[str]:
        """
        将区县名称列表展开为对应的所有站点编码列表

        LLM 传入区县名（如 ["白云区", "番禺区"]），工具内部自动展开为该区县下所有站点编码。
        支持精确匹配和去后缀模糊匹配（"白云区" 可匹配 "白云"）。

        Args:
            district_names: 区县名称列表

        Returns:
            站点编码列表（去重）
        """
        full_district_map = cls._get_full_district_stations_map()

        station_codes = []
        seen = set()

        for district_name in district_names:
            district_name = district_name.strip()
            # 精确匹配
            codes = full_district_map.get(district_name, [])
            # 去后缀模糊匹配（"白云区" -> "白云"）
            if not codes:
                district_short = district_name.rstrip("区县市")
                codes = full_district_map.get(district_short, [])

            if not codes:
                logger.warning(
                    "district_stations_not_found",
                    district_name=district_name,
                    available_districts=list(full_district_map.keys())[:20]
                )
                continue

            for code in codes:
                if code not in seen:
                    station_codes.append(code)
                    seen.add(code)

        logger.info(
            "district_names_resolved_to_station_codes",
            input_names=district_names,
            station_codes=station_codes,
            station_count=len(station_codes),
            total_districts=len(full_district_map)
        )

        return station_codes

    @classmethod
    def get_station_meta(cls, station_code: str) -> Optional[Dict]:
        """
        获取站点元数据（城市、区县、坐标等）

        Args:
            station_code: 站点编码

        Returns:
            元数据字典，包含 name/city/district/lng/lat/address/admin_code/type_id
        """
        cls._load_station_data_from_json()
        return cls._station_meta_map.get(station_code)

    @classmethod
    def _parse_station_type(cls, station_type: str) -> float:
        """
        解析站点类型字符串为数字ID

        Args:
            station_type: 站点类型（支持中文名称或数字ID字符串）

        Returns:
            站点类型ID（浮点数）

        Raises:
            ValueError: 无效的站点类型
        """
        cls._load_station_data_from_json()

        if station_type in cls.STATION_TYPE_MAP:
            return cls.STATION_TYPE_MAP[station_type]

        # 尝试直接转换为浮点数
        try:
            type_id = float(station_type)
            if type_id in cls.STATION_TYPE_MAP.values():
                return type_id
        except (ValueError, TypeError):
            pass

        valid_values = list(cls.STATION_TYPE_MAP.keys())
        raise ValueError(
            f"无效的站点类型: '{station_type}'。"
            f"有效值: {valid_values}"
        )

    @classmethod
    def _get_type_name(cls, type_id: float) -> str:
        """
        将类型ID转换为中文名称

        Args:
            type_id: 站点类型ID

        Returns:
            站点类型中文名称
        """
        type_name_map = {
            1.0: "国控",
            2.0: "省控",
            3.0: "市控",
            4.0: "区县控",
            5.0: "乡镇控",
            6.0: "其他",
            7.0: "背景站",
            8.0: "区域站",
            9.0: "交通站",
            15.0: "专项站",
        }
        return type_name_map.get(type_id, f"类型{type_id}")

    @classmethod
    def resolve_station_codes_by_type(
        cls,
        station_type: str,
        cities: List[str]
    ) -> Tuple[List[str], Dict]:
        """
        根据站点类型和城市列表获取站点编码列表

        Args:
            station_type: 站点类型（如"国控"/"省控"/"市控"或"1.0"/"2.0"/"3.0"）
            cities: 城市名称列表（必填，不允许全省查询）

        Returns:
            (站点编码列表, 元数据字典)

        Raises:
            ValueError: cities参数为空或站点类型无效
        """
        if not cities:
            raise ValueError(
                "必须提供cities参数。"
                "为避免数据量过大，不支持全省查询。"
                "请指定具体城市。"
            )

        cls._load_station_data_from_json()

        # 解析站点类型
        type_id = cls._parse_station_type(station_type)
        type_name = cls._get_type_name(type_id)

        # 获取城市下的所有站点
        all_station_codes = cls.resolve_station_codes_by_city(cities)

        # 按站点类型过滤
        filtered_stations = []
        for station_code in all_station_codes:
            meta = cls._station_meta_map.get(station_code, {})
            station_type_id = meta.get("type_id")
            if station_type_id == type_id:
                filtered_stations.append(station_code)

        metadata = {
            "type_id": type_id,
            "type_name": type_name,
            "station_count": len(filtered_stations),
            "cities": cities,
            "total_stations_in_cities": len(all_station_codes),
        }

        logger.info(
            "station_codes_resolved_by_type",
            station_type=station_type,
            type_id=type_id,
            type_name=type_name,
            cities=cities,
            filtered_count=len(filtered_stations),
            total_count=len(all_station_codes)
        )

        return filtered_stations, metadata

    @classmethod
    def validate_station_type_match(
        cls,
        station_names: List[str],
        station_type: str
    ) -> Tuple[bool, List[str], str]:
        """
        验证指定站点是否匹配给定类型

        Args:
            station_names: 站点名称列表
            station_type: 期望的站点类型

        Returns:
            (是否全部匹配, 不匹配的站点列表, 错误消息)
        """
        cls._load_station_data_from_json()

        # 解析站点类型
        type_id = cls._parse_station_type(station_type)
        type_name = cls._get_type_name(type_id)

        # 解析站点编码
        station_codes = cls.resolve_station_codes(station_names)

        # 检查每个站点的类型
        mismatched = []
        for station_code in station_codes:
            meta = cls._station_meta_map.get(station_code, {})
            station_type_id = meta.get("type_id")
            if station_type_id != type_id:
                station_name = meta.get("name", station_code)
                actual_type = cls._get_type_name(station_type_id) if station_type_id else "未知"
                mismatched.append(f"{station_name}({actual_type})")

        if mismatched:
            error_msg = (
                f"以下站点不是{type_name}站点: {', '.join(mismatched)}"
            )
            return False, mismatched, error_msg

        return True, [], ""

    @classmethod
    def _filter_stations_by_type(
        cls,
        station_codes: List[str],
        station_types: List[float]
    ) -> List[str]:
        """
        根据站点类型过滤站点编码列表

        Args:
            station_codes: 站点编码列表
            station_types: 允许的站点类型ID列表

        Returns:
            过滤后的站点编码列表
        """
        cls._load_station_data_from_json()

        filtered = []
        for station_code in station_codes:
            meta = cls._station_meta_map.get(station_code, {})
            station_type_id = meta.get("type_id")
            if station_type_id in station_types:
                filtered.append(station_code)

        return filtered


class QueryGDSuncereDataTool:
    """
    广东省 Suncere 数据查询工具

    提供多种查询方式：
    1. 城市日报数据查询
    2. 城市小时数据查询
    3. 综合统计报表查询
    4. 区域对比数据查询

    特性：
    - LLM 驱动的结构化参数查询
    - 城市/站点名称自动映射到编码
    - 多城市并发查询
    """

    # 污染物代码标准
    POLLUTANT_CODES = ["PM2.5", "PM10", "SO2", "NO2", "O3", "CO"]

    # 地理解析器
    geo_resolver = GeoMappingResolver()

    @classmethod
    def get_city_code(cls, city_name: str) -> str:
        """
        城市名称转代码（支持城市和区域编码）

        Args:
            city_name: 城市名称或区域名称

        Returns:
            城市代码或区域代码
        """
        # 优先查找区域编码
        if city_name in cls.geo_resolver.REGION_CODE_MAP:
            return cls.geo_resolver.REGION_CODE_MAP[city_name]
        # 查找城市编码
        return cls.geo_resolver.CITY_CODE_MAP.get(city_name, "")

    @classmethod
    def get_station_code(cls, station_name: str) -> str:
        """
        站点名称转编码

        Args:
            station_name: 站点名称

        Returns:
            站点代码
        """
        return cls.geo_resolver.STATION_CODE_MAP.get(station_name, "")

    @staticmethod
    def calculate_data_source(end_time: str) -> int:
        """
        根据 TimePoint 的结束时间智能计算 DataSource 参数

        规则（参考 Vanna 项目实现）：
        - 如果结束时间距离当前日期在三天内（含3天）→ 返回 0（原始实况）
        - 如果结束时间距离当前日期超过三天 → 返回 1（审核实况）

        Args:
            end_time: 结束时间字符串，格式如 "2024-12-01 23:59:59" 或 "2024-12-01"

        Returns:
            DataSource 值：0（原始实况）或 1（审核实况）
        """
        try:
            # 提取日期部分（去除时间）
            date_str = end_time.split()[0] if " " in end_time else end_time
            end_date = datetime.strptime(date_str, "%Y-%m-%d")

            # 计算天数差
            days_diff = (datetime.now() - end_date).days

            # 三天内用原始实况，否则用审核实况
            data_source = 0 if days_diff <= 3 else 1

            logger.debug(
                "calculate_data_source",
                end_time=end_time,
                end_date=date_str,
                days_diff=days_diff,
                data_source=data_source,
                data_source_type="原始实况" if data_source == 0 else "审核实况"
            )

            return data_source

        except Exception as e:
            logger.warning(
                "calculate_data_source_failed",
                end_time=end_time,
                error=str(e),
                fallback=0
            )
            # 解析失败时默认返回原始实况
            return 0

    @classmethod
    def query_city_day_data(
        cls,
        cities: List[str],
        start_date: str,
        end_date: str,
        context: ExecutionContext,
        data_type: int = 1,
        enable_sand_deduction: bool = True
    ) -> Dict[str, Any]:
        """
        查询城市日报数据

        Args:
            cities: 城市名称列表（LLM 输出，如 ["广州", "深圳"]）
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            context: 执行上下文
            data_type: 数据类型（0原始实况，1审核实况，2原始标况，3审核标况），默认1
            enable_sand_deduction: 是否启用扣沙处理（默认True，剔除沙尘暴天气的PM2.5/PM10数据）

        Returns:
            查询结果
        """
        logger.info(
            "query_gd_suncere_city_day_start",
            cities=cities,
            start_date=start_date,
            end_date=end_date,
            enable_sand_deduction=enable_sand_deduction
        )

        try:
            api_client = get_gd_suncere_api_client()

            # 转换城市名称为编码
            city_codes = cls.geo_resolver.resolve_city_codes(cities)

            if not city_codes:
                raise Exception(f"未找到任何有效的城市代码: {cities}")

            # 调用 API 查询城市日报数据
            response = api_client.query_city_day_data(
                city_codes=city_codes,
                start_date=start_date,
                end_date=end_date,
                data_type=data_type
            )

            if not response.get("success"):
                error_msg = response.get("msg", "Unknown error")
                raise Exception(f"API 查询失败: {error_msg}")

            # 提取结果
            raw_records = response.get("result", [])

            if not raw_records:
                logger.warning(
                    "query_city_day_no_data",
                    cities=cities,
                    date_range=f"{start_date} to {end_date}"
                )
                return {
                    "status": "empty",
                    "success": True,
                    "data": [],
                    "metadata": {
                        "tool_name": "query_gd_suncere_city_day",
                        "cities": cities,
                        "date_range": f"{start_date} to {end_date}",
                        "message": "查询成功但无数据返回"
                    },
                    "summary": f"未找到 {', '.join(cities)} 在指定时间段的日报数据"
                }

            logger.info(
                "query_city_day_data_received",
                record_count=len(raw_records)
            )

            # 数据标准化
            standardizer = get_data_standardizer()
            standardized_records = standardizer.standardize(raw_records)

            logger.info(
                "gd_suncere_data_standardized",
                raw_count=len(raw_records),
                standardized_count=len(standardized_records)
            )

            # 扣沙处理（在修约之前）
            sand_dates = {}
            if enable_sand_deduction:
                from app.tools.query.query_new_standard_report.tool import load_sand_deduction_dates, clean_sand_deduction_data

                sand_dates = load_sand_deduction_dates()
                if sand_dates:
                    standardized_records = clean_sand_deduction_data(standardized_records, sand_dates)
                    logger.info(
                        "sand_deduction_applied",
                        cities_count=len(sand_dates),
                        total_dates=sum(len(dates) for dates in sand_dates.values())
                    )
                else:
                    logger.info("sand_deduction_skipped", reason="no_sand_data_loaded")

            # 对日数据浓度值应用修约规则（按原始监测数据规则：保留整数位）
            def safe_float(value, default=0.0):
                """安全转换为浮点数"""
                if value is None or value == '' or value == '-':
                    return default
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return default

            for record in standardized_records:
                measurements = record.get("measurements", {})

                # 检查是否为扣沙日
                is_sand_day = record.get("is_sand_deduction_day", False)

                # 提取原始浓度值
                if is_sand_day:
                    # 扣沙日：PM2.5/PM10为"-"，不参与修约
                    pm25_raw = 0
                    pm10_raw = 0
                else:
                    pm25_raw = safe_float(measurements.get("PM2_5") or measurements.get("pm2_5") or
                                        record.get("pm2_5") or record.get("PM2_5"))
                    pm10_raw = safe_float(measurements.get("PM10") or measurements.get("pm10") or
                                        record.get("pm10") or record.get("PM10"))

                so2_raw = safe_float(measurements.get("SO2") or measurements.get("so2") or
                                   record.get("so2") or record.get("SO2"))
                no2_raw = safe_float(measurements.get("NO2") or measurements.get("no2") or
                                   record.get("no2") or record.get("NO2"))
                co_raw = safe_float(measurements.get("CO") or measurements.get("co") or
                                  record.get("co") or record.get("CO"))
                o3_8h_raw = safe_float(measurements.get("O3_8h") or measurements.get("o3_8h") or
                                    record.get("o3_8h") or record.get("O3_8h"))

                # 应用修约规则并更新 measurements
                if not is_sand_day:
                    # 非扣沙日：正常修约
                    # 0位小数转为整数类型，避免显示 .0
                    measurements['PM2_5'] = int(apply_rounding(pm25_raw, 'PM2_5', 'raw_data'))
                    measurements['PM10'] = int(apply_rounding(pm10_raw, 'PM10', 'raw_data'))
                # 扣沙日的PM2.5/PM10保持"-"（已在 clean_sand_deduction_data 中设置）

                measurements['SO2'] = int(apply_rounding(so2_raw, 'SO2', 'raw_data'))
                measurements['NO2'] = int(apply_rounding(no2_raw, 'NO2', 'raw_data'))
                measurements['CO'] = apply_rounding(co_raw, 'CO', 'raw_data')  # CO保留1位小数
                measurements['O3_8h'] = int(apply_rounding(o3_8h_raw, 'O3_8h', 'raw_data'))

            # 保存到上下文
            data_id = context.data_manager.save_data(
                data=standardized_records,
                schema="air_quality_unified",
                metadata={
                    "source": "gd_suncere_api",
                    "query_type": "city_day",
                    "cities": cities,
                    "date_range": f"{start_date} to {end_date}",
                    "schema_version": "v2.0",  # UDF v2.0 标记
                    "field_mapping_applied": True,
                    "field_mapping_info": standardizer.get_field_mapping_info() if standardizer else {},
                    "enable_sand_deduction": enable_sand_deduction,
                    "sand_deduction_applied": bool(sand_dates)
                }
            )

            logger.info(
                "gd_suncere_data_saved",
                data_id=data_id,
                record_count=len(standardized_records)
            )

            return {
                "status": "success",
                "success": True,
                "data": standardized_records[:24],  # 返回前24条供预览
                "metadata": {
                    "tool_name": "query_gd_suncere_city_day",
                    "data_id": data_id,
                    "total_records": len(standardized_records),
                    "returned_records": min(24, len(standardized_records)),
                    "cities": cities,
                    "date_range": f"{start_date} to {end_date}",
                    "schema_version": "v2.0",  # UDF v2.0 标记
                    "source": "gd_suncere_api"
                },
                "summary": f"成功获取 {', '.join(cities)} 的日报数据共 {len(standardized_records)} 条，已保存为 {data_id}"
            }

        except Exception as e:
            logger.error(
                "query_gd_suncere_city_day_failed",
                error=str(e),
                error_type=type(e).__name__
            )
            return cls._create_error_response(str(e))

    @classmethod
    def query_station_day_data(
        cls,
        cities: Optional[List[str]] = None,
        stations: Optional[List[str]] = None,
        start_date: str = None,
        end_date: str = None,
        context: ExecutionContext = None,
        data_type: int = 1,
        station_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        查询站点日报数据

        Args:
            cities: 城市名称列表（自动展开为站点，与 stations 二选一，可组合）
            stations: 站点名称列表（直接查询指定站点，与 cities 二选一，可组合）
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            context: 执行上下文
            data_type: 数据类型（0原始实况，1审核实况，2原始标况，3审核标况），默认1
            station_type: 站点类型（如"国控"/"省控"/"市控"或"1.0"/"2.0"/"3.0"）

        Returns:
            查询结果
        """
        logger.info(
            "query_gd_suncere_station_day_start",
            cities=cities,
            stations=stations,
            start_date=start_date,
            end_date=end_date,
            station_type=station_type
        )

        try:
            api_client = get_gd_suncere_api_client()

            # 解析站点代码（支持站点类型过滤）
            station_codes = []

            if stations:
                # 场景1: 指定站点 - 验证类型匹配
                if station_type:
                    is_valid, mismatched, error_msg = cls.geo_resolver.validate_station_type_match(
                        stations, station_type
                    )
                    if not is_valid:
                        return cls._create_error_response(
                            f"站点类型不匹配: {error_msg}"
                        )
                station_codes.extend(cls.geo_resolver.resolve_station_codes(stations))

            if cities:
                # 场景2: 指定城市 - 按类型+城市过滤（支持多城市并发查询）
                if station_type:
                    type_codes, metadata = cls.geo_resolver.resolve_station_codes_by_type(
                        station_type, cities
                    )
                    if not type_codes:
                        type_name = metadata.get("type_name", station_type)
                        return {
                            "status": "empty",
                            "success": True,
                            "data": [],
                            "summary": f"未找到类型为'{type_name}'的站点（城市：{', '.join(cities)}）",
                            "metadata": {
                                "station_type": station_type,
                                "type_id": metadata.get("type_id"),
                                "cities": cities,
                                "stations": [],
                                "suggestion": f"该城市没有{type_name}站点，建议使用其他站点类型查询"
                            }
                        }
                    station_codes.extend(type_codes)
                else:
                    station_codes.extend(cls.geo_resolver.resolve_station_codes_by_city(cities))

            # 去重保持顺序
            seen = set()
            unique_station_codes = []
            for code in station_codes:
                if code not in seen:
                    seen.add(code)
                    unique_station_codes.append(code)
            station_codes = unique_station_codes

            if not station_codes:
                raise Exception(f"未找到任何有效的站点代码: cities={cities}, stations={stations}")

            logger.info(
                "query_station_day_codes_resolved",
                cities=cities,
                stations=stations,
                station_codes=station_codes,
                count=len(station_codes)
            )

            # 智能计算 DataSource 参数（根据结束时间判断）
            calculated_data_type = QueryGDSuncereDataTool.calculate_data_source(end_date)

            logger.info(
                "query_station_day_data_type_calculated",
                end_date=end_date,
                data_type=calculated_data_type,
                data_type_name="原始实况" if calculated_data_type == 0 else "审核实况"
            )

            # 调用 API 查询站点日报数据
            response = api_client.query_station_day_data(
                station_codes=station_codes,
                start_date=start_date,
                end_date=end_date,
                data_type=calculated_data_type
            )

            if not response.get("success"):
                error_msg = response.get("msg", "Unknown error")
                raise Exception(f"API 查询失败: {error_msg}")

            # 提取结果
            raw_records = response.get("result", [])

            if not raw_records:
                logger.warning(
                    "query_station_day_no_data",
                    cities=cities,
                    stations=stations,
                    date_range=f"{start_date} to {end_date}"
                )
                return {
                    "status": "empty",
                    "success": True,
                    "data": [],
                    "metadata": {
                        "tool_name": "query_gd_suncere_station_day",
                        "cities": cities or [],
                        "stations": stations or [],
                        "date_range": f"{start_date} to {end_date}",
                        "message": "查询成功但无数据返回"
                    },
                    "summary": f"未找到指定站点在 {start_date} 至 {end_date} 的日报数据"
                }

            logger.info(
                "query_station_day_data_received",
                record_count=len(raw_records)
            )

            # 数据标准化
            standardizer = get_data_standardizer()
            standardized_records = standardizer.standardize(raw_records)

            logger.info(
                "gd_suncere_station_data_standardized",
                raw_count=len(raw_records),
                standardized_count=len(standardized_records)
            )

            # 对日数据浓度值应用修约规则（按原始监测数据规则：CO保留1位小数，其他取整）
            def safe_float(value, default=0.0):
                if value is None or value == '' or value == '-':
                    return default
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return default

            for record in standardized_records:
                measurements = record.get("measurements", {})

                pm25_raw = safe_float(measurements.get("PM2_5") or measurements.get("pm2_5") or
                                    record.get("pm2_5") or record.get("PM2_5"))
                pm10_raw = safe_float(measurements.get("PM10") or measurements.get("pm10") or
                                    record.get("pm10") or record.get("PM10"))
                so2_raw = safe_float(measurements.get("SO2") or measurements.get("so2") or
                                   record.get("so2") or record.get("SO2"))
                no2_raw = safe_float(measurements.get("NO2") or measurements.get("no2") or
                                   record.get("no2") or record.get("NO2"))
                co_raw = safe_float(measurements.get("CO") or measurements.get("co") or
                                  record.get("co") or record.get("CO"))
                o3_8h_raw = safe_float(measurements.get("O3_8h") or measurements.get("o3_8h") or
                                    record.get("o3_8h") or record.get("O3_8h"))

                measurements['PM2_5'] = int(apply_rounding(pm25_raw, 'PM2_5', 'raw_data'))
                measurements['PM10'] = int(apply_rounding(pm10_raw, 'PM10', 'raw_data'))
                measurements['SO2'] = int(apply_rounding(so2_raw, 'SO2', 'raw_data'))
                measurements['NO2'] = int(apply_rounding(no2_raw, 'NO2', 'raw_data'))
                measurements['CO'] = apply_rounding(co_raw, 'CO', 'raw_data')
                measurements['O3_8h'] = int(apply_rounding(o3_8h_raw, 'O3_8h', 'raw_data'))

            # 按新标准重算 IAQI、AQI 和首要污染物
            import math
            for record in standardized_records:
                measurements = record.get("measurements", {})

                # 获取修约后的浓度值
                pm25 = safe_float(measurements.get("PM2_5"))
                pm10 = safe_float(measurements.get("PM10"))
                so2 = safe_float(measurements.get("SO2"))
                no2 = safe_float(measurements.get("NO2"))
                co = safe_float(measurements.get("CO"))
                o3_8h = safe_float(measurements.get("O3_8h"))

                # 使用新标准计算 IAQI（向上进位取整数）
                pm25_iaqi = math.ceil(calculate_iaqi(pm25, 'PM2_5', 'new'))
                pm10_iaqi = math.ceil(calculate_iaqi(pm10, 'PM10', 'new'))
                so2_iaqi = math.ceil(calculate_iaqi(so2, 'SO2', 'new'))
                no2_iaqi = math.ceil(calculate_iaqi(no2, 'NO2', 'new'))
                co_iaqi = math.ceil(calculate_iaqi(co, 'CO', 'new'))
                o3_8h_iaqi = math.ceil(calculate_iaqi(o3_8h, 'O3_8h', 'new'))

                # 保存新标准 IAQI
                measurements['PM2_5_IAQI'] = pm25_iaqi
                measurements['PM10_IAQI'] = pm10_iaqi
                measurements['SO2_IAQI'] = so2_iaqi
                measurements['NO2_IAQI'] = no2_iaqi
                measurements['CO_IAQI'] = co_iaqi
                measurements['O3_8h_IAQI'] = o3_8h_iaqi

                # 计算 AQI（取最大 IAQI）
                aqi = max(pm25_iaqi, pm10_iaqi, so2_iaqi, no2_iaqi, co_iaqi, o3_8h_iaqi)
                measurements['AQI'] = aqi

                # 确定首要污染物（AQI > 50 时才有首要污染物）
                if aqi > 50:
                    pollutants_with_iaqi = {
                        'PM2_5': pm25_iaqi,
                        'PM10': pm10_iaqi,
                        'SO2': so2_iaqi,
                        'NO2': no2_iaqi,
                        'CO': co_iaqi,
                        'O3_8h': o3_8h_iaqi
                    }
                    primary_pollutants = [p for p, iaqi in pollutants_with_iaqi.items() if iaqi == aqi]
                    # 将首要污染物列表转换为中文
                    primary_pollutant_map = {
                        'PM2_5': 'PM2.5',
                        'PM10': 'PM10',
                        'SO2': 'SO2',
                        'NO2': 'NO2',
                        'CO': 'CO',
                        'O3_8h': 'O3'
                    }
                    primary_pollutants_zh = [primary_pollutant_map.get(p, p) for p in primary_pollutants]
                    record['primary_pollutant'] = ', '.join(primary_pollutants_zh) if primary_pollutants_zh else '-'
                else:
                    record['primary_pollutant'] = '-'

            logger.info(
                "station_day_new_standard_indices_calculated",
                record_count=len(standardized_records)
            )

            # 保存到数据上下文
            data_id = context.save_data(
                data=standardized_records,
                schema="air_quality_unified"
            )

            # 智能采样：如果记录数超过24条，进行采样
            preview_data = standardized_records
            if len(standardized_records) > 24:
                preview_data = cls._smart_sample_data(standardized_records, max_records=24)
                logger.info(
                    "station_day_data_sampled",
                    total=len(standardized_records),
                    preview=len(preview_data)
                )

            # 获取城市/站点列表用于摘要
            if stations:
                location_list = stations
            elif cities:
                location_list = cities
            else:
                location_list = [station_codes[0]]

            return {
                "status": "success",
                "success": True,
                "data": preview_data,
                "data_id": data_id,
                "metadata": {
                    "tool_name": "query_gd_suncere_station_day",
                    "data_id": data_id,
                    "total_records": len(standardized_records),
                    "returned_records": len(preview_data),
                    "cities": cities or [],
                    "stations": stations or [],
                    "station_codes": station_codes,
                    "date_range": f"{start_date} to {end_date}",
                    "schema_version": "v2.0",
                    "source": "gd_suncere_api"
                },
                "summary": f"成功获取 {', '.join(location_list)} 的站点日报数据共 {len(standardized_records)} 条，已保存为 {data_id}"
            }

        except Exception as e:
            logger.error(
                "query_gd_suncere_station_day_failed",
                error=str(e),
                error_type=type(e).__name__
            )
            return cls._create_error_response(str(e))

    @classmethod
    def query_city_hour_data(
        cls,
        cities: List[str],
        start_time: str,
        end_time: str,
        context: ExecutionContext,
        include_weather: bool = True
    ) -> Dict[str, Any]:
        """
        查询城市小时数据（用于区域对比分析）

        使用 DATCityHour API 查询城市级别的小时数据，
        适合进行多城市时序对比和区域传输分析。

        Args:
            cities: 城市名称列表或城市编码列表（LLM 输出，自动检测）
            start_time: 开始时间 (YYYY-MM-DD HH:MM:SS)
            end_time: 结束时间 (YYYY-MM-DD HH:MM:SS)
            context: 执行上下文
            include_weather: 是否包含气象字段（风速、风向、温度、湿度、气压等），默认 True

        Returns:
            查询结果

        Note:
            气象字段包括：
            - wind_speed_10m: 10米风速 (m/s)
            - wind_direction_10m: 10米风向 (度)
            - temperature_2m: 2米气温 (°C)
            - relative_humidity_2m: 2米相对湿度 (%)
            - surface_pressure: 地面气压 (hPa)
            - precipitation: 降水量 (mm)
            - visibility: 能见度 (km)

            某些站点的气象字段可能返回空值或无效值（如 -99.000），这是数据源的正常情况。
        """
        logger.info(
            "query_gd_suncere_city_hour_start",
            cities=cities,
            start_time=start_time,
            end_time=end_time
        )

        try:
            api_client = get_gd_suncere_api_client()

            # 智能判断：是城市名称还是城市编码
            # 编码格式：6位数字（如 440100）
            # 名称格式：中文或带"市"后缀
            city_codes = []
            for city in cities:
                city = city.strip()
                # 如果是6位数字编码，直接使用
                if city.isdigit() and len(city) == 6:
                    city_codes.append(city)
                    logger.debug(
                        "city_input_is_code",
                        city=city
                    )
                else:
                    # 否则尝试从名称映射
                    code = cls.get_city_code(city)
                    if code:
                        city_codes.append(code)
                        logger.debug(
                            "city_name_converted_to_code",
                            city_name=city,
                            city_code=code
                        )
                    else:
                        logger.warning(
                            "city_code_not_found",
                            city=city
                        )

            if not city_codes:
                raise Exception(f"未找到任何有效的城市代码: {cities}")

            logger.info(
                "query_city_hour_codes_resolved",
                cities=cities,
                city_codes=city_codes
            )

            # 智能计算 DataSource 参数（根据结束时间判断）
            data_type = cls.calculate_data_source(end_time)

            logger.info(
                "query_city_hour_data_type_calculated",
                end_time=end_time,
                data_type=data_type,
                data_type_name="原始实况" if data_type == 0 else "审核实况"
            )

            # 调用 API 查询城市小时数据
            response = api_client.query_city_hour_data(
                city_codes=city_codes,
                start_time=start_time,
                end_time=end_time,
                data_type=data_type  # 根据时间自动判断
            )

            if not response.get("success"):
                error_msg = response.get("msg", "Unknown error")
                raise Exception(f"API 查询失败: {error_msg}")

            # 提取结果
            raw_records = response.get("result", [])

            if not raw_records:
                logger.warning(
                    "query_city_hour_no_data",
                    cities=cities,
                    time_range=f"{start_time} - {end_time}"
                )
                return {
                    "status": "empty",
                    "success": True,
                    "data": [],
                    "metadata": {
                        "tool_name": "query_gd_suncere_city_hour",
                        "cities": cities,
                        "time_range": f"{start_time} - {end_time}",
                        "message": "查询成功但无数据返回"
                    },
                    "summary": f"未找到 {', '.join(cities)} 在指定时间段的小时数据"
                }

            logger.info(
                "query_city_hour_data_received",
                record_count=len(raw_records)
            )

            # 数据标准化
            standardizer = get_data_standardizer()
            standardized_records = standardizer.standardize(raw_records)

            logger.info(
                "gd_suncere_city_hour_standardized",
                raw_count=len(raw_records),
                standardized_count=len(standardized_records)
            )

            # 根据 include_weather 参数决定是否保留气象字段
            if not include_weather:
                # 移除气象字段（当用户显式设置为False时）
                weather_fields = [
                    'wind_speed_10m', 'wind_direction_10m',
                    'temperature_2m', 'relative_humidity_2m',
                    'surface_pressure', 'wind_gusts_10m',
                    'precipitation', 'cloud_cover', 'visibility'
                ]
                for record in standardized_records:
                    measurements = record.get('measurements', {})
                    for field in weather_fields:
                        measurements.pop(field, None)
                logger.debug(
                    "gd_suncere_city_hour_weather_fields_removed",
                    weather_fields=weather_fields
                )
            else:
                logger.debug(
                    "gd_suncere_city_hour_weather_fields_included"
                )

            # 对小时数据浓度值应用修约规则（按原始监测数据规则：保留整数位）
            def safe_float(value, default=0.0):
                """安全转换为浮点数"""
                if value is None or value == '' or value == '-':
                    return default
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return default

            for record in standardized_records:
                measurements = record.get("measurements", {})

                # 提取原始浓度值
                pm25_raw = safe_float(measurements.get("PM2_5") or measurements.get("pm2_5") or
                                    record.get("pm2_5") or record.get("PM2_5"))
                pm10_raw = safe_float(measurements.get("PM10") or measurements.get("pm10") or
                                    record.get("pm10") or record.get("PM10"))
                so2_raw = safe_float(measurements.get("SO2") or measurements.get("so2") or
                                   record.get("so2") or record.get("SO2"))
                no2_raw = safe_float(measurements.get("NO2") or measurements.get("no2") or
                                   record.get("no2") or record.get("NO2"))
                co_raw = safe_float(measurements.get("CO") or measurements.get("co") or
                                  record.get("co") or record.get("CO"))
                o3_8h_raw = safe_float(measurements.get("O3_8h") or measurements.get("o3_8h") or
                                    record.get("o3_8h") or record.get("O3_8h"))

                # 应用修约规则并更新 measurements
                # 0位小数转为整数类型，避免显示 .0
                measurements['PM2_5'] = int(apply_rounding(pm25_raw, 'PM2_5', 'raw_data'))
                measurements['PM10'] = int(apply_rounding(pm10_raw, 'PM10', 'raw_data'))
                measurements['SO2'] = int(apply_rounding(so2_raw, 'SO2', 'raw_data'))
                measurements['NO2'] = int(apply_rounding(no2_raw, 'NO2', 'raw_data'))
                measurements['CO'] = apply_rounding(co_raw, 'CO', 'raw_data')  # CO保留1位小数
                measurements['O3_8h'] = int(apply_rounding(o3_8h_raw, 'O3_8h', 'raw_data'))

            # 保存到上下文
            data_id = context.data_manager.save_data(
                data=standardized_records,
                schema="air_quality_unified",
                metadata={
                    "source": "gd_suncere_api",
                    "query_type": "city_hour",
                    "cities": cities,
                    "time_range": f"{start_time} - {end_time}",
                    "schema_version": "v2.0",  # UDF v2.0 标记
                    "field_mapping_applied": True,
                    "field_mapping_info": standardizer.get_field_mapping_info() if standardizer else {}
                }
            )

            logger.info(
                "gd_suncere_city_hour_saved",
                data_id=data_id,
                record_count=len(standardized_records)
            )

            return {
                "status": "success",
                "success": True,
                "data": standardized_records[:24],  # 返回前24条供预览
                "metadata": {
                    "tool_name": "query_gd_suncere_city_hour",
                    "data_id": data_id,
                    "total_records": len(standardized_records),
                    "returned_records": min(24, len(standardized_records)),
                    "cities": cities,
                    "time_range": f"{start_time} - {end_time}",
                    "schema_version": "v2.0",  # UDF v2.0 标记
                    "source": "gd_suncere_api"
                },
                "summary": f"成功获取 {', '.join(cities)} 的小时数据共 {len(standardized_records)} 条，已保存为 {data_id}"
            }

        except Exception as e:
            logger.error(
                "query_gd_suncere_city_hour_failed",
                error=str(e),
                error_type=type(e).__name__
            )
            return cls._create_error_response(str(e))

    @classmethod
    def query_station_hour_data(
        cls,
        stations: List[str],
        start_time: str,
        end_time: str,
        context: ExecutionContext,
        include_weather: bool = True
    ) -> Dict[str, Any]:
        """
        查询站点小时数据（用于精细化分析）

        注意：此方法需要提供具体的站点代码或站点名称
        城市级别数据请使用 query_city_hour_data

        Args:
            stations: 站点名称列表或站点编码列表（如 "广雅中学" 或 "1001A"）
            start_time: 开始时间 (YYYY-MM-DD HH:MM:SS)
            end_time: 结束时间 (YYYY-MM-DD HH:MM:SS)
            context: 执行上下文
            include_weather: 是否包含气象字段（风速、风向、温度、湿度、气压等），默认 True

        Returns:
            查询结果

        Note:
            站点编码格式：通常为字母数字组合（如 "1001A"）
            可以通过站点名称自动解析为站点编码

            气象字段包括：
            - wind_speed_10m: 10米风速 (m/s)
            - wind_direction_10m: 10米风向 (度)
            - temperature_2m: 2米气温 (°C)
            - relative_humidity_2m: 2米相对湿度 (%)
            - surface_pressure: 地面气压 (hPa)
            - precipitation: 降水量 (mm)
            - visibility: 能见度 (km)

            某些站点的气象字段可能返回空值或无效值（如 -99.000），这是数据源的正常情况。
        """
        logger.info(
            "query_gd_suncere_station_hour_start",
            stations=stations,
            start_time=start_time,
            end_time=end_time
        )

        try:
            api_client = get_gd_suncere_api_client()

            # 解析站点代码（支持站点名称或编码）
            station_codes = []
            for station in stations:
                station = station.strip()
                # 尝试从站点名称映射
                code = cls.get_station_code(station)
                if code:
                    station_codes.append(code)
                    logger.debug(
                        "station_name_converted_to_code",
                        station_name=station,
                        station_code=code
                    )
                else:
                    # 如果直接提供了站点编码，使用它
                    # 站点编码通常包含字母（如 "1001A"）
                    if any(c.isalpha() for c in station):
                        station_codes.append(station)
                        logger.debug(
                            "station_input_is_code",
                            station=station
                        )
                    else:
                        logger.warning(
                            "station_code_not_found",
                            station=station
                        )

            if not station_codes:
                raise Exception(f"未找到任何有效的站点代码: {stations}")

            logger.info(
                "query_station_hour_codes_resolved",
                stations=stations,
                station_codes=station_codes
            )

            # 智能计算 DataSource 参数（根据结束时间判断）
            data_type = cls.calculate_data_source(end_time)

            logger.info(
                "query_station_hour_data_type_calculated",
                end_time=end_time,
                data_type=data_type,
                data_type_name="原始实况" if data_type == 0 else "审核实况"
            )

            # 调用 API 查询站点小时数据
            response = api_client.query_station_hour_data(
                station_codes=station_codes,
                start_time=start_time,
                end_time=end_time,
                data_type=data_type
            )

            if not response.get("success"):
                error_msg = response.get("msg", "Unknown error")
                raise Exception(f"API 查询失败: {error_msg}")

            # 提取结果
            raw_records = response.get("result", [])

            if not raw_records:
                logger.warning(
                    "query_station_hour_no_data",
                    stations=stations,
                    time_range=f"{start_time} - {end_time}"
                )
                return {
                    "status": "empty",
                    "success": True,
                    "data": [],
                    "metadata": {
                        "tool_name": "query_gd_suncere_station_hour",
                        "stations": stations,
                        "time_range": f"{start_time} - {end_time}",
                        "message": "查询成功但无数据返回"
                    },
                    "summary": f"未找到 {', '.join(stations)} 在指定时间段的小时数据"
                }

            logger.info(
                "query_station_hour_data_received",
                record_count=len(raw_records)
            )

            # 数据标准化
            standardizer = get_data_standardizer()
            standardized_records = standardizer.standardize(raw_records)

            logger.info(
                "gd_suncere_station_hour_standardized",
                raw_count=len(raw_records),
                standardized_count=len(standardized_records)
            )

            # 根据 include_weather 参数决定是否保留气象字段
            if not include_weather:
                # 移除气象字段（保持当前默认行为）
                weather_fields = [
                    'wind_speed_10m', 'wind_direction_10m',
                    'temperature_2m', 'relative_humidity_2m',
                    'surface_pressure', 'wind_gusts_10m',
                    'precipitation', 'cloud_cover', 'visibility'
                ]
                for record in standardized_records:
                    measurements = record.get('measurements', {})
                    for field in weather_fields:
                        measurements.pop(field, None)
                logger.debug(
                    "gd_suncere_station_hour_weather_fields_removed",
                    weather_fields=weather_fields
                )
            else:
                logger.debug(
                    "gd_suncere_station_hour_weather_fields_included"
                )

            # 对小时数据浓度值应用修约规则（按原始监测数据规则：保留整数位）
            def safe_float(value, default=0.0):
                """安全转换为浮点数"""
                if value is None or value == '' or value == '-':
                    return default
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return default

            for record in standardized_records:
                measurements = record.get("measurements", {})

                # 提取原始浓度值
                pm25_raw = safe_float(measurements.get("PM2_5") or measurements.get("pm2_5") or
                                    record.get("pm2_5") or record.get("PM2_5"))
                pm10_raw = safe_float(measurements.get("PM10") or measurements.get("pm10") or
                                    record.get("pm10") or record.get("PM10"))
                so2_raw = safe_float(measurements.get("SO2") or measurements.get("so2") or
                                   record.get("so2") or record.get("SO2"))
                no2_raw = safe_float(measurements.get("NO2") or measurements.get("no2") or
                                   record.get("no2") or record.get("NO2"))
                co_raw = safe_float(measurements.get("CO") or measurements.get("co") or
                                  record.get("co") or record.get("CO"))
                o3_8h_raw = safe_float(measurements.get("O3_8h") or measurements.get("o3_8h") or
                                    record.get("o3_8h") or record.get("O3_8h"))

                # 应用修约规则并更新 measurements
                # 0位小数转为整数类型，避免显示 .0
                measurements['PM2_5'] = int(apply_rounding(pm25_raw, 'PM2_5', 'raw_data'))
                measurements['PM10'] = int(apply_rounding(pm10_raw, 'PM10', 'raw_data'))
                measurements['SO2'] = int(apply_rounding(so2_raw, 'SO2', 'raw_data'))
                measurements['NO2'] = int(apply_rounding(no2_raw, 'NO2', 'raw_data'))
                measurements['CO'] = apply_rounding(co_raw, 'CO', 'raw_data')  # CO保留1位小数
                measurements['O3_8h'] = int(apply_rounding(o3_8h_raw, 'O3_8h', 'raw_data'))

            # 保存到上下文
            data_id = context.data_manager.save_data(
                data=standardized_records,
                schema="air_quality_unified",
                metadata={
                    "source": "gd_suncere_api",
                    "query_type": "station_hour",
                    "stations": stations,
                    "time_range": f"{start_time} - {end_time}",
                    "schema_version": "v2.0",  # UDF v2.0 标记
                    "field_mapping_applied": True,
                    "field_mapping_info": standardizer.get_field_mapping_info() if standardizer else {}
                }
            )

            logger.info(
                "gd_suncere_station_hour_saved",
                data_id=data_id,
                record_count=len(standardized_records)
            )

            return {
                "status": "success",
                "success": True,
                "data": standardized_records[:24],  # 返回前24条供预览
                "metadata": {
                    "tool_name": "query_gd_suncere_station_hour",
                    "data_id": data_id,
                    "total_records": len(standardized_records),
                    "returned_records": min(24, len(standardized_records)),
                    "stations": stations,
                    "time_range": f"{start_time} - {end_time}",
                    "schema_version": "v2.0",  # UDF v2.0 标记
                    "source": "gd_suncere_api"
                },
                "summary": f"成功获取 {', '.join(stations)} 的小时数据共 {len(standardized_records)} 条，已保存为 {data_id}"
            }

        except Exception as e:
            logger.error(
                "query_gd_suncere_station_hour_failed",
                error=str(e),
                error_type=type(e).__name__
            )
            return cls._create_error_response(str(e))

    @classmethod
    def query_regional_comparison(
        cls,
        target_city: str,
        nearby_cities: List[str],
        start_time: str,
        end_time: str,
        context: ExecutionContext
    ) -> Dict[str, Any]:
        """
        区域对比数据查询

        查询目标城市和周边城市的小时数据，用于区域传输分析

        Args:
            target_city: 目标城市名称
            nearby_cities: 周边城市名称列表
            start_time: 开始时间 (YYYY-MM-DD HH:MM:SS)
            end_time: 结束时间 (YYYY-MM-DD HH:MM:SS)
            context: 执行上下文

        Returns:
            查询结果
        """
        logger.info(
            "query_gd_suncere_regional_comparison_start",
            target_city=target_city,
            nearby_cities=nearby_cities,
            start_time=start_time,
            end_time=end_time
        )

        try:
            # 合并目标城市和周边城市
            all_cities = [target_city] + nearby_cities

            # 使用城市小时数据查询
            result = cls.query_city_hour_data(
                cities=all_cities,
                start_time=start_time,
                end_time=end_time,
                context=context
            )

            # 更新元数据以反映这是区域对比查询
            if result.get("success"):
                result["metadata"]["query_type"] = "regional_comparison"
                result["metadata"]["target_city"] = target_city
                result["metadata"]["nearby_cities"] = nearby_cities
                result["summary"] = f"区域对比分析：获取 {target_city} 与 {', '.join(nearby_cities)} 的小时数据共 {result['metadata']['total_records']} 条"

            return result

        except Exception as e:
            logger.error(
                "query_gd_suncere_regional_comparison_failed",
                error=str(e),
                error_type=type(e).__name__
            )
            return cls._create_error_response(str(e))

    @classmethod
    def _create_error_response(cls, message: str) -> Dict[str, Any]:
        """创建错误响应"""
        return {
            "status": "failed",
            "success": False,
            "error": message,
            "data": None,
            "metadata": {},
            "summary": f"查询失败: {message}"
        }

    @staticmethod
    def _smart_sample_data(data: List[Dict], max_records: int = 24) -> List[Dict]:
        """
        智能采样数据（用于大数据集采样）

        策略：
        1. 优先保留首尾数据（时间序列的起点和终点）
        2. 中间部分均匀采样

        Args:
            data: 原始数据列表
            max_records: 最大保留记录数

        Returns:
            采样后的数据
        """
        n = len(data)
        if n <= max_records:
            return data

        # 分配采样比例
        head_ratio = 0.3  # 前30%的记录
        tail_ratio = 0.3  # 后30%的记录
        middle_ratio = 0.4  # 中间40%的记录

        head_count = int(max_records * head_ratio)
        tail_count = int(max_records * tail_ratio)
        middle_count = max_records - head_count - tail_count

        # 采样首部
        head_sample = data[:head_count]

        # 采样尾部
        tail_sample = data[-tail_count:] if tail_count > 0 else []

        # 采样中间部分（均匀采样）
        middle_start = head_count
        middle_end = n - tail_count
        middle_data = data[middle_start:middle_end]

        if middle_count > 0 and len(middle_data) > 0:
            step = max(1, len(middle_data) // middle_count)
            middle_sample = middle_data[::step][:middle_count]
        else:
            middle_sample = []

        sampled = head_sample + middle_sample + tail_sample
        sampled = sampled[:max_records]  # 确保不超过max_records

        return sampled


# 导出函数供工具调用
def execute_query_gd_suncere_city_day(
    cities: List[str],
    start_date: str,
    end_date: str,
    context: ExecutionContext,
    data_type: int = 1,
    enable_sand_deduction: bool = True
) -> Dict[str, Any]:
    """
    执行城市日报数据查询

    Args:
        cities: 城市名称列表，如 ["广州", "深圳", "佛山"]
        start_date: 开始日期，格式 "YYYY-MM-DD"
        end_date: 结束日期，格式 "YYYY-MM-DD"
        context: 执行上下文
        data_type: 数据类型（0原始实况，1审核实况，2原始标况，3审核标况），默认1
        enable_sand_deduction: 是否启用扣沙处理（默认True，剔除沙尘暴天气的PM2.5/PM10数据）

    Returns:
        查询结果字典
    """
    return QueryGDSuncereDataTool.query_city_day_data(
        cities=cities,
        start_date=start_date,
        end_date=end_date,
        context=context,
        data_type=data_type,
        enable_sand_deduction=enable_sand_deduction
    )


def execute_query_gd_suncere_station_hour(
    cities: List[str],
    start_time: str,
    end_time: str,
    context: ExecutionContext,
    include_weather: bool = True
) -> Dict[str, Any]:
    """
    执行站点小时数据查询（实际使用城市小时数据 API）

    注意：此函数内部调用 query_city_hour_data，因为：
    1. 城市小时数据更适合区域对比分析
    2. API 不支持通过城市代码查询站点数据，需要具体站点代码
    3. 城市级别数据已满足大多数分析需求

    Args:
        cities: 城市名称列表
        start_time: 开始时间，格式 "YYYY-MM-DD HH:MM:SS"
        end_time: 结束时间，格式 "YYYY-MM-DD HH:MM:SS"
        context: 执行上下文
        include_weather: 是否包含气象字段（风速、风向、温度、湿度、气压等），默认 True

    Returns:
        查询结果字典

    Note:
        气象字段包括：
        - wind_speed_10m: 10米风速 (m/s)
        - wind_direction_10m: 10米风向 (度)
        - temperature_2m: 2米气温 (°C)
        - relative_humidity_2m: 2米相对湿度 (%)
        - surface_pressure: 地面气压 (hPa)
        - precipitation: 降水量 (mm)
        - visibility: 能见度 (km)

        某些站点的气象字段可能返回空值或无效值（如 -99.000），这是数据源的正常情况。
    """
    return QueryGDSuncereDataTool.query_city_hour_data(
        cities=cities,
        start_time=start_time,
        end_time=end_time,
        context=context,
        include_weather=include_weather
    )


def execute_query_gd_suncere_station_hour_real(
    start_time: str,
    end_time: str,
    context: ExecutionContext,
    cities: Optional[List[str]] = None,
    stations: Optional[List[str]] = None,
    station_type: Optional[str] = None,
    include_weather: bool = True
) -> Dict[str, Any]:
    """
    执行站点级别小时数据查询（真实站点数据）

    与 execute_query_gd_suncere_station_hour（城市级别）不同，此函数：
    1. 将城市名/站点名展开为对应的站点代码列表
    2. 调用 query_station_hour_data API（POST，传站点代码）
    3. 返回站点级别的小时数据（含 station_name 字段）
    4. 支持按站点类型过滤（国控/省控/市控等）
    5. 支持提取气象字段（风速、风向、温度、湿度、气压等）

    Args:
        start_time: 开始时间，格式 "YYYY-MM-DD HH:MM:SS"
        end_time: 结束时间，格式 "YYYY-MM-DD HH:MM:SS"
        context: 执行上下文
        cities: 城市名称列表（如 ["广州"]），工具自动展开为站点代码
        stations: 站点名称列表（如 ["广雅中学", "市监测站"]），直接转编码
        station_type: 站点类型（如"国控"/"省控"/"市控"或"1.0"/"2.0"/"3.0"）
        include_weather: 是否包含气象字段（风速、风向、温度、湿度、气压等），默认 True

    Returns:
        UDF v2.0 格式的查询结果

    Note:
        气象字段包括：
        - wind_speed_10m: 10米风速 (m/s)
        - wind_direction_10m: 10米风向 (度)
        - temperature_2m: 2米气温 (°C)
        - relative_humidity_2m: 2米相对湿度 (%)
        - surface_pressure: 地面气压 (hPa)
        - precipitation: 降水量 (mm)
        - visibility: 能见度 (km)

        某些站点的气象字段可能返回空值或无效值（如 -99.000），这是数据源的正常情况。
    """
    logger.info(
        "query_gd_suncere_station_hour_real_start",
        cities=cities,
        stations=stations,
        start_time=start_time,
        end_time=end_time,
        station_type=station_type
    )

    try:
        api_client = get_gd_suncere_api_client()

        # 将站点名/城市名展开为站点代码（支持站点类型过滤）
        station_codes = []

        if stations:
            # 场景1: 指定站点 - 验证类型匹配
            if station_type:
                is_valid, mismatched, error_msg = GeoMappingResolver.validate_station_type_match(
                    stations, station_type
                )
                if not is_valid:
                    return {
                        "status": "failed",
                        "success": False,
                        "data": [],
                        "summary": f"站点类型不匹配: {error_msg}",
                        "metadata": {
                            "station_type": station_type,
                            "stations": stations,
                            "error": "Station type mismatch"
                        }
                    }
            station_codes.extend(GeoMappingResolver.resolve_station_codes(stations))

        if cities:
            # 场景2: 指定城市 - 按类型+城市过滤（支持多城市并发查询）
            if station_type:
                type_codes, metadata = GeoMappingResolver.resolve_station_codes_by_type(
                    station_type, cities
                )
                if not type_codes:
                    type_name = metadata.get("type_name", station_type)
                    return {
                        "status": "empty",
                        "success": True,
                        "data": [],
                        "summary": f"未找到类型为'{type_name}'的站点（城市：{', '.join(cities)}）",
                        "metadata": {
                            "station_type": station_type,
                            "type_id": metadata.get("type_id"),
                            "cities": cities,
                            "stations": [],
                            "suggestion": f"该城市没有{type_name}站点，建议使用其他站点类型查询"
                        }
                    }
                station_codes.extend(type_codes)
            else:
                station_codes.extend(GeoMappingResolver.resolve_station_codes_by_city(cities))

        # 去重保持顺序
        seen = set()
        station_codes = [c for c in station_codes if not (c in seen or seen.add(c))]

        if not station_codes:
            raise Exception(f"未找到任何有效的站点代码: cities={cities}, stations={stations}")

        logger.info(
            "station_hour_real_codes_resolved",
            cities=cities,
            stations=stations,
            station_codes=station_codes,
            station_count=len(station_codes)
        )

        # 智能计算 DataSource 参数
        data_type = QueryGDSuncereDataTool.calculate_data_source(end_time)

        # 调用站点小时数据 API
        response = api_client.query_station_hour_data(
            station_codes=station_codes,
            start_time=start_time,
            end_time=end_time,
            data_type=data_type
        )

        if not response.get("success"):
            error_msg = response.get("msg", "Unknown error")
            raise Exception(f"API 查询失败: {error_msg}")

        # 提取结果
        raw_records = response.get("result", [])

        if not raw_records:
            logger.warning(
                "query_station_hour_real_no_data",
                cities=cities,
                stations=stations,
                station_codes=station_codes,
                time_range=f"{start_time} - {end_time}"
            )
            return {
                "status": "empty",
                "success": True,
                "data": [],
                "metadata": {
                    "tool_name": "query_gd_suncere_station_hour",
                    "cities": cities,
                    "stations": stations,
                    "station_codes": station_codes,
                    "time_range": f"{start_time} - {end_time}",
                    "message": "查询成功但无数据返回"
                },
                "summary": f"未找到 {', '.join(cities)} 站点在指定时间段的小时数据"
            }

        logger.info(
            "station_hour_real_data_received",
            record_count=len(raw_records)
        )

        # 数据标准化
        standardizer = get_data_standardizer()
        standardized_records = standardizer.standardize(raw_records)

        # 根据 include_weather 参数决定是否保留气象字段
        if not include_weather:
            # 移除气象字段（保持当前默认行为）
            weather_fields = [
                'wind_speed_10m', 'wind_direction_10m',
                'temperature_2m', 'relative_humidity_2m',
                'surface_pressure', 'wind_gusts_10m',
                'precipitation', 'cloud_cover', 'visibility'
            ]
            for record in standardized_records:
                measurements = record.get('measurements', {})
                for field in weather_fields:
                    measurements.pop(field, None)
            logger.debug(
                "gd_suncere_station_hour_real_weather_fields_removed",
                weather_fields=weather_fields
            )
        else:
            logger.debug(
                "gd_suncere_station_hour_real_weather_fields_included"
            )

        # 补充 station_name 字段（优先使用 API 返回的 name 字段）
        for record in standardized_records:
            # 优先使用 API 返回的 name 字段（站点中文名称）
            station_name = record.get("name", "")
            if station_name:
                record["station_name"] = station_name
            else:
                # 降级：通过 station_code 解析站点名称
                code = record.get("station_code", "")
                record["station_name"] = GeoMappingResolver.resolve_station_name(code)

        # 对小时数据浓度值应用修约规则（按原始监测数据规则：保留整数位）
        def safe_float(value, default=0.0):
            if value is None or value == '' or value == '-':
                return default
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        for record in standardized_records:
            measurements = record.get("measurements", {})

            pm25_raw = safe_float(measurements.get("PM2_5") or measurements.get("pm2_5") or
                                record.get("pm2_5") or record.get("PM2_5"))
            pm10_raw = safe_float(measurements.get("PM10") or measurements.get("pm10") or
                                record.get("pm10") or record.get("PM10"))
            so2_raw = safe_float(measurements.get("SO2") or measurements.get("so2") or
                               record.get("so2") or record.get("SO2"))
            no2_raw = safe_float(measurements.get("NO2") or measurements.get("no2") or
                               record.get("no2") or record.get("NO2"))
            co_raw = safe_float(measurements.get("CO") or measurements.get("co") or
                              record.get("co") or record.get("CO"))
            o3_8h_raw = safe_float(measurements.get("O3_8h") or measurements.get("o3_8h") or
                                record.get("o3_8h") or record.get("O3_8h"))

            measurements['PM2_5'] = int(apply_rounding(pm25_raw, 'PM2_5', 'raw_data'))
            measurements['PM10'] = int(apply_rounding(pm10_raw, 'PM10', 'raw_data'))
            measurements['SO2'] = int(apply_rounding(so2_raw, 'SO2', 'raw_data'))
            measurements['NO2'] = int(apply_rounding(no2_raw, 'NO2', 'raw_data'))
            measurements['CO'] = apply_rounding(co_raw, 'CO', 'raw_data')
            measurements['O3_8h'] = int(apply_rounding(o3_8h_raw, 'O3_8h', 'raw_data'))

        # 按新标准重算 IAQI、AQI 和首要污染物
        import math
        for record in standardized_records:
            measurements = record.get("measurements", {})

            # 获取修约后的浓度值
            pm25 = safe_float(measurements.get("PM2_5"))
            pm10 = safe_float(measurements.get("PM10"))
            so2 = safe_float(measurements.get("SO2"))
            no2 = safe_float(measurements.get("NO2"))
            co = safe_float(measurements.get("CO"))
            o3_8h = safe_float(measurements.get("O3_8h"))

            # 使用新标准计算 IAQI（向上进位取整数）
            pm25_iaqi = math.ceil(calculate_iaqi(pm25, 'PM2_5', 'new'))
            pm10_iaqi = math.ceil(calculate_iaqi(pm10, 'PM10', 'new'))
            so2_iaqi = math.ceil(calculate_iaqi(so2, 'SO2', 'new'))
            no2_iaqi = math.ceil(calculate_iaqi(no2, 'NO2', 'new'))
            co_iaqi = math.ceil(calculate_iaqi(co, 'CO', 'new'))
            o3_8h_iaqi = math.ceil(calculate_iaqi(o3_8h, 'O3_8h', 'new'))

            # 保存新标准 IAQI
            measurements['PM2_5_IAQI'] = pm25_iaqi
            measurements['PM10_IAQI'] = pm10_iaqi
            measurements['SO2_IAQI'] = so2_iaqi
            measurements['NO2_IAQI'] = no2_iaqi
            measurements['CO_IAQI'] = co_iaqi
            measurements['O3_8h_IAQI'] = o3_8h_iaqi

            # 计算 AQI（取最大 IAQI）
            aqi = max(pm25_iaqi, pm10_iaqi, so2_iaqi, no2_iaqi, co_iaqi, o3_8h_iaqi)
            measurements['AQI'] = aqi

            # 确定首要污染物（AQI > 50 时才有首要污染物）
            if aqi > 50:
                pollutants_with_iaqi = {
                    'PM2_5': pm25_iaqi,
                    'PM10': pm10_iaqi,
                    'SO2': so2_iaqi,
                    'NO2': no2_iaqi,
                    'CO': co_iaqi,
                    'O3_8h': o3_8h_iaqi
                }
                primary_pollutants = [p for p, iaqi in pollutants_with_iaqi.items() if iaqi == aqi]
                # 将首要污染物列表转换为中文
                primary_pollutant_map = {
                    'PM2_5': 'PM2.5',
                    'PM10': 'PM10',
                    'SO2': 'SO2',
                    'NO2': 'NO2',
                    'CO': 'CO',
                    'O3_8h': 'O3'
                }
                primary_pollutants_zh = [primary_pollutant_map.get(p, p) for p in primary_pollutants]
                record['primary_pollutant'] = ', '.join(primary_pollutants_zh) if primary_pollutants_zh else '-'
            else:
                record['primary_pollutant'] = '-'

        logger.info(
            "station_hour_new_standard_indices_calculated",
            record_count=len(standardized_records)
        )

        # 保存到上下文
        data_id = context.data_manager.save_data(
            data=standardized_records,
            schema="air_quality_unified",
            metadata={
                "source": "gd_suncere_api",
                "query_type": "station_hour",
                "cities": cities,
                "stations": stations,
                "station_codes": station_codes,
                "time_range": f"{start_time} - {end_time}",
                "schema_version": "v2.0",
                "field_mapping_applied": True,
                "field_mapping_info": standardizer.get_field_mapping_info() if standardizer else {}
            }
        )

        logger.info(
            "gd_suncere_station_hour_real_saved",
            data_id=data_id,
            record_count=len(standardized_records)
        )

        return {
            "status": "success",
            "success": True,
            "data": standardized_records[:24],
            "metadata": {
                "tool_name": "query_gd_suncere_station_hour",
                "data_id": data_id,
                "total_records": len(standardized_records),
                "returned_records": min(24, len(standardized_records)),
                "cities": cities,
                "stations": stations,
                "station_codes": station_codes,
                "time_range": f"{start_time} - {end_time}",
                "schema_version": "v2.0",
                "source": "gd_suncere_api"
            },
            "summary": f"成功获取站点级别小时数据共 {len(standardized_records)} 条，已保存为 {data_id}"
        }

    except Exception as e:
        logger.error(
            "query_gd_suncere_station_hour_real_failed",
            error=str(e),
            error_type=type(e).__name__
        )
        return QueryGDSuncereDataTool._create_error_response(str(e))


def execute_query_gd_suncere_regional_comparison(
    target_city: str,
    nearby_cities: List[str],
    start_time: str,
    end_time: str,
    context: ExecutionContext
) -> Dict[str, Any]:
    """
    执行区域对比数据查询

    查询目标城市和周边城市的小时数据，用于区域传输分析

    Args:
        target_city: 目标城市名称
        nearby_cities: 周边城市名称列表
        start_time: 开始时间，格式 "YYYY-MM-DD HH:MM:SS"
        end_time: 结束时间，格式 "YYYY-MM-DD HH:MM:SS"
        context: 执行上下文

    Returns:
        查询结果字典
    """
    return QueryGDSuncereDataTool.query_regional_comparison(
        target_city=target_city,
        nearby_cities=nearby_cities,
        start_time=start_time,
        end_time=end_time,
        context=context
    )


def execute_query_gd_suncere_report(
    cities: List[str],
    start_time: str,
    end_time: str,
    time_type: int = 8,
    area_type: int = 2,
    pollutant_codes: Optional[List[str]] = None,
    context: Optional[ExecutionContext] = None
) -> Dict[str, Any]:
    """
    执行综合统计报表查询

    支持周报、月报、季报、年报、任意时间综合报表数据查询

    Args:
        cities: 城市名称列表
        start_time: 开始时间，格式 "YYYY-MM-DD HH:MM:SS"
        end_time: 结束时间，格式 "YYYY-MM-DD HH:MM:SS"
        time_type: 报表类型，3=周报, 4=月报, 5=季报, 7=年报, 8=任意时间（默认8）
        area_type: 区域类型，0=站点, 1=区县, 2=城市（默认2）
        pollutant_codes: 污染物代码列表（可选），如 ["PM2.5", "SO2"]
        context: 执行上下文

    Returns:
        查询结果字典
    """
    logger.info(
        "query_gd_suncere_report_start",
        cities=cities,
        start_time=start_time,
        end_time=end_time,
        time_type=time_type,
        area_type=area_type,
        pollutant_codes=pollutant_codes
    )

    try:
        api_client = get_gd_suncere_api_client()

        # 转换城市名称为编码
        city_codes = QueryGDSuncereDataTool.geo_resolver.resolve_city_codes(cities)

        if not city_codes:
            raise Exception(f"未找到任何有效的城市代码: {cities}")

        # 智能计算 DataSource 参数
        data_source = QueryGDSuncereDataTool.calculate_data_source(end_time)

        # 调用 API 综合统计报表查询
        # 参考 Vanna 实现：使用 GetReportForRangeListFilterAsync 端点
        endpoint = "/api/airprovinceproduct/dataanalysis/ReportDataQuery/GetReportForRangeListFilterAsync"

        # 构造请求参数
        payload = {
            "AreaType": area_type,
            "TimeType": time_type,
            "TimePoint": [start_time, end_time],
            "StationCode": city_codes,
            "DataSource": data_source
        }

        # 添加污染物代码过滤（可选）
        if pollutant_codes:
            # 转换污染物代码格式（如 "PM2.5" -> "pM2_5"）
            mapped_codes = []
            for code in pollutant_codes:
                # 标准化污染物代码
                code_upper = code.upper().replace(".", "_")
                if code_upper.startswith("PM"):
                    code_upper = code_upper.replace("PM", "pM") + "_"
                elif code_upper in ["SO2", "NO2", "O3", "CO"]:
                    code_upper = code_upper.lower()
                mapped_codes.append(code_upper)
            payload["PollutantCode"] = mapped_codes

        logger.info(
            "query_report_calling_api",
            endpoint=endpoint,
            payload=payload
        )

        # 使用 _make_request 调用 API
        token = api_client.get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "SysCode": "SunAirProvince",
            "syscode": "SunAirProvince",
            "Content-Type": "application/json"
        }

        url = f"{api_client.BASE_URL}{endpoint}"

        import requests
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=30
        )

        if response.status_code != 200:
            raise Exception(f"API 请求失败: {response.status_code} - {response.text}")

        response_data = response.json()

        if not response_data.get("success"):
            error_msg = response_data.get("msg", "Unknown error")
            raise Exception(f"API 查询失败: {error_msg}")

        # 提取结果 - 处理不同的响应格式
        result = response_data.get("result")

        # 处理不同的响应格式
        if isinstance(result, list):
            # result 直接是列表
            raw_records = result
        elif isinstance(result, dict):
            # result 是字典，提取 items
            raw_records = result.get("items", [])
        else:
            # 未知格式
            raw_records = []

        logger.info(
            "query_report_response_parsed",
            result_type=type(result).__name__,
            record_count=len(raw_records) if raw_records else 0
        )

        if not raw_records:
            logger.warning(
                "query_report_no_data",
                cities=cities,
                time_range=f"{start_time} to {end_time}"
            )
            return {
                "status": "empty",
                "success": True,
                "data": [],
                "metadata": {
                    "tool_name": "query_gd_suncere_report",
                    "cities": cities,
                    "time_range": f"{start_time} to {end_time}",
                    "time_type": time_type,
                    "area_type": area_type,
                    "message": "查询成功但无数据返回"
                },
                "summary": f"未找到 {', '.join(cities)} 在指定时间段的综合报表数据"
            }

        logger.info(
            "query_report_data_received",
            record_count=len(raw_records)
        )

        # 数据标准化（如果提供了 context）
        standardized_records = raw_records
        if context:
            standardizer = get_data_standardizer()
            standardized_records = standardizer.standardize(raw_records)

            logger.info(
                "gd_suncere_report_standardized",
                raw_count=len(raw_records),
                standardized_count=len(standardized_records)
            )

            # 保存到上下文
            data_id = context.data_manager.save_data(
                data=standardized_records,
                schema="air_quality_unified",
                metadata={
                    "source": "gd_suncere_api",
                    "query_type": "report",
                    "cities": cities,
                    "time_range": f"{start_time} to {end_time}",
                    "time_type": time_type,
                    "area_type": area_type,
                    "schema_version": "v2.0",
                    "field_mapping_applied": True,
                    "field_mapping_info": standardizer.get_field_mapping_info() if standardizer else {}
                }
            )

            logger.info(
                "gd_suncere_report_saved",
                data_id=data_id,
                record_count=len(standardized_records)
            )

            return {
                "status": "success",
                "success": True,
                "data": standardized_records[:24],  # 返回前24条供预览
                "metadata": {
                    "tool_name": "query_gd_suncere_report",
                    "data_id": data_id,
                    "total_records": len(standardized_records),
                    "returned_records": min(24, len(standardized_records)),
                    "cities": cities,
                    "time_range": f"{start_time} to {end_time}",
                    "time_type": time_type,
                    "area_type": area_type,
                    "schema_version": "v2.0",
                    "source": "gd_suncere_api"
                },
                "summary": f"成功获取 {', '.join(cities)} 的综合报表数据共 {len(standardized_records)} 条，已保存为 {data_id}"
            }

        # 没有 context 时直接返回数据
        return {
            "status": "success",
            "success": True,
            "data": raw_records[:24],
            "metadata": {
                "tool_name": "query_gd_suncere_report",
                "total_records": len(raw_records),
                "returned_records": min(24, len(raw_records)),
                "cities": cities,
                "time_range": f"{start_time} to {end_time}",
                "time_type": time_type,
                "area_type": area_type,
                "source": "gd_suncere_api"
            },
            "summary": f"成功获取 {', '.join(cities)} 的综合报表数据共 {len(raw_records)} 条"
        }

    except Exception as e:
        logger.error(
            "query_gd_suncere_report_failed",
            error=str(e),
            error_type=type(e).__name__
        )
        return QueryGDSuncereDataTool._create_error_response(str(e))


def execute_query_gd_suncere_report_compare(
    cities: List[str],
    time_point: List[str],
    contrast_time: List[str],
    time_type: int = 8,
    area_type: int = 2,
    pollutant_codes: Optional[List[str]] = None,
    context: Optional[ExecutionContext] = None
) -> Dict[str, Any]:
    """
    执行对比分析报表查询

    支持月报、任意时间段对比分析报表数据查询

    Args:
        cities: 城市名称列表
        time_point: 当前时间范围，格式 ["YYYY-MM-DD HH:MM:SS", "YYYY-MM-DD HH:MM:SS"]
        contrast_time: 对比时间范围，格式 ["YYYY-MM-DD HH:MM:SS", "YYYY-MM-DD HH:MM:SS"]
        time_type: 报表类型，4=月报, 8=任意时间（默认8）
        area_type: 区域类型，0=站点, 1=区县, 2=城市（默认2）
        pollutant_codes: 污染物代码列表（可选）
        context: 执行上下文

    Returns:
        查询结果字典
    """
    logger.info(
        "query_gd_suncere_report_compare_start",
        cities=cities,
        time_point=time_point,
        contrast_time=contrast_time,
        time_type=time_type,
        area_type=area_type,
        pollutant_codes=pollutant_codes
    )

    try:
        api_client = get_gd_suncere_api_client()

        # 转换城市名称为编码
        city_codes = QueryGDSuncereDataTool.geo_resolver.resolve_city_codes(cities)

        if not city_codes:
            raise Exception(f"未找到任何有效的城市代码: {cities}")

        # 智能计算 DataSource 参数（使用当前时间的结束时间）
        current_end_time = time_point[1] if len(time_point) > 1 else time_point[0]
        data_source = QueryGDSuncereDataTool.calculate_data_source(current_end_time)

        # 调用 API 对比分析报表查询
        # 参考 Vanna 实现：使用 GetReportForRangeCompareListFilterAsync 端点
        endpoint = "/api/airprovinceproduct/dataanalysis/ReportDataQuery/GetReportForRangeCompareListFilterAsync"

        # 构造请求参数
        payload = {
            "AreaType": area_type,
            "TimeType": time_type,
            "TimePoint": time_point,
            "ContrastTime": contrast_time,
            "StationCode": city_codes,
            "DataSource": data_source
        }

        # 添加污染物代码过滤（可选）
        if pollutant_codes:
            # 转换污染物代码格式
            mapped_codes = []
            for code in pollutant_codes:
                # 标准化污染物代码
                code_upper = code.upper().replace(".", "_")
                if code_upper.startswith("PM"):
                    code_upper = "pM" + code_upper[2:] + "_"
                elif code_upper in ["SO2", "NO2", "O3", "CO"]:
                    code_upper = code_upper.lower()
                mapped_codes.append(code_upper)
            payload["PollutantCode"] = mapped_codes

        logger.info(
            "query_report_compare_calling_api",
            endpoint=endpoint,
            payload=payload
        )

        # 使用 _make_request 调用 API
        token = api_client.get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "SysCode": "SunAirProvince",
            "syscode": "SunAirProvince",
            "Content-Type": "application/json"
        }

        url = f"{api_client.BASE_URL}{endpoint}"

        import requests
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=30
        )

        if response.status_code != 200:
            raise Exception(f"API 请求失败: {response.status_code} - {response.text}")

        response_data = response.json()

        if not response_data.get("success"):
            error_msg = response_data.get("msg", "Unknown error")
            raise Exception(f"API 查询失败: {error_msg}")

        # 提取结果
        raw_records = response_data.get("result", [])

        if not raw_records:
            logger.warning(
                "query_report_compare_no_data",
                cities=cities,
                time_point=time_point,
                contrast_time=contrast_time
            )
            return {
                "status": "empty",
                "success": True,
                "data": [],
                "metadata": {
                    "tool_name": "query_gd_suncere_report_compare",
                    "cities": cities,
                    "time_point": time_point,
                    "contrast_time": contrast_time,
                    "time_type": time_type,
                    "area_type": area_type,
                    "message": "查询成功但无数据返回"
                },
                "summary": f"未找到 {', '.join(cities)} 在指定时间段的对比报表数据"
            }

        logger.info(
            "query_report_compare_data_received",
            record_count=len(raw_records)
        )

        # 数据标准化（如果提供了 context）
        standardized_records = raw_records
        if context:
            standardizer = get_data_standardizer()
            standardized_records = standardizer.standardize(raw_records)

            logger.info(
                "gd_suncere_report_compare_standardized",
                raw_count=len(raw_records),
                standardized_count=len(standardized_records)
            )

            # 保存到上下文
            data_id = context.data_manager.save_data(
                data=standardized_records,
                schema="air_quality_unified",
                metadata={
                    "source": "gd_suncere_api",
                    "query_type": "report_compare",
                    "cities": cities,
                    "time_point": time_point,
                    "contrast_time": contrast_time,
                    "time_type": time_type,
                    "area_type": area_type,
                    "schema_version": "v2.0",
                    "field_mapping_applied": True,
                    "field_mapping_info": standardizer.get_field_mapping_info() if standardizer else {}
                }
            )

            logger.info(
                "gd_suncere_report_compare_saved",
                data_id=data_id,
                record_count=len(standardized_records)
            )

            return {
                "status": "success",
                "success": True,
                "data": standardized_records[:24],  # 返回前24条供预览
                "metadata": {
                    "tool_name": "query_gd_suncere_report_compare",
                    "data_id": data_id,
                    "total_records": len(standardized_records),
                    "returned_records": min(24, len(standardized_records)),
                    "cities": cities,
                    "time_point": time_point,
                    "contrast_time": contrast_time,
                    "time_type": time_type,
                    "area_type": area_type,
                    "schema_version": "v2.0",
                    "source": "gd_suncere_api"
                },
                "summary": f"成功获取 {', '.join(cities)} 的对比报表数据共 {len(standardized_records)} 条，已保存为 {data_id}"
            }

        # 没有 context 时直接返回数据
        return {
            "status": "success",
            "success": True,
            "data": raw_records[:24],
            "metadata": {
                "tool_name": "query_gd_suncere_report_compare",
                "total_records": len(raw_records),
                "returned_records": min(24, len(raw_records)),
                "cities": cities,
                "time_point": time_point,
                "contrast_time": contrast_time,
                "time_type": time_type,
                "area_type": area_type,
                "source": "gd_suncere_api"
            },
            "summary": f"成功获取 {', '.join(cities)} 的对比报表数据共 {len(raw_records)} 条"
        }

    except Exception as e:
        logger.error(
            "query_gd_suncere_report_compare_failed",
            error=str(e),
            error_type=type(e).__name__
        )
        return QueryGDSuncereDataTool._create_error_response(str(e))


def execute_query_gd_suncere_station_day(
    cities: Optional[List[str]] = None,
    stations: Optional[List[str]] = None,
    start_date: str = None,
    end_date: str = None,
    context: Optional[ExecutionContext] = None,
    data_type: int = 1,
    station_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    执行站点日报数据查询

    支持按城市名展开（自动查询该城市下所有站点）或直接输入站点名称
    支持按站点类型过滤（国控/省控/市控等）

    Args:
        cities: 城市名称列表（与 stations 二选一，可组合）
        stations: 站点名称列表（与 cities 二选一，可组合）
        start_date: 开始日期，格式 "YYYY-MM-DD"
        end_date: 结束日期，格式 "YYYY-MM-DD"
        context: 执行上下文
        data_type: 数据类型（0原始实况，1审核实况，2原始标况，3审核标况），默认1
        station_type: 站点类型（如"国控"/"省控"/"市控"或"1.0"/"2.0"/"3.0"）

    Returns:
        查询结果字典
    """
    logger.info(
        "execute_query_gd_suncere_station_day",
        cities=cities,
        stations=stations,
        start_date=start_date,
        end_date=end_date,
        data_type=data_type,
        station_type=station_type
    )

    return QueryGDSuncereDataTool.query_station_day_data(
        cities=cities,
        stations=stations,
        start_date=start_date,
        end_date=end_date,
        context=context,
        data_type=data_type,
        station_type=station_type
    )


# =============================================================================
# 新旧标准对比查询工具
# =============================================================================

# -----------------------------------------------------------------------------
# API 字段映射速查表 (调试参考)
# -----------------------------------------------------------------------------
"""
【日报数据接口】DATCityDay 关键字段：
  原始字段名     → 标准化字段名    示例值
  ───────────────────────────────────────────────
  name          → city          广州  ← 注意：不是 cityName！
  code          → city_code     440100
  timePoint     → timestamp     2026-03-01T00:00:00
  pM2_5         → PM2_5         9
  pM10          → PM10          17
  sO2           → SO2           5
  nO2           → NO2           18
  o3_8H         → O3_8h         53
  co            → CO            0.6
  pM2_5_IAQI    → PM2_5_IAQI    13
  aqi           → AQI           27

【统计数据接口】ReportDataQuery 关键字段：
  原始字段名        → 标准化字段名       示例值
  ───────────────────────────────────────────────────
  cityName          → city             广州
  cityCode          → city_code        440100
  compositeIndex    → composite_index  2.10  ← 旧标准综合指数
  overDays          → over_days        0     ← 超标天数
  overRate          → over_rate        0     ← 超标率
  rank              → rank             1     ← 排名
  maxIndex          → max_index        0.67  ← 最大单项指数

【字段映射配置位置】
  文件: app/utils/data_standardizer.py
  映射: self.station_field_mapping = {
      "name": "city",         # ← 日报数据必须添加此映射
      "cityName": "city",     # ← 统计数据必须添加此映射
      ...
  }
"""

# -----------------------------------------------------------------------------
# 修约规则配置（按GB/T 8170-2008数值修约规则与极限数值的表示和判定）
# -----------------------------------------------------------------------------
# 四舍六入五成双（银行家舍入法）- Python的round()函数已实现此规则
#
# 说明：
# 1. 原始监测数据：污染物原始监测数据（小时或日数据）的保留小数位数要求
# 2. 统计数据：基于日数据计算月、季、年均值及特定百分位数时的保留小数位数
#    - 统计数据可比日数据多保留1位小数或同日数据
#    - PM2.5：日数据0位 → 统计数据1位（多保留1位）
#    - 其他污染物：统计数据同日数据
#
# 保留小数位数配置
ROUNDING_PRECISION = {
    # 原始监测数据（小时或日数据）- "原始监测数据"列
    'raw_data': {
        'PM2_5': 0,      # μg/m³，保留0位
        'PM10': 0,       # μg/m³，保留0位
        'SO2': 0,        # μg/m³，保留0位
        'NO2': 0,        # μg/m³，保留0位
        'O3_8h': 0,      # μg/m³，保留0位
        'CO': 1,         # mg/m³，保留1位
        'NO': 0,         # μg/m³，保留0位
        'NOx': 0,        # μg/m³，保留0位
    },
    # 统计数据（月、季、年均值及特定百分位数）- "统计数据"列
    # 基于日数据计算时，可比日数据多保留1位或同日数据
    'statistical_data': {
        'PM2_5': 1,      # μg/m³，保留1位
        'PM10': 1,       # μg/m³，保留1位
        'SO2': 1,        # μg/m³，保留1位
        'NO2': 1,        # μg/m³，保留1位
        'O3_8h': 1,      # μg/m³，保留1位
        'CO': 2,         # mg/m³，保留2位
        'NO': 0,         # μg/m³，保留0位（同日数据）
        'NOx': 0,        # μg/m³，保留0位（同日数据）
    },
    # 达标评价数据 - "达标评价数据"列
    'evaluation_data': {
        'PM2_5': 0,      # μg/m³，保留0位
        'PM10': 0,       # μg/m³，保留0位
        'SO2': 0,        # μg/m³，保留0位
        'NO2': 0,        # μg/m³，保留0位
        'O3_8h': 0,      # μg/m³，保留0位
        'CO': 1,         # mg/m³，保留1位
        'exceed_multiple': 2,  # 超标倍数，保留2位
        'compliance_rate': 1,  # 达标率（%），保留1位
    },
    # 最终输出修约规则（一般修约规范）
    'final_output': {
        'PM2_5': 1,      # μg/m³，保留1位小数
        'CO': 1,         # mg/m³，保留1位小数
        'SO2': 0,        # μg/m³，取整
        'NO2': 0,        # μg/m³，取整
        'PM10': 0,       # μg/m³，取整
        'O3_8h': 0,      # μg/m³，取整
    },
    # 其他指标（中间计算值）
    'other': {
        'composite_index': 3,      # 综合指数，保留3位
        'single_index': 3,         # 单项质量指数，保留3位（中间计算值）
    }
}


def safe_round(value: float, precision: int) -> float:
    """
    通用修约函数（四舍六入五成双）

    使用Decimal进行精确修约，避免浮点数精度问题

    Args:
        value: 原始值
        precision: 保留的小数位数

    Returns:
        修约后的值
    """
    if value is None:
        return 0.0

    from decimal import Decimal, ROUND_HALF_EVEN

    # 将浮点数转换为字符串再转换为Decimal，避免浮点数精度问题
    value_str = format(value, f'.{precision + 5}f').rstrip('0').rstrip('.')
    decimal_value = Decimal(value_str)

    # 构造修约单位（如0.01表示保留2位小数）
    quantize_unit = Decimal('0.' + '0' * precision) if precision > 0 else Decimal('1')

    # 使用ROUND_HALF_EVEN进行修约
    rounded = decimal_value.quantize(quantize_unit, rounding=ROUND_HALF_EVEN)

    return float(rounded)


def apply_rounding(value: float, pollutant: str, data_type: str = 'statistical_data') -> float:
    """
    应用修约规则（四舍六入五成双）

    使用Decimal进行精确修约，避免浮点数精度问题

    Args:
        value: 原始值
        pollutant: 污染物名称（如'PM2_5', 'SO2'等）
        data_type: 数据类型（'raw_data', 'statistical_data', 'evaluation_data', 'final_output'）

    Returns:
        修约后的值
    """
    if value is None:
        return 0.0

    # 获取该污染物的修约精度
    precision = ROUNDING_PRECISION.get(data_type, {}).get(pollutant, 2)

    # 调用通用修约函数
    return safe_round(value, precision)


def format_pollutant_value(value: float, pollutant: str, data_type: str = 'statistical_data', use_final_rounding: bool = False):
    """
    格式化污染物浓度值，确保按修约规范正确显示小数位数

    用于返回结果中的数值格式化：
    - 默认（综合指数计算）：所有污染物（除CO外）保留1位小数，CO保留2位小数
    - 最终输出（use_final_rounding=True）：PM2.5和CO保留1位小数，其他四个指标取整

    Args:
        value: 已修约的数值
        pollutant: 污染物名称
        data_type: 数据类型
        use_final_rounding: 是否使用最终输出修约规则（一般修约规范）

    Returns:
        格式化后的值（整数、浮点数或字符串）
    """
    if value is None:
        return 0.0

    # 如果使用最终输出修约规则，重新应用修约
    if use_final_rounding:
        rounded_value = apply_rounding(value, pollutant, 'final_output')
        # 获取修约精度，决定返回类型
        precision = ROUNDING_PRECISION.get('final_output', {}).get(pollutant, 2)
        if precision == 0:
            return int(rounded_value)  # 返回整数类型
        return rounded_value

    # 返回浮点数（已修约的值）
    return float(value)


# -----------------------------------------------------------------------------
# 新标准断点配置
# -----------------------------------------------------------------------------
# 《环境空气质量标准》（GB 3095-2012）二级标准限值（单位：μg/m³，CO为mg/m³）

# 24小时平均标准限值（用于超标判断）
# 注意：新标准（HJ 633-2026）相比旧标准（HJ 633-2013）加严了PM2.5和PM10的限值
# - PM2.5: 新标准60 vs 旧标准75
# - PM10: 新标准120 vs 旧标准150
STANDARD_LIMITS = {
    'PM2_5': 60,   # 新标准24小时平均二级标准（HJ 633-2026，IAQI=100对应60）
    'PM10': 120,   # 新标准24小时平均二级标准（HJ 633-2026，IAQI=100对应120）
    'SO2': 150,    # 24小时平均二级标准
    'NO2': 80,     # 24小时平均二级标准
    'CO': 4,       # 24小时平均二级标准（mg/m³）
    'O3_8h': 160   # 日最大8小时平均二级标准
}

# 旧标准24小时平均限值（用于旧标准超标判断）
# 参考：HJ 633-2013 环境空气质量评价技术规范
OLD_STANDARD_LIMITS = {
    'PM2_5': 75,   # 旧标准24小时平均二级标准（HJ 633-2013，IAQI=100对应75）
    'PM10': 150,   # 旧标准24小时平均二级标准（HJ 633-2013，IAQI=100对应150）
    'SO2': 150,    # 24小时平均二级标准（与新标准相同）
    'NO2': 80,     # 24小时平均二级标准（与新标准相同）
    'CO': 4,       # 24小时平均二级标准（mg/m³，与新标准相同）
    'O3_8h': 160   # 日最大8小时平均二级标准（与新标准相同）
}

# 用于年均综合指数计算的标准限值（与超标判断分开）
# 注意：PM10和PM2.5采用收严后的新标准限值
ANNUAL_STANDARD_LIMITS = {
    'PM2_5': 30,   # 年平均二级标准（新标准收严：35→30）
    'PM10': 60,    # 年平均二级标准（新标准收严：70→60）
    'SO2': 60,     # 年平均二级标准
    'NO2': 40,     # 年平均二级标准
    'CO': 4,       # 24小时平均二级标准（mg/m³）
    'O3_8h': 160   # 日最大8小时平均二级标准
}

# 旧标准年均标准限值（HJ 633-2013）
ANNUAL_STANDARD_LIMITS_OLD = {
    'PM2_5': 35,   # 年平均二级标准（旧标准）
    'PM10': 70,    # 年平均二级标准（旧标准）
    'SO2': 60,     # 年平均二级标准
    'NO2': 40,     # 年平均二级标准
    'CO': 4,       # 24小时平均二级标准（mg/m³）
    'O3_8h': 160   # 日最大8小时平均二级标准
}

# 权重配置（PM2.5取3，O3、NO2取2）
WEIGHTS = {
    'PM2_5': 3,
    'PM10': 1,
    'SO2': 1,
    'NO2': 2,
    'CO': 1,
    'O3_8h': 2
}

# -----------------------------------------------------------------------------
# IAQI 分段标准表（用于计算空气质量分指数）
# 参考：HJ 633-2026 环境空气质量评价技术规范
# -----------------------------------------------------------------------------
# IAQI 分段断点表：[浓度限值, IAQI值]
# 浓度单位：μg/m³（CO为mg/m³）

# 旧标准IAQI分段表（HJ 633-2013）
IAQI_BREAKPOINTS_OLD = {
    'SO2': [        # SO2 日平均
        (0, 0), (50, 50), (150, 100), (475, 150),
        (800, 200), (1600, 300), (2100, 400), (2620, 500)
    ],
    'NO2': [        # NO2 日平均
        (0, 0), (40, 50), (80, 100), (180, 150),
        (280, 200), (565, 300), (750, 400), (940, 500)
    ],
    'PM10': [       # PM10 日平均（旧标准）
        (0, 0), (50, 50), (150, 100), (250, 150),
        (350, 200), (420, 300), (500, 400), (600, 500)
    ],
    'CO': [         # CO 日平均（mg/m³）
        (0, 0), (2, 50), (4, 100), (14, 150),
        (24, 200), (36, 300), (48, 400), (60, 500)
    ],
    'O3_8h': [      # O3 日最大8小时平均
        (0, 0), (100, 50), (160, 100), (215, 150),
        (265, 200), (800, 300)  # 浓度 > 800 时，IAQI 固定为 300
    ],
    'PM2_5': [      # PM2.5 日平均（旧标准）
        (0, 0), (35, 50), (75, 100), (115, 150),
        (150, 200), (250, 300), (350, 400), (500, 500)
    ]
}

# 新标准IAQI分段表（HJ 633-2026）
IAQI_BREAKPOINTS_NEW = {
    'SO2': [        # SO2 日平均
        (0, 0), (50, 50), (150, 100), (475, 150),
        (800, 200), (1600, 300), (2100, 400), (2620, 500)
    ],
    'NO2': [        # NO2 日平均
        (0, 0), (40, 50), (80, 100), (180, 150),
        (280, 200), (565, 300), (750, 400), (940, 500)
    ],
    'PM10': [       # PM10 日平均（新标准，收严）
        (0, 0), (50, 50), (120, 100), (250, 150),
        (350, 200), (420, 300), (500, 400), (600, 500)
    ],
    'CO': [         # CO 日平均（mg/m³）
        (0, 0), (2, 50), (4, 100), (14, 150),
        (24, 200), (36, 300), (48, 400), (60, 500)
    ],
    'O3_8h': [      # O3 日最大8小时平均
        (0, 0), (100, 50), (160, 100), (215, 150),
        (265, 200), (800, 300)  # 浓度 > 800 时，IAQI 固定为 300
    ],
    'PM2_5': [      # PM2.5 日平均（新标准，收严）
        (0, 0), (35, 50), (60, 100), (115, 150),
        (150, 200), (250, 300), (350, 400), (500, 500)
    ]
}


def calculate_iaqi(concentration: float, pollutant: str, standard: str = 'new') -> int:
    """
    计算污染物的空气质量分指数（IAQI）

    使用分段线性插值公式：
    IAQIP = (IAQIHi - IAQILo) / (BPHi - BPLo) × (CP - BPLo) + IAQILo

    特殊情况：
    - O3_8h 浓度 > 800 时，IAQI 固定为 300（最高值）

    Args:
        concentration: 污染物浓度值（μg/m³，CO为mg/m³）
        pollutant: 污染物名称（'SO2', 'NO2', 'PM10', 'CO', 'O3_8h', 'PM2_5'）
        standard: 标准类型，'new' 或 'old'，默认为 'new'

    Returns:
        IAQI值（整数）
    """
    # 确保concentration是数值类型（处理API返回的字符串类型）
    if concentration is None or concentration == '' or concentration == '-':
        return 0
    try:
        concentration = float(concentration)
    except (TypeError, ValueError):
        return 0

    if concentration <= 0:
        return 0

    # O3_8h 特殊处理：浓度 > 800 时，IAQI 固定为 300
    if pollutant == 'O3_8h' and concentration > 800:
        return 300

    # 选择对应的分段标准表
    breakpoints_map = IAQI_BREAKPOINTS_NEW if standard == 'new' else IAQI_BREAKPOINTS_OLD
    breakpoints = breakpoints_map.get(pollutant, [])
    if not breakpoints:
        return 0

    # 找到浓度所在的分段
    for i in range(len(breakpoints) - 1):
        bp_lo, iaqi_lo = breakpoints[i]
        bp_hi, iaqi_hi = breakpoints[i + 1]

        if bp_lo <= concentration <= bp_hi:
            # 使用分段线性插值公式计算IAQI
            if bp_hi == bp_lo:  # 防止除零
                return iaqi_hi
            iaqi = (iaqi_hi - iaqi_lo) / (bp_hi - bp_lo) * (concentration - bp_lo) + iaqi_lo
            # 返回浮点数，由调用方决定如何取整（四舍五入或向上进位）
            return iaqi

    # 浓度超过最高分段，返回最高IAQI
    return breakpoints[-1][1]


def calculate_new_composite_index(concentrations: dict) -> float:
    """
    计算新标准综合指数（带权重）

    计算方法（按 HJ 633-2026 新标准）：
    1. 计算各污染物单项质量指数 Ii = Ci / Si（浓度/标准值）
    2. 按权重求和：Isum = 3×PM2.5 + 2×O3 + 2×NO2 + PM10 + SO2 + CO
       - PM2.5权重为3
       - O3权重为2
       - NO2权重为2
       - PM10、SO2、CO权重为1

    Args:
        concentrations: 各污染物平均浓度字典
        格式：{'PM2_5': 14.0, 'PM10': 21.43, 'SO2': 5.0, 'NO2': 18.29, 'CO': 0.67, 'O3_8h': 62.71}

    Returns:
        新标准综合指数
    """
    # 计算各污染物单项质量指数 Ii = Ci / Si
    # 注意：综合指数计算使用年均标准限值
    indices = {}

    # PM2.5：浓度 / 35（年均标准）
    if 'PM2_5' in concentrations and concentrations['PM2_5'] is not None:
        indices['PM2_5'] = concentrations['PM2_5'] / ANNUAL_STANDARD_LIMITS['PM2_5']

    # PM10：浓度 / 70（年均标准）
    if 'PM10' in concentrations and concentrations['PM10'] is not None:
        indices['PM10'] = concentrations['PM10'] / ANNUAL_STANDARD_LIMITS['PM10']

    # SO2：浓度 / 60（年均标准）
    if 'SO2' in concentrations and concentrations['SO2'] is not None:
        indices['SO2'] = concentrations['SO2'] / ANNUAL_STANDARD_LIMITS['SO2']

    # NO2：浓度 / 40（年均标准）
    if 'NO2' in concentrations and concentrations['NO2'] is not None:
        indices['NO2'] = concentrations['NO2'] / ANNUAL_STANDARD_LIMITS['NO2']

    # CO：浓度 / 4（注意单位：mg/m³）
    if 'CO' in concentrations and concentrations['CO'] is not None:
        indices['CO'] = concentrations['CO'] / ANNUAL_STANDARD_LIMITS['CO']

    # O3_8h：浓度 / 160
    if 'O3_8h' in concentrations and concentrations['O3_8h'] is not None:
        indices['O3_8h'] = concentrations['O3_8h'] / ANNUAL_STANDARD_LIMITS['O3_8h']

    # 按权重求和
    composite_index = 0.0
    for pollutant, weight in WEIGHTS.items():
        if pollutant in indices and indices[pollutant] is not None:
            composite_index += indices[pollutant] * weight

    return round(composite_index, 2)


# -----------------------------------------------------------------------------
# 智能分段查询辅助函数（用于标准对比工具）
# -----------------------------------------------------------------------------

def calculate_date_segments(start_date: str, end_date: str) -> List[Tuple[str, str, int]]:
    """
    计算查询日期的智能分段

    规则：
    - 距离当天3天内（含3天）的数据使用原始数据（data_type=0）
    - 距离当天3天外的数据使用审核数据（data_type=1）
    - 如果查询周期跨越3天边界，分成两个时间段

    Args:
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)

    Returns:
        分段列表，每个元素为 (start_date, end_date, data_type)
    """
    from datetime import datetime, timedelta

    segments = []
    today = datetime.now().date()
    three_days_ago = today - timedelta(days=3)

    # 解析日期
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()

    # 计算查询结束日期距离今天的天数
    days_from_today = (today - end).days

    logger.info(
        "calculate_date_segments",
        start_date=start_date,
        end_date=end_date,
        today=today.isoformat(),
        three_days_ago=three_days_ago.isoformat(),
        days_from_today=days_from_today
    )

    # 判断是否跨越3天边界
    # 计算查询开始和结束日期距离今天的天数
    start_days_from_today = (today - start).days
    end_days_from_today = (today - end).days

    # 情况1: 查询范围全部在原始实况范围（今天及3天内）
    # 条件：查询开始日期距离今天 ≤ 3天
    if start_days_from_today <= 3:
        # 全部使用原始实况
        segments.append((start_date, end_date, 0))
        logger.info(
            "date_segments_all_recent",
            data_type=0,
            type="原始实况",
            reason=f"查询范围全部在原始实况范围内（{start_date}至{end_date}），全部使用原始实况"
        )

    # 情况2: 查询范围全部在审核实况范围（4天前及更早）
    # 条件：查询结束日期距离今天 ≥ 4天
    elif end_days_from_today >= 4:
        # 全部使用审核实况
        segments.append((start_date, end_date, 1))
        logger.info(
            "date_segments_all_historical",
            data_type=1,
            type="审核实况",
            reason=f"查询范围全部在审核实况范围内（{start_date}至{end_date}），全部使用审核实况"
        )

    # 情况3: 查询范围跨越3天边界，需要分段
    else:
        # 分界点：
        # - 3天外部分（审核实况）：到 three_days_ago - 1（≥4天前）
        # - 3天内部分（原始实况）：从 three_days_ago 到 three_days_ago + 2（1-3天前）
        # 注意：今天（0天前）归入审核实况
        # 示例：今天是2026-03-18，three_days_ago=2026-03-15（3天前）
        #   - 第一段：2026-03-11 至 2026-03-14（审核实况，≥4天前）
        #   - 第二段：2026-03-15 至 2026-03-18（原始实况1-3天前 + 今天）

        # 第一段：审核实况（start 到 three_days_ago - 1）
        segment1_end = three_days_ago - timedelta(days=1)
        segments.append((start_date, segment1_end.isoformat(), 1))

        # 第二段：原始实况（three_days_ago 到 end）
        segment2_start = three_days_ago
        segments.append((segment2_start.isoformat(), end_date, 0))

        logger.info(
            "date_segments_split",
            segment1=(start_date, segment1_end.isoformat(), 1),
            segment2=(segment2_start.isoformat(), end_date, 0),
            split_point=three_days_ago.isoformat(),
            reason=f"查询范围跨越3天边界({three_days_ago.isoformat()})，分段查询"
        )

    return segments


async def query_day_data_by_segment(
    api_client,
    city_codes: List[str],
    start_date: str,
    end_date: str,
    data_type: int
) -> List[Dict]:
    """
    按时间段查询日报数据

    Args:
        api_client: API客户端
        city_codes: 城市编码列表
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        data_type: 数据类型（0原始实况，1审核实况）

    Returns:
        日报数据列表
    """
    try:
        logger.info(
            "query_day_data_by_segment",
            city_codes=city_codes,
            start_date=start_date,
            end_date=end_date,
            data_type=data_type,
            data_type_name="原始实况" if data_type == 0 else "审核实况"
        )

        response = api_client.query_city_day_data(
            city_codes=city_codes,
            start_date=start_date,
            end_date=end_date,
            data_type=data_type
        )

        if response.get("success"):
            raw_data = response.get("result", [])
            logger.info(
                "query_day_data_by_segment_success",
                record_count=len(raw_data),
                data_type=data_type
            )
            return raw_data
        else:
            error_msg = response.get('msg', 'Unknown error')
            logger.error(
                "query_day_data_by_segment_failed",
                error=error_msg,
                data_type=data_type
            )
            return []

    except Exception as e:
        logger.error(
            "query_day_data_by_segment_error",
            error=str(e),
            data_type=data_type
        )
        return []


def calculate_old_standard_stats_from_daily(
    daily_records: List[Dict],
    city_name: str
) -> Dict[str, Any]:
    """
    从日报数据计算旧标准统计指标（HJ 633-2013）

    业务规则：
    - 使用旧标准限值和IAQI断点表
    - 扣沙日数据已由上游清洗（PM2.5/PM10为None，原始值保存在 PM2_5_original/PM10_original）
    - 旧标准PM2.5断点：IAQI=100时75μg/m³（新标准60）
    - 旧标准PM10断点：IAQI=100时150μg/m³（新标准120）

    Args:
        daily_records: 日报数据列表（已清洗扣沙日）
        city_name: 城市名称

    Returns:
        旧标准统计结果
    """
    if not daily_records:
        return {}

    logger.info("calculating_old_standard_stats", city=city_name, day_count=len(daily_records))

    # 初始化统计变量
    total_days = len(daily_records)
    exceed_days = 0
    exceed_details = []
    pm25_sum = 0
    pm10_sum = 0
    pm25_valid_count = 0  # PM2.5有效天数（剔除扣沙日）
    pm10_valid_count = 0  # PM10有效天数（剔除扣沙日）
    so2_sum = 0
    no2_sum = 0
    co_sum = 0
    o3_8h_sum = 0

    # 收集每日浓度值用于计算百分位数
    daily_co_values = []
    daily_o3_8h_values = []
    daily_so2_values = []
    daily_no2_values = []
    daily_pm10_values = []
    daily_pm25_values = []

    # 首要污染物统计
    primary_pollutant_days = {
        'PM2_5': 0, 'PM10': 0, 'SO2': 0, 'NO2': 0, 'CO': 0, 'O3_8h': 0
    }

    # 各污染物超标天数统计
    exceed_days_by_pollutant = {
        'PM2_5': 0, 'PM10': 0, 'SO2': 0, 'NO2': 0, 'CO': 0, 'O3_8h': 0
    }

    for record in daily_records:
        measurements = record.get("measurements", {})

        def safe_float(value, default=0.0):
            if value is None or value == '' or value == '-':
                return default
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        # 检查是否为扣沙日
        is_sand_day = record.get("is_sand_deduction_day", False)

        # 提取浓度值
        pm25_raw = safe_float(measurements.get("PM2_5") or measurements.get("pm2_5") or
                record.get("pm2_5") or record.get("PM2_5"))
        pm10_raw = safe_float(measurements.get("PM10") or measurements.get("pm10") or
                record.get("pm10") or record.get("PM10"))
        so2_raw = safe_float(measurements.get("SO2") or measurements.get("so2") or
               record.get("so2") or record.get("SO2"))
        no2_raw = safe_float(measurements.get("NO2") or measurements.get("no2") or
               record.get("no2") or record.get("NO2"))
        co_raw = safe_float(measurements.get("CO") or measurements.get("co") or
              record.get("co") or record.get("CO"))
        o3_8h_raw = safe_float(measurements.get("O3_8h") or measurements.get("o3_8h") or
                record.get("o3_8h") or record.get("O3_8h"))

        # 按原始监测数据规则修约
        pm25 = apply_rounding(pm25_raw, 'PM2_5', 'raw_data')
        pm10 = apply_rounding(pm10_raw, 'PM10', 'raw_data')
        so2 = apply_rounding(so2_raw, 'SO2', 'raw_data')
        no2 = apply_rounding(no2_raw, 'NO2', 'raw_data')
        co = apply_rounding(co_raw, 'CO', 'raw_data')
        o3_8h = apply_rounding(o3_8h_raw, 'O3_8h', 'raw_data')

        # 扣沙日的AQI和首要污染物使用原始值计算
        if is_sand_day:
            pm25_original_raw = safe_float(record.get("PM2_5_original"))
            pm10_original_raw = safe_float(record.get("PM10_original"))
            pm25_for_aqi = apply_rounding(pm25_original_raw, 'PM2_5', 'raw_data')
            pm10_for_aqi = apply_rounding(pm10_original_raw, 'PM10', 'raw_data')
        else:
            pm25_for_aqi = pm25
            pm10_for_aqi = pm10

        # 累加修约后的浓度值（扣沙日PM2.5/PM10为0，不计入）
        if pm25 > 0:
            pm25_sum += pm25
            pm25_valid_count += 1
        if pm10 > 0:
            pm10_sum += pm10
            pm10_valid_count += 1

        # 其他污染物正常累加
        so2_sum += so2
        no2_sum += no2
        co_sum += co
        o3_8h_sum += o3_8h

        # 收集修约后的每日值（用于百分位数计算）
        if co > 0:
            daily_co_values.append(co)
        if o3_8h > 0:
            daily_o3_8h_values.append(o3_8h)
        if so2 > 0:
            daily_so2_values.append(so2)
        if no2 > 0:
            daily_no2_values.append(no2)
        if pm10 > 0:
            daily_pm10_values.append(pm10)
        if pm25 > 0:
            daily_pm25_values.append(pm25)

        # 计算旧标准单项质量指数 Ii = Ci / Si
        pm25_index_old = pm25 / OLD_STANDARD_LIMITS['PM2_5']
        pm10_index_old = pm10 / OLD_STANDARD_LIMITS['PM10']
        so2_index_old = so2 / OLD_STANDARD_LIMITS['SO2']
        no2_index_old = no2 / OLD_STANDARD_LIMITS['NO2']
        co_index_old = co / OLD_STANDARD_LIMITS['CO']
        o3_8h_index_old = o3_8h / OLD_STANDARD_LIMITS['O3_8h']

        # 判断该日是否超标
        max_single_index_old = max(pm25_index_old, pm10_index_old, so2_index_old,
                                   no2_index_old, co_index_old, o3_8h_index_old)

        # 计算旧标准IAQI并向上进位取整数
        import math
        pm25_iaqi_old = math.ceil(calculate_iaqi(pm25_for_aqi, 'PM2_5', 'old'))
        pm10_iaqi_old = math.ceil(calculate_iaqi(pm10_for_aqi, 'PM10', 'old'))
        so2_iaqi_old = math.ceil(calculate_iaqi(so2, 'SO2', 'old'))
        no2_iaqi_old = math.ceil(calculate_iaqi(no2, 'NO2', 'old'))
        co_iaqi_old = math.ceil(calculate_iaqi(co, 'CO', 'old'))
        o3_8h_iaqi_old = math.ceil(calculate_iaqi(o3_8h, 'O3_8h', 'old'))

        # 统计首要污染物（使用向上取整后的IAQI）
        pollutants_with_iaqi_old = {
            'PM2_5': pm25_iaqi_old, 'PM10': pm10_iaqi_old, 'SO2': so2_iaqi_old,
            'NO2': no2_iaqi_old, 'CO': co_iaqi_old, 'O3_8h': o3_8h_iaqi_old
        }
        # AQI 向上进位取整数
        aqi_old = math.ceil(max(pollutants_with_iaqi_old.values()))

        # 【调试日志】输出旧标准计算结果
        timestamp = record.get("timestamp", "unknown")
        date_only = timestamp[:10] if len(timestamp) >= 10 else timestamp

        # 只输出关键日期的详细日志
        if date_only in ['2026-01-17', '2026-01-20', '2026-01-01', '2026-01-24']:
            logger.info(
                "old_standard_daily_calculation_debug",
                date=date_only,
                concentrations={
                    'PM2_5': f"{pm25_for_aqi:.1f}",
                    'PM10': f"{pm10_for_aqi:.1f}",
                    'SO2': f"{so2:.1f}",
                    'NO2': f"{no2:.1f}",
                    'CO': f"{co:.1f}",
                    'O3_8h': f"{o3_8h:.1f}"
                },
                iaqi_old={
                    'PM2_5': f"{pm25_iaqi_old:.1f}",
                    'PM10': f"{pm10_iaqi_old:.1f}",
                    'SO2': f"{so2_iaqi_old:.1f}",
                    'NO2': f"{no2_iaqi_old:.1f}",
                    'CO': f"{co_iaqi_old:.1f}",
                    'O3_8h': f"{o3_8h_iaqi_old:.1f}"
                },
                index_old={
                    'PM2_5': f"{pm25_index_old:.3f}",
                    'PM10': f"{pm10_index_old:.3f}",
                    'SO2': f"{so2_index_old:.3f}",
                    'NO2': f"{no2_index_old:.3f}",
                    'CO': f"{co_index_old:.3f}",
                    'O3_8h': f"{o3_8h_index_old:.3f}"
                },
                aqi_old=f"{aqi_old:.1f}",
                max_single_index_old=f"{max_single_index_old:.3f}"
            )

        # 确定首要污染物
        primary_pollutants_this_day_old = []
        if aqi_old > 50:
            for pollutant, iaqi in pollutants_with_iaqi_old.items():
                if iaqi == aqi_old:
                    primary_pollutant_days[pollutant] += 1
                    primary_pollutants_this_day_old.append(pollutant)

        # 【调试日志】输出旧标准首要污染物判断结果
        if date_only in ['2026-01-17', '2026-01-20', '2026-01-01', '2026-01-24']:
            logger.info(
                "old_standard_primary_pollutant_debug",
                date=date_only,
                aqi_old=f"{aqi_old:.1f}",
                aqi_gt_50=aqi_old > 50,
                primary_pollutants=primary_pollutants_this_day_old,
                max_single_index=f"{max_single_index_old:.3f}",
                is_exceeded=max_single_index_old > 1
            )

        # 统计各污染物超标天数（单项质量指数 > 1）
        if pm25_index_old > 1:
            exceed_days_by_pollutant['PM2_5'] += 1
        if pm10_index_old > 1:
            exceed_days_by_pollutant['PM10'] += 1
        if so2_index_old > 1:
            exceed_days_by_pollutant['SO2'] += 1
        if no2_index_old > 1:
            exceed_days_by_pollutant['NO2'] += 1
        if co_index_old > 1:
            exceed_days_by_pollutant['CO'] += 1
        if o3_8h_index_old > 1:
            exceed_days_by_pollutant['O3_8h'] += 1

        # 旧标准超标天数统计
        if max_single_index_old > 1:
            exceed_days += 1
            # 记录超标详情
            exceed_pollutants = []
            pollutants = {
                'PM2_5': (pm25, pm25_index_old), 'PM10': (pm10, pm10_index_old),
                'SO2': (so2, so2_index_old), 'NO2': (no2, no2_index_old),
                'CO': (co, co_index_old), 'O3_8h': (o3_8h, o3_8h_index_old)
            }
            for name, (conc, index) in pollutants.items():
                if index > 1:
                    exceed_pollutants.append({
                        'name': name, 'concentration': conc, 'index': safe_round(index, 3)
                    })
            exceed_detail = {
                'date': record.get("timestamp", "unknown"),
                'max_index': safe_round(max_single_index_old, 3),
                'exceed_pollutants': exceed_pollutants
            }
            exceed_details.append(exceed_detail)

        # 统计有效天数（只要有一项污染物有数据就算有效天）
        if pm25 > 0 or pm10 > 0 or so2 > 0 or no2 > 0 or co > 0 or o3_8h > 0:
            valid_days += 1

            # 【调试日志】输出旧标准超标详情
            date_only = record.get("timestamp", "unknown")[:10] if len(record.get("timestamp", "")) >= 10 else record.get("timestamp", "unknown")
            if date_only in ['2026-01-17', '2026-01-20', '2026-01-01', '2026-01-24']:
                logger.info(
                    "old_standard_exceed_detail_debug",
                    date=date_only,
                    max_index=f"{max_single_index_old:.3f}",
                    exceed_pollutants_count=len(exceed_pollutants),
                    exceed_pollutants=exceed_pollutants,
                    primary_pollutants_this_day=primary_pollutants_this_day_old,
                    note="旧标准超标天记录"
                )

    # 计算平均浓度（按国家标准修约）
    avg_pm25 = apply_rounding(pm25_sum / pm25_valid_count if pm25_valid_count > 0 else 0, 'PM2_5', 'statistical_data')
    avg_pm10 = apply_rounding(pm10_sum / pm10_valid_count if pm10_valid_count > 0 else 0, 'PM10', 'statistical_data')
    avg_so2 = apply_rounding(so2_sum / total_days, 'SO2', 'statistical_data') if total_days > 0 else 0
    avg_no2 = apply_rounding(no2_sum / total_days, 'NO2', 'statistical_data') if total_days > 0 else 0
    avg_co = apply_rounding(co_sum / total_days, 'CO', 'statistical_data') if total_days > 0 else 0
    avg_o3_8h = apply_rounding(o3_8h_sum / total_days, 'O3_8h', 'statistical_data') if total_days > 0 else 0

    # 计算百分位数
    def calculate_percentile(values, percentile):
        if not values:
            return 0.0
        sorted_values = sorted(values)
        n = len(sorted_values)
        index = (percentile / 100) * (n - 1)
        lower = int(index)
        upper = lower + 1
        if upper >= n:
            return float(sorted_values[-1])
        weight = index - lower
        return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight

    co_percentile_95 = apply_rounding(calculate_percentile(daily_co_values, 95), 'CO', 'statistical_data')
    o3_8h_percentile_90 = apply_rounding(calculate_percentile(daily_o3_8h_values, 90), 'O3_8h', 'statistical_data')
    so2_percentile_98 = apply_rounding(calculate_percentile(daily_so2_values, 98), 'SO2', 'statistical_data')
    no2_percentile_98 = apply_rounding(calculate_percentile(daily_no2_values, 98), 'NO2', 'statistical_data')
    pm10_percentile_95 = apply_rounding(calculate_percentile(daily_pm10_values, 95), 'PM10', 'statistical_data')
    pm25_percentile_95 = apply_rounding(calculate_percentile(daily_pm25_values, 95), 'PM2_5', 'statistical_data')

    # 计算旧标准综合指数
    old_standard_concentrations = {
        'PM2_5': avg_pm25, 'PM10': avg_pm10, 'SO2': avg_so2,
        'NO2': avg_no2, 'CO': co_percentile_95, 'O3_8h': o3_8h_percentile_90
    }

    # 计算旧标准单项质量指数
    pm25_index = safe_round(old_standard_concentrations['PM2_5'] / ANNUAL_STANDARD_LIMITS_OLD['PM2_5'], 3)
    pm10_index = safe_round(old_standard_concentrations['PM10'] / ANNUAL_STANDARD_LIMITS_OLD['PM10'], 3)
    so2_index = safe_round(old_standard_concentrations['SO2'] / ANNUAL_STANDARD_LIMITS_OLD['SO2'], 3)
    no2_index = safe_round(old_standard_concentrations['NO2'] / ANNUAL_STANDARD_LIMITS_OLD['NO2'], 3)
    co_index = safe_round(old_standard_concentrations['CO'] / ANNUAL_STANDARD_LIMITS_OLD['CO'], 3)
    o3_8h_index = safe_round(old_standard_concentrations['O3_8h'] / ANNUAL_STANDARD_LIMITS_OLD['O3_8h'], 3)

    # 计算加权单项质量指数（所有权重均为1）
    pm25_weighted_index = safe_round(pm25_index * WEIGHTS['PM2_5'], 3)
    pm10_weighted_index = safe_round(pm10_index * WEIGHTS['PM10'], 3)
    so2_weighted_index = safe_round(so2_index * WEIGHTS['SO2'], 3)
    no2_weighted_index = safe_round(no2_index * WEIGHTS['NO2'], 3)
    co_weighted_index = safe_round(co_index * WEIGHTS['CO'], 3)
    o3_8h_weighted_index = safe_round(o3_8h_index * WEIGHTS['O3_8h'], 3)

    # 计算综合指数
    avg_composite_index = safe_round(
        pm25_weighted_index + pm10_weighted_index + so2_weighted_index +
        no2_weighted_index + co_weighted_index + o3_8h_weighted_index, 3
    )

    # 计算达标率和超标率（百分比形式，保留1位小数）
    # valid_days 在循环中已经统计（只要有一项污染物有数据就算有效天）
    compliance_rate = safe_round((total_days - exceed_days) / total_days * 100, 1) if total_days > 0 else 0
    exceed_rate = safe_round(exceed_days / valid_days * 100, 1) if valid_days > 0 else 0

    # 计算首要污染物比例
    total_primary_days = sum(primary_pollutant_days.values())
    primary_pollutant_ratio = {}
    if total_primary_days > 0:
        for pollutant, days in primary_pollutant_days.items():
            primary_pollutant_ratio[pollutant] = safe_round(days / total_primary_days * 100, 1)
    else:
        for pollutant in primary_pollutant_days.keys():
            primary_pollutant_ratio[pollutant] = 0.0

    # 计算各污染物超标率
    exceed_rate_by_pollutant = {}
    for pollutant, days in exceed_days_by_pollutant.items():
        if valid_days > 0:
            exceed_rate_by_pollutant[pollutant] = safe_round(days / valid_days * 100, 1)
        else:
            exceed_rate_by_pollutant[pollutant] = 0.0

    logger.info(
        "old_standard_stats_calculated",
        city=city_name,
        composite_index=avg_composite_index,
        exceed_days=exceed_days,
        compliance_rate=compliance_rate,
        sand_deduction_stats={
            "total_days": total_days,
            "pm25_valid_count": pm25_valid_count,
            "pm10_valid_count": pm10_valid_count
        }
    )

    return {
        "composite_index": avg_composite_index,
        "exceed_days": exceed_days,
        "exceed_details": exceed_details,
        "valid_days": valid_days,
        "exceed_rate": exceed_rate,
        "compliance_rate": compliance_rate,
        "total_days": total_days,
        # 六参数统计指标
        "SO2": format_pollutant_value(avg_so2, 'SO2', 'statistical_data', use_final_rounding=True),
        "SO2_P98": format_pollutant_value(so2_percentile_98, 'SO2', 'statistical_data', use_final_rounding=True),
        "NO2": format_pollutant_value(avg_no2, 'NO2', 'statistical_data', use_final_rounding=True),
        "NO2_P98": format_pollutant_value(no2_percentile_98, 'NO2', 'statistical_data', use_final_rounding=True),
        "PM10": format_pollutant_value(avg_pm10, 'PM10', 'statistical_data', use_final_rounding=True),
        "PM10_P95": format_pollutant_value(pm10_percentile_95, 'PM10', 'statistical_data', use_final_rounding=True),
        "PM2_5": format_pollutant_value(avg_pm25, 'PM2_5', 'statistical_data', use_final_rounding=True),
        "PM2_5_P95": format_pollutant_value(pm25_percentile_95, 'PM2_5', 'statistical_data', use_final_rounding=True),
        "CO_P95": format_pollutant_value(co_percentile_95, 'CO', 'statistical_data', use_final_rounding=True),
        "O3_8h_P90": format_pollutant_value(o3_8h_percentile_90, 'O3_8h', 'statistical_data', use_final_rounding=True),
        # 加权单项质量指数
        "single_indexes": {
            "SO2": so2_weighted_index, "NO2": no2_weighted_index,
            "PM10": pm10_weighted_index, "CO": co_weighted_index,
            "PM2_5": pm25_weighted_index, "O3_8h": o3_8h_weighted_index
        },
        # 首要污染物统计
        "primary_pollutant_days": primary_pollutant_days,
        "primary_pollutant_ratio": primary_pollutant_ratio,
        "total_primary_days": total_primary_days,
        # 各污染物超标统计
        "exceed_days_by_pollutant": exceed_days_by_pollutant,
        "exceed_rate_by_pollutant": exceed_rate_by_pollutant
    }


async def execute_query_standard_comparison(
    cities: List[str],
    start_date: str,
    end_date: str,
    context: ExecutionContext,
    enable_sand_deduction: bool = True
) -> Dict[str, Any]:
    """
    查询新旧标准对比统计指标（重构版）

    复用 query_new_standard_report 的计算结果，并基于日数据计算旧标准统计

    Args:
        cities: 城市名称列表
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        context: 执行上下文
        enable_sand_deduction: 是否启用扣沙处理（默认True）

    Returns:
        新旧标准对比结果

    =============================================================================
    API 返回字段映射说明 (调试参考)
    =============================================================================

    【日报数据接口】DATCityDay/GetDATCityDayDisplayListAsync
    ----------------------------------------------------------------------
    原始字段              → 标准化字段        说明
    ----------------------------------------------------------------------
    name                 → city            城市名称（关键字段！）
    code                 → city_code       城市编码
    timePoint            → timestamp       时间点
    pM2_5                → PM2_5           PM2.5浓度
    pM10                 → PM10            PM10浓度
    sO2                  → SO2             SO2浓度
    nO2                  → NO2             NO2浓度
    o3_8H                → O3_8h           O3 8小时均值
    co                   → CO              CO浓度
    pM2_5_IAQI           → PM2_5_IAQI      PM2.5分指数
    aqi                  → AQI             AQI指数
    ... (共60个字段)

    【统计数据接口】GetReportForRangeListFilterAsync
    ----------------------------------------------------------------------
    原始字段              → 标准化字段        说明
    ----------------------------------------------------------------------
    cityName             → city            城市名称
    cityCode             → city_code       城市编码
    timePoint            → timestamp       时间范围
    compositeIndex       → composite_index 综合指数（旧标准）
    overDays             → over_days       超标天数
    overRate             → over_rate       超标率
    rank                 → rank            排名
    maxIndex             → max_index       最大单项指数
    fineDays             → fine_days       优良天数
    ... (共96个字段)

    【字段映射规则】data_standardizer.py
    ----------------------------------------------------------------------
    "name" → "city"           # 日报数据专用
    "cityName" → "city"       # 统计数据专用
    "city_name" → "city"      # 通用字段
    "城市名称" → "city"       # 中文映射
    =============================================================================

    测试命令：
    python tests/test_api_response_structure.py

    【重构说明】
    - 复用 query_new_standard_report 获取新标准统计（含扣沙处理）
    - 基于日数据计算旧标准统计（使用旧标准限值和IAQI断点）
    - 合并新旧标准对比结果
    """
    logger.info(
        "query_standard_comparison_start",
        cities=cities,
        start_date=start_date,
        end_date=end_date
    )

    try:
        # 步骤1：调用 query_new_standard_report 获取新标准统计和日数据
        from app.tools.query.query_new_standard_report.tool import execute_query_new_standard_report

        new_standard_result = await execute_query_new_standard_report(
            cities=cities,
            start_date=start_date,
            end_date=end_date,
            enable_sand_deduction=enable_sand_deduction,
            context=context
        )

        if not new_standard_result.get("success"):
            return {
                "status": "failed",
                "success": False,
                "error": "新标准查询失败",
                "data": None,
                "metadata": {},
                "summary": f"新标准查询失败: {new_standard_result.get('summary', 'Unknown error')}"
            }

        # 提取新标准结果和日数据data_id
        new_standard_data = new_standard_result.get("result", {})
        day_data_id = new_standard_result.get("metadata", {}).get("data_id")

        # 步骤2：获取日数据用于计算旧标准统计
        if not day_data_id:
            return {
                "status": "failed",
                "success": False,
                "error": "未获取到日数据ID",
                "data": None,
                "metadata": {},
                "summary": "新标准查询未返回日数据ID"
            }

        # 从上下文获取日数据（使用get_raw_data获取字典格式）
        daily_data = context.data_manager.get_raw_data(day_data_id)

        if not daily_data:
            return {
                "status": "failed",
                "success": False,
                "error": "无法加载日数据",
                "data": None,
                "metadata": {},
                "summary": f"无法加载日数据: {day_data_id}"
            }

        # 步骤3：按城市分组并计算旧标准统计
        from collections import defaultdict

        daily_data_by_city = defaultdict(list)
        for record in daily_data:
            city_name = (
                record.get("city", "") or
                record.get("city_name", "") or
                record.get("cityName", "") or
                record.get("name", "")
            )
            if city_name:
                daily_data_by_city[city_name].append(record)

        # 容错：如果没有城市字段，使用查询参数
        if not daily_data_by_city and len(cities) == 1:
            daily_data_by_city[cities[0]] = daily_data

        # 计算各城市的旧标准统计
        city_comparison = {}

        for city, city_daily_records in daily_data_by_city.items():
            logger.info("calculating_old_standard_for_city", city=city, day_count=len(city_daily_records))

            # 计算旧标准统计
            old_standard_stats = calculate_old_standard_stats_from_daily(city_daily_records, city)

            # 获取新标准统计
            if len(cities) == 1:
                # 单城市查询，new_standard_data 直接是城市统计
                new_standard_stats = new_standard_data
            else:
                # 多城市查询，new_standard_data 是城市字典
                new_standard_stats = new_standard_data.get(city, {})

            # 计算对比数据
            comparison = {}
            if new_standard_stats and old_standard_stats:
                new_index = new_standard_stats.get("composite_index", 0)
                old_index = old_standard_stats.get("composite_index", 0)
                new_exceed = new_standard_stats.get("exceed_days", 0)
                old_exceed = old_standard_stats.get("exceed_days", 0)

                comparison = {
                    "composite_index_change": safe_round(new_index - old_index, 2),
                    "composite_index_change_rate": safe_round(((new_index - old_index) / old_index * 100) if old_index > 0 else 0, 2),
                    "exceed_days_change": new_exceed - old_exceed
                }

            city_comparison[city] = {
                "new_standard": new_standard_stats,
                "old_standard": old_standard_stats,
                "comparison": comparison
            }

        # 计算全省汇总对比（多城市查询时）
        if len(cities) > 1:
            # 导入全省汇总计算函数
            from app.tools.query.query_new_standard_report.tool import calculate_province_wide_stats

            # 提取新旧标准的全省数据
            new_standard_province_data = {
                city: city_comparison[city]["new_standard"]
                for city in city_comparison.keys()
                if city_comparison[city].get("new_standard")
            }

            old_standard_province_data = {
                city: city_comparison[city]["old_standard"]
                for city in city_comparison.keys()
                if city_comparison[city].get("old_standard")
            }

            # 计算全省汇总
            new_standard_province_wide = calculate_province_wide_stats(new_standard_province_data)
            old_standard_province_wide = calculate_province_wide_stats(old_standard_province_data)

            # 计算全省汇总对比
            province_wide_comparison = {}
            if new_standard_province_wide and old_standard_province_wide:
                new_index = new_standard_province_wide.get("composite_index", 0)
                old_index = old_standard_province_wide.get("composite_index", 0)
                new_exceed = new_standard_province_wide.get("exceed_days", 0)
                old_exceed = old_standard_province_wide.get("exceed_days", 0)

                province_wide_comparison = {
                    "composite_index_change": safe_round(new_index - old_index, 2),
                    "composite_index_change_rate": safe_round(((new_index - old_index) / old_index * 100) if old_index > 0 else 0, 2),
                    "exceed_days_change": new_exceed - old_exceed
                }

            # 添加到结果
            city_comparison["province_wide"] = {
                "new_standard": new_standard_province_wide,
                "old_standard": old_standard_province_wide,
                "comparison": province_wide_comparison
            }

        # 步骤4：构建返回结果
        total_days = (datetime.strptime(end_date, "%Y-%m-%d") - datetime.strptime(start_date, "%Y-%m-%d")).days + 1

        if len(cities) == 1 and city_comparison:
            # 单城市查询
            city = list(city_comparison.keys())[0]
            result_summary = {
                "city": city,
                **city_comparison[city]
            }
        else:
            # 多城市查询
            result_summary = {
                "cities": list(city_comparison.keys()),
                "city_stats": city_comparison
            }

        metadata = {
            "tool_name": "query_standard_comparison",
            "cities": cities,
            "date_range": f"{start_date} to {end_date}",
            "schema_version": "v2.0",
            "total_days": total_days,
            # "data_id": day_data_id  # ⚠️ 已禁用：统计报表工具不返回 data_id
        }

        # 构建摘要
        if len(cities) == 1:
            city = list(city_comparison.keys())[0] if city_comparison else cities[0]
            summary_text = f"{city} 新旧标准对比查询完成（数据为审核实况，最近的3天自动使用原始数据） | 无原始数据 data_id，统计汇总指标已完整展示在 result 字段中"
            # if day_data_id:
            #     summary_text += f" | 日报数据已保存 (data_id: {day_data_id})"
        else:
            summary_text = f"多城市新旧标准对比查询完成，共查询 {len(city_comparison)} 个城市（数据为审核实况，最近的3天自动使用原始数据） | 无原始数据 data_id，统计汇总指标已完整展示在 result 字段中"
            # if day_data_id:
            #     summary_text += f" | 日报数据已保存 (data_id: {day_data_id})"

        return {
            "status": "success",
            "success": True,
            "data": None,
            "metadata": metadata,
            "summary": summary_text,
            "result": result_summary
        }

    except Exception as e:
        logger.error(
            "query_standard_comparison_failed",
            error=str(e),
            error_type=type(e).__name__
        )
        return QueryGDSuncereDataTool._create_error_response(str(e))
