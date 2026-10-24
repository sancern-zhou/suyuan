"""广东运维指标语义层查询工具（Cube Core REST / 127.0.0.1:4611）。

DEPLOYMENT ADDITION (2026-10-24): serves the guangdong-cube semantic layer
(projects/guangdong/data-ops/cube, Cube Core 0.35). The agent asks for
*metrics* (measures + dimensions + time range) instead of writing SQL —
metric definitions live exactly once in the semantic layer, so the same
question always yields the same number. 对齐江苏 jiangsu_cube_metrics 模式。

口径一致性: 本文件的 CATALOG 必须与 sync/datasets/mart_work_order_analysis.yaml、
dbt models、cube/schema/*.js 四方保持一致（校验见
projects/guangdong/data-ops/semantic/validate_registry.py）。
查询走 JWT（CUBE_API_SECRET），连库侧仍是 agent_reader 只读，无新增数据库权限；
每次调用审计入 guangdong_sync.query_audit。
"""

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

import httpx
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from .semantic_registry import cube_metadata
from .result_contract import validate_result
from .quality_policy import quality_guidance

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()

# ---------------------------------------------------------------- 语义目录
# 单一事实源(本文件内): 结构化目录 → 渲染进工具描述。改口径时四处同步:
# datasets/mart_work_order_analysis.yaml ↔ dbt models ↔ cube/schema/*.js ↔ 此处。
CATALOG: Dict[str, Dict[str, List[Dict[str, str]]]] = {
    # WorkOrder 覆盖全类型运维工单(含作废单)。与江苏(仅故障单)不同:
    # 广东工单有计划完成时间, 超期可评估(分母=计划时间非空单);
    # 响应类指标仅故障单可评估(到站=首个 FaultProcess 步骤开始)。
    "WorkOrder": {
        "measures": [
            {"name": "count", "title": "工单量(全类型含作废,结论须声明口径)"},
            {"name": "finishedCount", "title": "已完成工单数"},
            {"name": "finishRate", "title": "完成率%(分母含作废单,剔除作废配合orderStatus过滤)"},
            {"name": "overdueEvaluable", "title": "超期可评估工单数(计划完成时间非空)"},
            {"name": "overdueCount", "title": "超期工单数"},
            {"name": "overdueRate", "title": "超期率%(分母=计划完成时间非空单;例行维护单该口径失真,超期以orderOvertime为准)"},
            {"name": "responseEvaluable", "title": "可评估响应的工单数(故障单)"},
            {"name": "responseWithin2hCount", "title": "2小时内到站故障工单数"},
            {"name": "responseWithin2hRate", "title": "2小时响应率%(仅故障单可评估)"},
            {"name": "faultCount", "title": "故障工单数(Fault/SupFault)"},
            {"name": "repeatFaultCount", "title": "30天重复故障工单数"},
            {"name": "repeatFaultRate", "title": "30天重复故障率%(分母=故障单)"},
            {"name": "hasAttachmentCount", "title": "有附件的工单数"},
            {"name": "attachmentRate", "title": "附件完整率%(有附件工单/工单数)"},
            {"name": "avgResponseMinutes", "title": "平均响应时长(分钟,仅故障单)"},
            {"name": "avgProcessMinutes", "title": "平均到站后处理时长(分钟)"},
            {"name": "avgRepairMinutes", "title": "平均全程修复时长(分钟)"},
            {"name": "avgNodeCount", "title": "平均流转节点数"},
            {"name": "avgExpense", "title": "平均工单费用(元)"},
        ],
        "dimensions": [
            {"name": "orderType", "title": "工单类型代码(28种,字典见 ops 提示词语义字典)"},
            {"name": "orderStatus", "title": "工单状态(已完成/处理中/待处理/已作废)"},
            {"name": "urgency", "title": "紧急程度"},
            {"name": "maintenanceType", "title": "维护周期(周/月/双周/季/半年/日/年/按需)"},
            {"name": "orderOvertime", "title": "源系统超时标记(原文;例行单超期以本标记为准,勿用overdueRate)"},
            {"name": "totalOvertime", "title": "源系统累计超时标记(原文)"},
            {"name": "stationCode", "title": "站点编码"},
            {"name": "stationName", "title": "站点名"},
            {"name": "stationType", "title": "站点类型(源库代码原文)"},
            {"name": "stationTypeName", "title": "站点类型中文名(经alm_home补充,覆盖率以推送为准)"},
            {"name": "cityName", "title": "城市名(经alm_home补充,覆盖率以推送为准)"},
            {"name": "cityCode", "title": "城市行政区码(经alm_home补充)"},
            {"name": "regionId", "title": "区域ID(无区域字典)"},
            {"name": "deviceCode", "title": "设备编码"},
            {"name": "deviceType", "title": "设备类型(源库代码原文)"},
            {"name": "isFinish", "title": "是否已完成"},
            {"name": "isOverdue", "title": "是否超期(仅计划完成时间非空的单有意义)"},
            {"name": "isRepeatFault", "title": "是否30天内重复故障(仅故障单口径)"},
            {"name": "createTime", "title": "创建时间(时间维度)"},
            {"name": "finishTime", "title": "完成时间(时间维度)"},
        ],
    },
    # ---- 一期扩展 cube(2026-10-25): 告警/设备生命周期/巡检任务/态势快照 ----
    "AlarmNotify": {
        "measures": [
            {"name": "count", "title": "告警通知量"},
            {"name": "distinctStationCount", "title": "涉及站点数(去重)"},
            {"name": "distinctDayCount", "title": "涉及天数(去重)"},
        ],
        "dimensions": [
            {"name": "alarmType", "title": "告警类型(站点断数等,自CONTENT解析)"},
            {"name": "cityName", "title": "城市名(经alm_home补充,覆盖率以推送为准)"},
            {"name": "stationTypeName", "title": "站点类型中文名"},
            {"name": "stationCode", "title": "站点编码"},
            {"name": "stationName", "title": "站点名"},
            {"name": "notifyChannels", "title": "发送渠道(SMS,Mail等)"},
            {"name": "notifyTime", "title": "告警时间(时间维度)"},
        ],
    },
    "StationAlarmStatus": {
        "measures": [
            {"name": "count", "title": "快照站点数(覆盖面以源系统推送为准)"},
            {"name": "alarmingCount", "title": "当前告警站点数(状态≠正常)"},
        ],
        "dimensions": [
            {"name": "alarmStatus", "title": "告警状态(正常/紧急)"},
            {"name": "isAlarming", "title": "是否告警中"},
            {"name": "cityName", "title": "城市名"},
            {"name": "stationTypeName", "title": "站点类型中文名"},
            {"name": "stationCode", "title": "站点编码"},
            {"name": "stationName", "title": "站点名"},
            {"name": "managerName", "title": "运维管理人"},
            {"name": "latestAlarmDesc", "title": "最新告警描述"},
            {"name": "latestAlarmTime", "title": "最新告警时间(时间维度)"},
        ],
    },
    "DeviceLifecycle": {
        "measures": [
            {"name": "count", "title": "生命周期事件数"},
            {"name": "distinctDevices", "title": "涉及设备数(去重)"},
            {"name": "checkEventCount", "title": "周期检查事件数(周/月/季/半年/年检)"},
            {"name": "lifecycleEventCount", "title": "启用/新增/停用/更新事件数"},
            {"name": "stopEventCount", "title": "停用事件数"},
        ],
        "dimensions": [
            {"name": "eventType", "title": "事件动作(原文:WeekCheck等)"},
            {"name": "eventTypeCn", "title": "事件动作中文(周检/月检/季检/启用/停用等)"},
            {"name": "stateAfter", "title": "变更后状态(DeviceNormal/DeviceSpare等)"},
            {"name": "cityName", "title": "城市名(经alm_home补充)"},
            {"name": "stationCode", "title": "站点编码"},
            {"name": "stationName", "title": "站点名"},
            {"name": "deviceCode", "title": "设备编码"},
            {"name": "deviceType", "title": "设备类型(源库代码原文)"},
            {"name": "orderRef", "title": "关联工单"},
            {"name": "eventTime", "title": "事件时间(时间维度)"},
        ],
    },
    "InspectionTask": {
        "measures": [
            {"name": "count", "title": "任务项数"},
            {"name": "finishedCount", "title": "已完成任务项数"},
            {"name": "finishedRate", "title": "完成率%"},
            {"name": "overdueCount", "title": "超期任务项数(未完成且过计划结束日)"},
            {"name": "overdueRate", "title": "超期率%(分母=全部任务项)"},
            {"name": "toOrderCount", "title": "已转工单任务项数"},
            {"name": "toOrderRate", "title": "转工单率%(分母=全部任务项)"},
            {"name": "distinctStations", "title": "涉及站点数(去重)"},
        ],
        "dimensions": [
            {"name": "cityName", "title": "城市名(经alm_home补充,覆盖率以推送为准)"},
            {"name": "stationCode", "title": "站点编码"},
            {"name": "stationName", "title": "站点名"},
            {"name": "ruleName", "title": "规则名"},
            {"name": "ruleType", "title": "规则类型"},
            {"name": "ruleCycle", "title": "周期(周/月/季等)"},
            {"name": "itemFormTag", "title": "表单类型(RF_W_GaseousCheck等)"},
            {"name": "pollutantType", "title": "监测项目(SO2/NOX/O3等)"},
            {"name": "isFinished", "title": "是否已完成"},
            {"name": "isOverdue", "title": "是否已超期"},
            {"name": "isToOrder", "title": "是否已转工单"},
            {"name": "planDate", "title": "计划日期(时间维度)"},
            {"name": "finishDatetime", "title": "完成时间(时间维度)"},
        ],
    },
}

