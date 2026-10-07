"""
大气环境监测数据接口中台查询工具（许昌专属）

- query_airdata_platform：区域/站点基础表 + 城市/站点/乡镇日小时空气质量数据查询
- airdata_calc_report_summary：按时间范围统计站点/区县/城市/区域报表并输出同比对比
  默认只回传当期值常用字段投影（PM2.5 为 PM2_5_Curr_ForNow_R1，银行家算法保留一位小数），
  同比字段需 include_compare=true；完整数据（含 PM2_5_Curr/PM2_5_Curr_ForNow 双口径原始值）落盘 file_path
"""
import asyncio
import json
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, Optional

import structlog

from app.agent.context.data_shape import shape_from_records

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

# 报表同比四件套后缀（对比期/变幅/变幅类型），默认从回传结果中剥离，include_compare=true 时保留
REPORT_COMPARE_SUFFIXES = ("_Compare", "_Increase", "_ChangeType")

# 报表常用字段投影白名单（PascalCase，与中台年报模板一致；顺序即预览输出顺序）
REPORT_IDENTIFIER_COLUMNS = (
    "TimePoint",
    "CityName",
    "CityCode",
    "DistrictName",
    "DistrictCode",
    "StationName",
    "StationCode",
    "UniqueCode",
)
REPORT_CONCENTRATION_COLUMNS = (
    "SO2_Curr",
    "NO2_Curr",
    "PM10_Curr",
    "CO_Curr",
    "O3_8h_Curr",
    "PM2_5_Curr",
    "SO2_Curr_ForNow",
    "NO2_Curr_ForNow",
    "PM10_Curr_ForNow",
    "CO_Curr_ForNow",
    "O3_8h_Curr_ForNow",
    "PM2_5_Curr_ForNow",
)
REPORT_STAT_COLUMNS = (
    "SO2_P_Curr",
    "NO2_P_Curr",
    "PM10_P_Curr",
    "CO_P_Curr",
    "O3_8h_P_Curr",
    "PM2_5_P_Curr",
    "SO2_SingleIndex",
    "NO2_SingleIndex",
    "PM10_SingleIndex",
    "CO_SingleIndex",
    "O3_8h_SingleIndex",
    "PM2_5_SingleIndex",
    "CompositeIndex",
    "DayCounts_Curr",
    "EffectDays",
    "EffDay",
    "FineDays",
    "StandardDay",
    "StandardRate",
    "OverDays",
    "Lvl1",
    "Lvl2",
    "Lvl3",
    "Lvl4",
    "Lvl5",
    "Lvl6",
)
REPORT_COMMON_COLUMNS = (
    REPORT_IDENTIFIER_COLUMNS + REPORT_CONCENTRATION_COLUMNS + REPORT_STAT_COLUMNS
)

# PM2.5 报表口径：上下文回传银行家算法（四舍六入五成双）保留一位小数的新字段，
# PM2_5_Curr（取整）与 PM2_5_Curr_ForNow（全精度）原始双口径仅保留在落盘原始视图
PM2_5_REPORT_COLUMN = "PM2_5_Curr_ForNow_R1"
PM2_5_RAW_REPORT_COLUMNS = ("PM2_5_Curr", "PM2_5_Curr_ForNow")

# 同比对比期跨 2026-01-01 规划期分段时（当期 155 表、对比期 145 表），平台单表取不到对比期，
# 工具自动改查 145 表并对齐行、回填 *_Compare，浓度列再计算 *_Increase/_ChangeType
CROSS_CALIBER_TABLE_SUFFIX_155 = "155"
CROSS_CALIBER_TABLE_SUFFIX_145 = "145"
CROSS_CALIBER_BOUNDARY_YEAR = 2026
REPORT_MATCH_ID_COLUMNS = ("UniqueCode", "StationCode", "DistrictCode", "CityCode")


# 报表预览的字符量上限，超出后减少预览行数并把完整数据落盘
REPORT_PREVIEW_MAX_CHARS = 6000

