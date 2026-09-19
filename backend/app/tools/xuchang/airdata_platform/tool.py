"""
大气环境监测数据接口中台查询工具（许昌专属）

- query_airdata_platform：区域/站点基础表 + 城市/站点/乡镇日小时空气质量数据查询
- airdata_calc_report_summary：按时间范围统计站点/区县/城市/区域报表并输出同比对比
"""
from typing import TYPE_CHECKING, Any, Optional

import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory

from .client import (
    ALL_API_CODES,
    DATA_API_CODES,
    REFERENCE_API_CODES,
    AirDataPlatformError,
    get_airdata_platform_client,
    get_filterable_fields,
)

if TYPE_CHECKING:
    from app.agent.context.execution_context import ExecutionContext

logger = structlog.get_logger()

PREVIEW_ROW_LIMIT = 24

_API_CODE_HINTS = {
    "region": "区域表（行政区划，含经纬度与气象编码）",
    "station": "站点表（站点名称/编码/坐标/地址）",
    "v_c_d_sb_145": "城市日数据-替代145口径",
    "v_c_d_sb_155": "城市日数据-替代155口径",
    "v_c_d_src_155": "城市日数据-原始155口径",
    "v_s_d_app_145": "站点日数据-审核145口径",
    "v_s_d_src_145": "站点日数据-原始145口径",
    "v_t_d_app": "乡镇日数据-审核",
    "v_t_d_src": "乡镇日数据-原始",
    "v_t_h_app": "乡镇小时数据-审核",
    "v_t_h_src": "乡镇小时数据-原始",
}


def _describe_result(
    rows: list[dict[str, Any]],
    total: int,
    truncated: bool,
    schema: str,
    metadata: dict[str, Any],
    summary_prefix: str,
    file_path: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "success",
        "success": True,
        "data": rows[:PREVIEW_ROW_LIMIT],
        "metadata": {
            **metadata,
            "total_records": total,
            "returned_records": len(rows[:PREVIEW_ROW_LIMIT]),
            "schema": schema,
        },
        "summary": f"{summary_prefix}共 {total} 条",
    }
    if truncated:
        result["metadata"]["truncated"] = True
        result["summary"] += "（因行数上限截断，完整结果以后续分页为准）"
    if file_path:
        result["file_path"] = file_path
        result["summary"] += f"，完整数据已保存为 {file_path}"
    else:
        result["summary"] += "，已全部返回"
    return result


