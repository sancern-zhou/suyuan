"""Read-only PostgreSQL/KingbaseES SQL queries across the app, sound-data and weather stores."""

from __future__ import annotations

import re
from datetime import date, datetime, time
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional

import structlog
from sqlalchemy import text

from app.agent.context.data_shape import shape_summary_suffix
from app.db.database import engine
from app.db.sound_database import sound_engine
from app.db.weather_database import weather_engine
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.sql_validator import SQLValidator

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext


logger = structlog.get_logger()


APP_SQL_TABLES = [
    "air_quality_forecast",
    "city_aqi_publish_history",
    "conversation_catalog",
    "data_contract",
    "data_contract_service_relationship",
    "data_ip",
    "data_service",
    "data_service_monitor",
    "data_service_param",
    "data_service_type",
    "data_service_type_param",
    "documents",
    "dust_events",
    "dust_forecasts",
    "era5_reanalysis_data",
    "fire_hotspots",
    "permit_documents",
    "permit_license_versions",
    "permit_licenses",
    "permit_pollution_details",
    "report_generation_history",
    "report_packages",
    "report_templates",
    "scheduled_task_executions",
    "scheduled_task_results",
    "session_messages",
    "session_resources",
    "sessions",
    "sys_business_system",
    "sys_dictionary",
    "sys_dictionary_item",
    "sys_institution",
    "sys_log",
    "sys_log_detail",
    "sys_menu",
    "sys_menu_log",
    "sys_operation_log",
    "sys_operation_log_detail",
    "sys_region",
    "sys_role",
    "sys_role_menu",
    "sys_user",
    "sys_user_menu",
    "sys_user_region",
    "sys_user_role",
    "weather_data_cache",
    "weather_stations",
]
# 项目专属业务表（如许昌路况时序 traffic_*、许昌告警事件聚合
# xuchang_station_alert_episodes）经 projects/<id>/project.yaml 的
# backend.tool_options.execute_postgres_sql_query.allowed_tables_extra 注入，
# 共享白名单只保留所有部署共有的表。

# 气象观测表位于独立气象库（WEATHER_DATABASE_URL/weather_engine），不在主库。
# weather_stations 主档表仅剩遗留站点，仅按名称查站时使用。
WEATHER_SQL_TABLES = [
    "observed_weather_data",
    "observed_weather_daily",
]

# 声环境监测库（sound_data）现有 1809 张表，且大量按年/按站点分表
# （如 noise_1m_2025_1771a_src、noise_h_2023_1001a_app），逐表枚举既不现实
# 也会撑爆工具描述。因此按业务前缀放行，前缀外的零散表逐条列出。
SOUND_DB_TABLE_PREFIXES = [
    "noise_",
    "opa_",
    "dat_",
    "aud_",
    "qc_",
    "task_",
    "dm_",
    "sub_",
    "biz_",
    "alm_",
]

# 跨库改道指引：前缀放行（含 dat_）会让别库同前缀表名通过白名单，随后必然 UndefinedTableError；在错误信息中直接给出归属工具（错误信息即召回钩子），避免模型在本工具内反复试错（2026-11-26 国控站 5 分钟查询踩坑）。
_CROSS_BACKEND_HINT_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("dat_zhongda_",),
        ("该表属于中大平台监测库（XcAiDb/SQL Server），不在本工具（PostgreSQL）——请改用 "
         "execute_sql_query 查询：dat_zhongda_station_minute=国控站5分钟、"
         "dat_zhongda_station_hour=国控站小时、dat_zhongda_city_hour=城市小时；"
         "过滤列 station_code 用中大站码 1003A 系，不要用国控唯一编码 4110*。"),
    ),
    (
        ("dat_", "city_168_", "province_statistics_"),
        ("该表属于监测 SQL Server 库（XcAiDb），不在本工具（PostgreSQL）——请改用 "
         "execute_sql_query 查询。"),
    ),
    (
        (
            "stationhour", "stationday", "cityhour", "cityday", "townstation",
            "town_five", "officestation", "ssfb", "shengkong", "countymonth",
            "provincemonth", "rank168", "xuchangcityyear", "xuchangcountyyear",
            "henancityyear",
        ),
        ("该表疑似采集长历史库（DataCrawler/MySQL）的表，不在本工具（PostgreSQL）——请改用 "
         "execute_crawler_sql_query 查询（长历史/同比）；国控站日值走 query_airdata_platform。"),
    ),
)