_API_CODE_HINTS = {
    "region": "区域表（行政区划，含经纬度与气象编码）",
    "station": "站点表（站点名称/编码/坐标/地址）",
    "v_c_d_sb_145": "城市日数据-替代145口径（十四五分段 2021-07-01~2025-12-31，新国标）",
    "v_c_d_sb_155": "城市日数据-替代155口径（十五五分段 2026-01-01 至今，新国标，默认）",
    "v_c_d_src_155": "城市日数据-原始155口径（非新国标替代口径，仅近半月少量，不作默认）",
    "v_s_d_app_145": "站点日数据-审核145口径",
    "v_s_d_src_145": "站点日数据-原始145口径",
    "v_t_d_app": "乡镇日数据-审核",
    "v_t_d_src": "乡镇日数据-原始",
    "v_t_h_app": "乡镇小时数据-审核",
    "v_t_h_src": "乡镇小时数据-原始",
}

# 许昌空气质量查询的三条数据通道同属中大国发平台，中台工具承担中台独有口径
DATA_SOURCE_NOTE = (
    "【数据源归属与优先级】许昌空气质量数据实际有三个查询通道，且同属中大国发平台数据源，仅时间粒度与覆盖时段不同："
    "①中大平台审核后数据（站点5分钟/站点小时/城市小时，近期高时效，审核后口径）；"
    "②长历史采集库（城市小时/城市日/站点日等历史归档，时间跨度最长）；"
    "③大气监测接口中台（本工具，区域/站点基础表、城市/站点/乡镇日时数据、同比报表）。"
    "①②为第一优先级：用户问许昌空气质量数据时，优先走中大平台审核后数据与长历史采集库；"
    "本工具用于中台独有口径（区域/站点基础表、乡镇日/小时数据、月度与年度报表统计），"
    "以及①②未落库的时间段；不要用本工具重复查询①②已覆盖且口径一致的数据。"
)

# 官方口径唯一，不做跨源交叉比对
OFFICIAL_CALIBER_NOTE = (
    "【官方口径】中大国发平台是许昌空气质量数据的官方口径，也是唯一权威来源。"
    "本工具返回的中台数据即官方口径，不要再为“验证”而引入其他数据源（外省平台、公开榜单、模式预报、"
    "第三方接口、模型反演等）做交叉比对，也不要因外部数值不同就改写官方值或声明官方数据存疑。"
    "只有用户明确要求对比不同来源时才做对比，并在回答中区分官方口径与参考来源。"
)

# 禁止用时/日数据自行汇总月度和年度统计
AGGREGATION_RULE_NOTE = (
    "【统计口径硬规则】禁止用小时数据、日数据自行汇总或计算月度、季度、半年、年度统计值"
    "（包括均值、极值、有效天数、达标率、重污染天数、排名、同比等任何月度及以上指标）。"
    "①中大平台审核后数据与②长历史采集库都是明细通道，不含月度及以上统计，"
    "不能用来满足月度及以上统计需求，也不能用其明细自行汇总代替报表。"
    "月度及以上统计一律直接查询平台已生成的统计报表接口 airdata_calc_report_summary，"
    "用 report_time_type 指定粒度：4 月报、5 季度报、6 半年报、7 年报、8 任意时间段。"
    "本接口只用于取明细/基础数据与中台独有口径；用户问“这个月/今年空气质量怎么样”、"
    "月均浓度、年度排名、月度同比等时必须改用 airdata_calc_report_summary，不得自行汇总代替报表。"
)

# 城市日数据按 timepoint 互斥分区，新国标默认口径
CITY_NEW_STANDARD_NOTE = (
    "【城市日数据默认国标2（新国标）】城市日数据默认使用替代（新国标）口径，按数据时间分段选接口："
    "2026-01-01 及以后用 v_c_d_sb_155，2021-07-01~2025-12-31 用 v_c_d_sb_145；"
    "两个接口按 timepoint 互斥分区，跨 2026-01-01 的时间范围必须分两次调用后合并，不得只查一个；"
    "用户未指定国标时不要用 v_c_d_src_155（原始口径，仅近半月十余条，覆盖极不全），"
    "用户明确要求原始口径时才使用。"
)

