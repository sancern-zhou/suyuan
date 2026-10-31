"""广东运维指标语义层查询工具（Cube Core REST / 127.0.0.1:4611）。

DEPLOYMENT ADDITION (2026-10-24): serves the guangdong-cube semantic layer
(projects/guangdong/data-ops/cube, Cube Core 0.35). The agent asks for
*metrics* (measures + dimensions + time range) instead of writing SQL —
metric definitions live exactly once in the semantic layer, so the same
question always yields the same number.

治理分离（2026-10-31）: 本文件不再手工维护成员目录 CATALOG——成员白名单与
口径语义全部来自 data-ops 生成产物 catalog.generated.json（同目录，
gen_semantic_artifacts.py 由 cube/schema/*.js ⊕ registry.yaml 生成，
缺失/损坏在导入期即失败）；治理中间件（JWT/DQ 门/审计/契约校验/
semantic_context 组装）来自 app.services.semantic_governance 共享库。
工具描述只保留路由与红线，成员目录按需 describe_cube 获取。

查询走 JWT（CUBE_API_SECRET），连库侧仍是 agent_reader 只读，无新增数据库权限；
每次调用审计入 guangdong_sync.query_audit。
"""

import difflib
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.services.semantic_governance import (
    build_query,
    build_semantic_context,
    cube_entry,
    cube_names,
    data_as_of,
    flatten_rows,
    has_member,
    load_catalog,
    load_contract,
    quality_status,
    query_cube,
    truncate_rows,
    validate_result,
    write_audit,
)
from app.utils.path_config import resolve_agent_path

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()

# ------------------------------------------------------------ 部署参数（项目专属）
# 生成目录产物与 contract.txt 同模式：生成器写入工具目录，模块导入期加载。
CATALOG_PATH = resolve_agent_path(
    "backend/app/tools/query/guangdong_cube_metrics/catalog.generated.json")
CONTRACT_PATH = resolve_agent_path(
    "projects/guangdong/data-ops/semantic/result_contract.yaml")
MART_SCHEMA = "guangdong_mart"
DQ_TABLE = "guangdong_sync.dq_results"
AUDIT_TABLE = "guangdong_sync.query_audit"

# 每个 cube 对应的宽表新鲜度列(用于返回 data_as_of 与 DQ 门按表查询)
FRESHNESS_COLUMN: Dict[str, Tuple[str, str]] = {
    "WorkOrder": ("mart_work_order_analysis", "refreshed_at"),
    "AlarmNotify": ("mart_alarm_notify_analysis", "refreshed_at"),
    "StationAlarmStatus": ("mart_station_alarm_status", "refreshed_at"),
    "DeviceLifecycle": ("mart_device_lifecycle_analysis", "refreshed_at"),
    "InspectionTask": ("mart_inspection_task_analysis", "refreshed_at"),
    "Performance": ("mart_performance_analysis", "refreshed_at"),
}

ALLOWED_FILTER_OPERATORS = {
    "equals", "notEquals", "contains", "notContains", "in", "notIn",
    "afterDate", "beforeDate", "set", "notSet",
}

CUBE_INDEX_KEYWORDS = {"cubes", "all", "index", "目录", "全部", "cube清单", "cube列表"}

CONTRACT = load_contract(CONTRACT_PATH)


def _cube_index(catalog: Dict[str, Any]) -> List[Dict[str, str]]:
    """全部 cube 的一句话索引（describe_cube='cubes'）。"""
    items = []
    for name in cube_names(catalog):
        entry = cube_entry(catalog, name) or {}
        grain = str(entry.get("grain") or "")
        summary = f"{entry.get('dataset') or '?'}：{grain}"
        items.append({
            "cube": name,
            "dataset": entry.get("dataset") or "",
            "measures": len(entry.get("measures") or {}),
            "dimensions": len(entry.get("dimensions") or {}),
            "summary": summary[:110],
        })
    return items


