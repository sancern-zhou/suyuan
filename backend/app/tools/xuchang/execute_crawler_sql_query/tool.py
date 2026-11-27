"""Read-only MySQL queries against the DataCrawler long-history monitoring database."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
import re
from typing import Any, Dict, Optional, TYPE_CHECKING

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.agent.context.data_shape import shape_summary_suffix
from app.utils.sql_validator import SQLValidator

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext


logger = structlog.get_logger()


# DataCrawler（MySQL 8，采集库）：许昌本地长历史表 + 河南实时发布采集表（Ssfb*）。
# 注意：省平台"排名"无物理表——SsfbCityHourRank/SsfbCountyHourRank/SsfbCountyDayRank/
# SsfbSiteHourRank/SsfbSiteDayRank 是 cube 语义层对 Ssfb*Hour/Day 基表的窗口函数现算；
# SQL 兜底可直接对基表自写 RANK() OVER（MySQL 8），口径为升序并列、1=最优
#（与 Rank168CityMonthly 的倒序 1=最重 相反，勿混淆）。
CRAWLER_SQL_TABLES = [
    "StationHour",
    "CityHour",
    "StationDay",
    "CityDay",
    "CitySandDay",
    "CityYearPm25Avg",
    "Station",
    "SsfbCityHour",
    "SsfbCityDay",
    "SsfbSiteHour",
    "SsfbSiteDay",
    "SsfbCountyHour",
    "SsfbCountyDay",
    "SsfbCityRanking",
    "CountyMonthReport",
    "ProvinceMonthReport",
    "XuchangCityYearTarget",
    "XuchangCountyYearTarget",
    "HenanCityYearTarget",
    "Rank168CityMonthly",
    "TownStationData",
    "TownStationFiveMinute",
    "OfficeStationFiveMinute",
    "ShengkongStationHour",
    "HenanPlatformAqYearStat",
    "HenanPlatformAqMonthStat",
    "HenanPlatformAqAccumulateStat",
]

# 各表白名单对应的数据时间范围（实测），供 Agent 直接判断可查窗口、避免空查。
TABLE_TIME_RANGES: dict[str, str] = {
    "StationHour": "2016-01~2026-11-15，许昌 6 国控站逐小时（政府侧采集镜像，2026-11-15 起停更，勿用于最新值；"
                   "最新小时与 5 分钟实时数据走 execute_sql_query 的 dat_zhongda_station_hour/dat_zhongda_station_minute）",
    "CityHour": "2020-07 起，许昌市逐小时",
    "StationDay": "2018-09 起，许昌站点逐日",
    "CityDay": "2018-09 起，许昌市逐日",
    "CitySandDay": "2019-04 起，许昌市沙尘日清单（仅城市+日期，无数值列，累计约 200 天）",
    "CityYearPm25Avg": "2014-2025，许昌市 PM2.5 年均值（每年 1 行）",
    "Station": "许昌站点目录（覆盖有限，站名可能为空）",
    "SsfbCityHour": "2026-10-09 起，河南 18 城市组逐小时（含济源）",
    "SsfbCityDay": "2026-10-03 起，河南 18 城市组逐日（含济源）",
    "SsfbSiteHour": "2026-10-09 起，许昌县级站逐小时",
    "SsfbSiteDay": "2026-10-08 起，许昌县级站逐日",
    "SsfbCountyHour": "2026-10-10 起，河南区县逐小时（189 区县含济源+功能区，"
                       "与省平台'区县'页签同源同口径；County/City 名称直接在行内；"
                       "County 使用短名如示范区/开发区/东城区；区县过程/对比优先 "
                       "xuchang_cube_metrics 的 SsfbCountyHour，避免误读基表重复行；"
                       "区县排名无物理表，可用窗口函数对基表现算）",
    "SsfbCountyDay": "2026-10-09 起，河南区县逐日（次日白天陆续发布，个别区县偏晚靠回看补齐）",
    "SsfbCityRanking": "2026-10-09 起（每日 06:10 对官方发布日值排序，仅 daily）",
    "CountyMonthReport": "2020-01 ~ 2026-09，许昌 10 县市区官方月报统计（剔除沙尘；"
                         "Scope=month 当月/cum 1-N月累计；重污染天 2023 起才有；"
                         "2020 年取自 2021 年月报同期列，SourceCol=prior）",
    "ProvinceMonthReport": "2025-12、2026-01~09 共 10 期河南省环境空气质量月报附表（官方口径："
                           "Level=city 19市(区)/district 88市辖区/county 101县市/province 全省；"
                           "Scope=month 当月/cum 1-N月累计；同比列 Xxx_YoY 为变化率）",
    "XuchangCityYearTarget": "2015-2026，许昌市年度目标 vs 实际（国家网考核定版；目标值唯一来源；"
                             "Year 过滤；无自动采集，随官方数据人工回补）",
    "XuchangCountyYearTarget": "2020-2025，许昌 10 县市区年度目标 vs 实际（官方考核剔沙尘定版；"
                               "2023 年重污染天与 CountyMonthReport 月报差 3~4 天系沙尘口径）",
    "HenanCityYearTarget": "2021-2025，河南 18 地市年度目标完成情况（省考核；优良天/重污染天"
                           " 2021/2022/2024 为天数、2023/2025 为比例%；2025 行未定稿）",
    "Rank168CityMonthly": "2026-01起，生态环境部 168 重点城市排名逐月+累计（01-07人工回补，"
                          "08起自动采集；PeriodType=month/cum；排名为倒序名次（*RankDesc）："
                          "1=污染最重，表述只按'倒序排名第N位（污染第N重）'口径，禁止换算"
                          "'第N好'、禁止得出'空气较好/最优'结论；仅用于全国排名与横向对比，"
                          "浓度绝对值以本地口径为准）",
    "TownStationData": "2024-01 起，许昌 76 乡镇站逐小时/逐日（IsHour=1 小时、0 日；"
                       "IsAudit=1 审核/0 原始，同站同刻各一行，聚合前必须先过滤口径；"
                       "-99 为无效值；日值约 2024-08 起；禹州 22 站 2026-11-19 起通讯中断；"
                       "数据现由许昌市空气质量管控平台替代抓取回写）；小时覆盖碎片化"
                       "（旧云平台断供史：部分月份仅约 1/4 天数，2026-05~08 整段缺失，"
                       "2026-09 起连续）——跨月历史对比勿假设连续覆盖，0 行多为真缺数",
    "TownStationFiveMinute": "2026-10-27 起，许昌乡镇站逐 5 分钟（滚动保留 30 天；"
                             "原始未审核口径，平台 5 分钟不发布 AQI 恒空；-99 为无效值）",
    "OfficeStationFiveMinute": "2026-11-23 起，许昌 31 办事处站5分钟与官方小时（仅 PM2.5/PM10 两因子；"
                                 "IsHour=0 五分钟、1 小时，必须过滤单一粒度与 IsAudit=0；"
                                 "滚动保留 30 天；AQI 需按 HJ633 推算并注明）",
    "ShengkongStationHour": "2026-11-23 起，许昌 8 省控站逐小时六参数（平台省控仅小时粒度；"
                              "2 个县'政府'站自 2026-04 起离线；滚动保留 30 天；AQI 需按 HJ633 推算并注明）",
    "HenanPlatformAqYearStat": "2020-2025，许昌市及9县市区年度统计（河南省城市空气质量大数据综合应用系统，"
                               "每日04:00同步；固定data_type='SK'、is_deduct=1，必须过滤单一standard；"
                               "非考核定版，年度考核仍以Xuchang*YearTarget为准）",
    "HenanPlatformAqMonthStat": "2020-01起，许昌市及9县市区自然月统计（省城市空气质量大数据综合应用系统本地副本；"
                                "固定data_type='SK'、is_deduct=1，必须过滤单一standard；补充官方月报缺期，非考核定版）",
    "HenanPlatformAqAccumulateStat": "许昌市及9县市区MTD/YTD累计（省城市空气质量大数据综合应用系统本地副本；"
                                     "固定data_type='SK'、is_deduct=1，必须过滤单一standard及period_type='mtd'/'ytd'；"
                                     "period_end为累计截止日，保留历史快照；非考核定版）",
}

MAX_LIMIT = 5000
DEFAULT_LIMIT = 50

# 结果级口径标注：查询/查结构结果命中下列列名时，在 summary 末尾追加固定方向说明。
# 背景：Rank168CityMonthly 排名列带 Desc 后缀（倒序=按浓度从高到低，1=最差），
# 再在结果层强制注入方向说明，双保险防模型/用户误读为"第N好"。
COLUMN_CALIBER_NOTES: Dict[str, str] = {
    "compositeindexrankdesc": "倒序名次：1=污染最重（浓度最高），数值越大污染越轻。"
                              "表述规范：只说'倒序排名第N位（污染第N重）'，禁止换算为"
                              "'第N好/由好到差第N名'，禁止得出'空气较好/表现最优'类结论",
    "pm25rankdesc": "倒序名次：1=污染最重（浓度最高），数值越大污染越轻。"
                    "表述规范：只说'倒序排名第N位（污染第N重）'，禁止换算为"
                    "'第N好/由好到差第N名'，禁止得出'空气较好/表现最优'类结论",
}


def _append_caliber_notes(summary: str, columns: Any) -> str:
    names = {str(column).strip().lower() for column in (columns or [])}
    notes: list[str] = []
    for note in dict.fromkeys(COLUMN_CALIBER_NOTES.get(name) for name in sorted(names)):
        if note:
            notes.append(note)
    if not notes:
        return summary
    return f"{summary} | 口径标注：{'；'.join(notes)}"

_engine = None


def _get_engine():
    """Lazily create the shared async engine for the crawler MySQL database."""
    global _engine
    if _engine is None:
        from config.settings import settings

        # aiomysql 方言与 pool_pre_ping 不兼容（ping 缺 reconnect 参数），
        # 用较短的 pool_recycle 保证连接新鲜度。
        _engine = create_async_engine(
            settings.crawler_mysql_url,
            echo=False,
            pool_recycle=240,
            pool_timeout=30,
        )
    return _engine


class ExecuteCrawlerSQLQueryTool(LLMTool):
    """Execute read-only SQL against the DataCrawler MySQL long-history database."""

    def __init__(self) -> None:
        schema_description = (
            "大气监测采集库（MySQL）只读 SQL 查询工具：许昌本地长历史"
            "（站点/城市小时日、PM2.5 年均、沙尘日清单）+ 河南实时发布采集表"
            "（Ssfb*：18 城市组含济源小时/日/排名、许昌县级站）+ 官方月报/年度定版表。"
            "describe_table 查表结构（含数据时间范围），或 sql 执行 SELECT/CTE，二者二选一。"
            f"白名单表：{', '.join(CRAWLER_SQL_TABLES)}。只允许 SELECT（禁写/DDL/注释/多语句），"
            f"LIMIT 分页最大 {MAX_LIMIT} 条；不确定字段先 describe_table，禁查 information_schema。"
            "\n【查询优先级】常规指标、功能区区域过程/对比（示范区/开发区/东城区等"
            "用 SsfbCountyHour/Day）优先 xuchang_cube_metrics，不要对 SsfbCountyHour "
            "基表反复平均或自行去重；区县名用短名如示范区，非城乡一体化示范区；"
            "排名/最新值/县级站/乡镇站同样优先语义层；"
            "国控站日值（含昨日）优先 query_airdata_platform；国控站最近小时与 5 分钟实时数据"
            "走 execute_sql_query（dat_zhongda_station_hour/dat_zhongda_station_minute，实时在流）；"
            "本工具用于长历史、同比、跨年趋势与语义层未覆盖的明细"
            "（StationHour 镜像 2026-11-15 起停更，勿用于最新值）。"
            "\n【状态口径】用户未明确要求标况（标准状态/参比状态）时，仅查询并返回实况数据，不得并列返回两种口径；"
            "仅用户明确要求标况或实况/标况对比时才查标况并分别标注。状态口径与原始/审核、实时/定版、考核口径不得混同；"
            "数据源未说明差异原因时不得自行解释。"
            "\n【统计口径硬规则】月度/季度/年度等统计禁止从 CityDay/StationDay/Ssfb* 等明细自算："
            "许昌市及县市区当月MTD、当年截至某日YTD、完整月/年及官方报表缺期一律优先"
            "xuchang_cube_metrics 的 HenanPlatformAqMonth/Year/Accumulate（也可用本工具查同名Stat表，"
            "固定data_type='SK'、is_deduct=1、单一standard，累计另过滤period_type=mtd/ytd）；"
            "中台报表airdata_calc_report_summary不支持区县市，禁止调用或改查站点替代；"
            "河南官方月报 ProvinceMonthReport；许昌县市区已发布官方月报 CountyMonthReport；年均历史 CityYearPm25Avg；"
            "年度目标 XuchangCityYearTarget/XuchangCountyYearTarget/HenanCityYearTarget；"
            "168 城排名 Rank168CityMonthly。报表没有的口径如实说明，不得明细手算。"
            "\n【扣沙天】用 CitySandDay（仅城市+日期清单，无数值）过滤："
            "WHERE Date NOT IN (SELECT DayTime FROM CitySandDay)。"
            "\n【易错列名】StationHour 站点列=StationName；StationDay/CityDay 用 PositionName/Area。"
            "老表仅许昌单城市，Ssfb* 覆盖 18 城市，两套口径勿混算同比。"
            "\n示例：SELECT Date, Area, AQI, PM2_5 FROM CityDay "
            "WHERE Area LIKE '%许昌%' AND Date >= '2020-01-01' ORDER BY Date LIMIT 100"
        )
        function_schema = {
            "name": "execute_crawler_sql_query",
            "description": schema_description,
            "parameters": {
                "type": "object",
                "properties": {
                    "describe_table": {
                        "type": "string",
                        "enum": CRAWLER_SQL_TABLES,
                        "description": "查看白名单业务表的字段及一条样例；与 sql 二选一。",
                    },
                    "sql": {
                        "type": "string",
                        "description": "仅允许使用白名单表的 MySQL SELECT 或 WITH...SELECT 查询；与 describe_table 二选一。",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_LIMIT,
                        "default": DEFAULT_LIMIT,
                        "description": f"未在 SQL 中指定 LIMIT 时使用的返回上限；最大 {MAX_LIMIT}。",
                    },
                },
            },
        }
        super().__init__(
            name="execute_crawler_sql_query",
            description="Execute read-only MySQL queries against the DataCrawler long-history monitoring database",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True,
        )
        self.sql_validator = SQLValidator(
            max_limit=MAX_LIMIT,
            allowed_tables=CRAWLER_SQL_TABLES,
        )

    async def execute(
        self,
        context: Optional["ExecutionContext"] = None,
        describe_table: Optional[str] = None,
        sql: Optional[str] = None,
        limit: Optional[int] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        del kwargs
        if bool(describe_table) == bool(sql):
            return {
                "success": False,
                "data": None,
                "summary": "请且只能提供 describe_table 或 sql 其中一个参数。",
            }
        if describe_table is not None:
            return await self._describe_table(describe_table)
        return await self._execute_sql(sql or "", limit, context)

    async def _describe_table(self, table_name: str) -> dict[str, Any]:
        if table_name not in CRAWLER_SQL_TABLES:
            return {
                "success": False,
                "data": None,
                "summary": f"表 '{table_name}' 不在白名单中。可用表: {', '.join(CRAWLER_SQL_TABLES)}",
            }

        try:
            columns = await self._run_query(
                """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = DATABASE() AND table_name = :table_name
                ORDER BY ordinal_position
                """,
                {"table_name": table_name},
                tables=[table_name],
            )
            sample_rows = await self._run_query(
                f"SELECT * FROM {table_name} LIMIT 1", tables=[table_name]
            )
        except Exception as exc:
            logger.error("crawler_sql_describe_failed", table_name=table_name, error=str(exc))
            return {"success": False, "data": None, "summary": f"查询表结构失败: {exc}"}

        if not columns:
            return {
                "success": False,
                "data": None,
                "summary": f"当前数据库中未找到白名单表 '{table_name}'。",
            }
        return {
            "success": True,
            "data": {
                "table_name": table_name,
                "columns": columns,
                "sample_data": sample_rows[0] if sample_rows else None,
                "time_range": TABLE_TIME_RANGES.get(table_name, "未登记"),
            },
            "summary": _append_caliber_notes(
                f"表 {table_name} 共 {len(columns)} 个字段；已返回字段结构、一条样例与数据时间范围。",
                [column.get("column_name") for column in columns],
            ),
        }

    async def _execute_sql(
        self,
        sql: str,
        limit: Optional[int],
        context: Optional["ExecutionContext"],
    ) -> dict[str, Any]:
        normalized_sql = self.sql_validator.normalize_sql(sql)
        valid, error = self.sql_validator.validate(normalized_sql)
        if not valid:
            return {
                "success": False,
                "data": [],
                "summary": f"SQL 验证失败: {error}。字段不确定时请先调用 describe_table。",
            }

        effective_limit = self._resolve_limit(limit)
        safe_sql, limit_error = self._sanitize_limit(normalized_sql, effective_limit)
        if limit_error:
            return {"success": False, "data": [], "summary": limit_error}

        referenced_tables = self.sql_validator.extract_tables(normalized_sql)

        logger.info(
            "crawler_sql_query_start",
            sql_preview=normalized_sql[:200],
            limit=effective_limit,
            session_id=getattr(context, "session_id", "unknown") if context else "unknown",
        )
        try:
            rows = await self._run_query(safe_sql, tables=referenced_tables)
        except Exception as exc:
            logger.error("crawler_sql_query_failed", error=str(exc), sql_preview=normalized_sql[:200])
            summary = f"查询失败: {exc}。"
            if self._is_column_error(exc):
                hint = self._columns_hint(referenced_tables)
                if hint:
                    summary += (
                        "\n涉及表的真实字段（大小写以此为准，直接据此修正 SQL 重试，"
                        "无需再调用 describe_table）：\n" + hint
                    )
                else:
                    summary += "字段不确定时请先调用 describe_table。"
            else:
                summary += "字段不确定时请先调用 describe_table。"
            return {
                "success": False,
                "data": [],
                "summary": summary,
            }

        result = self._format_result(
            rows, normalized_sql, effective_limit, context, tables=referenced_tables
        )
        if not rows and referenced_tables and len(referenced_tables) == 1:
            try:
                verdict = await self._zero_row_verdict(referenced_tables[0])
                if verdict:
                    result["summary"] = "{} | 0 行判读：{}".format(result.get("summary", ""), verdict)
            except Exception as exc:
                logger.info("crawler_sql_zero_row_probe_failed", error=str(exc))
        return result

    @staticmethod
    def _is_column_error(exc: Exception) -> bool:
        """MySQL 1054 Unknown column / 1054 类错误识别。"""
        original = getattr(exc, "orig", None)
        if original is not None and getattr(original, "args", None):
            if str(original.args[0]) == "1054":
                return True
        text = str(exc)
        return "1054" in text or "Unknown column" in text

    def _columns_hint(self, tables: Optional[list]) -> str:
        """渲染涉及表的真实字段清单（优先取契约文件，逐表限量防刷屏）。"""
        from app.utils.table_contracts import table_columns

        lines: list[str] = []
        for table in (tables or [])[:4]:
            columns = table_columns(str(table))
            display_name = str(table)
            if not columns:
                # sql_validator.extract_tables 会把表名转小写，这里按大小写不敏感回查
                for candidate in CRAWLER_SQL_TABLES:
                    if candidate.lower() == str(table).lower():
                        columns = table_columns(candidate)
                        display_name = candidate
                        break
            if not columns:
                continue
            rendered = ", ".join(columns)
            if len(rendered) > 700:
                rendered = rendered[:700] + " …"
            lines.append(f"{display_name}: {rendered}")
        return "\n".join(lines)

    @staticmethod
    def _resolve_limit(limit: Optional[int]) -> int:
        if limit is None:
            return DEFAULT_LIMIT
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            return DEFAULT_LIMIT
        return min(limit, MAX_LIMIT)

    @staticmethod
    def _sanitize_limit(sql: str, default_limit: int) -> tuple[str, Optional[str]]:
        if re.search(r"\b(fetch|offset)\b", sql, re.IGNORECASE):
            return "", "请仅使用 LIMIT 分页，不支持 FETCH 或 OFFSET。"
        if not re.search(r"\blimit\b", sql, re.IGNORECASE):
            return f"{sql.rstrip(' ;')} LIMIT {default_limit}", None

        limit_match = re.search(r"\blimit\s+(\d+)\b", sql, re.IGNORECASE)
        if not limit_match:
            return "", f"LIMIT 必须是 1 到 {MAX_LIMIT} 的整数。"
        limit_value = int(limit_match.group(1))
        if limit_value < 1:
            return "", "LIMIT 必须大于 0。"
        if limit_value <= MAX_LIMIT:
            return sql, None
        return (
            re.sub(r"\blimit\s+\d+\b", f"LIMIT {MAX_LIMIT}", sql, count=1, flags=re.IGNORECASE),
            None,
        )

    async def _run_query(
        self,
        sql: str,
        parameters: Optional[dict[str, Any]] = None,
        tables: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        async with _get_engine().connect() as connection:
            result = await connection.execute(text(sql), parameters or {})
            return [self._serialize_row(dict(row)) for row in result.mappings()]

    async def _zero_row_verdict(self, table: str) -> str:
        """0 行结果的数据可用性判读：区分“窗口内真缺数”与“参数/条件问题”。

        仅对单表白名单查询触发；按契约 time_columns 的时间列做表级范围 +
        近 12 个月逐月行数探针；探针失败一律放弃（fail-open），不影响原结果。
        """
        from app.utils.table_contracts import load_table_contracts

        display = str(table)
        canonical = ""
        for candidate in CRAWLER_SQL_TABLES:
            if candidate.lower() == display.lower():
                canonical = candidate
                break
        if not canonical:
            return ""
        contracts = load_table_contracts() or {}
        info = (contracts.get("tables") or {}).get(canonical) or {}
        time_cols = info.get("time_columns") or []
        if not time_cols:
            try:
                col_rows = await self._run_query(
                    "SELECT column_name AS c FROM information_schema.columns "
                    "WHERE table_schema = DATABASE() AND table_name = :tbl "
                    "AND data_type IN ('datetime', 'date', 'timestamp') "
                    "ORDER BY ordinal_position LIMIT 1",
                    {"tbl": canonical},
                    tables=[canonical],
                )
                time_cols = [r["c"] for r in col_rows if r.get("c")]
            except Exception:
                time_cols = []
        if not time_cols:
            return ""
        time_col = time_cols[0]
        time_col = time_cols[0]

        range_rows = await self._run_query(
            "SELECT MIN({col}) AS a, MAX({col}) AS b, COUNT(*) AS n FROM {tbl}".format(
                col=time_col, tbl=canonical
            ),
            tables=[canonical],
        )
        if not range_rows:
            return ""
        a, b, n = range_rows[0].get("a"), range_rows[0].get("b"), range_rows[0].get("n") or 0
        if not n:
            return "表 {} 当前整表无数据：请核对表名与口径，或该数据源尚未入库。".format(canonical)

        verdict = "表 {} 实际数据覆盖 {} ~ {}（共 {} 行）。".format(canonical, a, b, n)
        try:
            month_rows = await self._run_query(
                "SELECT DATE_FORMAT({col}, '%Y-%m') AS m, COUNT(*) AS n FROM {tbl} "
                "WHERE {col} >= DATE_SUB(:b, INTERVAL 11 MONTH) GROUP BY m ORDER BY m".format(
                    col=time_col, tbl=canonical
                ),
                {"b": b},
                tables=[canonical],
            )
        except Exception:
            month_rows = []
        if month_rows:
            pairs = ", ".join("{}:{}".format(r["m"], r["n"]) for r in month_rows)
            verdict += (
                "近 12 个月逐月行数（全表全口径，未按你的 WHERE 过滤）：{}。"
                "判读：某月 0 行=整月缺数（采集断供）；某月有行数但你的查询 0 行=该月缺你当前口径组合"
                "（常见于 IsHour/IsAudit 过滤），可放宽口径试探数据边界，或改月份窗口/换口径表/语义层统计。"
                .format(pairs)
            )
        return verdict

    def _format_result(
        self,
        rows: list[dict[str, Any]],
        sql: str,
        limit: int,
        context: Optional["ExecutionContext"],
        tables: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        columns = list(rows[0]) if rows else []
        data_shape = self._build_data_shape(columns, rows, len(rows), tables)
        if context and len(rows) > 24:
            try:
                data_id = context.save_data(
                    data=rows,
                    schema="crawler_sql_query_result",
                    metadata={
                        "database": "datacrawler_mysql",
                        "sql": sql,
                        "row_count": len(rows),
                        "columns": columns,
                        "limit": limit,
                        "data_shape": data_shape,
                    },
                )
                sample = rows[:12] + rows[-12:]
                return {
                    "success": True,
                    "data": sample,
                    "data_id": data_id,
                    "count": len(rows),
                    "sample_count": len(sample),
                    "summary": _append_caliber_notes(
                        f"查询到 {len(rows)} 条记录，完整结果已保存，当前返回 24 条样例。"
                        f"{shape_summary_suffix(data_shape)}",
                        columns,
                    ),
                    "data_shape": data_shape,
                    "metadata": {"columns": columns, "externalized": True},
                }
            except Exception as exc:
                logger.warning("crawler_sql_externalize_failed", error=str(exc))

        return {
            "success": True,
            "data": rows,
            "count": len(rows),
            "summary": _append_caliber_notes(
                f"查询到 {len(rows)} 条记录。{shape_summary_suffix(data_shape)}", columns
            ),
            "data_shape": data_shape,
            "metadata": {"columns": columns, "externalized": False},
        }

    def _build_data_shape(
        self,
        columns: list[str],
        rows: list[dict[str, Any]],
        row_count: int,
        tables: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """库侧精确类型优先（表契约），派生/跨表列回退样本推断。"""
        from app.agent.context.data_shape import (
            build_data_shape,
            infer_column_types,
        )
        from app.utils.table_contracts import (
            table_column_types,
        )

        exact_types: dict[str, str] = {}
        for table_name in tables or CRAWLER_SQL_TABLES:
            exact_types.update(table_column_types(str(table_name)))
        inferred_types = infer_column_types(rows, columns)
        columns_with_types = {
            str(name): exact_types.get(str(name)) or inferred_types.get(str(name), "str")
            for name in columns
        }
        source = "db" if exact_types else "inferred"
        return build_data_shape(columns_with_types, row_count, source)

    @staticmethod
    def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
        return {key: ExecuteCrawlerSQLQueryTool._serialize_value(value) for key, value in row.items()}

    @staticmethod
    def _serialize_value(value: Any) -> Any:
        if isinstance(value, (datetime, date, time)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, bytes):
            return value.hex()
        return value
