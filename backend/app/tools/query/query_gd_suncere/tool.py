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

from app.services.gd_suncere_api_client import get_gd_suncere_api_client
from app.agent.context.execution_context import ExecutionContext
from app.utils.data_standardizer import get_data_standardizer


logger = structlog.get_logger()


class GeoMappingResolver:
    """
    地理位置映射解析器

    参考 Vanna 项目的 geo_mappings.json，提供：
    1. 城市名称 → 城市编码映射
    2. 站点名称 → 站点编码映射

    LLM 输出城市/站点名称，工具内部自动转换为编码
    """

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

    # 主要站点代码映射（参考 Vanna geo_mappings.json）
    STATION_CODE_MAP = {
        # 广州主要站点
        "广雅中学": "1001A",
        "市监测站": "1008A",
        "市五中": "1002A",
        "体育西": "1145A",
        "广东商学院": "1004A",
        "麓湖": "1010A",
        "市八十六中": "1005A",
        "番禺中学": "1006A",
        "花都师范": "1007A",
        "黄埔科学城": "4561A",
        "南沙街": "4564A",
        "海珠湖": "1422A",
        "天河奥体": "9006A",
        "白云山": "9011A",
        "黄埔港": "1386A",
        "番禺大学城": "1421A",
        "从化街口": "1420A",
        "增城荔城": "1429A",
        "增城新塘": "9025A",

        # 深圳主要站点
        "洪湖": "1018A",
        "华侨城": "1019A",
        "南海子站": "1020A",
        "盐田": "1021A",
        "龙岗": "1022A",
        "梅沙": "1026A",
        "南澳": "1024A",
        "西乡": "4575A",
        "深南": "5002A",
        "莲塘": "1431A",
        "坪山": "4560A",
        "横岗": "1432A",

        # 珠海主要站点
        "吉大": "1028A",
        "前山": "1029A",
        "唐家": "1030A",

        # 佛山主要站点
        "湾梁": "1033A",
        "华材职中": "1115A",
        "南海气象局": "1384A",

        # 韶关主要站点
        "韶关学院": "1015A",
        "曲江监测站": "1016A",
        "碧湖山庄": "4572A",
        "浈江十里亭": "1437A",
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

            # 直接查找
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
                available_cities=list(cls.CITY_CODE_MAP.keys())
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

        Args:
            station_names: 站点名称列表（LLM 输出）

        Returns:
            站点编码列表
        """
        station_codes = []

        for station_name in station_names:
            station_name = station_name.strip()

            # 直接查找
            if station_name in cls.STATION_CODE_MAP:
                station_codes.append(cls.STATION_CODE_MAP[station_name])
                continue

            # 模糊匹配
            for mapped_name, code in cls.STATION_CODE_MAP.items():
                if station_name in mapped_name or mapped_name in station_name:
                    station_codes.append(code)
                    break
            else:
                logger.warning(
                    "station_code_not_found",
                    station_name=station_name
                )

        logger.info(
            "station_names_resolved_to_codes",
            input_names=station_names,
            output_codes=station_codes
        )

        return station_codes


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
        城市名称转代码

        Args:
            city_name: 城市名称

        Returns:
            城市代码
        """
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
        data_type: int = 1
    ) -> Dict[str, Any]:
        """
        查询城市日报数据

        Args:
            cities: 城市名称列表（LLM 输出，如 ["广州", "深圳"]）
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            context: 执行上下文
            data_type: 数据类型（0原始实况，1审核实况，2原始标况，3审核标况），默认1

        Returns:
            查询结果
        """
        logger.info(
            "query_gd_suncere_city_day_start",
            cities=cities,
            start_date=start_date,
            end_date=end_date
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
                    "field_mapping_info": standardizer.get_field_mapping_info() if standardizer else {}
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
                "data": standardized_records[:50],  # 返回前50条供预览
                "metadata": {
                    "tool_name": "query_gd_suncere_city_day",
                    "data_id": data_id,
                    "total_records": len(standardized_records),
                    "returned_records": min(50, len(standardized_records)),
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
    def query_city_hour_data(
        cls,
        cities: List[str],
        start_time: str,
        end_time: str,
        context: ExecutionContext
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

        Returns:
            查询结果
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
                "data": standardized_records[:100],  # 返回前100条供预览
                "metadata": {
                    "tool_name": "query_gd_suncere_city_hour",
                    "data_id": data_id,
                    "total_records": len(standardized_records),
                    "returned_records": min(100, len(standardized_records)),
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
        cities: List[str],
        start_time: str,
        end_time: str,
        context: ExecutionContext
    ) -> Dict[str, Any]:
        """
        查询站点小时数据（用于精细化分析）

        注意：此方法需要提供具体的站点代码，而不是城市代码
        如果只查询城市级别数据，请使用 query_city_hour_data

        Args:
            cities: 城市名称列表（保留参数兼容性，但此方法不推荐使用）
            start_time: 开始时间 (YYYY-MM-DD HH:MM:SS)
            end_time: 结束时间 (YYYY-MM-DD HH:MM:SS)
            context: 执行上下文

        Returns:
            查询结果
        """
        logger.warning(
            "query_station_hour_data_deprecated",
            message="此方法已弃用，请使用 query_city_hour_data 代替"
        )

        # 重定向到城市小时数据查询
        return cls.query_city_hour_data(
            cities=cities,
            start_time=start_time,
            end_time=end_time,
            context=context
        )

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


# 导出函数供工具调用
def execute_query_gd_suncere_city_day(
    cities: List[str],
    start_date: str,
    end_date: str,
    context: ExecutionContext,
    data_type: int = 1
) -> Dict[str, Any]:
    """
    执行城市日报数据查询

    Args:
        cities: 城市名称列表，如 ["广州", "深圳", "佛山"]
        start_date: 开始日期，格式 "YYYY-MM-DD"
        end_date: 结束日期，格式 "YYYY-MM-DD"
        context: 执行上下文
        data_type: 数据类型（0原始实况，1审核实况，2原始标况，3审核标况），默认1

    Returns:
        查询结果字典
    """
    return QueryGDSuncereDataTool.query_city_day_data(
        cities=cities,
        start_date=start_date,
        end_date=end_date,
        context=context,
        data_type=data_type
    )


def execute_query_gd_suncere_station_hour(
    cities: List[str],
    start_time: str,
    end_time: str,
    context: ExecutionContext
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

    Returns:
        查询结果字典
    """
    return QueryGDSuncereDataTool.query_city_hour_data(
        cities=cities,
        start_time=start_time,
        end_time=end_time,
        context=context
    )


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
                "data": standardized_records[:50],  # 返回前50条供预览
                "metadata": {
                    "tool_name": "query_gd_suncere_report",
                    "data_id": data_id,
                    "total_records": len(standardized_records),
                    "returned_records": min(50, len(standardized_records)),
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
            "data": raw_records[:100],
            "metadata": {
                "tool_name": "query_gd_suncere_report",
                "total_records": len(raw_records),
                "returned_records": min(100, len(raw_records)),
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
                "data": standardized_records[:50],  # 返回前50条供预览
                "metadata": {
                    "tool_name": "query_gd_suncere_report_compare",
                    "data_id": data_id,
                    "total_records": len(standardized_records),
                    "returned_records": min(50, len(standardized_records)),
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
            "data": raw_records[:100],
            "metadata": {
                "tool_name": "query_gd_suncere_report_compare",
                "total_records": len(raw_records),
                "returned_records": min(100, len(raw_records)),
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
        'PM2_5': 2,      # μg/m³，保留2位（测试用）
        'PM10': 0,       # μg/m³，保留0位（同日数据）
        'SO2': 0,        # μg/m³，保留0位（同日数据）
        'NO2': 0,        # μg/m³，保留0位（同日数据）
        'O3_8h': 0,      # μg/m³，保留0位（同日数据）
        'CO': 1,         # mg/m³，保留1位（同日数据）
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
    # 其他指标（中间计算值）
    'other': {
        'composite_index': 2,      # 综合指数，保留2位
        'single_index': 3,         # 单项质量指数，保留3位（中间计算值）
    }
}


def apply_rounding(value: float, pollutant: str, data_type: str = 'statistical_data') -> float:
    """
    应用修约规则（四舍六入五成双）

    Args:
        value: 原始值
        pollutant: 污染物名称（如'PM2_5', 'SO2'等）
        data_type: 数据类型（'raw_data', 'statistical_data', 'evaluation_data'）

    Returns:
        修约后的值
    """
    if value is None:
        return 0.0

    # 获取该污染物的修约精度
    precision = ROUNDING_PRECISION.get(data_type, {}).get(pollutant, 2)

    # 使用Python的round()函数（四舍六入五成双）
    return round(value, precision)


def format_pollutant_value(value: float, pollutant: str, data_type: str = 'statistical_data'):
    """
    格式化污染物浓度值，确保按表3规范正确显示小数位数

    用于返回结果中的数值格式化，确保：
    - 需要保留0位小数的污染物（SO2、NO2、O3、PM10）：返回整数类型（如 15 而非 15.0）
    - PM2.5：返回字符串类型，强制显示2位小数（如 30.00）
    - 其他保留小数的污染物（CO等）：返回浮点数类型（如 15.2）

    Args:
        value: 已修约的数值
        pollutant: 污染物名称
        data_type: 数据类型

    Returns:
        格式化后的值（整数、浮点数或字符串）
    """
    if value is None:
        return 0.0

    # 获取该污染物的修约精度
    precision = ROUNDING_PRECISION.get(data_type, {}).get(pollutant, 2)

    # PM2.5 特殊处理：强制显示两位小数（字符串格式）
    if pollutant == 'PM2_5' and data_type == 'statistical_data':
        return f"{value:.2f}"

    # 0位小数：返回整数
    if precision == 0:
        return int(value)
    # 1位或更多小数：返回浮点数
    else:
        return float(value)


# -----------------------------------------------------------------------------
# 新标准断点配置
# -----------------------------------------------------------------------------
# 《环境空气质量标准》（GB 3095-2012）二级标准限值（单位：μg/m³，CO为mg/m³）

# 24小时平均标准限值（用于超标判断）
# 注意：新标准（HJ 633-2024）相比旧标准（HJ 633-2011）加严了PM2.5和PM10的限值
# - PM2.5: 新标准60 vs 旧标准75
# - PM10: 新标准120 vs 旧标准150
STANDARD_LIMITS = {
    'PM2_5': 60,   # 新标准24小时平均二级标准（HJ 633-2024，IAQI=100对应60）
    'PM10': 120,   # 新标准24小时平均二级标准（HJ 633-2024，IAQI=100对应120）
    'SO2': 150,    # 24小时平均二级标准
    'NO2': 80,     # 24小时平均二级标准
    'CO': 4,       # 24小时平均二级标准（mg/m³）
    'O3_8h': 160   # 日最大8小时平均二级标准
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

# 权重配置（所有污染物权重均为1）
WEIGHTS = {
    'PM2_5': 1,
    'PM10': 1,
    'SO2': 1,
    'NO2': 1,
    'CO': 1,
    'O3_8h': 1
}

# -----------------------------------------------------------------------------
# IAQI 分段标准表（用于计算空气质量分指数）
# 参考：HJ 633-2024 环境空气质量评价技术规范
# -----------------------------------------------------------------------------
# IAQI 分段断点表：[浓度限值, IAQI值]
# 浓度单位：μg/m³（CO为mg/m³）

# 旧标准IAQI分段表（HJ 633-2011）
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

# 新标准IAQI分段表（HJ 633-2024）
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
            return int(round(iaqi))

    # 浓度超过最高分段，返回最高IAQI
    return breakpoints[-1][1]


def calculate_new_composite_index(concentrations: dict) -> float:
    """
    计算新标准综合指数（带权重）

    计算方法（按 GB 3095-2012）：
    1. 计算各污染物单项质量指数 Ii = Ci / Si（浓度/标准值）
    2. 按权重求和：Isum = SO2 + NO2×2 + PM10 + PM2.5×3 + CO + O3×2

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


def execute_query_standard_comparison(
    cities: List[str],
    start_date: str,
    end_date: str,
    context: ExecutionContext
) -> Dict[str, Any]:
    """
    查询新旧标准对比统计指标

    并发查询日报数据和统计数据，计算新旧标准对比

    Args:
        cities: 城市名称列表
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        context: 执行上下文

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
    """
    logger.info(
        "query_standard_comparison_start",
        cities=cities,
        start_date=start_date,
        end_date=end_date
    )

    try:
        # 使用线程池并发查询
        from concurrent.futures import ThreadPoolExecutor, as_completed

        api_client = get_gd_suncere_api_client()

        # 转换城市名称为编码
        city_codes = QueryGDSuncereDataTool.geo_resolver.resolve_city_codes(cities)

        if not city_codes:
            raise Exception(f"未找到任何有效的城市代码: {cities}")

        # 准备查询参数
        start_time = f"{start_date} 00:00:00"
        end_time = f"{end_date} 23:59:59"
        data_source = QueryGDSuncereDataTool.calculate_data_source(end_time)

        # 存储查询结果
        day_data = None
        report_data = None
        errors = []

        def query_day_data():
            """查询日报数据（智能分段：3天内用原始实况，3天外用审核实况）"""
            nonlocal day_data
            try:
                logger.info("querying_day_data_with_segments", cities=cities, start_date=start_date, end_date=end_date)

                # 计算分段
                segments = calculate_date_segments(start_date, end_date)
                logger.info("day_data_segments_calculated", segment_count=len(segments), segments=segments)

                # 使用异步IO并发查询各分段
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                async def fetch_all_segments():
                    tasks = []
                    for seg_start, seg_end, data_type in segments:
                        task = query_day_data_by_segment(
                            api_client=api_client,
                            city_codes=city_codes,
                            start_date=seg_start,
                            end_date=seg_end,
                            data_type=data_type
                        )
                        tasks.append(task)
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    return results

                # 执行并发查询
                all_results = loop.run_until_complete(fetch_all_segments())
                loop.close()

                # 合并结果
                merged_data = []
                for i, result in enumerate(all_results):
                    if isinstance(result, Exception):
                        logger.error("segment_query_error", segment_index=i, error=str(result))
                        errors.append(f"分段{i+1}查询异常: {str(result)}")
                    elif isinstance(result, list):
                        merged_data.extend(result)
                        logger.info("segment_query_success", segment_index=i, record_count=len(result))

                day_data = merged_data

                # 记录原始数据结构，便于调试
                if merged_data:
                    first_record = merged_data[0]
                    logger.info(
                        "day_data_raw_structure",
                        record_count=len(merged_data),
                        sample_fields=list(first_record.keys())[:30],
                        has_cityName="cityName" in first_record if merged_data else False,
                        has_city="city" in first_record if merged_data else False,
                        has_city_name="city_name" in first_record if merged_data else False
                    )
                logger.info("day_data_query_success", record_count=len(day_data), segments_count=len(segments))

            except Exception as e:
                errors.append(f"日报数据查询异常: {str(e)}")
                logger.error("day_data_query_error", error=str(e))

        def query_report_data():
            """查询统计数据（不分段，根据结束日期智能选择数据源）"""
            nonlocal report_data
            try:
                from datetime import datetime

                logger.info("querying_report_data", cities=cities, start_time=start_time, end_time=end_time)

                # 统计数据不分段，根据查询结束日期智能选择数据源类型
                # 规则：三天内不包含当天，即昨天(1天前)、前天(2天前)、大前天(3天前)用原始实况
                #       今天(0天前)和4天前及更早用审核实况
                today = datetime.now().date()
                end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").date()
                days_from_today = (today - end_date_obj).days

                # 智能选择数据源类型
                # 原始实况：今天（0天前）及3天内（1-3天前）
                # 审核实况：4天前及更早
                if days_from_today <= 3:
                    report_data_type = 0  # 原始实况
                    data_type_name = "原始实况"
                else:
                    report_data_type = 1  # 审核实况
                    data_type_name = "审核实况"

                logger.info(
                    "report_data_type_selected",
                    end_date=end_date,
                    days_from_today=days_from_today,
                    data_type=report_data_type,
                    data_type_name=data_type_name
                )

                endpoint = "/api/airprovinceproduct/dataanalysis/ReportDataQuery/GetReportForRangeListFilterAsync"

                payload = {
                    "AreaType": 2,  # 城市级别
                    "TimeType": 8,  # 任意时间
                    "TimePoint": [start_time, end_time],
                    "StationCode": city_codes,
                    "DataSource": report_data_type
                }

                token = api_client.get_token()
                headers = {
                    "Authorization": f"Bearer {token}",
                    "SysCode": "SunAirProvince",
                    "syscode": "SunAirProvince",
                    "Content-Type": "application/json"
                }

                url = f"{api_client.BASE_URL}{endpoint}"
                import requests
                response = requests.post(url, headers=headers, json=payload, timeout=30)

                if response.status_code == 200:
                    response_data = response.json()
                    if response_data.get("success"):
                        result = response_data.get("result")
                        # 处理不同的响应格式
                        if isinstance(result, list):
                            report_data = result
                        elif isinstance(result, dict):
                            report_data = result.get("items", [])
                        else:
                            report_data = []
                        logger.info(
                            "report_data_query_success",
                            data_type=report_data_type,
                            data_type_name=data_type_name,
                            record_count=len(report_data) if report_data else 0
                        )
                    else:
                        errors.append(f"统计数据查询失败: {response_data.get('msg', 'Unknown error')}")
                else:
                    errors.append(f"统计数据查询HTTP错误: {response.status_code}")

            except Exception as e:
                errors.append(f"统计数据查询异常: {str(e)}")
                logger.error("report_data_query_error", error=str(e))

        # 并发执行查询
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(query_day_data), executor.submit(query_report_data)]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    errors.append(f"查询执行异常: {str(e)}")

        # 检查是否有数据
        if not day_data and not report_data:
            error_msg = "; ".join(errors) if errors else "未查询到任何数据"
            return {
                "status": "failed",
                "success": False,
                "error": error_msg,
                "data": None,
                "metadata": {},
                "summary": f"新旧标准对比查询失败: {error_msg}"
            }

        # 处理日报数据，计算新标准指标
        new_standard_stats = {}
        statistical_concentrations = {}
        city_stats = {}
        day_data_id = None  # 用于存储日报数据的 data_id

        if day_data:
            logger.info("processing_day_data", record_count=len(day_data))

            # 数据标准化
            standardizer = get_data_standardizer()
            standardized_records = standardizer.standardize(day_data)

            logger.info(
                "standard_comparison_day_data_standardized",
                raw_count=len(day_data),
                standardized_count=len(standardized_records),
                # 记录第一条数据的字段名，便于调试
                sample_fields=list(standardized_records[0].keys())[:20] if standardized_records else [],
                has_city_field="city" in standardized_records[0] if standardized_records else False,
                has_city_name_field="city_name" in standardized_records[0] if standardized_records else False
            )

            # 更新为新标准字段（避免Agent误认为旧标准数据）
            # 定义安全转换函数（处理API返回的字符串类型浓度值）
            def safe_float(value, default=0.0):
                """安全转换为浮点数，处理None、空字符串等异常情况"""
                if value is None or value == '' or value == '-':
                    return default
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return default

            for record in standardized_records:
                measurements = record.get("measurements", {})

                # 提取浓度值（使用safe_float确保类型正确）
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

                # 计算新标准IAQI（HJ 633-2024）
                pm25_iaqi = calculate_iaqi(pm25_raw, 'PM2_5', 'new')
                pm10_iaqi = calculate_iaqi(pm10_raw, 'PM10', 'new')
                so2_iaqi = calculate_iaqi(so2_raw, 'SO2', 'new')
                no2_iaqi = calculate_iaqi(no2_raw, 'NO2', 'new')
                co_iaqi = calculate_iaqi(co_raw, 'CO', 'new')
                o3_8h_iaqi = calculate_iaqi(o3_8h_raw, 'O3_8h', 'new')

                # 计算AQI（最大IAQI）
                aqi = max(pm25_iaqi, pm10_iaqi, so2_iaqi, no2_iaqi, co_iaqi, o3_8h_iaqi)

                # 确定首要污染物（AQI > 50时）
                pollutants_with_iaqi = {
                    'PM2_5': pm25_iaqi,
                    'PM10': pm10_iaqi,
                    'SO2': so2_iaqi,
                    'NO2': no2_iaqi,
                    'CO': co_iaqi,
                    'O3_8h': o3_8h_iaqi
                }
                primary_pollutant = None
                if aqi > 50:
                    for pollutant, iaqi in pollutants_with_iaqi.items():
                        if iaqi == aqi:
                            primary_pollutant = pollutant
                            break

                # 确定空气质量等级
                if aqi <= 50:
                    air_quality_level = '优'
                elif aqi <= 100:
                    air_quality_level = '良'
                elif aqi <= 150:
                    air_quality_level = '轻度污染'
                elif aqi <= 200:
                    air_quality_level = '中度污染'
                elif aqi <= 300:
                    air_quality_level = '重度污染'
                else:
                    air_quality_level = '严重污染'

                # 更新measurements中的IAQI字段
                measurements['PM2_5_IAQI'] = pm25_iaqi
                measurements['PM10_IAQI'] = pm10_iaqi
                measurements['SO2_IAQI'] = so2_iaqi
                measurements['NO2_IAQI'] = no2_iaqi
                measurements['CO_IAQI'] = co_iaqi
                measurements['O3_8h_IAQI'] = o3_8h_iaqi
                measurements['AQI'] = aqi

                # 更新顶层字段
                record['air_quality_level'] = air_quality_level
                record['primary_pollutant'] = primary_pollutant

            logger.info(
                "new_standard_fields_updated",
                record_count=len(standardized_records),
                update_fields=["PM2_5_IAQI", "PM10_IAQI", "AQI", "air_quality_level", "primary_pollutant"]
            )

            # 保存到上下文，返回 data_id 和 file_path
            save_result = context.data_manager.save_data(
                data=standardized_records,
                schema="air_quality_unified",
                metadata={
                    "source": "gd_suncere_api",
                    "query_type": "standard_comparison_day_data",
                    "cities": cities,
                    "date_range": f"{start_date} to {end_date}",
                    "schema_version": "v2.0",
                    "field_mapping_applied": True,
                    "field_mapping_info": standardizer.get_field_mapping_info() if standardizer else {}
                }
            )

            # save_data 返回字典: {data_id, file_path}
            day_data_id = save_result["data_id"]
            day_data_file_path = save_result["file_path"]

            logger.info(
                "standard_comparison_day_data_saved",
                data_id=day_data_id,
                file_path=day_data_file_path,
                record_count=len(standardized_records)
            )

            # 按城市分组统计（使用标准化后的数据）
            from collections import defaultdict
            city_daily_data = defaultdict(list)

            for record in standardized_records:
                # 标准化后字段名从 city_name 变为 city，需要兼容两种字段名
                city_name = record.get("city", "") or record.get("city_name", "")
                if city_name:
                    city_daily_data[city_name].append(record)

            # 【关键修复】如果日报数据中没有城市字段（API不返回），使用查询参数中的城市名称
            if not city_daily_data and len(cities) == 1:
                logger.info(
                    "no_city_field_in_day_data",
                    message="日报数据中没有城市字段，使用查询参数中的城市名称",
                    query_city=cities[0],
                    record_count=len(standardized_records)
                )
                # 将所有记录归类到查询的城市
                city_daily_data[cities[0]] = standardized_records

            logger.info(
                "city_grouping_completed",
                total_records=len(standardized_records),
                cities_found=list(city_daily_data.keys()),
                records_per_city={city: len(recs) for city, recs in city_daily_data.items()}
            )

            # 对每个城市计算新标准统计
            for city, daily_records in city_daily_data.items():
                logger.info("calculating_new_standard", city=city, day_count=len(daily_records))

                # 初始化统计变量
                total_days = len(daily_records)
                exceed_days = 0
                exceed_details = []  # 记录新标准超标详情
                old_exceed_details = []  # 记录旧标准超标详情（基于AQI>100）
                pm25_sum = 0
                pm10_sum = 0
                so2_sum = 0
                no2_sum = 0
                co_sum = 0
                o3_8h_sum = 0
                no_sum = 0
                nox_sum = 0

                # 收集每日浓度值用于计算百分位数
                # CO: 第95百分位数，O3_8h: 第90百分位数
                # SO2/NO2: 第98百分位数，PM10/PM2.5: 第95百分位数
                daily_co_values = []
                daily_o3_8h_values = []
                daily_so2_values = []
                daily_no2_values = []
                daily_pm10_values = []
                daily_pm25_values = []

                # 首要污染物统计
                primary_pollutant_days = {
                    'PM2_5': 0,
                    'PM10': 0,
                    'SO2': 0,
                    'NO2': 0,
                    'CO': 0,
                    'O3_8h': 0
                }

                # 各污染物超标天数统计
                exceed_days_by_pollutant = {
                    'PM2_5': 0,
                    'PM10': 0,
                    'SO2': 0,
                    'NO2': 0,
                    'CO': 0,
                    'O3_8h': 0
                }

                # 旧标准首要污染物统计（与新标准使用相同的逻辑）
                old_primary_pollutant_days = {
                    'PM2_5': 0,
                    'PM10': 0,
                    'SO2': 0,
                    'NO2': 0,
                    'CO': 0,
                    'O3_8h': 0
                }

                # 旧标准各污染物超标天数统计（基于单项质量指数 > 1，与新标准相同方法）
                old_exceed_days_by_pollutant = {
                    'PM2_5': 0,
                    'PM10': 0,
                    'SO2': 0,
                    'NO2': 0,
                    'CO': 0,
                    'O3_8h': 0
                }

                for record in daily_records:
                    # 提取浓度值
                    # 数据被标准化为 UnifiedDataRecord 格式后，污染物数据在 measurements 字段中
                    # 需要同时检查顶层字段和 measurements 嵌套字段
                    measurements = record.get("measurements", {})
                    # 安全转换函数（处理API返回的字符串类型浓度值）
                    def safe_float(value, default=0.0):
                        if value is None or value == '' or value == '-':
                            return default
                        try:
                            return float(value)
                        except (TypeError, ValueError):
                            return default

                    # 优先从 measurements 中提取，其次从顶层字段提取
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
                    no_raw = safe_float(measurements.get("NO") or measurements.get("no") or
                          record.get("no") or record.get("NO"))
                    nox_raw = safe_float(measurements.get("NOx") or measurements.get("nox") or
                          record.get("nox") or record.get("NOx"))

                    # 按原始监测数据规则修约日数据（GB/T 8170-2008）
                    # 日数据修约：PM2.5/PM10/SO2/NO2/O3/NO/NOx保留0位，CO保留1位
                    pm25 = apply_rounding(pm25_raw, 'PM2_5', 'raw_data')
                    pm10 = apply_rounding(pm10_raw, 'PM10', 'raw_data')
                    so2 = apply_rounding(so2_raw, 'SO2', 'raw_data')
                    no2 = apply_rounding(no2_raw, 'NO2', 'raw_data')
                    co = apply_rounding(co_raw, 'CO', 'raw_data')
                    o3_8h = apply_rounding(o3_8h_raw, 'O3_8h', 'raw_data')
                    no = apply_rounding(no_raw, 'NO', 'raw_data')
                    nox = apply_rounding(nox_raw, 'NOx', 'raw_data')

                    # 调试日志：记录第一条记录的提取和修约情况
                    if record == daily_records[0]:
                        logger.info(
                            "daily_data_rounding_debug",
                            raw_values={
                                "PM2_5": pm25_raw,
                                "SO2": so2_raw,
                                "NO2": no2_raw,
                                "CO": co_raw
                            },
                            rounded_values={
                                "PM2_5": pm25,
                                "SO2": so2,
                                "NO2": no2,
                                "CO": co
                            }
                        )

                    # 累加修约后的浓度值（用于平均值计算）
                    pm25_sum += pm25
                    pm10_sum += pm10
                    so2_sum += so2
                    no2_sum += no2
                    co_sum += co
                    o3_8h_sum += o3_8h
                    no_sum += no
                    nox_sum += nox

                    # 收集修约后的每日值（用于百分位数计算）
                    if co > 0:  # 排除无效值
                        daily_co_values.append(co)
                    if o3_8h > 0:  # 排除无效值
                        daily_o3_8h_values.append(o3_8h)
                    if so2 > 0:  # 排除无效值
                        daily_so2_values.append(so2)
                    if no2 > 0:  # 排除无效值
                        daily_no2_values.append(no2)
                    if pm10 > 0:  # 排除无效值
                        daily_pm10_values.append(pm10)
                    if pm25 > 0:  # 排除无效值
                        daily_pm25_values.append(pm25)

                    # 计算该日各污染物的单项质量指数 Ii = Ci / Si
                    # 使用24小时平均标准限值进行超标判断
                    pm25_index = pm25 / STANDARD_LIMITS['PM2_5']
                    pm10_index = pm10 / STANDARD_LIMITS['PM10']
                    so2_index = so2 / STANDARD_LIMITS['SO2']
                    no2_index = no2 / STANDARD_LIMITS['NO2']
                    co_index = co / STANDARD_LIMITS['CO']
                    o3_8h_index = o3_8h / STANDARD_LIMITS['O3_8h']

                    # 计算各污染物的 IAQI（空气质量分指数）
                    # 使用分段线性插值公式：IAQIP = (IAQIHi - IAQILo) / (BPHi - BPLo) × (CP - BPLo) + IAQILo
                    # 新标准
                    pm25_iaqi_new = calculate_iaqi(pm25, 'PM2_5', 'new')
                    pm10_iaqi_new = calculate_iaqi(pm10, 'PM10', 'new')
                    so2_iaqi_new = calculate_iaqi(so2, 'SO2', 'new')
                    no2_iaqi_new = calculate_iaqi(no2, 'NO2', 'new')
                    co_iaqi_new = calculate_iaqi(co, 'CO', 'new')
                    o3_8h_iaqi_new = calculate_iaqi(o3_8h, 'O3_8h', 'new')

                    # 旧标准
                    pm25_iaqi_old = calculate_iaqi(pm25, 'PM2_5', 'old')
                    pm10_iaqi_old = calculate_iaqi(pm10, 'PM10', 'old')
                    so2_iaqi_old = calculate_iaqi(so2, 'SO2', 'old')
                    no2_iaqi_old = calculate_iaqi(no2, 'NO2', 'old')
                    co_iaqi_old = calculate_iaqi(co, 'CO', 'old')
                    o3_8h_iaqi_old = calculate_iaqi(o3_8h, 'O3_8h', 'old')

                    # 判断该日是否超标：任意污染物单项质量指数 > 1
                    max_single_index = max(pm25_index, pm10_index, so2_index, no2_index, co_index, o3_8h_index)

                    # 统计首要污染物（新标准）
                    # AQI = MAX(IAQIP)，即所有污染物的最大IAQI值
                    # 当 AQI > 50 时，IAQI最大的污染物为首要污染物
                    pollutants_with_iaqi_new = {
                        'PM2_5': pm25_iaqi_new,
                        'PM10': pm10_iaqi_new,
                        'SO2': so2_iaqi_new,
                        'NO2': no2_iaqi_new,
                        'CO': co_iaqi_new,
                        'O3_8h': o3_8h_iaqi_new
                    }
                    aqi_new = max(pollutants_with_iaqi_new.values())
                    if aqi_new > 50:
                        for pollutant, iaqi in pollutants_with_iaqi_new.items():
                            if iaqi == aqi_new:
                                primary_pollutant_days[pollutant] += 1

                    # 统计首要污染物（旧标准）
                    pollutants_with_iaqi_old = {
                        'PM2_5': pm25_iaqi_old,
                        'PM10': pm10_iaqi_old,
                        'SO2': so2_iaqi_old,
                        'NO2': no2_iaqi_old,
                        'CO': co_iaqi_old,
                        'O3_8h': o3_8h_iaqi_old
                    }
                    aqi_old = max(pollutants_with_iaqi_old.values())
                    if aqi_old > 50:
                        for pollutant, iaqi in pollutants_with_iaqi_old.items():
                            if iaqi == aqi_old:
                                old_primary_pollutant_days[pollutant] += 1

                    # 统计各污染物超标天数（单项质量指数 > 1）
                    if pm25_index > 1:
                        exceed_days_by_pollutant['PM2_5'] += 1
                        old_exceed_days_by_pollutant['PM2_5'] += 1
                    if pm10_index > 1:
                        exceed_days_by_pollutant['PM10'] += 1
                        old_exceed_days_by_pollutant['PM10'] += 1
                    if so2_index > 1:
                        exceed_days_by_pollutant['SO2'] += 1
                        old_exceed_days_by_pollutant['SO2'] += 1
                    if no2_index > 1:
                        exceed_days_by_pollutant['NO2'] += 1
                        old_exceed_days_by_pollutant['NO2'] += 1
                    if co_index > 1:
                        exceed_days_by_pollutant['CO'] += 1
                        old_exceed_days_by_pollutant['CO'] += 1
                    if o3_8h_index > 1:
                        exceed_days_by_pollutant['O3_8h'] += 1
                        old_exceed_days_by_pollutant['O3_8h'] += 1

                    if max_single_index > 1:
                        exceed_days += 1
                        # 记录超标详情
                        exceed_pollutants = []
                        pollutants = {
                            'PM2_5': (pm25, pm25_index),
                            'PM10': (pm10, pm10_index),
                            'SO2': (so2, so2_index),
                            'NO2': (no2, no2_index),
                            'CO': (co, co_index),
                            'O3_8h': (o3_8h, o3_8h_index)
                        }
                        for name, (conc, index) in pollutants.items():
                            if index > 1:
                                exceed_pollutants.append({
                                    'name': name,
                                    'concentration': conc,
                                    'index': round(index, 3)
                                })
                        exceed_details.append({
                            'date': record.get("timestamp", "unknown"),
                            'max_index': round(max_single_index, 3),
                            'exceed_pollutants': exceed_pollutants
                        })

                    # 计算旧标准超标详情（基于AQI > 100）
                    # 从记录中提取AQI值
                    aqi = (measurements.get("AQI") or measurements.get("aqi") or
                           record.get("aqi") or record.get("AQI") or 0)
                    if aqi > 100:
                        # AQI > 100 判定为超标，记录超标详情
                        # 尝试获取首要污染物
                        primary_pollutant = (record.get("primary_pollutant") or
                                           record.get("primaryPollutant") or
                                           "Unknown")
                        old_exceed_details.append({
                            'date': record.get("timestamp", "unknown"),
                            'aqi': int(aqi),
                            'primary_pollutant': primary_pollutant
                        })

                    # 调试日志：记录第一天的超标判断详情
                    if record == daily_records[0]:
                        logger.info(
                            "exceed_judgment_debug",
                            date=record.get("timestamp", "unknown"),
                            single_indexes={
                                "PM2_5": round(pm25_index, 3),
                                "PM10": round(pm10_index, 3),
                                "SO2": round(so2_index, 3),
                                "NO2": round(no2_index, 3),
                                "CO": round(co_index, 3),
                                "O3_8h": round(o3_8h_index, 3)
                            },
                            max_single_index=round(max_single_index, 3),
                            is_exceeded=max_single_index > 1
                        )

                # 计算平均浓度（按国家标准修约）
                # 统计数据修约规则：PM2.5保留1位，PM10/SO2/NO2/O3保留0位，CO保留1位
                avg_pm25 = apply_rounding(pm25_sum / total_days, 'PM2_5', 'statistical_data') if total_days > 0 else 0
                avg_pm10 = apply_rounding(pm10_sum / total_days, 'PM10', 'statistical_data') if total_days > 0 else 0
                avg_so2 = apply_rounding(so2_sum / total_days, 'SO2', 'statistical_data') if total_days > 0 else 0
                avg_no2 = apply_rounding(no2_sum / total_days, 'NO2', 'statistical_data') if total_days > 0 else 0
                avg_co = apply_rounding(co_sum / total_days, 'CO', 'statistical_data') if total_days > 0 else 0
                avg_o3_8h = apply_rounding(o3_8h_sum / total_days, 'O3_8h', 'statistical_data') if total_days > 0 else 0
                avg_no = apply_rounding(no_sum / total_days, 'NO', 'statistical_data') if total_days > 0 else 0
                avg_nox = apply_rounding(nox_sum / total_days, 'NOx', 'statistical_data') if total_days > 0 else 0

                # 计算百分位数（按国家标准）
                # CO: 第95百分位数，O3_8h: 第90百分位数
                def calculate_percentile(values, percentile):
                    """计算百分位数"""
                    if not values:
                        return 0.0
                    sorted_values = sorted(values)
                    n = len(sorted_values)
                    index = (percentile / 100) * (n - 1)
                    lower = int(index)
                    upper = lower + 1
                    if upper >= n:
                        return float(sorted_values[-1])
                    # 线性插值
                    weight = index - lower
                    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight

                # 计算百分位数（按国家标准修约）
                # CO使用95百分位，O3_8h使用90百分位，SO2/NO2使用98百分位，PM10/PM2.5使用95百分位
                co_percentile_95 = apply_rounding(calculate_percentile(daily_co_values, 95), 'CO', 'statistical_data')
                o3_8h_percentile_90 = apply_rounding(calculate_percentile(daily_o3_8h_values, 90), 'O3_8h', 'statistical_data')
                so2_percentile_98 = apply_rounding(calculate_percentile(daily_so2_values, 98), 'SO2', 'statistical_data')
                no2_percentile_98 = apply_rounding(calculate_percentile(daily_no2_values, 98), 'NO2', 'statistical_data')
                pm10_percentile_95 = apply_rounding(calculate_percentile(daily_pm10_values, 95), 'PM10', 'statistical_data')
                pm25_percentile_95 = apply_rounding(calculate_percentile(daily_pm25_values, 95), 'PM2_5', 'statistical_data')

                logger.info(
                    "percentile_calculated",
                    co_values_count=len(daily_co_values),
                    o3_8h_values_count=len(daily_o3_8h_values),
                    so2_values_count=len(daily_so2_values),
                    no2_values_count=len(daily_no2_values),
                    pm10_values_count=len(daily_pm10_values),
                    pm25_values_count=len(daily_pm25_values),
                    co_percentile_95=co_percentile_95,
                    o3_8h_percentile_90=o3_8h_percentile_90,
                    so2_percentile_98=so2_percentile_98,
                    no2_percentile_98=no2_percentile_98,
                    pm10_percentile_95=pm10_percentile_95,
                    pm25_percentile_95=pm25_percentile_95
                )

                # 计算新标准综合指数
                # 按国家标准：CO使用95百分位，O3_8h使用90百分位，其余使用平均值
                new_standard_concentrations = {
                    'PM2_5': avg_pm25,      # 平均值
                    'PM10': avg_pm10,       # 平均值
                    'SO2': avg_so2,         # 平均值
                    'NO2': avg_no2,         # 平均值
                    'CO': co_percentile_95,     # ✅ 第95百分位数
                    'O3_8h': o3_8h_percentile_90  # ✅ 第90百分位数
                }

                # 计算新标准单项质量指数 Ii = Ci / Si
                # 注意：综合指数计算使用年均标准限值
                pm25_index = round(new_standard_concentrations['PM2_5'] / ANNUAL_STANDARD_LIMITS['PM2_5'], 3)
                pm10_index = round(new_standard_concentrations['PM10'] / ANNUAL_STANDARD_LIMITS['PM10'], 3)
                so2_index = round(new_standard_concentrations['SO2'] / ANNUAL_STANDARD_LIMITS['SO2'], 3)
                no2_index = round(new_standard_concentrations['NO2'] / ANNUAL_STANDARD_LIMITS['NO2'], 3)
                co_index = round(new_standard_concentrations['CO'] / ANNUAL_STANDARD_LIMITS['CO'], 3)
                o3_8h_index = round(new_standard_concentrations['O3_8h'] / ANNUAL_STANDARD_LIMITS['O3_8h'], 3)

                # 计算新标准加权单项质量指数（带权重）
                # PM2.5:3, O3_8h:2, NO2:2, SO2:1, CO:1, PM10:1
                pm25_weighted_index = round(pm25_index * WEIGHTS['PM2_5'], 3)
                pm10_weighted_index = round(pm10_index * WEIGHTS['PM10'], 3)
                so2_weighted_index = round(so2_index * WEIGHTS['SO2'], 3)
                no2_weighted_index = round(no2_index * WEIGHTS['NO2'], 3)
                co_weighted_index = round(co_index * WEIGHTS['CO'], 3)
                o3_8h_weighted_index = round(o3_8h_index * WEIGHTS['O3_8h'], 3)

                # 计算综合指数（加权单项质量指数之和）
                avg_composite_index = round(
                    pm25_weighted_index + pm10_weighted_index + so2_weighted_index +
                    no2_weighted_index + co_weighted_index + o3_8h_weighted_index, 2
                )

                logger.info(
                    "new_composite_index_calculated",
                    concentrations_used=new_standard_concentrations,
                    avg_composite_index=avg_composite_index,
                    single_indexes={
                        "PM2_5": pm25_index,
                        "PM10": pm10_index,
                        "SO2": so2_index,
                        "NO2": no2_index,
                        "CO": co_index,
                        "O3_8h": o3_8h_index
                    },
                    weighted_indexes={
                        "PM2_5": pm25_weighted_index,
                        "PM10": pm10_weighted_index,
                        "SO2": so2_weighted_index,
                        "NO2": no2_weighted_index,
                        "CO": co_weighted_index,
                        "O3_8h": o3_8h_weighted_index
                    },
                    calculation_detail={
                        "PM2_5": {"avg": avg_pm25, "index": pm25_index, "weighted": pm25_weighted_index, "weight": WEIGHTS['PM2_5']},
                        "PM10": {"avg": avg_pm10, "index": pm10_index, "weighted": pm10_weighted_index, "weight": WEIGHTS['PM10']},
                        "SO2": {"avg": avg_so2, "index": so2_index, "weighted": so2_weighted_index, "weight": WEIGHTS['SO2']},
                        "NO2": {"avg": avg_no2, "index": no2_index, "weighted": no2_weighted_index, "weight": WEIGHTS['NO2']},
                        "CO": {
                            "avg": avg_co,
                            "p95": co_percentile_95,
                            "avg_index": round(avg_co / 4, 3),
                            "p95_index": co_index,
                            "weighted": co_weighted_index,
                            "weight": WEIGHTS['CO']
                        },
                        "O3_8h": {
                            "avg": avg_o3_8h,
                            "p90": o3_8h_percentile_90,
                            "avg_index": round(avg_o3_8h / 160, 3),
                            "p90_index": o3_8h_index,
                            "weighted": o3_8h_weighted_index,
                            "weight": WEIGHTS['O3_8h']
                        }
                    }
                )

                # 计算达标率和超标率（按国家标准修约）
                # 达标率保留1位小数
                valid_days = total_days  # 有效天数等于总天数
                compliance_rate = round((total_days - exceed_days) / total_days, 1) if total_days > 0 else 0
                exceed_rate = round(exceed_days / valid_days * 100, 1) if valid_days > 0 else 0

                logger.info(
                    "city_new_standard_stats_calculated",
                    city=city,
                    total_days=total_days,
                    exceed_days=exceed_days,
                    valid_days=valid_days,
                    compliance_rate=compliance_rate,
                    exceed_rate=exceed_rate,
                    avg_composite_index=avg_composite_index,
                    pm25_avg=avg_pm25,
                    pm10_avg=avg_pm10,
                    co_p95=co_percentile_95,
                    o3_8h_p90=o3_8h_percentile_90,
                    so2_p98=so2_percentile_98,
                    no2_p98=no2_percentile_98,
                    pm10_p95=pm10_percentile_95,
                    pm25_p95=pm25_percentile_95,
                    single_indexes={
                        "SO2": so2_weighted_index,
                        "NO2": no2_weighted_index,
                        "PM10": pm10_weighted_index,
                        "CO": co_weighted_index,
                        "PM2_5": pm25_weighted_index,
                        "O3_8h": o3_8h_weighted_index
                    },
                    primary_pollutant_days=primary_pollutant_days
                )

                # 计算首要污染物比例
                # 总的首要污染物天数（同日多首要污染物的情况都计入）
                total_primary_days = sum(primary_pollutant_days.values())
                primary_pollutant_ratio = {}
                if total_primary_days > 0:
                    for pollutant, days in primary_pollutant_days.items():
                        primary_pollutant_ratio[pollutant] = round(days / total_primary_days * 100, 1)
                else:
                    for pollutant in primary_pollutant_days.keys():
                        primary_pollutant_ratio[pollutant] = 0.0

                # 计算各污染物超标率（超标天数/有效天数）
                exceed_rate_by_pollutant = {}
                for pollutant, days in exceed_days_by_pollutant.items():
                    if valid_days > 0:
                        exceed_rate_by_pollutant[pollutant] = round(days / valid_days * 100, 1)
                    else:
                        exceed_rate_by_pollutant[pollutant] = 0.0

                # 计算旧标准首要污染物比例
                old_total_primary_days = sum(old_primary_pollutant_days.values())
                old_primary_pollutant_ratio = {}
                if old_total_primary_days > 0:
                    for pollutant, days in old_primary_pollutant_days.items():
                        old_primary_pollutant_ratio[pollutant] = round(days / old_total_primary_days * 100, 1)
                else:
                    for pollutant in old_primary_pollutant_days.keys():
                        old_primary_pollutant_ratio[pollutant] = 0.0

                # 计算旧标准各污染物超标率
                old_exceed_rate_by_pollutant = {}
                for pollutant, days in old_exceed_days_by_pollutant.items():
                    if valid_days > 0:
                        old_exceed_rate_by_pollutant[pollutant] = round(days / valid_days * 100, 1)
                    else:
                        old_exceed_rate_by_pollutant[pollutant] = 0.0

                city_stats[city] = {
                    "new_standard": {
                        "composite_index": avg_composite_index,
                        "exceed_days": exceed_days,
                        "exceed_details": exceed_details,  # 新标准超标详情列表
                        "valid_days": valid_days,
                        "exceed_rate": exceed_rate,
                        "compliance_rate": compliance_rate,
                        "total_days": total_days,
                        # 六参数统计指标（按国家标准修约并格式化显示）
                        "SO2": format_pollutant_value(avg_so2, 'SO2', 'statistical_data'),
                        "SO2_P98": format_pollutant_value(so2_percentile_98, 'SO2', 'statistical_data'),
                        "NO2": format_pollutant_value(avg_no2, 'NO2', 'statistical_data'),
                        "NO2_P98": format_pollutant_value(no2_percentile_98, 'NO2', 'statistical_data'),
                        "PM10": format_pollutant_value(avg_pm10, 'PM10', 'statistical_data'),
                        "PM10_P95": format_pollutant_value(pm10_percentile_95, 'PM10', 'statistical_data'),
                        "PM2_5": format_pollutant_value(avg_pm25, 'PM2_5', 'statistical_data'),
                        "PM2_5_P95": format_pollutant_value(pm25_percentile_95, 'PM2_5', 'statistical_data'),
                        "CO": format_pollutant_value(avg_co, 'CO', 'statistical_data'),
                        "CO_P95": format_pollutant_value(co_percentile_95, 'CO', 'statistical_data'),
                        "O3_8h": format_pollutant_value(avg_o3_8h, 'O3_8h', 'statistical_data'),
                        "O3_8h_P90": format_pollutant_value(o3_8h_percentile_90, 'O3_8h', 'statistical_data'),
                        # 加权单项质量指数（带权重）
                        "single_indexes": {
                            "SO2": so2_weighted_index,
                            "NO2": no2_weighted_index,
                            "PM10": pm10_weighted_index,
                            "CO": co_weighted_index,
                            "PM2_5": pm25_weighted_index,
                            "O3_8h": o3_8h_weighted_index
                        },
                        # 首要污染物统计
                        "primary_pollutant_days": primary_pollutant_days,
                        "primary_pollutant_ratio": primary_pollutant_ratio,
                        "total_primary_days": total_primary_days,
                        # 各污染物超标统计
                        "exceed_days_by_pollutant": exceed_days_by_pollutant,
                        "exceed_rate_by_pollutant": exceed_rate_by_pollutant
                    },
                    # 暂存旧标准超标详情（基于AQI>100），后面会合并API数据
                    "old_standard_exceed_details": old_exceed_details
                }

                logger.info(
                    "city_new_standard_calculated",
                    city=city,
                    composite_index=avg_composite_index,
                    exceed_days=exceed_days,
                    compliance_rate=compliance_rate
                )

        # 处理统计数据（旧标准）
        # API 返回字段映射（原始字段名 → 本地字段名）：
        #   cityName       → city           (城市名称)
        #   compositeIndex → composite_index (综合指数)
        #   overDays       → exceed_days     (超标天数)
        #   overRate       → exceed_rate     (超标率)
        #   rank           → rank           (排名)
        #   validDays      → valid_days     (有效天数)
        #   pM2_5_Rank     → pm2_5_rank     (PM2.5排名)
        #
        # 注意：report_data 是原始 API 返回数据，未经标准化，字段名是驼峰格式
        if report_data:
            logger.info(
                "processing_report_data",
                record_count=len(report_data),
                sample_fields=list(report_data[0].keys())[:15] if report_data else [],
                existing_cities=list(city_stats.keys())
            )

            # 【调试】记录统计数据第一条记录的城市字段
            if report_data:
                first_report = report_data[0]
                logger.info(
                    "report_data_city_field_debug",
                    has_cityName="cityName" in first_report,
                    has_city="city" in first_report,
                    cityName_value=first_report.get("cityName"),
                    city_value=first_report.get("city"),
                    all_city_fields=[k for k in first_report.keys() if "city" in k.lower()]
                )

            for record in report_data:
                # 统计数据是原始 API 格式，需要从原始字段名提取
                # 原始字段是驼峰命名：cityName, compositeIndex, overDays 等
                city_name = (
                    record.get("city", "") or           # 标准化后的字段
                    record.get("city_name", "") or      # 备用字段
                    record.get("cityName", "") or      # 原始 API 字段（驼峰）
                    ""
                )

                logger.info(
                    "report_record_city_check",
                    city_name=city_name,
                    in_city_stats=city_name in city_stats,
                    city_stats_keys=list(city_stats.keys()),
                    # 记录所有可能的城市相关字段值
                    city_fields_debug={
                        "city": record.get("city"),
                        "city_name": record.get("city_name"),
                        "cityName": record.get("cityName"),
                        "CityName": record.get("CityName")
                    }
                )
                if city_name and city_name in city_stats:
                    # 提取旧标准统计指标
                    # 注意：API 返回的字段可能是字符串类型，需要转换为数字
                    # 使用辅助函数安全转换数字类型
                    def safe_float(value, default=0):
                        """安全转换为浮点数"""
                        if value is None:
                            return default
                        try:
                            return float(value)
                        except (ValueError, TypeError):
                            return default

                    def safe_int(value, default=0):
                        """安全转换为整数"""
                        if value is None:
                            return default
                        try:
                            return int(float(value))  # 先转float再转int，支持 "2.0" 格式
                        except (ValueError, TypeError):
                            return default

                    old_standard = {
                        "composite_index": safe_float(record.get("compositeIndex") or record.get("CompositeIndex")),
                        "exceed_days": safe_int(record.get("overDays") or record.get("OverDays")),
                        "exceed_rate": safe_float(record.get("overRate") or record.get("OverRate")),
                        "valid_days": safe_int(record.get("validDays") or record.get("ValidDays")),
                        # 六参数统计指标（按表3规范进行修约并格式化显示）
                        "SO2": format_pollutant_value(apply_rounding(safe_float(record.get("sO2_Decimal") or record.get("sO2")), 'SO2', 'statistical_data'), 'SO2', 'statistical_data'),
                        "NO2": format_pollutant_value(apply_rounding(safe_float(record.get("nO2_Decimal") or record.get("nO2")), 'NO2', 'statistical_data'), 'NO2', 'statistical_data'),
                        "PM2_5": format_pollutant_value(apply_rounding(safe_float(record.get("pM2_5_Decimal") or record.get("pM2_5")), 'PM2_5', 'statistical_data'), 'PM2_5', 'statistical_data'),
                        "PM10": format_pollutant_value(apply_rounding(safe_float(record.get("pM10_Decimal") or record.get("pM10")), 'PM10', 'statistical_data'), 'PM10', 'statistical_data'),
                        "CO": format_pollutant_value(apply_rounding(safe_float(record.get("cO_Decimal") or record.get("cO")), 'CO', 'statistical_data'), 'CO', 'statistical_data'),
                        "O3_8h": format_pollutant_value(apply_rounding(safe_float(record.get("o3_8h_Decimal") or record.get("o3_8h")), 'O3_8h', 'statistical_data'), 'O3_8h', 'statistical_data'),
                        # 单项质量指数（从 API 获取）
                        "single_indexes": {
                            "SO2": safe_float(record.get("sO2_SingleIndex") or 0),
                            "NO2": safe_float(record.get("nO2_SingleIndex") or 0),
                            "PM10": safe_float(record.get("pM10_SingleIndex") or 0),
                            "CO": safe_float(record.get("cO_SingleIndex") or 0),
                            "PM2_5": safe_float(record.get("pM2_5_SingleIndex") or 0),
                            "O3_8h": safe_float(record.get("o3_8h_SingleIndex") or 0)
                        },
                        # 首要污染物统计（基于AQI > 100时的首要污染物字段）
                        "primary_pollutant_days": old_primary_pollutant_days,
                        "primary_pollutant_ratio": old_primary_pollutant_ratio,
                        "total_primary_days": old_total_primary_days,
                        # 各污染物超标统计（基于单项质量指数 > 1）
                        "exceed_days_by_pollutant": old_exceed_days_by_pollutant,
                        "exceed_rate_by_pollutant": old_exceed_rate_by_pollutant
                    }

                    # 调试日志：记录旧标准指标提取结果
                    logger.info(
                        "old_standard_extracted",
                        city=city,
                        composite_index=old_standard["composite_index"],
                        exceed_days=old_standard["exceed_days"],
                        raw_compositeIndex=record.get("compositeIndex"),
                        raw_type=type(record.get("compositeIndex")),
                        concentrations={
                            "SO2": old_standard.get("SO2"),
                            "NO2": old_standard.get("NO2"),
                            "PM2_5": old_standard.get("PM2_5"),
                            "PM10": old_standard.get("PM10"),
                            "CO": old_standard.get("CO"),
                            "O3_8h": old_standard.get("O3_8h")
                        },
                        single_indexes=old_standard.get("single_indexes", {})
                    )

                    # 合并旧标准超标详情（从日报数据的AQI计算得出）
                    old_standard_exceed_details = city_stats[city].get("old_standard_exceed_details", [])
                    old_standard["exceed_details"] = old_standard_exceed_details

                    city_stats[city]["old_standard"] = old_standard

                    # 计算对比数据
                    new_index = city_stats[city]["new_standard"]["composite_index"]
                    old_index = old_standard["composite_index"]
                    new_exceed = city_stats[city]["new_standard"]["exceed_days"]
                    old_exceed = old_standard["exceed_days"]

                    city_stats[city]["comparison"] = {
                        "composite_index_change": round(new_index - old_index, 2),
                        "composite_index_change_rate": round(((new_index - old_index) / old_index * 100) if old_index > 0 else 0, 2),
                        "exceed_days_change": new_exceed - old_exceed
                    }

        # 构建返回结果
        # 如果只有一个城市，直接返回该城市的统计
        # 如果有多个城市，返回汇总统计

        logger.info(
            "building_final_result",
            total_cities_in_stats=len(city_stats),
            city_names=list(city_stats.keys()),
            has_day_data=day_data is not None,
            has_report_data=report_data is not None,
            # 详细调试信息
            has_old_standard=bool(any("old_standard" in v for v in city_stats.values())),
            cities_with_old_standard=[city for city, data in city_stats.items() if "old_standard" in data]
        )

        # 【调试】如果统计数据存在但未匹配，记录详细信息
        if report_data and not any("old_standard" in v for v in city_stats.values()):
            logger.warning(
                "report_data_not_matched",
                message="统计数据存在但未能匹配到任何城市",
                report_count=len(report_data),
                city_stats_keys=list(city_stats.keys()),
                sample_report_cityName=report_data[0].get("cityName") if report_data else None,
                sample_report_city=report_data[0].get("city") if report_data else None,
                sample_report_fields=list(report_data[0].keys())[:10] if report_data else []
            )

        # 【调试】记录标准化后第一条记录的结构，帮助排查浓度提取问题
        if standardized_records:
            first_record = standardized_records[0]
            has_measurements = "measurements" in first_record
            measurements_keys = list(first_record.get("measurements", {}).keys()) if has_measurements else []
            logger.info(
                "standardized_record_structure_debug",
                has_measurements=has_measurements,
                measurements_count=len(measurements_keys),
                measurements_keys=measurements_keys[:20],
                top_level_fields=[k for k in first_record.keys() if k != "measurements"][:15],
                # 尝试从多个位置提取 PM2.5
                pm25_direct=first_record.get("pm2_5") or first_record.get("PM2_5"),
                pm25_from_measurements=first_record.get("measurements", {}).get("PM2_5") if has_measurements else None
            )

        result_data = None
        result_summary = {}

        if len(cities) == 1 and city_stats:
            # 单城市查询
            city = list(city_stats.keys())[0]
            city_data = city_stats[city]

            result_summary = {
                "city": city,
                "old_standard": city_data.get("old_standard", {}),
                "new_standard": city_data["new_standard"],
                "comparison": city_data.get("comparison", {})
            }
        else:
            # 多城市查询
            result_summary = {
                "cities": list(city_stats.keys()),
                "city_stats": city_stats
            }

        # 构建元数据
        total_days = (datetime.strptime(end_date, "%Y-%m-%d") - datetime.strptime(start_date, "%Y-%m-%d")).days + 1

        metadata = {
            "tool_name": "query_standard_comparison",
            "cities": cities,
            "date_range": f"{start_date} to {end_date}",
            "schema_version": "v2.0",
            "total_days": total_days,
            "data_id": day_data_id,  # 数据传递符号
            "file_path": f"backend_data_registry/datasets/{day_data_id.replace(':', '_')}.json"  # 存储地址（相对路径）
        }

        # 构建摘要
        if len(cities) == 1:
            city = list(city_stats.keys())[0] if city_stats else cities[0]
            summary_parts = [
                f"{city} 新旧标准对比查询完成"
            ]

            # 在摘要中添加数据存储信息
            if day_data_id:
                summary_parts.append(f"日报数据已保存 (data_id: {day_data_id})")

            result_summary_text = " | ".join(summary_parts)

        else:
            result_summary_text = f"多城市新旧标准对比查询完成，共查询 {len(city_stats)} 个城市"

            # 在摘要中添加数据存储信息
            if day_data_id:
                result_summary_text += f" | 日报数据已保存 (data_id: {day_data_id})"

        return {
            "status": "success",
            "success": True,
            "data": result_data,  # 统计工具不返回详细记录
            "metadata": metadata,
            "summary": result_summary_text,
            "result": result_summary  # 详细结果在summary字段中
        }

    except Exception as e:
        logger.error(
            "query_standard_comparison_failed",
            error=str(e),
            error_type=type(e).__name__
        )
        return QueryGDSuncereDataTool._create_error_response(str(e))
