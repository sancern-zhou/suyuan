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
        context: ExecutionContext
    ) -> Dict[str, Any]:
        """
        查询城市日报数据

        Args:
            cities: 城市名称列表（LLM 输出，如 ["广州", "深圳"]）
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            context: 执行上下文

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
                end_date=end_date
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
    context: ExecutionContext
) -> Dict[str, Any]:
    """
    执行城市日报数据查询

    Args:
        cities: 城市名称列表，如 ["广州", "深圳", "佛山"]
        start_date: 开始日期，格式 "YYYY-MM-DD"
        end_date: 结束日期，格式 "YYYY-MM-DD"
        context: 执行上下文

    Returns:
        查询结果字典
    """
    return QueryGDSuncereDataTool.query_city_day_data(
        cities=cities,
        start_date=start_date,
        end_date=end_date,
        context=context
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
