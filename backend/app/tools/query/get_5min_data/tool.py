"""
5分钟数据查询工具

查询站点5分钟污染物浓度和气象数据

功能：
- 查询站点5分钟污染物浓度数据
- 查询站点5分钟气象数据（风速、风向、温度、湿度、气压）
- 支持数据透视（PIVOT）转换为宽表格式
- 返回 UDF v2.0 标准格式
"""
from typing import Dict, Any, List, Optional, TYPE_CHECKING
from datetime import datetime
import structlog
import pyodbc
import re

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.data_standardizer import get_data_standardizer

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()


class Get5MinDataTool(LLMTool):
    """
    5分钟数据查询工具

    查询站点5分钟污染物浓度和气象数据
    """

    # 污染物代码映射表（基于 /tmp/BSD_Pollutant_export.csv）
    POLLUTANT_CODE_MAP = {
        # 污染物（按照CSV文件的正确映射）
        "100": "SO2",     # SO2 (二氧化硫)
        "101": "NO2",     # NO2 (二氧化氮)
        "102": "O3",      # O3 (臭氧)
        "103": "CO",      # CO (一氧化碳)
        "104": "PM10",    # PM10 (颗粒物)
        "105": "PM2_5",   # PM2.5 (细颗粒物)
        "106": "NO",      # NO (一氧化氮)
        "107": "NOx",     # NOx (氮氧化物)
        "1028": "O3_8h",  # O3_8h (臭氧8小时)

        # 气象
        "108": "WS",      # 风速 (m/s)
        "109": "WD",      # 风向 (度)
        "110": "PRESSURE", # 气压 (hpa)
        "111": "TEMP",    # 气温 (℃)
        "112": "RH",      # 湿度 (%)
    }

    # 反向映射（用户友好输入）
    POLLUTANT_NAME_TO_CODE = {
        "SO2": "100", "二氧化硫": "100", "SO₂": "100",
        "NO2": "101", "二氧化氮": "101", "NO₂": "101",
        "O3": "102", "臭氧": "102", "O₃": "102",
        "CO": "103", "一氧化碳": "103",
        "PM10": "104", "颗粒物": "104",
        "PM2.5": "105", "PM2_5": "105", "细颗粒物": "105",
        "NO": "106", "一氧化氮": "106",
        "NOx": "107", "氮氧化物": "107",
        "O3_8h": "1028", "O3_8h": "1028", "臭氧8小时": "1028",
        "风速": "108", "WS": "108",
        "风向": "109", "WD": "109",
        "气压": "110", "PRESSURE": "110",
        "温度": "111", "TEMP": "111", "气温": "111",
        "湿度": "112", "RH": "112"
    }

    def __init__(self):
        function_schema = {
            "name": "get_5min_data",
            "description": """
查询站点5分钟污染物浓度和气象数据。

**数据来源**：
- 数据库：air_quality_db (SQL Server)
- 表名格式：Air_5m_{年份}_{站点代码}_Src
- 数据内容：污染物浓度 + 气象参数（风速、风向、温度、湿度、气压）

**支持查询**：
- 站点5分钟污染物浓度数据（PM2.5、PM10、SO2、NO2、O3、CO等）
- 站点5分钟气象数据（风速WS、风向WD、温度TEMP、湿度RH、气压PRESSURE）

**参数说明**：
- station: 站点名称或站点代码（如"万寿西宫"或"1001A"）
- start_time: 开始时间（ISO 8601格式，如"2026-01-01T00:00:00"）
- end_time: 结束时间（ISO 8601格式，如"2026-01-02T00:00:00"）
- pollutants: 污染物列表（可选，如["PM2.5", "O3", "WS", "WD"]，默认查询所有污染物）

**限制**：
- 不支持跨年查询（时间段必须在单一年内）
- 需要站点代码对应的5分钟数据表存在

**示例**：
- 查询万寿西宫站点2026年1月1日的5分钟数据：
  get_5min_data(station="万寿西宫", start_time="2026-01-01T00:00:00", end_time="2026-01-02T00:00:00")
- 查询特定污染物：
  get_5min_data(station="万寿西宫", start_time="2026-01-01T00:00:00", end_time="2026-01-02T00:00:00", pollutants=["PM2.5", "O3", "WS", "WD"])

**返回格式**：
- status: "success" | "failed"
- data: 5分钟数据列表（宽表格式）
- metadata.schema_version: "v2.0"
- metadata.data_id: 数据存储ID（供下游工具使用）
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "station": {
                        "type": "string",
                        "description": "站点名称或站点代码（如'万寿西宫'或'1001A'）"
                    },
                    "start_time": {
                        "type": "string",
                        "description": "开始时间（ISO 8601格式，如'2026-01-01T00:00:00'）"
                    },
                    "end_time": {
                        "type": "string",
                        "description": "结束时间（ISO 8601格式，如'2026-01-02T00:00:00'）"
                    },
                    "pollutants": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "污染物列表（可选，如['PM2.5', 'O3', 'WS', 'WD']，默认查询所有污染物）"
                    }
                },
                "required": ["station", "start_time", "end_time"]
            }
        }

        super().__init__(
            name="get_5min_data",
            description="Query 5-minute air quality and weather data",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True
        )

    async def execute(
        self,
        context: "ExecutionContext",
        station: str,
        start_time: str,
        end_time: str,
        pollutants: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行5分钟数据查询

        Args:
            context: 执行上下文
            station: 站点名称或站点代码
            start_time: 开始时间
            end_time: 结束时间
            pollutants: 污染物列表（可选）

        Returns:
            Dict: UDF v2.0格式的查询结果
        """
        try:
            logger.info(
                "5min_data_query_started",
                station=station,
                start_time=start_time,
                end_time=end_time,
                pollutants=pollutants
            )

            # 1. 解析站点代码
            station_code = self._resolve_station_code(station)
            if not station_code:
                return {
                    "status": "failed",
                    "success": False,
                    "data": None,
                    "summary": f"未找到站点 '{station}'。请使用正确的站点名称或代码。"
                }

            # 2. 解析时间并检查是否跨年
            start_dt = self._parse_datetime(start_time)
            end_dt = self._parse_datetime(end_time)

            if not start_dt or not end_dt:
                return {
                    "status": "failed",
                    "success": False,
                    "data": None,
                    "summary": "时间格式错误。请使用ISO 8601格式，如'2026-01-01T00:00:00'"
                }

            if start_dt.year != end_dt.year:
                return {
                    "status": "failed",
                    "success": False,
                    "data": None,
                    "summary": f"时间范围跨年（{start_dt.year}→{end_dt.year}），不支持跨年查询。请分段查询。"
                }

            year = start_dt.year

            # 3. 构建表名
            table_name = f"Air_5m_{year}_{station_code}_Src"

            # 4. 转换污染物名称到代码
            if pollutants:
                pollutant_codes = [
                    self.POLLUTANT_NAME_TO_CODE.get(p, p)
                    for p in pollutants
                ]
            else:
                # 默认查询所有污染物
                pollutant_codes = list(self.POLLUTANT_CODE_MAP.keys())

            # 5. 查询数据
            raw_records = self._query_5min_data(
                table_name=table_name,
                start_time=start_time,
                end_time=end_time,
                pollutant_codes=pollutant_codes
            )

            if not raw_records:
                return {
                    "status": "empty",
                    "success": True,
                    "data": [],
                    "summary": f"表 {table_name} 中没有找到符合条件的数据。请检查时间范围和站点代码是否正确。"
                }

            # 6. 数据透视（长表 → 宽表）
            pivoted_records = self._pivot_data(raw_records)

            # 7. 数据标准化（UDF v2.0）
            standardized_records = self._standardize_data(
                pivoted_records,
                station_code=station_code
            )

            # 8. 保存数据
            data_id = context.save_data(
                data=standardized_records,
                schema="air_quality_5min"
            )

            logger.info(
                "5min_data_query_successful",
                station=station,
                station_code=station_code,
                table_name=table_name,
                record_count=len(standardized_records),
                data_id=data_id
            )

            return {
                "status": "success",
                "success": True,
                "data": standardized_records[:288],  # 返回前288条（1天）供LLM查看
                "metadata": {
                    "schema_version": "v2.0",
                    "field_mapping_applied": True,
                    "field_mapping_info": {
                        "source_format": "long_table",
                        "target_format": "wide_table",
                        "pollutant_codes": pollutant_codes
                    },
                    "generator": "get_5min_data",
                    "scenario": "5min_pollutant_weather",
                    "record_count": len(standardized_records),
                    "data_id": data_id,
                    "station_code": station_code,
                    "table_name": table_name
                },
                "summary": f"查询到{len(standardized_records)}条5分钟数据（站点：{station}，时间：{start_time} ~ {end_time}）"
            }

        except Exception as e:
            logger.error(
                "5min_data_query_failed",
                station=station,
                error=str(e),
                exc_info=True
            )
            return {
                "status": "failed",
                "success": False,
                "data": None,
                "summary": f"查询失败: {str(e)}"
            }

    def _resolve_station_code(self, station: str) -> Optional[str]:
        """
        解析站点代码

        Args:
            station: 站点名称或站点代码

        Returns:
            站点代码，如果未找到返回None
        """
        # 复用 GeoMappingResolver
        try:
            from app.tools.query.query_gd_suncere.tool import GeoMappingResolver

            # 尝试解析为站点名称
            station_codes = GeoMappingResolver.resolve_station_codes([station])
            if station_codes:
                return station_codes[0]

            # 如果输入本身就是代码格式（4位数字+字母），直接返回
            if re.match(r'^\d{4}[A-Z]?$', station.strip()):
                return station.strip()

            return None

        except Exception as e:
            logger.warning(
                "station_resolution_failed",
                station=station,
                error=str(e)
            )
            return None

    def _parse_datetime(self, datetime_str: str) -> Optional[datetime]:
        """
        解析ISO 8601时间字符串

        Args:
            datetime_str: 时间字符串

        Returns:
            datetime对象，解析失败返回None
        """
        try:
            # 支持多种格式
            formats = [
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%d %H:%M:%S.%f"
            ]

            for fmt in formats:
                try:
                    return datetime.strptime(datetime_str, fmt)
                except ValueError:
                    continue

            return None

        except Exception:
            return None

    def _query_5min_data(
        self,
        table_name: str,
        start_time: str,
        end_time: str,
        pollutant_codes: List[str]
    ) -> List[Dict]:
        """
        查询5分钟数据

        Args:
            table_name: 表名
            start_time: 开始时间
            end_time: 结束时间
            pollutant_codes: 污染物代码列表

        Returns:
            原始数据记录（长表格式）
        """
        try:
            # 构建SQL
            codes_str = ",".join([f"'{code}'" for code in pollutant_codes])
            sql = f"""
                SELECT TimePoint, PollutantCode, MonValue
                FROM {table_name}
                WHERE TimePoint BETWEEN '{start_time}' AND '{end_time}'
                  AND PollutantCode IN ({codes_str})
                ORDER BY TimePoint, PollutantCode
            """

            # 执行查询
            records = self._execute_query(sql, database="air_quality_db")

            logger.info(
                "5min_data_query_executed",
                table_name=table_name,
                record_count=len(records)
            )

            # 【调试】记录前10条原始数据
            if records:
                logger.info(
                    "5min_raw_data_sample",
                    sample_records=records[:10],
                    sample_fields=list(records[0].keys()) if records else []
                )

            return records

        except pyodbc.ProgrammingError as e:
            # 表不存在
            error_msg = str(e).lower()
            if "invalid object name" in error_msg or "对象名" in error_msg:
                logger.warning(
                    "table_not_found",
                    table_name=table_name,
                    error=str(e)
                )
                return []

            raise

    # 需要单位转换的污染物字段（mg/m³ → μg/m³，乘以1000）
    # 数据库存储单位统一为 mg/m³，显示时需要转换：
    # - SO2、NO2、O3、PM10、PM2_5、NO、NOx、O3_8h：需要转换为 μg/m³（乘以1000）
    # - CO：保持 mg/m³（不需要转换）
    # - 气象参数（WS、WD、TEMP、RH、PRESSURE）：不转换
    POLLUTANT_FIELDS_NEED_CONVERSION = {
        "SO2", "NO2", "O3", "PM10", "PM2_5", "NO", "NOx", "O3_8h"
    }

    def _pivot_data(self, raw_records: List[Dict]) -> List[Dict]:
        """
        将长表数据透视转换为宽表

        输入：[TimePoint, PollutantCode, MonValue]
        输出：[TimePoint, PM2_5, O3, WS, WD, ...]

        单位转换：
        - 污染物浓度：mg/m³ → μg/m³（乘以1000）
        - 气象参数：不转换（WS、WD、TEMP、RH、PRESSURE）

        Args:
            raw_records: 原始数据（长表格式）

        Returns:
            透视后的数据（宽表格式）
        """
        pivoted = {}

        for record in raw_records:
            time_point = record.get('TimePoint')
            pollutant_code = record.get('PollutantCode')
            mon_value = record.get('MonValue')

            if not time_point or pollutant_code is None:
                continue

            # 映射污染物代码（支持字符串和整数类型）
            # 统一转换为字符串进行查找
            code_str = str(pollutant_code)
            field_name = self.POLLUTANT_CODE_MAP.get(code_str)
            if not field_name:
                # 记录未映射的污染物代码，便于调试
                logger.warning(
                    "unmapped_pollutant_code",
                    pollutant_code=pollutant_code,
                    code_str=code_str,
                    time_point=time_point
                )
                continue

            # 初始化时序点
            if time_point not in pivoted:
                pivoted[time_point] = {'timestamp': time_point}

            # 单位转换：污染物浓度从 mg/m³ 转换为 μg/m³
            if field_name in self.POLLUTANT_FIELDS_NEED_CONVERSION:
                # 污染物浓度需要乘以1000（mg/m³ → μg/m³）
                converted_value = mon_value * 1000 if mon_value is not None else None
                pivoted[time_point][field_name] = converted_value
            else:
                # 气象参数不转换
                pivoted[time_point][field_name] = mon_value

        # 转换为列表并排序
        result = list(pivoted.values())
        result.sort(key=lambda x: x['timestamp'])

        # 【调试】记录透视后的前5条数据
        if result:
            logger.info(
                "5min_pivoted_data_sample",
                sample_count=5,
                sample_records=result[:5]
            )

        return result

    def _standardize_data(
        self,
        records: List[Dict],
        station_code: str
    ) -> List[Dict]:
        """
        标准化数据（UDF v2.0）

        Args:
            records: 原始记录
            station_code: 站点代码

        Returns:
            标准化后的记录
        """
        standardizer = get_data_standardizer()

        standardized_records = []

        for record in records:
            # 添加站点信息
            record['station_code'] = station_code

            # 标准化字段名
            standardized_record = {}
            for key, value in record.items():
                standard_key = standardizer._get_standard_field_name(key)
                final_key = standard_key if standard_key else key
                standardized_record[final_key] = value

            standardized_records.append(standardized_record)

        return standardized_records

    def _get_connection_string(self, database: str) -> str:
        """获取数据库连接字符串"""
        try:
            from config.settings import Settings
            settings = Settings()

            # 替换数据库名称
            conn_str = settings.sqlserver_connection_string
            conn_str = re.sub(
                r'DATABASE=\w+',
                f'DATABASE={database}',
                conn_str,
                flags=re.IGNORECASE
            )

            return conn_str

        except Exception as e:
            logger.error("获取数据库配置失败", error=str(e))
            raise

    def _execute_query(self, sql: str, database: str) -> list:
        """执行SQL查询"""
        connection_string = self._get_connection_string(database)

        conn = pyodbc.connect(connection_string, timeout=30)
        cursor = conn.cursor()

        try:
            cursor.execute(sql)

            # 转换为字典列表
            columns = [column[0] for column in cursor.description]
            results = []
            for row in cursor.fetchall():
                record = dict(zip(columns, row))

                # 转换datetime为字符串
                for key, value in record.items():
                    if hasattr(value, 'strftime'):
                        record[key] = value.strftime('%Y-%m-%d %H:%M:%S')

                results.append(record)

            return results

        finally:
            cursor.close()
            conn.close()