def _unknown_cube_summary(catalog: Dict[str, Any], cube: str) -> str:
    close = difflib.get_close_matches(cube, cube_names(catalog), n=3, cutoff=0.6)
    hint = f"相近 Cube：{', '.join(close)}；" if close else ""
    return (f"未知 Cube: {cube}。{hint}"
            f"describe_cube='cubes' 列出全部 Cube 与一句话索引。")


class GuangdongQueryMetricsTool(LLMTool):
    """经语义层查询广东运维指标（口径唯一,免写SQL）。"""

    DEFAULT_LIMIT = 50
    MAX_LIMIT = 1000

    def __init__(self):
        self.tool_name = "guangdong_query_metrics"
        catalog = load_catalog(CATALOG_PATH)
        cubes_line = "、".join(cube_names(catalog))
        function_schema = {
            "name": self.tool_name,
            "description": (
                "查询广东运维指标(语义层,口径唯一,免写SQL)。Cube: WorkOrder(全类型运维工单量/完成率/超期率/"
                "2小时响应率/30天重复故障率/附件完整率)、AlarmNotify(告警通知量与站点覆盖)、"
                "StationAlarmStatus(当前告警站点态势)、DeviceLifecycle(设备周期检查与启停)、"
                "InspectionTask(巡检任务完成率/超期率/转工单率)、Performance(站点绩效月度考核,平台口径不重算)。"
                f"成员目录(measures/dimensions 全集)用 describe_cube='<Cube名>' 获取; describe_cube='cubes' 列出全部Cube({cubes_line})。"
                "红线: 工单量与时效结论必须按 orderType/orderStatus 声明口径(全类型含作废);"
                "超期率分母只计有计划完成时间的单;响应类指标仅故障单可评估;告警通知无处理状态,未处理率不可评估。"
                "数据窗口=今年窗口+持续增量,窗口前历史不可查;实时在办状态用 execute_ops_sql_query 直查源库;"
                "字段级明细取证用 execute_guangdong_mart_sql。"
                "返回含 semantic_context(指标定义/粒度/适用范围/数据时点/质量状态),生成结论前必须结合判断可评估性。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "measures": {
                        "type": "array", "items": {"type": "string"},
                        "description": "度量成员,如 ['WorkOrder.responseWithin2hRate','WorkOrder.count'],须同一Cube",
                    },
                    "describe_cube": {
                        "type": "string",
                        "description": "(可选)只查语义目录不执行查询:'cubes' 列出全部Cube,或传 Cube 名取其指标定义/粒度/适用范围",
                    },
                    "dimensions": {
                        "type": "array", "items": {"type": "string"},
                        "description": "(可选)分组维度,如 ['WorkOrder.stationName']",
                    },
                    "time_dimension": {
                        "type": "string",
                        "description": "(可选)时间维度成员,如 'WorkOrder.createTime'",
                    },
                    "date_range": {
                        "description": "(可选)'last 7 days'等关键字,或 ['2026-10-01','2026-10-31']",
                    },
                    "granularity": {
                        "type": "string", "enum": ["day", "week", "month", "year"],
                        "description": "(可选)时间粒度,给趋势序列时用",
                    },
                    "filters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "member": {"type": "string"},
                                "operator": {"type": "string"},
                                "values": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["member", "operator"],
                        },
                        "description": "(可选)过滤条件,operator ∈ equals/notEquals/contains/in/afterDate/beforeDate等",
                    },
                    "order": {
                        "type": "object",
                        "description": "(可选)排序,如 {'WorkOrder.count':'desc'}",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回行数上限(默认50,最大1000)",
                        "default": 50,
                    },
                },
                "required": [],
            },
        }
        super().__init__(
            name=self.tool_name,
            description="查询广东运维指标(语义层REST,口径唯一,免SQL)",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="2.0.0",
            requires_context=True,
        )

    # ------------------------------------------------------------ 校验
    @staticmethod
    def _member_cube(catalog: Dict[str, Any], member: str, kind: str) -> Optional[str]:
        if "." not in member:
            return None
        cube, name = member.split(".", 1)
        part_key = "measures" if kind == "measure" else "dimensions"
        if has_member(catalog, cube, part_key, name):
            return cube
        return None

    def _validate(self, catalog: Dict[str, Any], measures, dimensions,
                  time_dimension, filters) -> Tuple[Optional[str], Optional[str]]:
        if not measures:
            return None, "measures 不能为空"
        hint = ("describe_cube='cubes' 列出全部 Cube;"
                "describe_cube='<Cube名>' 取该 Cube 的成员目录")
        cubes = set()
        for m in measures:
            c = self._member_cube(catalog, m, "measure")
            if c is None:
                return None, f"未知度量 {m}(不在语义目录中)。{hint}"
            cubes.add(c)
        for d in dimensions or []:
            c = self._member_cube(catalog, d, "dimension")
            if c is None:
                return None, f"未知维度 {d}(不在语义目录中)。{hint}"
            cubes.add(c)
        if time_dimension:
            c = self._member_cube(catalog, time_dimension, "dimension")
            if c is None:
                return None, f"未知时间维度 {time_dimension}。{hint}"
            cubes.add(c)
        for f in filters or []:
            member = f.get("member", "")
            c = self._member_cube(catalog, member, "dimension")
            if c is None:
                return None, f"过滤条件成员未知或不是维度: {member}。{hint}"
            if f.get("operator") not in ALLOWED_FILTER_OPERATORS:
                return None, f"不支持的过滤操作符: {f.get('operator')}"
            cubes.add(c)
        if len(cubes) > 1:
            return None, f"一次查询只能用一个 Cube 的成员,当前跨了: {sorted(cubes)}"
        return cubes.pop(), None

    # ------------------------------------------------------------ 执行
    async def execute(
        self,
        context: Optional["ExecutionContext"] = None,
        measures: Optional[List[str]] = None,
        dimensions: Optional[List[str]] = None,
        time_dimension: Optional[str] = None,
        date_range: Any = None,
        granularity: Optional[str] = None,
        filters: Optional[List[Dict[str, Any]]] = None,
        order: Optional[Dict[str, str]] = None,
        limit: Optional[int] = None,
        describe_cube: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        if describe_cube:
            return await self._describe(context, describe_cube)
        catalog = load_catalog(CATALOG_PATH)
        cube, err = self._validate(catalog, measures, dimensions, time_dimension, filters)
        if err:
            return {"success": False, "data": None, "summary": f"参数校验失败: {err}"}

        requested_limit = min(limit or self.DEFAULT_LIMIT, self.MAX_LIMIT)
        # 多取一行用于判定结果是否被截断
        query = build_query(measures, dimensions, time_dimension, date_range,
                            granularity, filters, order, limit=requested_limit + 1)

        started = time.monotonic()
        status, error, row_count = "ok", None, 0
        truncated = False
        try:
            base_url = os.getenv("CUBE_API_URL", "http://127.0.0.1:4611/cubejs-api/v1")
            body = await query_cube(base_url, os.getenv("CUBE_API_SECRET", ""), query)
            results = flatten_rows(body)
            results, truncated = truncate_rows(results, requested_limit)
            row_count = len(results)

            entry = cube_entry(catalog, cube) or {}
            mart_table, freshness_column = FRESHNESS_COLUMN[cube]
            dsn = self._mart_dsn()
            data_as_of_value = await data_as_of(dsn, MART_SCHEMA, mart_table, freshness_column)
            quality, quality_checks = await quality_status(dsn, DQ_TABLE, mart_table)

            requested_metrics = {}
            for member in measures or []:
                metric_name = member.split(".", 1)[-1]
                if metric_name in entry.get("measures", {}):
                    requested_metrics[metric_name] = entry["measures"][metric_name]

            sample_data = results
            file_path = None
            if context and len(results) > 24:
                file_path = context.save_data(
                    data=results,
                    schema="metrics_query_result",
                    metadata={
                        "cube": cube,
                        "query": query,
                        "row_count": row_count,
                        "registry_version": catalog.get("version", 0),
                        "quality_status": quality,
                        "data_as_of": data_as_of_value,
                    },
                )
                sample_data = results[:12] + results[-12:]

            payload = {
                "success": True,
                "data": sample_data,
                "file_path": file_path,
                "count": row_count,
                "sample_count": len(sample_data),
                "limit": requested_limit,
                "truncated": truncated,
                "cube": cube,
                "data_as_of": data_as_of_value,
                "quality_status": quality,
                "semantic_context": build_semantic_context(
                    catalog.get("version", 0), entry, requested_metrics,
                    data_as_of=data_as_of_value, include_data_as_of=True,
                    quality_status=quality, quality_checks=quality_checks,
                ),
                "summary": (
                    f"返回 {row_count} 行（数据截至 {data_as_of_value}，"
                    f"质量状态：{quality}）"
                    + (f"；已达返回上限 {requested_limit} 行，结果被截断，匹配行数更多"
                       if truncated else "")
                ),
            }
            contract_errors = validate_result(CONTRACT, "metric_query", payload)
            if contract_errors:
                logger.warning("guangdong_metric_result_contract_violation", errors=contract_errors)
            return payload
        except Exception as exc:  # noqa: BLE001
            status = "error"
            error = f"{type(exc).__name__}: {exc}"
            logger.warning("guangdong_query_metrics_failed", error=error)
            return {"success": False, "data": [], "summary": f"查询失败: {error}"}
        finally:
            await self._audit(context, cube, query, row_count, status, error,
                              truncated, int((time.monotonic() - started) * 1000))

    async def _describe(self, context, describe_cube: str) -> Dict[str, Any]:
        """语义目录按需获取（'cubes' 索引 或 单 Cube 全成员），不执行数据查询。"""
        started = time.monotonic()
        status, error = "ok", None
        try:
            catalog = load_catalog(CATALOG_PATH)
            if describe_cube.lower() in CUBE_INDEX_KEYWORDS:
                items = _cube_index(catalog)
                return {
                    "success": True,
                    "mode": "cube_index",
                    "total": len(items),
                    "cubes": items,
                    "summary": (f"共 {len(items)} 个 Cube；用 describe_cube='<Cube名>' "
                                "取该 Cube 的全部 measures/dimensions 与业务口径。"),
                }
            if describe_cube not in catalog["cubes"]:
                status = "error"
                error = f"unknown cube: {describe_cube}"
                return {"success": False, "summary": _unknown_cube_summary(catalog, describe_cube)}
            entry = cube_entry(catalog, describe_cube) or {}
            payload = {
                "success": True,
                "cube": describe_cube,
                "semantic_context": build_semantic_context(
                    catalog.get("version", 0), entry,
                    metric_definitions=entry.get("measures", {}),
                    quality_status="unknown",
                ),
                "summary": (f"{describe_cube} 成员与口径目录（registry v{catalog.get('version', 0)}），"
                            "率类指标返回百分数0-100"),
            }
            contract_errors = validate_result(CONTRACT, "metric_definition", payload)
            if contract_errors:
                logger.warning("guangdong_metric_definition_contract_violation", errors=contract_errors)
            return payload
        finally:
            await self._audit(context, describe_cube,
                              {"describe_cube": describe_cube}, 0, status, error,
                              False, int((time.monotonic() - started) * 1000))

    # ------------------------------------------------------------ 基础设施
    @staticmethod
    def _mart_dsn() -> str:
        return os.getenv("OPS_MART_DATABASE_URL", "")

    async def _audit(self, context, cube, query, row_count, status, error,
                     truncated, duration_ms) -> None:
        """Best-effort 审计（guangdong_sync 与 mart 同库, 走 OPS_MART_DATABASE_URL）。"""
        record = {
            "user_id": str(getattr(context, "user_id", "") or "") if context else "",
            "agent_mode": str(getattr(context, "agent_mode", "") or "") if context else "",
            "tool": self.tool_name,
            "dataset": f"cube:{cube}" if cube else "cube:?",
            "params": json.dumps({"query": query, "status": status},
                                 ensure_ascii=False, default=str)[:4000],
            "row_count": row_count,
            "truncated": truncated,
            "duration_ms": duration_ms,
            "error": error,
        }
        await write_audit(self._mart_dsn(), AUDIT_TABLE, record,
                          log_event="guangdong_metrics_audit_failed")