# 回答中必须回传数据源与口径，便于溯源
DATA_SOURCE_DISCLOSURE_NOTE = (
    "【数据源声明】回答中必须说明本次查询实际使用的数据源与口径，"
    "写明数据源名称（大气监测接口中台 / 中大平台审核后数据 / 长历史采集库）、api_code 或表名、"
    "国标口径（新国标/国标二 还是原始或旧口径）、时间范围与筛选条件；"
    "混用多通道或跨分段查询时逐段说明。缺少该说明视为未完成查询。"
)


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


def _round_bankers_1(value: Any) -> str | None:
    """按银行家算法（四舍六入五成双）保留一位小数，无效值返回 None"""
    if value is None or value == "" or value == "—":
        return None
    try:
        return str(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_EVEN))
    except (InvalidOperation, ValueError):
        return None


def _strip_report_compare_fields(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """剥离同比字段（*_Compare/_Increase/_ChangeType），仅保留当期值与标识列"""
    return [
        {k: v for k, v in row.items() if not k.endswith(REPORT_COMPARE_SUFFIXES)}
        for row in rows
    ]


def _project_report_row(row: dict[str, Any], include_compare: bool) -> dict[str, Any]:
    """投影到常用字段；include_compare 时附带常用字段的同比对比（浓度列另带变幅与变幅类型）

    PM2_5_Curr/PM2_5_Curr_ForNow 原始双口径不进上下文，由 PM2_5_Curr_ForNow_R1 代替，
    原始值与其同比字段仅保留在落盘原始视图。
    """
    projected: dict[str, Any] = {}
    for col in REPORT_COMMON_COLUMNS:
        if col == "PM2_5_Curr_ForNow":
            rounded = _round_bankers_1(row.get(col))
            if rounded is not None:
                projected[PM2_5_REPORT_COLUMN] = rounded
                if include_compare:
                    rounded_compare = _round_bankers_1(row.get(f"{col}_Compare"))
                    if rounded_compare is not None:
                        projected[f"{PM2_5_REPORT_COLUMN}_Compare"] = rounded_compare
                        increase = _format_rate_increase(rounded, rounded_compare)
                        if increase is not None:
                            projected[f"{PM2_5_REPORT_COLUMN}_Increase"] = increase
                            projected[f"{PM2_5_REPORT_COLUMN}_ChangeType"] = "Rate"
            continue
        if col in PM2_5_RAW_REPORT_COLUMNS:
            continue
        if col in row:
            projected[col] = row[col]
        if not include_compare:
            continue
        compare_key = f"{col}_Compare"
        if compare_key in row:
            projected[compare_key] = row[compare_key]
        if col in REPORT_CONCENTRATION_COLUMNS:
            for suffix in ("_Increase", "_ChangeType"):
                key = f"{col}{suffix}"
                if key in row:
                    projected[key] = row[key]
    return projected


def _shift_date_year(date_str: str, year: int) -> str | None:
    """把日期字符串的年部分替换为指定年份（同比对比期 = 当期窗口平移到 year 年）"""
    text = str(date_str or "").strip()
    if len(text) >= 4 and text[:4].isdigit():
        return f"{year}{text[4:]}"
    return None


def _cross_caliber_table(input_table_name: str) -> str | None:
    """155 口径表返回对应的 145 口径表名；非 155 口径返回 None"""
    name = str(input_table_name or "").strip()
    prefix, sep, table = name.rpartition(".")
    if not table.endswith(CROSS_CALIBER_TABLE_SUFFIX_155):
        return None
    swapped = f"{table[: -len(CROSS_CALIBER_TABLE_SUFFIX_155)]}{CROSS_CALIBER_TABLE_SUFFIX_145}"
    return f"{prefix}{sep}{swapped}" if sep else swapped


def _has_compare_values(rows: list[dict[str, Any]]) -> bool:
    """任一行存在非空（非 —）的对比期值 *_Compare 即视为平台已给出同比"""
    return any(
        value not in (None, "", "—")
        for row in rows
        for key, value in row.items()
        if key.endswith("_Compare")
    )


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "" or value == "—":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _format_rate_increase(current: Any, compare: Any) -> str | None:
    """按平台比分口径计算变幅（%），保留一位小数；对比值为 0 或非数值时返回 None"""
    curr = _to_decimal(current)
    base = _to_decimal(compare)
    if curr is None or base is None or base == 0:
        return None
    rounded = ((curr - base) / base * Decimal("100")).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_EVEN
    )
    return "0" if rounded == 0 else str(rounded)