# 每个 cube 对应的宽表新鲜度列(用于返回 data_as_of)
FRESHNESS_COLUMN: Dict[str, Tuple[str, str]] = {
    "WorkOrder": ("mart_work_order_analysis", "refreshed_at"),
    "AlarmNotify": ("mart_alarm_notify_analysis", "refreshed_at"),
    "StationAlarmStatus": ("mart_station_alarm_status", "refreshed_at"),
    "DeviceLifecycle": ("mart_device_lifecycle_analysis", "refreshed_at"),
    "InspectionTask": ("mart_inspection_task_analysis", "refreshed_at"),
}

ALLOWED_FILTER_OPERATORS = {
    "equals", "notEquals", "contains", "notContains", "in", "notIn",
    "afterDate", "beforeDate", "set", "notSet",
}


def _render_guide() -> str:
    lines = ["", "【语义目录】(成员名 = Cube.成员; 率类指标返回百分数0-100)"]
    for cube, parts in CATALOG.items():
        lines.append(f"\n■ {cube}")
        lines.append("  度量(measures): " + "; ".join(
            f"{m['name']}={m['title']}" for m in parts["measures"]))
        lines.append("  维度(dimensions): " + "; ".join(
            f"{d['name']}={d['title']}" for d in parts["dimensions"]))
    lines.append("")
    lines.append("数据窗口: 今年窗口+持续增量(full_load_since={year_start}-01-01,每年滚动),"
                 "窗口前历史不可查。工单量结论必须声明口径"
                 "(全类型含作废/已完成/故障单); 实时在办状态用 execute_ops_sql_query 直查源库。")
    return "\n".join(lines)