class QueryAirDataPlatformTool(LLMTool):
    """大气环境监测数据接口中台通用数据查询工具"""

    def __init__(self):
        api_code_enum = list(ALL_API_CODES)
        data_hint = "；".join(f"{code}={_API_CODE_HINTS[code]}" for code in DATA_API_CODES)
        function_schema = {
            "name": "query_airdata_platform",
            "description": (
                "查询大气环境监测数据接口中台的数据（许昌项目）。"
                f"可选接口：{'；'.join(f'{code}={_API_CODE_HINTS[code]}' for code in REFERENCE_API_CODES)}。"
                f"空气质量数据接口：{data_hint}。"
                "数据接口输出 32 个字段：8 项污染物浓度（so2/no2/pm10/co/o3_8h/o3/pm2_5/no/nox）、"
                "对应 *_mark 数据标记、*_iaqi 分指数、aqi、qualitytype 空气质量等级、primarypollutant 首要污染物；"
                "name/code 为城市或站点或乡镇名称与编码，timepoint 为时间点（日粒度 yyyy-MM-dd，时粒度 yyyy-MM-dd HH）。"
                "filters 多条件为 AND；field 必须是该接口可过滤字段，否则条件被静默忽略；"
                "时间字段格式 yyyy-MM-dd 或 yyyy-MM-dd HH:mm:ss；同一字段可传多条（如 gte+lte）。"
                "注意 v_t_d_app（乡镇日-审核）当前中台侧配置故障暂不可用，乡镇日数据请改用 v_t_d_src。"
                "乡镇站/站点编码应先用 xuchang_station_catalog 解析，不要凭名称猜测编码。"
                "自动翻页聚合，超过 24 行时完整数据落盘并返回 file_path。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "api_code": {
                        "type": "string",
                        "enum": api_code_enum,
                        "description": "接口编码",
                    },
                    "filters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field": {
                                    "type": "string",
                                    "description": "过滤字段，必须在接口可过滤字段内",
                                },
                                "operator": {
                                    "type": "string",
                                    "enum": ["eq", "like", "in", "between", "gte", "lte"],
                                    "description": "谓词，缺省 eq",
                                },
                                "value": {
                                    "description": "单值（eq/like/gte/lte）、数组或逗号分隔字符串（in）、起始值（between）",
                                },
                                "second_value": {
                                    "description": "结束值，仅 between 需要",
                                },
                            },
                            "required": ["field", "value"],
                        },
                        "description": "过滤条件数组，可选",
                    },
                    "selected_fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "返回字段编码数组，可选；传空或非法字段回退默认输出",
                    },
                    "sort_config": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field": {"type": "string"},
                                "order": {
                                    "type": "string",
                                    "enum": ["asc", "desc"],
                                },
                            },
                            "required": ["field"],
                        },
                        "description": "排序配置，可选",
                    },
                    "max_rows": {
                        "type": "integer",
                        "description": "聚合查询最大行数，默认 2000，上限 5000",
                    },
                },
                "required": ["api_code"],
            },
        }

        super().__init__(
            name="query_airdata_platform",
            description="Query AirDataPlatform datasets (region/station/city/station/town air quality)",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True,
        )

    async def execute(
        self,
        context: Optional["ExecutionContext"] = None,
        api_code: str = "",
        filters: list[dict[str, Any]] | None = None,
        selected_fields: list[str] | None = None,
        sort_config: list[dict[str, Any]] | None = None,
        max_rows: int = 2000,
        **kwargs,
    ) -> dict[str, Any]:
        logger.info(
            "query_airdata_platform_start",
            api_code=api_code,
            filters=filters,
        )
        try:
            filterable = get_filterable_fields(api_code)
            effective_max_rows = min(max(int(max_rows or 2000), 1), 5000)
            client = get_airdata_platform_client()
            result = client.query_all(
                api_code,
                filters=filters,
                selected_fields=selected_fields,
                sort_config=sort_config,
                max_rows=effective_max_rows,
            )
            rows = result["rows"]
            metadata = {
                "tool_name": self.name,
                "api_code": api_code,
                "filterable_fields": list(filterable),
                "total": result["total"],
                "pages_fetched": result["pages_fetched"],
            }

            if not rows:
                return {
                    "status": "empty",
                    "success": True,
                    "data": [],
                    "metadata": {**metadata, "message": "查询成功但无数据返回"},
                    "summary": f"接口 {api_code} 在指定条件下无数据",
                }

            file_path = None
            if context is not None and len(rows) > PREVIEW_ROW_LIMIT:
                file_path = context.save_data(
                    data=rows,
                    schema="airdata_platform_query",
                    metadata={
                        "source": "airdata_platform",
                        "api_code": api_code,
                        "filters": filters,
                        "total": result["total"],
                    },
                )
                logger.info(
                    "query_airdata_platform_data_saved",
                    file_path=file_path,
                    record_count=len(rows),
                )

            return _describe_result(
                rows,
                result["total"],
                result["truncated"],
                "airdata_platform_query",
                metadata,
                f"接口 {api_code} 查询成功，",
                file_path=file_path,
            )
        except AirDataPlatformError as exc:
            return self._failed(api_code, str(exc))
        except Exception as exc:
            logger.error(
                "query_airdata_platform_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return self._failed(api_code, str(exc))

    def _failed(self, api_code: str, message: str) -> dict[str, Any]:
        return {
            "status": "failed",
            "success": False,
            "error": message,
            "data": None,
            "metadata": {
                "tool_name": self.name,
                "api_code": api_code,
            },
            "summary": f"中台数据查询失败: {message}",
        }


class AirDataCalcReportSummaryTool(LLMTool):
    """中台报表汇总接口工具（同比统计）"""

    def __init__(self):
        table_hint = (
            "DataCrawler 源表常用取值：view_dat_city_day_substitutionback_pantype145、"
            "view_dat_city_day_substitutionback_pantype155、view_dat_city_day_src_pantype155、"
            "view_dat_station_day_app_pantype145、view_dat_station_day_src_pantype145、"
            "view_dat_town_day_app、view_dat_town_day_src、view_dat_town_hour_app、view_dat_town_hour_src"
        )
        function_schema = {
            "name": "airdata_calc_report_summary",
            "description": (
                "按时间范围对站点/区县/城市/区域做空气质量报表统计，并输出与 year 指定年份同期的同比对比数据"
                "（大气环境监测数据接口中台，许昌项目）。"
                "返回行为扁平字典，键名为 PascalCase：当前期值（如 SO2_Curr）、对比期值（*_Compare）、"
                "变幅（*_Increase）与变幅类型（*_ChangeType，Rate 为百分比、Difference 为差值）；"
                "统计值均为字符串，无效值统一为 —。"
                f"基础统计模块含 8 项污染物均值、百分位、单项指数与综合指数 CompositeIndex；"
                "还含级别统计（Lvl1~Lvl6、FineDays、StandardRate、OverDays 等）、极值统计、超标天数与首要污染物统计模块。"
                f"{table_hint}。"
                "统计窗口和 reportTimeType 决定报表粒度：4 月报、5 季度报、6 半年报、7 年报、8 任意时间段。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start_time": {
                        "type": "string",
                        "description": "统计窗口开始时间，格式 yyyy-MM-dd",
                    },
                    "end_time": {
                        "type": "string",
                        "description": "统计窗口结束时间，格式 yyyy-MM-dd",
                    },
                    "input_table_name": {
                        "type": "string",
                        "description": "输入数据表名，可带 DataCrawler. 前缀",
                    },
                    "year": {
                        "type": "integer",
                        "description": "对比年份，取该年同月同日区间作为同比对比期",
                    },
                    "area_type": {
                        "type": "integer",
                        "enum": [0, 1, 2, 3],
                        "description": "区域类型：0 站点、1 区县、2 城市、3 区域",
                    },
                    "report_time_type": {
                        "type": "integer",
                        "enum": [4, 5, 6, 7, 8],
                        "description": "报表时间类型：4 月报、5 季度报、6 半年报、7 年报、8 任意时间段",
                    },
                    "ns_type": {
                        "type": "integer",
                        "enum": [1, 2],
                        "description": "国标类型：1 国标一、2 国标二，默认 2",
                    },
                    "region_area": {
                        "type": "object",
                        "description": "区域编码映射 {区域编码: '城市编码1,城市编码2'}，area_type=3 时必传",
                    },
                    "region_area_name": {
                        "type": "object",
                        "description": "区域名称映射 {区域编码: 区域名称}，area_type=3 时必传",
                    },
                    "need_keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "需要的字段名列表（区分大小写，如 PM2_5_Curr、FineDays），为空返回全部字段",
                    },
                },
                "required": [
                    "start_time",
                    "end_time",
                    "input_table_name",
                    "year",
                    "area_type",
                    "report_time_type",
                ],
            },
        }

        super().__init__(
            name="airdata_calc_report_summary",
            description="Calc air quality report summary with YoY comparison via AirDataPlatform",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True,
        )

    async def execute(
        self,
        context: Optional["ExecutionContext"] = None,
        start_time: str = "",
        end_time: str = "",
        input_table_name: str = "",
        year: int = 0,
        area_type: int = 0,
        report_time_type: int = 8,
        ns_type: int = 2,
        region_area: dict[str, Any] | None = None,
        region_area_name: dict[str, Any] | None = None,
        need_keys: list[str] | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        logger.info(
            "airdata_calc_report_summary_start",
            start_time=start_time,
            end_time=end_time,
            input_table_name=input_table_name,
            year=year,
            area_type=area_type,
            report_time_type=report_time_type,
        )
        try:
            client = get_airdata_platform_client()
            data = client.calc_report_summary(
                start_time=start_time,
                end_time=end_time,
                input_table_name=input_table_name,
                year=year,
                area_type=int(area_type),
                report_time_type=int(report_time_type),
                ns_type=int(ns_type) if ns_type else 2,
                region_area=region_area,
                region_area_name=region_area_name,
                need_keys=need_keys,
            )
            metadata = {
                "tool_name": self.name,
                "time_range": f"{start_time} ~ {end_time}",
                "input_table_name": input_table_name,
                "year": year,
                "area_type": area_type,
                "report_time_type": report_time_type,
                "ns_type": ns_type,
                "compare_year": year,
            }

            if not data:
                return {
                    "status": "empty",
                    "success": True,
                    "data": [],
                    "metadata": {**metadata, "message": "统计成功但无数据返回"},
                    "summary": "报表统计完成但指定范围无数据",
                }

            file_path = None
            if context is not None and len(data) > PREVIEW_ROW_LIMIT:
                file_path = context.save_data(
                    data=data,
                    schema="airdata_calc_report_summary",
                    metadata={
                        "source": "airdata_platform",
                        "time_range": f"{start_time} ~ {end_time}",
                        "input_table_name": input_table_name,
                        "year": year,
                        "area_type": area_type,
                    },
                )

            return _describe_result(
                data,
                len(data),
                False,
                "airdata_calc_report_summary",
                metadata,
                "报表统计成功，",
                file_path=file_path,
            )
        except AirDataPlatformError as exc:
            return self._failed(str(exc))
        except Exception as exc:
            logger.error(
                "airdata_calc_report_summary_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return self._failed(str(exc))

    def _failed(self, message: str) -> dict[str, Any]:
        return {
            "status": "failed",
            "success": False,
            "error": message,
            "data": None,
            "metadata": {
                "tool_name": self.name,
            },
            "summary": f"报表统计失败: {message}",
        }