def _merge_cross_caliber_compare(
    rows: list[dict[str, Any]],
    compare_rows: list[dict[str, Any]],
    requested_keys: set[str] | None = None,
) -> int:
    """把对比期行的当期值回填到当期行的 *_Compare，并计算浓度列变幅；返回合并行数"""
    if not rows or not compare_rows:
        return 0
    match_keys = [k for k in REPORT_MATCH_ID_COLUMNS if all(k in row for row in rows)]
    compare_index: dict[tuple, dict[str, Any]] = {}
    if match_keys:
        for compare_row in compare_rows:
            compare_index[tuple(compare_row.get(k) for k in match_keys)] = compare_row

    merged = 0
    for idx, row in enumerate(rows):
        if match_keys:
            compare_row = compare_index.get(tuple(row.get(k) for k in match_keys))
        elif idx < len(compare_rows):
            compare_row = compare_rows[idx]
        else:
            compare_row = None
        if not compare_row:
            continue
        touched = False
        for key in list(row.keys()):
            if not key.endswith("_Compare") or row[key] not in (None, "", "—"):
                continue
            if requested_keys is not None and key not in requested_keys:
                continue
            value = compare_row.get(key[: -len("_Compare")])
            if value in (None, "", "—"):
                continue
            row[key] = value
            touched = True
        for base_col in REPORT_CONCENTRATION_COLUMNS:
            if base_col not in row:
                continue
            increase_key = f"{base_col}_Increase"
            if requested_keys is not None and increase_key not in requested_keys:
                continue
            increase = _format_rate_increase(row.get(base_col), row.get(f"{base_col}_Compare"))
            if increase is None:
                continue
            row[increase_key] = increase
            row[f"{base_col}_ChangeType"] = "Rate"
            touched = True
        if touched:
            merged += 1
    return merged