def _make_token(secret: str, ttl_seconds: int = 300) -> str:
    """HS256 JWT（Cube API_SECRET 鉴权, 短时效, 每次调用现签）。"""
    def b64url(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    header = b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = b64url(json.dumps({"exp": int(time.time()) + ttl_seconds}).encode())
    sig = b64url(hmac.new(secret.encode(), f"{header}.{payload}".encode(),
                          hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


class GuangdongQueryMetricsTool(LLMTool):
    """经语义层查询广东运维指标（口径唯一,免写SQL）。"""

    DEFAULT_LIMIT = 50
    MAX_LIMIT = 1000

    def __init__(self):
        self.tool_name = "guangdong_query_metrics"
        function_schema = {
            "name": self.tool_name,
            "description": (
                "查询广东运维指标(语义层,口径唯一):工单量/完成率/超期率/2小时响应率/30天重复故障率/附件完整率、"
                "告警通知量与站点覆盖(AlarmNotify)、当前告警站点态势(StationAlarmStatus)、"
                "设备周期检查与启停事件(DeviceLifecycle)、巡检任务完成率/超期率/转工单率(InspectionTask)。"
                "注意: 工单量与时效结论必须按工单类型与状态声明口径(全类型含作废);"
                "工单超期率分母只计有计划完成时间的单;响应类指标仅故障单可评估;"
                "告警通知无处理状态,未处理率不可评估。"
                "传 measures+dimensions+时间范围即可,不需要写SQL;"
                "同一问题的数字与 execute_guangdong_mart_sql 口径一致。"
                "返回结果包含 semantic_context：指标定义、粒度、适用范围、数据时点、质量状态和限制，"
                "生成结论前必须结合这些解释元数据判断是否可评估。"
                + _render_guide()
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
                        "description": "(可选)只查询某个Cube的指标定义、粒度和适用范围，不执行数据查询",
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
            version="1.0.0",
            requires_context=True,
        )

    # ------------------------------------------------------------ 校验
    def _member_cube(self, member: str, kind: str) -> Optional[str]:
        if "." not in member:
            return None
        cube, name = member.split(".", 1)
        part = CATALOG.get(cube)
        if not part:
            return None
        key = "measures" if kind == "measure" else "dimensions"
        if name not in {m["name"] for m in part[key]}:
            return None
        return cube

    def _validate(self, measures, dimensions, time_dimension, filters):
        if not measures:
            return None, "measures 不能为空"
        cubes = set()
        for m in measures:
            c = self._member_cube(m, "measure")
            if c is None:
                return None, f"未知度量 {m}(不在语义目录中)"
            cubes.add(c)
        for d in dimensions or []:
            c = self._member_cube(d, "dimension")
            if c is None:
                return None, f"未知维度 {d}(不在语义目录中)"
            cubes.add(c)
        if time_dimension:
            c = self._member_cube(time_dimension, "dimension")
            if c is None:
                return None, f"未知时间维度 {time_dimension}"
            cubes.add(c)
        for f in filters or []:
            member = f.get("member", "")
            c = self._member_cube(member, "dimension")
            if c is None:
                return None, f"过滤条件成员未知或不是维度: {member}"
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
            started = time.monotonic()
            status, error = "ok", None
            try:
                if describe_cube not in CATALOG:
                    status = "error"
                    error = f"unknown cube: {describe_cube}"
                    return {"success": False, "summary": f"未知 Cube: {describe_cube}。允许: {', '.join(CATALOG)}"}
                semantic = cube_metadata(describe_cube, CATALOG)
                payload = {
                    "success": True,
                    "cube": describe_cube,
                    "semantic_context": {
                        "registry_version": semantic.get("registry_version", 0),
                        "dataset": semantic.get("dataset"),
                        "grain": semantic.get("grain"),
                        "applicability": semantic.get("applicability"),
                        "source_window": semantic.get("source_window"),
                        "freshness_slo": semantic.get("freshness_slo"),
                        "limitations": semantic.get("limitations", []),
                        "metric_definitions": semantic.get("measures", {}),
                        "quality_guidance": quality_guidance("unknown"),
                    },
                    "summary": f"{describe_cube} 指标定义（registry v{semantic.get('registry_version', 0)}）",
                }
                contract_errors = validate_result("metric_definition", payload)
                if contract_errors:
                    logger.warning("guangdong_metric_definition_contract_violation", errors=contract_errors)
                return payload
            finally:
                await self._audit(context, describe_cube,
                                  {"describe_cube": describe_cube}, 0, status, error,
                                  False, int((time.monotonic() - started) * 1000))
        cube, err = self._validate(measures, dimensions, time_dimension, filters)
        if err:
            return {"success": False, "data": None, "summary": f"参数校验失败: {err}"}

        query: Dict[str, Any] = {"measures": measures}
        if dimensions:
            query["dimensions"] = dimensions
        if time_dimension:
            td: Dict[str, Any] = {"dimension": time_dimension}
            if date_range:
                td["dateRange"] = date_range
            if granularity:
                td["granularity"] = granularity
            query["timeDimensions"] = [td]
        if filters:
            query["filters"] = filters
        if order:
            query["order"] = order
        requested_limit = min(limit or self.DEFAULT_LIMIT, self.MAX_LIMIT)
        # 多取一行用于判定结果是否被截断
        query["limit"] = requested_limit + 1

        started = time.monotonic()
        status, error, row_count = "ok", None, 0
        truncated = False
        try:
            base_url = os.getenv("CUBE_API_URL", "http://127.0.0.1:4611/cubejs-api/v1")
            secret = os.getenv("CUBE_API_SECRET", "")
            if not secret:
                raise RuntimeError("CUBE_API_SECRET 未配置(语义层鉴权)")

            token = _make_token(secret)
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{base_url}/load",
                    json={"query": query},
                    headers={"Authorization": token},
                )
                if resp.status_code != 200:
                    detail = resp.text[:500]
                    raise RuntimeError(f"语义层返回 {resp.status_code}: {detail}")
                body = resp.json()
                if "error" in body:
                    raise RuntimeError(f"语义层错误: {body['error']}")

            results = [
                {k: (v.get("value") if isinstance(v, dict) else v)
                 for k, v in row.items()}
                for row in body.get("data", [])
            ]
            truncated = len(results) > requested_limit
            results = results[:requested_limit]
            row_count = len(results)
            data_as_of = await self._data_as_of(cube)
            quality_status, quality_checks = await self._quality_status(cube)
            semantic = cube_metadata(cube, CATALOG)
            requested_metrics = {}
            for member in measures or []:
                metric_name = member.split(".", 1)[-1]
                if metric_name in semantic.get("measures", {}):
                    requested_metrics[metric_name] = semantic["measures"][metric_name]

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
                        "registry_version": semantic.get("registry_version", 0),
                        "quality_status": quality_status,
                        "data_as_of": data_as_of,
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
                "data_as_of": data_as_of,
                "quality_status": quality_status,
                "semantic_context": {
                    "registry_version": semantic.get("registry_version", 0),
                    "dataset": semantic.get("dataset"),
                    "grain": semantic.get("grain"),
                    "applicability": semantic.get("applicability"),
                    "source_window": semantic.get("source_window"),
                    "freshness_slo": semantic.get("freshness_slo"),
                    "data_as_of": data_as_of,
                    "limitations": semantic.get("limitations", []),
                    "metric_definitions": requested_metrics,
                    "quality_checks": quality_checks,
                    "quality_guidance": quality_guidance(quality_status),
                },
                "summary": (
                    f"返回 {row_count} 行（数据截至 {data_as_of}，"
                    f"质量状态：{quality_status}）"
                    + (f"；已达返回上限 {requested_limit} 行，结果被截断，匹配行数更多"
                       if truncated else "")
                ),
            }
            contract_errors = validate_result("metric_query", payload)
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

    async def _mart_dsn(self) -> str:
        return os.getenv("OPS_MART_DATABASE_URL", "")

    async def _data_as_of(self, cube: str) -> Optional[str]:
        """宽表新鲜度(与 SQL 工具同源);失败不阻塞查询。"""
        try:
            import asyncpg
            dsn = await self._mart_dsn()
            if not dsn:
                return None
            table, column = FRESHNESS_COLUMN[cube]
            conn = await asyncpg.connect(dsn)
            try:
                return await conn.fetchval(
                    f"SELECT max({column})::text FROM guangdong_mart.{table}")
            finally:
                await conn.close()
        except Exception:  # noqa: BLE001
            return None

    async def _quality_status(self, cube: str) -> Tuple[str, List[Dict[str, str]]]:
        """Read the latest DQ gate results without blocking a metric query."""
        table_info = FRESHNESS_COLUMN.get(cube)
        dsn = await self._mart_dsn()
        if not table_info or not dsn:
            return "unknown", []
        try:
            import asyncpg
            conn = await asyncpg.connect(dsn)
            try:
                rows = await conn.fetch(
                    """
                    SELECT DISTINCT ON (check_name) check_name, status, detail
                    FROM guangdong_sync.dq_results
                    WHERE table_name = $1
                    ORDER BY check_name, checked_at DESC
                    """,
                    table_info[0],
                )
            finally:
                await conn.close()
            checks = [
                {"check": row["check_name"], "status": row["status"], "detail": row["detail"]}
                for row in rows
            ]
            if not checks:
                return "unknown", []
            statuses = {item["status"] for item in checks}
            if "FAIL" in statuses:
                return "blocked", checks
            if "WARN" in statuses:
                return "degraded", checks
            return "ok", checks
        except Exception as exc:  # noqa: BLE001
            logger.warning("guangdong_query_metrics_quality_unavailable", error=str(exc))
            return "unknown", []

    async def _audit(self, context, cube, query, row_count, status, error,
                     truncated, duration_ms) -> None:
        """Best-effort 审计（guangdong_sync 与 mart 同库, 走 OPS_MART_DATABASE_URL）; 失败只记日志。"""
        try:
            import asyncpg
            dsn = await self._mart_dsn()
            if not dsn:
                return
            conn = await asyncpg.connect(dsn)
            try:
                await conn.execute(
                    """INSERT INTO guangdong_sync.query_audit
                       (user_id, agent_mode, tool, dataset, params, row_count,
                        truncated, duration_ms, error)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
                    str(getattr(context, "user_id", "") or "") if context else "",
                    str(getattr(context, "agent_mode", "") or "") if context else "",
                    self.tool_name,
                    f"cube:{cube}" if cube else "cube:?",
                    json.dumps({"query": query, "status": status},
                               ensure_ascii=False, default=str)[:4000],
                    row_count,
                    truncated,
                    duration_ms,
                    error,
                )
            finally:
                await conn.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("guangdong_metrics_audit_failed", error=str(exc))
