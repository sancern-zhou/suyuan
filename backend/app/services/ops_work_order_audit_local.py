"""Local (guangdong_mart/PostgreSQL) data source for operations work order audits.

镜像 ops_work_order_audit_engine.fetch_dataset 的查询集，数据改读本地
guangdong_mart（data-ops 链路同步），行键经别名映射与源库大小写对齐。

启用开关：环境变量 OPS_AUDIT_DATA_SOURCE=local（默认）| source；
未配置 OPS_MART_DATABASE_URL 时自动回退 source。

口径与源库差异（registry/契约已登记）：
- 数据范围 = 今年窗口（full_load_since 滚动），更早历史不可查；
- RF 表单/附件为快照同步，非实时；
- OPERATIONUNITID 本地暂缺（dim_station 未同步运维单位部门ID），仅 OPERATIONUNIT 名称可用。
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import psycopg2
import psycopg2.extras
import structlog

from app.services.ops_work_order_audit_aliases import _COLUMN_ALIASES
from app.services.ops_work_order_audit_engine import (
    EXCLUDED_AUDIT_ORDER_TYPES,
    RF_TABLES,
    SUP_AUDIT_ORDER_TYPES,
    _clean_values,
    _history_form_from_joined_row,
    _history_form_seeds,
    _history_order_from_form_row,
    _history_target_tables,
    _normalize_dataset_filter,
    _select_rf_forms_with_filter_stats,
    effective_audit_order_types,
    parse_time,
)

logger = structlog.get_logger()

_MART_SCHEMA = "guangdong_mart"

# 审核消费的工单字段（大写键 → 本地小写列，来自视图双命名家族的大写侧）
_ORDER_FIELD_MAP = {
    "WORKINGORDERID": "workingorderid",
    "STATIONID": "stationid",
    "DEVICEID": "deviceid",
    "WORKINGORDERCODE": "workingordercode",
    "CREATETIME": "createtime",
    "UPDATETIME": "updatetime",
    "DDORDERCREATETYPE": "ddordercreatetype",
    "DDWORKINGORDERTYPE": "ddworkingordertype",
    "DDURGENCYTYPE": "ddurgencytype",
    "DDWORKINGORDERSTATUS": "ddworkingorderstatus",
    "DDISSUEDTYPE": "ddissuedtype",
    "ORDERTITLE": "ordertitle",
    "ORDERCONTENT": "ordercontent",
    "CURRENTWORKFLOWSTATUS": "currentworkflowstatus",
    "CURRENTWORKFLOWPOINT": "currentworkflowpoint",
    "FINISHTIME": "finishtime",
    "PLANFINISHTIME": "planfinishtime",
    "MAINTENANCETYPE": "maintenancetype",
    "TOTALOVERTIME": "totalovertime",
    "TOTALEXPENSE": "totalexpense",
}

_DETAIL_FIELD_MAP = {
    "WORKINGORDERCODE": "working_order_code",
    "PROCESSSTEP": "process_step",
    "PROCESSSTARTDATETIME": "process_start_time",
    "PROCESSENDDATETIME": "process_end_time",
    "PROCESSUSERID": "process_user_id",
    "PROCESSSTATUS": "process_status",
    "SUBMITREMARK": "submit_remark",
    "DESCRIPTIONTA": "description_ta",
    "EXPENSE": "expense",
    "PROCESSTIME": "process_time",
}

_LINK_FIELD_MAP = {
    "ID": "id",
    "REFID": "working_order_code",
    "FUNCTIONCODE": "function_code",
    "TYPECODE": "type_code",
    "FILENAME": "file_name",
    "FILEPATH": "file_path",
    "CREATEUSERID": "create_user_id",
    "CREATEDATE": "create_time",
    # remark 本地 links 视图无此列（WO_COMMONFILE 部分已含）
}

_DEVICE_FIELD_MAP = {
    "DEVICEID": "device_id",
    "DEVICEBRAND": "device_brand",
    "DEVICEMODEL": "device_model",
    "DEVICECODE": "device_code",
    "STATIONID": "station_id",
    "POLLUTANTID": "pollutant_id",
    "DEVICETYPE": "device_type",
}

# sup_rf_common 头信息列小写 → 大写（通用规则按大写字段名匹配 profile 组；
# 题目项列不映射，保留小写原样，待二期列语义普查后按需补充）。
_SUP_FORM_UPPER_MAP = {
    "id": "ID",
    "detailid": "DETAILID",
    "workingordercode": "WORKINGORDERCODE",
    "stationid": "STATIONID",
    "stationcode": "STATIONCODE",
    "uniquecode": "UNIQUECODE",
    "deviceid": "DEVICEID",
    "ruleitemtag": "RULEITEMTAG",
    "pollutanttype": "POLLUTANTTYPE",
    "operationunitid": "OPERATIONUNITID",
    "checkdate": "CHECKDATE",
    "devicebrand": "DEVICEBRAND",
    "devicemodel": "DEVICEMODEL",
    "devicecode": "DEVICECODE",
    "prepareuserid": "PREPAREUSERID",
    "preparetime": "PREPARETIME",
    "reviewuserid": "REVIEWUSERID",
    "reviewtime": "REVIEWTIME",
    "audituserid": "AUDITUSERID",
    "audittime": "AUDITTIME",
    "processtype": "PROCESSTYPE",
    "createuserid": "CREATEUSERID",
    "createtime": "CREATETIME",
    "updateuserid": "UPDATEUSERID",
    "updatetime": "UPDATETIME",
}


def is_sup_station_request(order_types: list[str] | None) -> bool:
    """组分站审核请求判定：显式请求的类型全部属于组分站集合。"""
    values = _clean_values(order_types)
    return bool(values) and set(values) <= set(SUP_AUDIT_ORDER_TYPES)


# 组分站表单载体（本地 mart 表名，小写）：sup_rf_common 通用宽表 + Sup_RF_* 专用分表。
# 源库按 RULEITEMTAG 把多数组分站表单写在专用分表（2026-10-26 复盘：周窗口 21 单中
# 17 单的表单只在分表），仅读宽表会把整单判成"无表单数据"。
SUP_MART_FORM_TABLES: tuple[str, ...] = (
    "sup_rf_common",
    "sup_rf_pm1monitorinspection",
    "sup_rf_deviceflowcheck",
    "sup_rf_monitorinspection",
    "sup_rf_ambienttemperature",
)


def _uppercase_sup_form_row(record: dict[str, Any]) -> dict[str, Any]:
    """sup_rf_common 行头信息列大写化（同键小写列保留，供二期普查对照）。"""
    row = dict(record)
    for low, upper in _SUP_FORM_UPPER_MAP.items():
        if low in row and row[low] is not None:
            row[upper] = row[low]
    return row


def local_source_enabled() -> bool:
    """本地数据源开关：默认 local；未配置 mart 连接时回退 source。"""
    return (
        os.getenv("OPS_AUDIT_DATA_SOURCE", "local") == "local"
        and bool(os.getenv("OPS_MART_DATABASE_URL"))
    )


def connect_pg():
    dsn = os.getenv("OPS_MART_DATABASE_URL", "").replace("+asyncpg", "")
    if not dsn:
        raise RuntimeError("OPS_MART_DATABASE_URL 未配置，无法使用本地审计数据源")
    return psycopg2.connect(dsn, connect_timeout=30)


def _rows(cursor, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    from decimal import Decimal

    with cursor.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
        c.execute(sql, params or [])
        result = []
        for raw in c.fetchall():
            record = dict(raw)
            # 与引擎 rows() 相同的值归一化（datetime/Decimal/bytes），保证下游规则引擎
            # 与 JSON 序列化行为一致
            for key, value in list(record.items()):
                if isinstance(value, datetime):
                    record[key] = value.strftime("%Y-%m-%d %H:%M:%S")
                elif isinstance(value, Decimal):
                    record[key] = float(value)
                elif isinstance(value, bytes):
                    record[key] = value.hex()
            result.append(record)
        return result


def _select_aliased(table: str, field_map: dict[str, str]) -> str:
    """本地表 → 大写键投影（field_map：大写键 → 本地列名）。"""
    cols = ", ".join(f'"{local}" AS "{upper}"' for upper, local in field_map.items())
    return f"SELECT {cols} FROM {_mart(table)}"


def _mart(table: str) -> str:
    return f'{_MART_SCHEMA}.{table.lower()}'


def _rf_select(table: str) -> str:
    """RF 表全列投影：ODS 小写列 → 源库原始列名（保留大小写）。"""
    mapping = _COLUMN_ALIASES.get(table.lower()) or {}
    if not mapping:
        return f"SELECT * FROM {_mart(table)}"
    cols = ", ".join(f'"{low}" AS "{orig}"' for low, orig in mapping.items())
    return f"SELECT {cols} FROM {_mart(table)}"


def _in_clause_pg(field_sql: str, values: list[Any], params: list[Any]) -> str:
    placeholders = ", ".join("%s" for _ in values)
    params.extend(values)
    return f"{field_sql} IN ({placeholders})"


def _not_in_clause_pg(field_sql: str, values: list[Any], params: list[Any]) -> str:
    if not values:
        return "1 = 1"
    placeholders = ", ".join("%s" for _ in values)
    params.extend(values)
    return f"({field_sql} NOT IN ({placeholders}) OR {field_sql} IS NULL)"


def _table_exists(cursor, table: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema=%s AND table_name=%s",
        (_MART_SCHEMA, table),
    )
    return bool(cursor.fetchone())


def _empty_dataset(filters, order_statuses, limit, station_ids, order_types,
                   maintenance_types, working_order_codes) -> dict[str, Any]:
    return {
        "query_info": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "database": "guangdong_mart(local, data-ops)",
            "order_filter": {
                "status": order_statuses or "all",
                "create_time_start": filters.create_time_start,
                "create_time_end": filters.create_time_end,
                "finish_time_start": filters.finish_time_start,
                "finish_time_end": filters.finish_time_end,
                "station_ids": station_ids,
                "operation_units": _clean_values(getattr(filters, "operation_units", None)) or None,
                "order_types": order_types,
                "maintenance_types": maintenance_types,
                "working_order_codes": working_order_codes,
            },
            "order_by": "FINISHTIME DESC, CREATETIME DESC",
            "limit": limit,
        },
        "orders": [],
        "details": [],
        "attachments": [],
        "wo_commonfile": [],
        "stations": [],
        "devices": [],
        "device_history": {"orders": [], "rf_forms": {}, "query_info": {"skipped": True, "reason": "no_orders"}},
        "rf_forms": {},
        "sup_taskitems": [],
    }


def fetch_dataset_local(filter_config: Any) -> dict[str, Any]:
    """fetch_dataset 的本地 PG 实现（行键与源库大小写对齐）。"""
    filters = _normalize_dataset_filter(filter_config)
    limit = max(1, min(int(filters.limit or 200), 3000))
    station_ids = _clean_values(filters.station_ids)
    operation_units = _clean_values(filters.operation_units)
    requested_order_types = _clean_values(filters.order_types)
    # 组分站审核请求（类型全部为 SupCheck/SupSECCheck）不过主网类型过滤，
    # 表单改读 sup_rf_common 通用宽表；主网请求维持原口径（SupCheck 仍被排除）。
    sup_mode = is_sup_station_request(requested_order_types)
    order_types = list(requested_order_types) if sup_mode else effective_audit_order_types(requested_order_types)
    maintenance_types = _clean_values(filters.maintenance_types)
    working_order_codes = _clean_values(filters.working_order_codes)
    order_statuses = _clean_values(filters.order_statuses)
    if working_order_codes:
        limit = max(limit, min(len(working_order_codes), 3000))

    params: list[Any] = []
    where_parts: list[str] = []
    if order_statuses:
        where_parts.append(_in_clause_pg('"ddworkingorderstatus"', order_statuses, params))
    if filters.create_time_start:
        where_parts.append('"createtime" >= %s')
        params.append(filters.create_time_start)
    if filters.create_time_end:
        where_parts.append('"createtime" < %s')
        params.append(filters.create_time_end)
    if filters.finish_time_start:
        where_parts.append('"finishtime" >= %s')
        params.append(filters.finish_time_start)
    if filters.finish_time_end:
        where_parts.append('"finishtime" < %s')
        params.append(filters.finish_time_end)
    if station_ids:
        where_parts.append(_in_clause_pg('"stationid"', station_ids, params))
    if operation_units:
        # 运维单位按站点档案过滤：主网走 dim_station 档案，组分站走 sup_devicedaycheck
        # （组分网站点不在 dim_station，且 Sup 站点→运维单位关系随合同更新，以日检表为准）。
        unit_ph = ", ".join("%s" for _ in operation_units)
        if sup_mode:
            unit_subquery = (
                f'SELECT DISTINCT "stationid"::text FROM {_mart("sup_devicedaycheck")} '
                f'WHERE "operationunitname" IN ({unit_ph})'
            )
        else:
            unit_subquery = (
                f'SELECT "station_id"::text FROM {_mart("dim_station")} '
                f'WHERE "operation_unit_name" IN ({unit_ph})'
            )
        where_parts.append(f'"stationid"::text IN ({unit_subquery})')
        params.extend(operation_units)
    if order_types:
        where_parts.append(_in_clause_pg('"ddworkingordertype"', order_types, params))
    elif requested_order_types:
        where_parts.append("1 = 0")
    if not sup_mode:
        where_parts.append(_not_in_clause_pg('"ddworkingordertype"', sorted(EXCLUDED_AUDIT_ORDER_TYPES), params))
    if maintenance_types:
        where_parts.append(_in_clause_pg('"maintenancetype"', maintenance_types, params))
    if working_order_codes:
        where_parts.append(_in_clause_pg('"workingordercode"', working_order_codes, params))
    where_sql = " AND ".join(where_parts) if where_parts else "1 = 1"

    orders_sql = (
        f"SELECT {_select_aliased_fields(_ORDER_FIELD_MAP)} "
        f"FROM {_mart('working_orders')} WHERE {where_sql} "
        f'ORDER BY "finishtime" DESC NULLS LAST, "createtime" DESC NULLS LAST LIMIT {limit}'
    )

    conn = connect_pg()
    try:
        with conn.cursor() as cur:
            orders = _rows(cur, orders_sql, params)
            codes = [row["WORKINGORDERCODE"] for row in orders if row.get("WORKINGORDERCODE")]
            if not codes:
                return _empty_dataset(filters, order_statuses, limit, station_ids,
                                      order_types, maintenance_types, working_order_codes)
            code_ph = ", ".join("%s" for _ in codes)

            details = _rows(cur,
                f"SELECT {_select_aliased_fields(_DETAIL_FIELD_MAP)} "
                f"FROM {_mart('working_order_details')} "
                f'WHERE "working_order_code" IN ({code_ph}) '
                f'ORDER BY "working_order_code", "process_start_time" NULLS LAST, "process_step"',
                codes)
            attachments = _rows(cur,
                f"SELECT {_select_aliased_links()} "
                f"FROM {_mart('wo_commonfile_links')} "
                f'WHERE "working_order_code" IN ({code_ph}) '
                f'ORDER BY "create_time" DESC NULLS LAST LIMIT 6000',
                codes)
            wo_commonfile = _rows(cur,
                f"SELECT {_select_wo_commonfile()} "
                f"FROM {_mart('wo_commonfile')} "
                f'WHERE "refid" IN ({code_ph}) '
                f'ORDER BY "createdate" DESC NULLS LAST LIMIT 6000',
                codes)

            station_ids_for_query = sorted({str(row.get("STATIONID")) for row in orders if row.get("STATIONID")})
            stations: list[dict[str, Any]] = []
            if station_ids_for_query:
                st_ph = ", ".join("%s" for _ in station_ids_for_query)
                stations = _rows(cur,
                    'SELECT "STATIONID", "NAME", "CODE", "UNIQUECODE", '
                    '"OPERATIONUNITID", "OPERATIONUNIT", "CITYNAME", "ADDRESS", "LONGITUDE", "LATITUDE" '
                    "FROM (SELECT station_id AS \"STATIONID\", station_name AS \"NAME\", "
                    'station_code AS "CODE", unique_code AS "UNIQUECODE", '
                    'operation_unit_id AS "OPERATIONUNITID", operation_unit_name AS "OPERATIONUNIT", '
                    'city_name AS "CITYNAME", address AS "ADDRESS", '
                    'longitude AS "LONGITUDE", latitude AS "LATITUDE" '
                    f"FROM {_mart('dim_station')}) st "
                    f'WHERE "STATIONID" IN ({st_ph}) LIMIT 3000',
                    station_ids_for_query)

            rf_forms: dict[str, list[dict[str, Any]]] = {}
            rf_form_filter_stats: dict[str, dict[str, Any]] = {}
            sup_taskitems: list[dict[str, Any]] = []
            if sup_mode:
                # 组分站：表单体分布在 sup_rf_common 通用宽表与 Sup_RF_* 专用分表，
                # 按工单号整取，头信息列大写化后以各表大写名进入 rf_forms 供通用规则消费。
                for local_table in SUP_MART_FORM_TABLES:
                    table_key = local_table.upper()
                    try:
                        if not _table_exists(cur, local_table):
                            raise RuntimeError(f"local table missing: {local_table}")
                        sup_rows = _rows(cur,
                            f"SELECT * FROM {_mart(local_table)} "
                            f'WHERE "workingordercode" IN ({code_ph}) LIMIT 3000',
                            codes)
                        selected_rows, stats = _select_rf_forms_with_filter_stats(
                            table_key,
                            [_uppercase_sup_form_row(row) for row in sup_rows],
                        )
                        rf_forms[table_key] = selected_rows
                        rf_form_filter_stats[table_key] = stats
                    except Exception as exc:
                        error_rows = [{"_query_error": str(exc)}]
                        selected_rows, stats = _select_rf_forms_with_filter_stats(table_key, error_rows)
                        rf_forms[table_key] = selected_rows
                        rf_form_filter_stats[table_key] = stats
                        logger.warning("ops_audit_local_sup_rf_failed", table=local_table, error=str(exc))
                # 质控计划任务项（阶段 2.4）：按工单号整取，提供周期任务计划完成时间，
                # 供及时性规则用计划口径替换表单侧代理口径。
                try:
                    if _table_exists(cur, "sup_mtc_taskitem"):
                        sup_taskitems = _rows(cur,
                            'SELECT "workingordercode" AS "WORKINGORDERCODE", '
                            '"ruleitemtag" AS "RULEITEMTAG", "pollutanttype" AS "POLLUTANTTYPE", '
                            '"planfinishtime" AS "PLANFINISHTIME", "finishtime" AS "FINISHTIME", '
                            '"status" AS "STATUS" '
                            f"FROM {_mart('sup_mtc_taskitem')} "
                            f'WHERE "workingordercode" IN ({code_ph}) LIMIT 6000',
                            codes)
                    else:
                        sup_taskitems = []
                except Exception as exc:
                    sup_taskitems = []
                    logger.warning("ops_audit_local_sup_taskitems_failed", error=str(exc))
            else:
                for table in RF_TABLES:
                    local_table = table.lower()
                    try:
                        if not _table_exists(cur, local_table):
                            raise RuntimeError(f"local table missing: {local_table}")
                        alias_map = _COLUMN_ALIASES.get(local_table) or {}
                        if alias_map:
                            cols = ", ".join(f'"{low}" AS "{orig}"' for low, orig in alias_map.items())
                            table_sql = f"SELECT {cols} FROM {_mart(local_table)} "
                        else:
                            table_sql = f"SELECT * FROM {_mart(local_table)} "
                        table_rows = _rows(cur,
                            table_sql
                            + f'WHERE "workingordercode" IN ({code_ph}) LIMIT 3000',
                            codes)
                        selected_rows, stats = _select_rf_forms_with_filter_stats(table, table_rows)
                        rf_forms[table] = selected_rows
                        rf_form_filter_stats[table] = stats
                    except Exception as exc:
                        error_rows = [{"_query_error": str(exc)}]
                        selected_rows, stats = _select_rf_forms_with_filter_stats(table, error_rows)
                        rf_forms[table] = selected_rows
                        rf_form_filter_stats[table] = stats
                        logger.warning("ops_audit_local_rf_failed", table=table, error=str(exc))

            device_ids = {str(row.get("DEVICEID")) for row in orders if row.get("DEVICEID")}
            device_codes = {
                str(form.get("DEVICECODE") or form.get("DEVICECODEN"))
                for forms in rf_forms.values()
                for form in forms
                if form.get("DEVICECODE") or form.get("DEVICECODEN")
            }
            device_where_parts = []
            device_params: list[Any] = []
            if device_ids:
                device_where_parts.append(_in_clause_pg('"device_id"', sorted(device_ids), device_params))
            if device_codes:
                device_where_parts.append(_in_clause_pg('"device_code"', sorted(device_codes), device_params))
            devices: list[dict[str, Any]] = []
            if device_where_parts:
                bare_parts = [p.replace('"', '') for p in device_where_parts]
                devices = _rows(cur,
                    f"SELECT {_select_aliased_fields(_DEVICE_FIELD_MAP)} "
                    f"FROM {_mart('dim_device')} "
                    f'WHERE {" OR ".join(bare_parts)}',
                    device_params)
            device_history = _fetch_device_history_pg(cur, orders, rf_forms, limit=500)
    finally:
        conn.close()

    return {
        "query_info": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "database": "guangdong_mart(local, data-ops)",
            "order_filter": {
                "status": order_statuses or "all",
                "create_time_start": filters.create_time_start,
                "create_time_end": filters.create_time_end,
                "finish_time_start": filters.finish_time_start,
                "finish_time_end": filters.finish_time_end,
                "station_ids": station_ids,
                "operation_units": operation_units or None,
                "order_types": order_types,
                "maintenance_types": maintenance_types,
                "working_order_codes": working_order_codes,
            },
            "order_by": "FINISHTIME DESC, CREATETIME DESC",
            "limit": limit,
        },
        "orders": orders,
        "details": details,
        "attachments": attachments,
        "wo_commonfile": wo_commonfile,
        "stations": stations,
        "devices": devices,
        "device_history": device_history,
        "rf_forms": rf_forms,
        "sup_taskitems": sup_taskitems,
    }


def _select_aliased_fields(field_map: dict[str, str]) -> str:
    return ", ".join(f'"{local}" AS "{upper}"' for upper, local in field_map.items())


def _select_aliased_links() -> str:
    fields = _select_aliased_fields(_LINK_FIELD_MAP)
    return fields + ', NULL::text AS "REMARK"'


def _select_wo_commonfile() -> str:
    mapping = _COLUMN_ALIASES.get("wo_commonfile", {})
    cols = ", ".join(f'"{low}" AS "{orig}"' for low, orig in mapping.items())
    return cols


def _fetch_device_history_pg(cursor, orders, rf_forms, limit: int = 500) -> dict[str, Any]:
    """_fetch_device_history 的本地 PG 实现（同策略：同表单同设备的历史记录）。"""
    target_tables = _history_target_tables(rf_forms)
    if not target_tables:
        return {"orders": [], "rf_forms": {},
                "query_info": {"skipped": True, "reason": "no_configured_history_forms_in_batch"}}

    seeds = _history_form_seeds(orders, rf_forms, target_tables)
    if not seeds:
        return {"orders": [], "rf_forms": {},
                "query_info": {"skipped": True, "reason": "missing_device_identity",
                               "history_rf_tables": target_tables}}

    total_limit = max(1, min(int(limit or 500), 1000))
    history_orders_by_code: dict[str, dict[str, Any]] = {}
    history_rf_forms: dict[str, list[dict[str, Any]]] = {table: [] for table in target_tables}

    for table in target_tables:
        local_table = table.lower()
        if not _table_exists(cursor, local_table):
            history_rf_forms[table].append({"_query_error": f"local table missing: {local_table}"})
            continue
        alias_map = _COLUMN_ALIASES.get(local_table, {})
        table_seeds = [seed for seed in seeds if seed["table"] == table]
        for match_field in sorted({str(seed["match_field"]) for seed in table_seeds}):
            field_seeds = [seed for seed in table_seeds if seed["match_field"] == match_field]
            batch = field_seeds[:250]
            values_rows = ", ".join(
                "(%s::text, %s::text, %s::timestamp)" for _ in batch
            )
            seed_params: list[Any] = []
            for seed in batch:
                seed_params.extend([seed["station_id"], seed["device_key"],
                                    seed["cutoff"].strftime("%Y-%m-%d %H:%M:%S")])
            alias_map = alias_map or {}
            rf_alias_cols = (", ".join(f'rf."{low}" AS "{orig}"' for low, orig in alias_map.items())
                             if alias_map else "rf.*")
            wo_alias_cols = ", ".join(
                f'wo."{low}" AS "HISTORY_WO_{upper}"' for upper, low in _ORDER_FIELD_MAP.items())
            try:
                joined_rows = _rows(cursor,
                    f"WITH form_device_seeds(STATIONID, DEVICE_KEY, CUTOFF) AS (VALUES {values_rows}), "
                    "ranked_history AS ("
                    f"SELECT {rf_alias_cols}, {wo_alias_cols}, "
                    'ROW_NUMBER() OVER (PARTITION BY seed.STATIONID, seed.DEVICE_KEY '
                    'ORDER BY wo."createtime" DESC NULLS LAST, wo."workingorderid" DESC) AS "HISTORY_RANK" '
                    f"FROM {_mart(local_table)} rf "
                    f'JOIN {_mart("working_orders")} wo ON wo."workingordercode" = rf."workingordercode" '
                    "JOIN form_device_seeds seed "
                    'ON upper(btrim(rf."stationid"::text)) = seed.STATIONID '
                    f'AND upper(btrim(rf."{match_field.lower()}"::text)) = seed.DEVICE_KEY '
                    'WHERE wo."createtime" < seed.CUTOFF AND wo."ddworkingorderstatus" = \'Finish\''
                    ") SELECT * FROM ranked_history "
                    'WHERE "HISTORY_RANK" <= 5 '
                    'ORDER BY "HISTORY_WO_CREATETIME" DESC NULLS LAST, "HISTORY_WO_WORKINGORDERID" DESC '
                    f"LIMIT {total_limit}",
                    seed_params)
            except Exception as exc:
                history_rf_forms[table].append({"_query_error": str(exc)})
                continue
            for joined_row in joined_rows:
                history_order = _history_order_from_form_row(joined_row)
                code = str(history_order.get("WORKINGORDERCODE") or "")
                if code and code not in history_orders_by_code:
                    history_orders_by_code[code] = history_order
                history_rf_forms[table].append(_history_form_from_joined_row(joined_row))
        history_rf_forms[table], _ = _select_rf_forms_with_filter_stats(table, history_rf_forms[table])

    history_orders = sorted(
        history_orders_by_code.values(),
        key=lambda order: parse_time(order.get("CREATETIME")) or datetime.min,
        reverse=True,
    )[:total_limit]
    allowed_codes = {
        str(order.get("WORKINGORDERCODE"))
        for order in history_orders
        if order.get("WORKINGORDERCODE")
    }
    for table, forms in history_rf_forms.items():
        history_rf_forms[table] = [
            form
            for form in forms
            if form.get("_query_error") or str(form.get("WORKINGORDERCODE") or "") in allowed_codes
        ]

    return {
        "orders": history_orders,
        "rf_forms": history_rf_forms,
        "query_info": {
            "strategy": "previous_same_form_device",
            "history_rf_tables": target_tables,
            "history_limit": total_limit,
            "seed_identity_count": len(seeds),
            "order_count": len(history_orders),
        },
    }