def _limit_report_preview(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按行数与字符量限制预览规模，超出时从尾部截行"""
    preview = rows[:PREVIEW_ROW_LIMIT]
    while preview and len(json.dumps(preview, ensure_ascii=False)) > REPORT_PREVIEW_MAX_CHARS:
        preview.pop()
    return preview


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
                f"{DATA_SOURCE_NOTE}"
                f"{OFFICIAL_CALIBER_NOTE}"
                f"{CITY_NEW_STANDARD_NOTE}"
                f"{AGGREGATION_RULE_NOTE}"
                f"{DATA_SOURCE_DISCLOSURE_NOTE}"
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
            result = await asyncio.to_thread(
                client.query_all,
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
                data_shape = shape_from_records(rows, len(rows), source="inferred")
                file_path = context.save_data(
                    data=rows,
                    schema="airdata_platform_query",
                    metadata={
                        "source": "airdata_platform",
                        "api_code": api_code,
                        "filters": filters,
                        "total": result["total"],
                        "data_shape": data_shape,
                    },
                )
                logger.info(
                    "query_airdata_platform_data_saved",
                    file_path=file_path,
                    record_count=len(rows),
                )

            response = _describe_result(
                rows,
                result["total"],
                result["truncated"],
                "airdata_platform_query",
                metadata,
                f"接口 {api_code} 查询成功，",
                file_path=file_path,
            )
            if file_path:
                response["data_shape"] = data_shape
            return response
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
                "按时间范围对站点/区县/城市/区域做空气质量报表统计，并与 year 指定年份同期做同比对比"
                "（大气环境监测数据接口中台，许昌项目）。"
                "返回行为扁平字典，键名为 PascalCase，统计值均为字符串，无效值统一为 —。"
                "默认只返回当期值，且仅投影常用字段到上下文：标识列（站点/城市/区县名称编码、TimePoint）+ "
                "六项污染物（SO2/NO2/PM10/CO/O3_8h/PM2_5）浓度，其余五项为 *_Curr 取整口径、*_Curr_ForNow 全精度口径；"
                "PM2.5 在上下文中只回传 PM2_5_Curr_ForNow_R1（由全精度值按四舍六入五成双/银行家算法保留一位小数，"
                "回答中 PM2.5 浓度一律用该字段），PM2_5_Curr 与 PM2_5_Curr_ForNow 原始双口径及其同比字段只保存在落盘原始视图，不进上下文；"
                "百分位（*_P_Curr）、单项指数（*_SingleIndex）、综合指数 CompositeIndex、"
                "天数统计（FineDays/StandardDay/StandardRate/OverDays/DayCounts_Curr、Lvl1~Lvl6）。"
                "同比对比字段（*_Compare 对比期值、*_Increase 变幅、*_ChangeType 变幅类型）仅在 include_compare=true 时返回，"
                "默认不传时同比字段全部剔除、不进上下文。"
                "同比对比期跨 2026-01-01 规划期分段时（当期窗口在 155 表、year 落在 2025 及以前），"
                "平台单表取不到对比期，工具会自动改查对应的 145 表、按站点/区县/城市对齐后计算同比，"
                "并在 metadata.compare_source=auto_cross_caliber_145 与 summary 中说明，无需再分两次调用。"
                "完整报表模板有 300+ 统计项（含极值、超标天数、首要污染物、沙尘等模块）；"
                "需要白名单之外的字段时，用 need_keys 精确指定（区分大小写，如 PM2_5_Curr_ForNow_R1、PM25ExcessDays、"
                "PM2_5_Curr_ForNow_Compare），传入后跳过默认过滤与投影、原样返回；"
                "need_keys 指定 PM2_5_Curr_ForNow_R1 时由平台全精度值计算后返回。"
                "因字段投影省略或行数/字符量超限，完整当期数据（含字段清单）自动落盘并在 metadata 返回 file_path，"
                "可结合 file_path 原始视图与 need_keys 二次查询。"
                f"{table_hint}。"
                "统计窗口和 reportTimeType 决定报表粒度：4 月报、5 季度报、6 半年报、7 年报、8 任意时间段。"
                f"{DATA_SOURCE_NOTE}"
                f"{OFFICIAL_CALIBER_NOTE}"
                "【统计口径硬规则】本接口是许昌月度及以上统计的唯一来源："
                "禁止用小时数据、日数据自行汇总或计算月度、季度、半年、年度统计值"
                "（包括均值、极值、有效天数、达标率、重污染天数、排名、同比等任何月度及以上指标），"
                "也不得用自行汇总的结果代替或修正平台报表；报表数值以本接口返回为准。"
                "①中大平台审核后数据与②长历史采集库都是明细通道，不含月度及以上统计，"
                "月度及以上统计只能来自本接口，不要用①②的明细自行汇总。"
                "用户问月均浓度、年度排名、月度同比、达标天数等月度及以上指标时，必须调用本接口，"
                "并按 report_time_type 指定粒度（4 月报、5 季度报、6 半年报、7 年报、8 任意时间段）。"
                "本接口只覆盖平台已生成的统计项；报表未包含的字段用 need_keys 精确指定，"
                "仍取不到时才说明平台报表无该口径，不得改用明细数据自行计算。"
                "【国标口径】ns_type 默认 2（国标二/新国标），用户未指定国标时不要传 1；"
                "input_table_name 必须与统计窗口的规划期分段匹配（pantype145 对应 2021-2025，pantype155 对应 2026 起），"
                "跨 2026-01-01 的窗口需分两段统计后合并。"
                f"{DATA_SOURCE_DISCLOSURE_NOTE}"
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
                        "description": (
                            "报表时间类型：4 月报、5 季度报、6 半年报、7 年报、8 任意时间段；"
                            "问月度及以上统计时必传，月报用 4、年报用 7"
                        ),
                    },
                    "include_compare": {
                        "type": "boolean",
                        "description": (
                            "是否返回同比字段：*_Compare 对比期值、*_Increase 变幅、*_ChangeType 变幅类型"
                            "（浓度列含全套，其余常用列仅 *_Compare）；默认 false 只返回当期值"
                        ),
                    },
                    "ns_type": {
                        "type": "integer",
                        "enum": [1, 2],
                        "description": "国标类型：1 国标一（旧国标）、2 国标二（新国标），默认 2，不要改为 1",
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
                        "description": (
                            "精确指定返回字段（区分大小写），为空返回常用当期字段投影；"
                            "传入后跳过默认的同比剥离与字段投影，原样返回平台结果"
                        ),
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
            version="1.1.0",
            requires_context=True,
        )

    def _maybe_fill_cross_caliber_compare(
        self,
        *,
        client: Any,
        data: list[dict[str, Any]],
        include_compare: bool,
        input_table_name: str,
        start_time: str,
        end_time: str,
        year: int,
        area_type: int,
        report_time_type: int,
        ns_type: int,
        region_area: dict[str, Any] | None,
        region_area_name: dict[str, Any] | None,
        need_keys: list[str] | None,
    ) -> dict[str, Any] | None:
        """同比对比期落在 145 口径时自动补查并回填同比；不适用返回 None"""
        if not include_compare or not data:
            return None
        compare_table = _cross_caliber_table(input_table_name)
        compare_start = _shift_date_year(start_time, year)
        compare_end = _shift_date_year(end_time, year)
        if not compare_table or not compare_start or not compare_end:
            return None
        try:
            compare_year = int(year)
        except (TypeError, ValueError):
            return None
        if compare_year >= CROSS_CALIBER_BOUNDARY_YEAR or _has_compare_values(data):
            return None

        compare_rows = client.calc_report_summary(
            start_time=compare_start,
            end_time=compare_end,
            input_table_name=compare_table,
            year=compare_year,
            area_type=int(area_type),
            report_time_type=int(report_time_type),
            ns_type=int(ns_type) if ns_type else 2,
            region_area=region_area,
            region_area_name=region_area_name,
        )
        if not compare_rows:
            return None

        requested = set(need_keys) if need_keys else None
        matched = _merge_cross_caliber_compare(data, compare_rows, requested)
        if not matched:
            return None

        logger.info(
            "airdata_calc_report_summary_cross_caliber_compare",
            compare_table_name=compare_table,
            compare_time_range=f"{compare_start} ~ {compare_end}",
            matched_rows=matched,
        )
        note = (
            f"当期统计窗口属 155 口径，同比对比期（{compare_start} ~ {compare_end}）落在 145 口径，"
            f"已自动改查 145 表 {compare_table} 并对齐站点/区县/城市后计算同比"
        )
        return {
            "metadata": {
                "compare_source": "auto_cross_caliber_145",
                "compare_table_name": compare_table,
                "compare_time_range": f"{compare_start} ~ {compare_end}",
                "compare_note": note,
            },
            "summary": note,
        }

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
        include_compare: bool = False,
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
            include_compare=include_compare,
            need_keys=need_keys,
        )
        try:
            client = get_airdata_platform_client()
            data = await asyncio.to_thread(
                client.calc_report_summary,
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

            compare_requested = bool(include_compare) or bool(
                need_keys and any(str(k).endswith(REPORT_COMPARE_SUFFIXES) for k in need_keys)
            )
            cross_caliber_info = await asyncio.to_thread(
                self._maybe_fill_cross_caliber_compare,
                client=client,
                data=data,
                include_compare=compare_requested,
                input_table_name=input_table_name,
                start_time=start_time,
                end_time=end_time,
                year=year,
                area_type=area_type,
                report_time_type=report_time_type,
                ns_type=ns_type,
                region_area=region_area,
                region_area_name=region_area_name,
                need_keys=need_keys,
            )
            cross_caliber_metadata = cross_caliber_info["metadata"] if cross_caliber_info else {}
            if cross_caliber_metadata:
                metadata.update(cross_caliber_metadata)

            # need_keys 显式指定时完全透传，不做剥离与投影；显式请求 PM2_5_Curr_ForNow_R1 时按原始全精度值计算
            explicit_keys = bool(need_keys)
            if explicit_keys and PM2_5_REPORT_COLUMN in need_keys:
                for row in data:
                    rounded = _round_bankers_1(row.get("PM2_5_Curr_ForNow"))
                    if rounded is not None:
                        row[PM2_5_REPORT_COLUMN] = rounded
            if explicit_keys or include_compare:
                filtered = data
            else:
                filtered = _strip_report_compare_fields(data)

            preview_rows = (
                filtered if explicit_keys else [_project_report_row(r, include_compare) for r in filtered]
            )
            total_fields = max(len(row) for row in filtered)
            preview_fields = max((len(row) for row in preview_rows), default=0)
            fields_omitted = not explicit_keys and preview_fields < total_fields
            full_count = len(filtered)

            preview_rows = _limit_report_preview(preview_rows)
            rows_truncated = full_count > len(preview_rows)

            file_path = None
            if context is not None and (rows_truncated or fields_omitted):
                data_shape = shape_from_records(filtered, full_count, source="inferred")
                file_path = context.save_data(
                    data=filtered,
                    schema="airdata_calc_report_summary",
                    metadata={
                        "source": "airdata_platform",
                        "time_range": f"{start_time} ~ {end_time}",
                        "input_table_name": input_table_name,
                        "year": year,
                        "area_type": area_type,
                        "report_time_type": report_time_type,
                        "include_compare": bool(include_compare) and not explicit_keys,
                        "columns": sorted(filtered[0].keys()) if filtered else [],
                        "record_count": full_count,
                        **cross_caliber_metadata,
                        "data_shape": data_shape,
                    },
                )

            metadata.update(
                {
                    "include_compare": bool(include_compare) and not explicit_keys,
                    "need_keys_passthrough": explicit_keys,
                    "total_records": full_count,
                    "returned_records": len(preview_rows),
                    "total_fields": total_fields,
                    "preview_fields": preview_fields,
                }
            )
            if rows_truncated:
                metadata["truncated"] = True
            if file_path:
                metadata["file_path"] = file_path
                metadata["data_shape"] = data_shape

            summary_parts = [f"报表统计成功，共 {full_count} 条"]
            if cross_caliber_info:
                summary_parts.append(cross_caliber_info["summary"])
            if fields_omitted:
                summary_parts.append(
                    f"上下文仅展示 {preview_fields} 个常用当期字段，其余 {total_fields - preview_fields} 个统计项见落盘数据"
                )
            if explicit_keys:
                summary_parts.append(f"按 need_keys 原样返回 {preview_fields} 个字段")
            if rows_truncated:
                summary_parts.append(f"预览截断为 {len(preview_rows)} 条")
            if file_path:
                summary_parts.append(f"完整数据已保存为 {file_path}")

            return {
                "status": "success",
                "success": True,
                "data": preview_rows,
                "metadata": metadata,
                "summary": "，".join(summary_parts),
                **({"file_path": file_path} if file_path else {}),
                **({"data_shape": data_shape} if file_path else {}),
            }
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