def _cross_backend_table_hint(table_name: str) -> str:
    lowered = str(table_name or "").strip().lower()
    if not lowered:
        return ""
    for prefixes, hint in _CROSS_BACKEND_HINT_RULES:
        if lowered.startswith(prefixes):
            return hint
    return ""


def _cross_backend_hints_for_tables(table_names) -> str:
    hints: list[str] = []
    for name in table_names or []:
        hint = _cross_backend_table_hint(str(name))
        if hint and hint not in hints:
            hints.append(hint)
    return (" " + " ".join(hints)) if hints else ""

SOUND_DB_SQL_TABLES = [
    "NoiseRecount",
    "NoiseRecountReportTemplate",
    "noisecalibrationrecords",
    "data_uploadtask",
    "datareplenishdata",
    "datareplenishlog",
    "equipment_replenishment",
    "event_file_download_record",
    "faultinspectionrecords_day",
    "funstationfile",
    "point_filing",
    "power_outage_plans",
    "pw_month_taskitem",
    "reflow_data_log",
    "stationhourlyweathermonitorrecord",
    "sun_commonfile",
    "sys_alarm_2026",
    "sys_selfcheck_2026",
]

ALLOWED_SQL_TABLES = (
    list(APP_SQL_TABLES) + list(WEATHER_SQL_TABLES) + list(SOUND_DB_SQL_TABLES)
)

MAIN_DATABASE = "bigdata_system"
SOUND_DATA_DATABASE = "sound_data"
WEATHER_DATABASE = "weather"
DATABASE_NAMES = (MAIN_DATABASE, SOUND_DATA_DATABASE, WEATHER_DATABASE)

MAX_LIMIT = 1000
DEFAULT_LIMIT = 50


def _load_postgres_tool_options() -> dict[str, Any]:
    """读取 backend.tool_options 中的 execute_postgres_sql_query 项目扩展。

    支持 keys：allowed_tables_extra（追加到共享白名单的项目专属业务表）、
    schema_notes（追加到工具描述末尾的项目口径注记与示例）。
    """
    try:
        from app.project_config.loader import load_project_context
        from config.settings import settings

        manifest = load_project_context(settings.project_id).manifest
        return manifest.backend.tool_options.get("execute_postgres_sql_query") or {}
    except Exception as exc:
        logger.warning("execute_postgres_tool_options_unavailable", error=str(exc))
        return {}


class ExecutePostgresSQLQueryTool(LLMTool):
    """Execute read-only SQL against the configured PostgreSQL/KingbaseES databases."""

    def __init__(self) -> None:
        from app.agent.context.data_shape import TableTypesCache

        # 每个库一个缓存：TableTypesCache 的键只有 schema.table，多库共用会串类型。
        self._table_types_caches = {
            MAIN_DATABASE: TableTypesCache(),
            SOUND_DATA_DATABASE: TableTypesCache(),
            WEATHER_DATABASE: TableTypesCache(),
        }
        options = _load_postgres_tool_options()
        # 实例级白名单：共享表 + 项目扩展表（项目 tool_options 声明通道）。
        self._allowed_tables = list(ALLOWED_SQL_TABLES) + list(
            options.get("allowed_tables_extra") or []
        )
        project_notes = str(options.get("schema_notes") or "")
        schema_description = (
            "KingbaseES/PostgreSQL 只读 SQL 查询工具，覆盖三个库：bigdata_system（平台库）、"
            "sound_data（声环境监测库）与 weather（独立气象库，按表名自动路由）。"
            "describe_table 查表结构/表清单，或 sql 执行 SELECT/CTE，二者二选一。"
            "只允许 SELECT（禁写/DDL/注释/多语句），"
            f"LIMIT 分页最大 {MAX_LIMIT} 条；字段不确定先 describe_table，禁查 information_schema。"
            "\n\n【bigdata_system｜平台库】"
            "会话与资源：sessions/session_messages/session_resources/conversation_catalog；"
            "权限区划：sys_user/sys_role/sys_user_role/sys_menu/sys_role_menu/sys_region/sys_institution/sys_dictionary(_item)；"
            "数据服务：data_service*/data_contract*/data_ip；日志：sys_operation_log(_detail)/sys_log(_detail)/sys_menu_log；"
            "业务：permit_licenses 及 permit_* 子表（以 license_id 关联主表）、scheduled_task_results/executions"
            "（conclusion 结论 / findings、image_paths 为 JSON 列，查具体任务按 task_id 过滤）、report_*、documents。"
            "\n【sound_data｜声环境监测库，1809 张表，多数按年/按站分表】"
            "站点主档：dat_station、noise_areastation/noise_funstation/noise_roadstation（三类站点）；"
            "实测时序：dat_station_day、dat_station_hour_<年>、dat_city_day/hour、biz_station_day/hour、"
            "noise_1m_<年>_<站号>a_src（分钟级，单表千万级）、noise_h_<年>_<站号>a_app（对应小时级）、"
            "noise_1s/noise_5m/noise_livedata(_his)/noise_station_monitor_data/record、"
            "noise_areastationdata_<年>/noise_funstationdata_<年>/noise_roadstationdata_<年>（功能区/道路交通年表族）；"
            "业务：noise_event(_strategy)/noise_alarmlog/aud_noise_event/dm_*（声源、静音城市、敏感区）/opa_*（运维）/"
            "aud_*（审核）/qc_*（质控）/sub_*（子站与车流量）/task_*/alm_shortmessege/sys_alarm_2026/sys_selfcheck_2026。"
            "\n【weather｜独立气象库】"
            "observed_weather_data 逐小时观测（主键 time+station_id，站点清单 SELECT DISTINCT station_id, station_name；NULL=缺测）；"
            "observed_weather_daily 逐日聚合（obs_date 为 00-24 北京时口径，建议附带 data_quality/valid_hours 判可靠性）。"
            "\ndescribe_table 用法：传具体表名查字段+一条样例；传 'tables' 列出该库表清单；"
            "传关键字（如 'noise_1m'、'dat_station'）做表名模糊匹配；database 指定 bigdata_system/sound_data/weather。"
            "\n硬约束：只允许 SELECT/CTE；禁写/DDL/注释/多语句；LIMIT 最大 1000（默认 50）；禁查 information_schema；"
            "不得查询 sys_user.password 等凭据字段；多库不支持跨库 JOIN，需在应用层合并；大表必须带时间/站点过滤与 LIMIT。"
            "\n统计红线：环境统计值（均值/分位数/达标率/同比环比等）的计算由数据源完成——优先所属领域的统计接口，"
            "库内现成的统计字段/聚合结果列（日值/小时值等）也可直接查询使用；"
            "禁止查询秒/分等原始明细后自行汇总计算统计值，自算必有口径与精度偏差；"
            "数据缺口如实上报，不得估算补齐。"
            "\n示例："
            "\n- 站点日噪声：SELECT * FROM dat_station_day WHERE station_code = '36010001' ORDER BY monitor_time DESC LIMIT 20"
            "\n- 声环境事件：SELECT * FROM noise_event WHERE alarm_time >= '2026-01-01' ORDER BY alarm_time DESC LIMIT 50"
            "\n- 企业大气污染物：SELECT l.enterprise_name, p.air_pollutant_types FROM permit_licenses l JOIN permit_pollution_details p ON p.license_id = l.id "
            "WHERE l.city_name = N'城市名称' LIMIT 50"
        )
        # 项目专属业务表的路由口径与示例经 tool_options.schema_notes 追加（如许昌
        # 路况时序/站点快速告警 task_id/站点点编码），共享层不写死任何项目地名。
        if project_notes:
            schema_description = schema_description + "\n\n【项目扩展口径】" + project_notes
        function_schema = {
            "name": "execute_postgres_sql_query",
            "description": schema_description,
            "parameters": {
                "type": "object",
                "properties": {
                    "describe_table": {
                        "type": "string",
                        "description": (
                            "查表结构（与 sql 二选一）：表名返回字段与一条样例；"
                            "'tables' 列出该库表清单；其他值按表名前缀模糊匹配。"
                        ),
                    },
                    "sql": {
                        "type": "string",
                        "description": "仅允许使用白名单表的 KingbaseES/PostgreSQL SELECT 或 WITH...SELECT 查询；与 describe_table 二选一。",
                    },
                    "database": {
                        "type": "string",
                        "enum": list(DATABASE_NAMES),
                        "default": MAIN_DATABASE,
                        "description": (
                            "目标库：bigdata_system（平台库）、sound_data（声环境监测库）或 weather（独立气象库）。"
                            "默认 bigdata_system；气象表与声环境前缀表可省略由表名自动路由。"
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_LIMIT,
                        "default": DEFAULT_LIMIT,
                        "description": "未在 SQL 中指定 LIMIT 时使用的返回上限；最大 1000。",
                    },
                },
            },
        }
        super().__init__(
            name="execute_postgres_sql_query",
            description="Execute read-only KingbaseES/PostgreSQL SQL across the platform, sound-monitoring and weather databases",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="2.1.0",
            requires_context=True,
        )
        self.sql_validator = SQLValidator(
            max_limit=MAX_LIMIT,
            allowed_tables=self._allowed_tables,
            allowed_table_prefixes=SOUND_DB_TABLE_PREFIXES,
        )

    async def execute(
        self,
        context: Optional["ExecutionContext"] = None,
        describe_table: Optional[str] = None,
        sql: Optional[str] = None,
        limit: Optional[int] = None,
        database: Optional[str] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        del kwargs
        if database and database not in DATABASE_NAMES:
            return {
                "success": False,
                "data": None,
                "summary": f"database 只支持: {', '.join(DATABASE_NAMES)}。",
            }
        if bool(describe_table) == bool(sql):
            return {
                "success": False,
                "data": None,
                "summary": "请且只能提供 describe_table 或 sql 其中一个参数。",
            }
        if describe_table is not None:
            return await self._describe_table(describe_table, database)
        return await self._execute_sql(sql or "", limit, context, database)

    async def _describe_table(
        self,
        table_name: str,
        database: Optional[str] = None,
    ) -> dict[str, Any]:
        target_db = self._resolve_database(table_name, database)
        lookup = table_name.strip()
        if not lookup or lookup.lower() == "tables":
            return await self._list_tables(target_db, "")

        if not self._is_table_allowed(lookup):
            matches = await self._find_tables(lookup, target_db)
            if matches:
                return {
                    "success": True,
                    "data": {"database": target_db, "tables": matches},
                    "summary": (
                        f"表 '{lookup}' 不在白名单中；库 {target_db} 中匹配到的白名单表："
                        f"{', '.join(matches[:30])}。请用完整表名再调用 describe_table。"
                    ),
                }
            return {
                "success": False,
                "data": None,
                "summary": (
                    f"表 '{lookup}' 不在白名单中（库 {target_db}）。"
                    "可传 describe_table='tables' 查看表清单，或传表名前缀做模糊匹配。"
                    + (lambda _h: f" {_h}" if _h else "")(_cross_backend_table_hint(lookup))
                ),
            }

        try:
            columns = await self._run_query(
                """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = current_schema() AND table_name = :table_name
                ORDER BY ordinal_position
                """,
                {"table_name": lookup},
                tables=[lookup],
                database=target_db,
            )
            sample_rows = await self._run_query(
                f"SELECT * FROM {lookup} LIMIT 1",
                tables=[lookup],
                database=target_db,
            )
        except Exception as exc:
            logger.error(
                "postgres_sql_describe_failed",
                table_name=lookup,
                database=target_db,
                error=str(exc),
            )
            hint = _cross_backend_table_hint(lookup)
            hint_suffix = f" {hint}" if hint else ""
            return {
                "success": False,
                "data": None,
                "summary": f"查询表结构失败: {exc}{hint_suffix}",
            }

        if not columns:
            return {
                "success": False,
                "data": None,
                "summary": (
                f"库 {target_db} 中未找到白名单表 '{lookup}'。"
                + (f" {_cross_backend_table_hint(lookup)}" if _cross_backend_table_hint(lookup) else "")
                ),
            }
        return {
            "success": True,
            "data": {
                "database": target_db,
                "table_name": lookup,
                "columns": columns,
                "sample_data": sample_rows[0] if sample_rows else None,
            },
            "summary": f"表 {lookup}（{target_db}）共 {len(columns)} 个字段；已返回字段结构和一条样例。",
        }

    async def _list_tables(self, database: str, keyword: str) -> dict[str, Any]:
        tables = await self._find_tables(keyword, database)
        return {
            "success": True,
            "data": {"database": database, "keyword": keyword, "tables": tables},
            "summary": (
                f"库 {database} 中匹配的白名单表 {len(tables)} 张"
                + (f"（关键字 '{keyword}'）" if keyword else "")
                + "。"
            ),
        }

    async def _find_tables(self, keyword: str, database: str) -> list[str]:
        """在白名单范围内按前缀/子串查找表名（内部查询 information_schema）。"""
        try:
            rows = await self._run_query(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_type = 'BASE TABLE'
                  AND table_name ILIKE :keyword
                ORDER BY table_name
                LIMIT 200
                """,
                {"keyword": f"%{keyword}%"},
                database=database,
            )
        except Exception as exc:
            logger.warning(
                "postgres_sql_table_lookup_failed",
                database=database,
                keyword=keyword,
                error=str(exc),
            )
            return []
        return [
            str(row["table_name"])
            for row in rows
            if self._is_table_allowed(str(row["table_name"]))
        ]

    def _is_table_allowed(self, table_name: str) -> bool:
        lowered = table_name.lower()
        if lowered in {name.lower() for name in self._allowed_tables}:
            return True
        return lowered.startswith(tuple(SOUND_DB_TABLE_PREFIXES))

    @staticmethod
    def _resolve_database(table_name: str, database: Optional[str]) -> str:
        """显式 database 优先；否则按表名推断（气象表 → weather，声环境前缀/专有表 → sound_data）。"""
        if database:
            return database
        lowered = table_name.lower()
        if lowered in {name.lower() for name in WEATHER_SQL_TABLES}:
            return WEATHER_DATABASE
        if lowered in {name.lower() for name in SOUND_DB_SQL_TABLES}:
            return SOUND_DATA_DATABASE
        if lowered.startswith(tuple(SOUND_DB_TABLE_PREFIXES)):
            return SOUND_DATA_DATABASE
        return MAIN_DATABASE

    async def _execute_sql(
        self,
        sql: str,
        limit: Optional[int],
        context: Optional["ExecutionContext"],
        database: Optional[str] = None,
    ) -> dict[str, Any]:
        normalized_sql = self.sql_validator.normalize_sql(sql)
        valid, error = self.sql_validator.validate(normalized_sql)
        if not valid:
            return {
                "success": False,
                "data": [],
                "summary": f"SQL 验证失败: {error}。字段不确定时请先调用 describe_table。",
            }
        if re.search(r"\bpassword\b", normalized_sql, re.IGNORECASE):
            return {
                "success": False,
                "data": [],
                "summary": "不允许查询 password 等凭据字段。",
            }

        effective_limit = self._resolve_limit(limit)
        safe_sql, limit_error = self._sanitize_limit(normalized_sql, effective_limit)
        if limit_error:
            return {"success": False, "data": [], "summary": limit_error}

        referenced_tables = self.sql_validator.extract_tables(normalized_sql)
        databases = {
            self._resolve_database(table, database) for table in referenced_tables
        }
        if len(databases) > 1:
            return {
                "success": False,
                "data": [],
                "summary": (
                    "多库分属不同连接，不支持跨库 JOIN："
                    f"{', '.join(sorted(databases))}。请分开查询后在应用层合并。"
                ),
            }
        target_db = databases.pop() if databases else (database or MAIN_DATABASE)

        logger.info(
            "postgres_sql_query_start",
            sql_preview=normalized_sql[:200],
            limit=effective_limit,
            database=target_db,
            session_id=getattr(context, "session_id", "unknown") if context else "unknown",
        )
        try:
            rows = await self._run_query(
                safe_sql,
                tables=referenced_tables,
                database=target_db,
            )
        except Exception as exc:
            logger.error(
                "postgres_sql_query_failed",
                database=target_db,
                error=str(exc),
                sql_preview=normalized_sql[:200],
            )
            return {
                "success": False,
                "data": [],
                "summary": (
                    f"查询失败: {exc}。字段不确定时请先调用 describe_table。"
                    + _cross_backend_hints_for_tables(referenced_tables)
                ),
            }

        data_shape = await self._build_data_shape(
            list(rows[0].keys()) if rows else [],
            rows,
            len(rows),
            referenced_tables,
            target_db,
        )
        return self._format_result(
            rows,
            normalized_sql,
            effective_limit,
            context,
            database=target_db,
            data_shape=data_shape,
        )

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
            return "", "LIMIT 必须是 1 到 1000 的整数。"
        limit_value = int(limit_match.group(1))
        if limit_value < 1:
            return "", "LIMIT 必须大于 0。"
        if limit_value <= MAX_LIMIT:
            return sql, None
        return (
            re.sub(r"\blimit\s+\d+\b", f"LIMIT {MAX_LIMIT}", sql, count=1, flags=re.IGNORECASE),
            None,
        )

    @staticmethod
    def _select_engine(tables: list[str], database: Optional[str] = None):
        """按引用表/显式库名选择连接：声环境表走 sound_engine，气象表走独立气象库，其余走主库。"""
        if database == SOUND_DATA_DATABASE:
            return sound_engine
        if database == WEATHER_DATABASE:
            return weather_engine
        if database:
            return engine
        for table in tables:
            resolved = ExecutePostgresSQLQueryTool._resolve_database(table, None)
            if resolved == SOUND_DATA_DATABASE:
                return sound_engine
            if resolved == WEATHER_DATABASE:
                return weather_engine
        return engine

    async def _run_query(
        self,
        sql: str,
        parameters: Optional[dict[str, Any]] = None,
        tables: Optional[list[str]] = None,
        database: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        target_engine = self._select_engine(
            tables if tables is not None else self.sql_validator.extract_tables(sql),
            database,
        )
        async with target_engine.connect() as connection:
            result = await connection.execute(text(sql), parameters or {})
            return [self._serialize_row(dict(row)) for row in result.mappings()]

    async def _build_data_shape(
        self,
        columns: list[str],
        rows: list[dict[str, Any]],
        row_count: int,
        tables: list[str],
        database: Optional[str] = None,
    ) -> dict[str, Any]:
        """information_schema 精确类型优先，派生列回退样本推断。"""
        from app.agent.context.data_shape import (
            build_data_shape,
            infer_column_types,
        )

        exact_types: dict[str, str] = {}
        for table_name in tables:
            table_db = database or self._resolve_database(table_name, None)
            cache = self._table_types_caches.get(table_db) or self._table_types_caches[MAIN_DATABASE]
            exact_types.update(
                await cache.load(self._select_engine([table_name], table_db), table_name)
            )
        inferred_types = infer_column_types(rows, columns)
        columns_with_types = {
            str(name): exact_types.get(str(name)) or inferred_types.get(str(name), "str")
            for name in columns
        }
        source = "db" if exact_types else "inferred"
        return build_data_shape(columns_with_types, row_count, source)

    def _format_result(
        self,
        rows: list[dict[str, Any]],
        sql: str,
        limit: int,
        context: Optional["ExecutionContext"],
        database: str = MAIN_DATABASE,
        data_shape: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        columns = list(rows[0]) if rows else []
        suffix = shape_summary_suffix(data_shape)
        if context and len(rows) > 24:
            try:
                data_id = context.save_data(
                    data=rows,
                    schema="sql_query_result",
                    metadata={
                        "database": database,
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
                    "summary": f"查询到 {len(rows)} 条记录，完整结果已保存，当前返回 24 条样例。{suffix}",
                    "data_shape": data_shape,
                    "metadata": {"columns": columns, "externalized": True},
                }
            except Exception as exc:
                logger.warning("postgres_sql_externalize_failed", error=str(exc))

        return {
            "success": True,
            "data": rows,
            "count": len(rows),
            "summary": f"查询到 {len(rows)} 条记录。{suffix}",
            "data_shape": data_shape,
            "metadata": {"columns": columns, "externalized": False},
        }

    @staticmethod
    def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
        return {key: ExecutePostgresSQLQueryTool._serialize_value(value) for key, value in row.items()}

    @staticmethod
    def _serialize_value(value: Any) -> Any:
        if isinstance(value, (datetime, date, time)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, bytes):
            return value.hex()
        return value
