"""江苏运维指标语义层查询工具（Cube Core REST / 127.0.0.1:4610）。

DEPLOYMENT ADDITION (2026-10-02): serves the jiangsu-cube semantic layer
(E:\\Tools\\suyuan-jiangsu\\cube, Cube Core 0.35). The agent asks for
*metrics* (measures + dimensions + time range) instead of writing SQL —
metric definitions live exactly once in the semantic layer, so the same
question always yields the same number.

口径一致性: 本文件的 CATALOG 必须与 sync/datasets/*.yaml、dbt models、
cube/schema/*.js 三方保持一致（盘点底稿 E:\\Tools\\suyuan-jiangsu\\指标口径盘点.md）。
查询走 JWT（CUBE_API_SECRET），连库侧仍是 agent_reader 只读，无新增数据库权限；
每次调用审计入 jiangsu_sync.query_audit。
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
# datasets/*.yaml ↔ dbt models ↔ cube/schema/*.js ↔ 此处。
CATALOG: Dict[str, Dict[str, List[Dict[str, str]]]] = {
    # WorkOrder 仅覆盖故障工单(宽表过滤 ordertype='Fault'); 例行单不入宽表, 巡检走 Inspection。
    # 响应/恢复类指标依赖故障单流程节点(FaultProcess)与关联告警, 定义上即故障单专属;
    # 全部指标结论均须注明为故障单口径(2026-10-06 收敛)。
    "WorkOrder": {
        "measures": [
            {"name": "count", "title": "故障工单量(仅Fault类型)"},
            {"name": "overdueCount", "title": "超期故障工单数(故障单无计划完成时间,恒0不可评估,勿用)"},
            {"name": "overdueRate", "title": "超期率%(故障单无计划完成时间,恒0;历史~85%系含例行单旧口径,勿用)"},
            {"name": "responseEvaluable", "title": "可评估响应的故障工单数(故障单均有到场节点,全量可评估)"},
            {"name": "responseWithin2hCount", "title": "2小时内到场故障工单数"},
            {"name": "responseWithin2hRate", "title": "2小时响应率%(故障单全量可评估)"},
            {"name": "recoverEvaluable", "title": "可评估恢复的故障工单数(有已解除关联告警,约47%)"},
            {"name": "recoverWithin4hCount", "title": "4小时内恢复故障工单数"},
            {"name": "recoverWithin4hRate", "title": "4小时恢复率%(分母=可评估单约47%,须注明占比)"},
            {"name": "repeatFaultCount", "title": "30天重复故障工单数"},
            {"name": "repeatFaultRate", "title": "30天重复故障率%"},
            {"name": "avgResponseMinutes", "title": "平均响应时长(分钟)"},
            {"name": "avgProcessMinutes", "title": "平均处理时长(分钟)"},
            {"name": "avgRepairMinutes", "title": "平均修复时长(分钟)"},
            {"name": "avgLinkedAlarms1d", "title": "平均关联告警数(建单前24h)"},
        ],
        "dimensions": [
            {"name": "cityName", "title": "城市名"},
            {"name": "cityCode", "title": "城市行政区码"},
            {"name": "stationCode", "title": "站点编码"},
            {"name": "stationName", "title": "站点名"},
            {"name": "stationTypeName", "title": "站点类型(省控站/省建站/省乡镇站/国控站等; 按站点类型统计用本维度)"},
            {"name": "orderStatus", "title": "工单状态(处理中/已完成)"},
            {"name": "urgency", "title": "紧急程度"},
            {"name": "orderType", "title": "工单类型(本cube仅故障单Fault,保留作口径核对)"},
            {"name": "isOverdue", "title": "是否超期(故障单无计划完成时间,恒false不可评估,勿用)"},
            {"name": "isRepeatFault", "title": "是否重复故障"},
            {"name": "repeatBasis", "title": "重复故障判定维度(故障单均填设备,恒为站点+设备)"},
            {"name": "createTime", "title": "创建时间(时间维度)"},
            {"name": "finishTime", "title": "完成时间(时间维度)"},
        ],
    },
    "AlarmEvent": {
        "measures": [
            {"name": "count", "title": "告警量"},
            {"name": "unresolvedCount", "title": "未处理告警数"},
            {"name": "unresolvedRate", "title": "未处理率%"},
            {"name": "convertedCount", "title": "转化工单的告警数(24h内同站建单)"},
            {"name": "toWorkOrderRate", "title": "告警转工单率%(代理口径)"},
            {"name": "avgDurationMinutes", "title": "平均告警持续分钟(已解除)"},
            {"name": "avgHandleMinutes", "title": "平均处理时长分钟(已处理)"},
        ],
        "dimensions": [
            {"name": "cityName", "title": "城市名"},
            {"name": "stationCode", "title": "站点编码"},
            {"name": "stationName", "title": "站点名"},
            {"name": "alarmLevel", "title": "告警级别(紧急/中级/一般)"},
            {"name": "alarmState", "title": "处理状态(未处理/已解除)"},
            {"name": "ruleType", "title": "告警规则类型"},
            {"name": "isUnresolved", "title": "是否未处理"},
            {"name": "alarmTime", "title": "告警时间(时间维度)"},
        ],
    },
    "StationAlarmLog": {
        "measures": [
            {"name": "count", "title": "站房/仪器告警量(2026-07起,本地区步链)"},
            {"name": "severeCount", "title": "严重告警量"},
            {"name": "urgentCount", "title": "紧急告警量"},
            {"name": "unresolvedCount", "title": "未恢复告警量"},
        ],
        "dimensions": [
            {"name": "cityName", "title": "城市名"},
            {"name": "stationCode", "title": "站点编码"},
            {"name": "stationName", "title": "站点名"},
            {"name": "alarmGrade", "title": "告警级别(提示/一般/严重/紧急)"},
            {"name": "alarmType", "title": "告警类型编码(平台内部码)"},
            {"name": "subcatalog", "title": "告警子类"},
            {"name": "source", "title": "告警来源"},
            {"name": "alarmStatus", "title": "告警状态(平台原值)"},
            {"name": "description", "title": "告警描述"},
            {"name": "alarmTime", "title": "告警时间(时间维度)"},
        ],
    },
    "QcTaskStatus": {
        "measures": [
            {"name": "count", "title": "质控任务量(快照数,2026-07起)"},
        ],
        "dimensions": [
            {"name": "cityName", "title": "城市名"},
            {"name": "stationCode", "title": "站点编码"},
            {"name": "stationName", "title": "站点名"},
            {"name": "poll", "title": "监测项"},
            {"name": "qcType", "title": "质控类型"},
            {"name": "rStart", "title": "任务开始时间(时间维度)"},
            {"name": "rid", "title": "任务标识 rId"},
        ],
    },
    "StationEnvPower": {
        "measures": [
            {"name": "count", "title": "动环数据点数"},
            {"name": "avgValue", "title": "平均动环值(数值点)"},
            {"name": "maxValue", "title": "最大动环值"},
            {"name": "minValue", "title": "最小动环值"},
        ],
        "dimensions": [
            {"name": "cityName", "title": "城市名"},
            {"name": "stationCode", "title": "站点编码"},
            {"name": "stationName", "title": "站点名"},
            {"name": "pollutantCode", "title": "动环指标编码"},
            {"name": "timePoint", "title": "数据时间点(时间维度)"},
            {"name": "mark", "title": "平台原始标记"},
        ],
    },
    "QcAirData": {
        "measures": [
            {"name": "count", "title": "质控曲线点数"},
            {"name": "avgDataValue", "title": "平均监测值(数值点)"},
            {"name": "maxDataValue", "title": "最大监测值"},
            {"name": "minDataValue", "title": "最小监测值"},
        ],
        "dimensions": [
            {"name": "cityName", "title": "城市名"},
            {"name": "stationCode", "title": "站点编码"},
            {"name": "stationName", "title": "站点名"},
            {"name": "poll", "title": "监测项"},
            {"name": "qcType", "title": "质控类型"},
            {"name": "timePoint", "title": "监测时间点(时间维度)"},
            {"name": "unit", "title": "单位"},
            {"name": "isQCing", "title": "质控进行中"},
        ],
    },
    "QcRunLog": {
        "measures": [
            {"name": "count", "title": "运行日志条数(2026-07起)"},
            {"name": "errorCount", "title": "错误事件数"},
            {"name": "warnCount", "title": "警告事件数"},
        ],
        "dimensions": [
            {"name": "stationCode", "title": "站点编码"},
            {"name": "stationName", "title": "站点名"},
            {"name": "rid", "title": "任务标识 rId"},
            {"name": "poll", "title": "监测项"},
            {"name": "qcType", "title": "质控类型"},
            {"name": "strEvent", "title": "事件分类(提示/警告/错误)"},
            {"name": "target", "title": "执行环节"},
            {"name": "userName", "title": "操作用户"},
            {"name": "recordTime", "title": "事件时间(时间维度)"},
        ],
    },
    "QcExecution": {
        "measures": [
            {"name": "count", "title": "质控执行量"},
            {"name": "assessedCount", "title": "已判定数(合格+不合格)"},
            {"name": "qualifiedCount", "title": "合格数"},
            {"name": "qualifiedRate", "title": "质控合格率%(平台判定文本,不重算)"},
            {"name": "avgInaccuracy", "title": "平均不准确度"},
        ],
        "dimensions": [
            {"name": "cityName", "title": "城市名"},
            {"name": "stationCode", "title": "站点编码"},
            {"name": "stationName", "title": "站点名"},
            {"name": "pollutant", "title": "污染物"},
            {"name": "taskType", "title": "任务类型(零点/跨度/O3/校准类)"},
            {"name": "resultCn", "title": "判定文本"},
            {"name": "isQualified", "title": "是否合格"},
            {"name": "qcDate", "title": "质控日期(时间维度)"},
        ],
    },
    "Inspection": {
        "measures": [
            {"name": "count", "title": "巡检任务项数"},
            {"name": "finishedCount", "title": "已完成数"},
            {"name": "finishedRate", "title": "巡检完成率%"},
            {"name": "overdueCount", "title": "超期数"},
            {"name": "overdueRate", "title": "巡检超期率%"},
            {"name": "linkedOrderCount", "title": "转工单数"},
            {"name": "toWorkOrderRate", "title": "巡检转工单率%"},
        ],
        "dimensions": [
            {"name": "cityName", "title": "城市名"},
            {"name": "stationCode", "title": "站点编码"},
            {"name": "stationName", "title": "站点名"},
            {"name": "stationTypeName", "title": "站点类型(省控站/省乡镇站/省建站等; 约37%任务项非省控站, 按类型统计用本维度)"},
            {"name": "ruleType", "title": "周期类型(周/月/季/半年/年巡检)"},
            {"name": "statusCn", "title": "状态(未开始/处理中/已完成)"},
            {"name": "isFinished", "title": "是否完成"},
            {"name": "isOverdue", "title": "是否超期"},
            {"name": "taskDate", "title": "任务日期(时间维度)"},
        ],
    },
    # ---- 扩展 cube(2026-10-07): 存量宽表接入语义目录 ----
    # StationHealth 为当前态势快照(一行=一个站点), 工单侧统计仅故障单口径(Fault)。
    "StationHealth": {
        "measures": [
            {"name": "count", "title": "站点数"},
            {"name": "highRiskCount", "title": "高风险站点数(当前快照)"},
            {"name": "midRiskCount", "title": "中风险站点数(当前快照)"},
            {"name": "totalOrders30d", "title": "近30天故障工单总数(站点合计)"},
            {"name": "totalOverdue30d", "title": "近30天超期故障工单总数(故障单无计划完成时间,恒0勿用)"},
            {"name": "totalRepeatFault30d", "title": "近30天重复故障工单总数(站点合计)"},
            {"name": "avgOverdueRate30d", "title": "近30天超期率均值%(故障单无计划完成时间,恒0勿用)"},
            {"name": "avgResponseMinutes30d", "title": "近30天平均响应时长分钟(仅可评估站点,覆盖率约15%)"},
            {"name": "totalAlarms7d", "title": "近7天告警总数(站点合计)"},
            {"name": "totalAlarms30d", "title": "近30天告警总数(站点合计)"},
            {"name": "totalUnresolvedAlarms", "title": "未处理告警总数(站点合计)"},
        ],
        "dimensions": [
            {"name": "cityName", "title": "城市名"},
            {"name": "stationCode", "title": "站点编码"},
            {"name": "stationName", "title": "站点名"},
            {"name": "riskLevel", "title": "风险分级(高/中/低/稳定)"},
            {"name": "stationStatus", "title": "站点启用状态"},
            {"name": "isMonitor", "title": "是否监测站"},
            {"name": "lastAlarmTime", "title": "最近告警时间(时间维度)"},
        ],
    },
    # StationDaily 为站点×日趋势(2026-06-01 起, 当日数据次日刷新才完整, 签到源数据稀疏)。
    "StationDaily": {
        "measures": [
            {"name": "count", "title": "站点日数(活跃站点日)"},
            {"name": "activeStations", "title": "活跃站点数(去重)"},
            {"name": "createdSum", "title": "新建故障工单数"},
            {"name": "finishedSum", "title": "完成故障工单数"},
            {"name": "overdueCreatedSum", "title": "新建且超期故障工单数(故障单无计划完成时间,恒0勿用)"},
            {"name": "alarmsSum", "title": "告警数"},
            {"name": "signinsSum", "title": "到站签到数(源数据稀疏)"},
        ],
        "dimensions": [
            {"name": "profileDate", "title": "日期(时间维度)"},
            {"name": "cityName", "title": "城市名"},
            {"name": "stationCode", "title": "站点编码"},
            {"name": "stationName", "title": "站点名"},
        ],
    },
    # DeviceLifecycle 为设备生命周期事件(状态变更日志+报废审批), working_order_code 关联故障工单。
    "DeviceLifecycle": {
        "measures": [
            {"name": "count", "title": "生命周期事件数"},
            {"name": "distinctDevices", "title": "涉及设备数(去重)"},
            {"name": "startEvents", "title": "启用事件数"},
            {"name": "repairEvents", "title": "维修事件数"},
            {"name": "stopEvents", "title": "停用事件数"},
            {"name": "scrapEvents", "title": "报废审批事件数"},
        ],
        "dimensions": [
            {"name": "cityName", "title": "城市名"},
            {"name": "cityCode", "title": "城市行政区码"},
            {"name": "stationCode", "title": "站点编码"},
            {"name": "stationName", "title": "站点名"},
            {"name": "deviceCode", "title": "设备编码"},
            {"name": "deviceTypeName", "title": "设备类型名(如O3分析仪)"},
            {"name": "eventType", "title": "事件动作(启用/维修/停用等)"},
            {"name": "stateAfter", "title": "变更后状态(DeviceNormal/DeviceFault/DeviceSpare等)"},
            {"name": "eventSource", "title": "事件来源(log_device状态日志/dev_scrap报废审批)"},
            {"name": "eventTime", "title": "事件时间(时间维度)"},
        ],
    },
    # QcArrangement 只回答质控任务安排与过期积压; 执行结果(合格判定)走 QcExecution。
    "QcArrangement": {
        "measures": [
            {"name": "count", "title": "质控任务数"},
            {"name": "expiredCount", "title": "已过期任务数"},
            {"name": "waitingCount", "title": "等待中任务数"},
            {"name": "runningCount", "title": "运行中任务数"},
            {"name": "deletedCount", "title": "已删除任务数"},
        ],
        "dimensions": [
            {"name": "cityName", "title": "城市名"},
            {"name": "cityCode", "title": "城市行政区码"},
            {"name": "stationCode", "title": "站点编码"},
            {"name": "stationName", "title": "站点名"},
            {"name": "pollutant", "title": "污染物"},
            {"name": "taskType", "title": "任务类型"},
            {"name": "statusCn", "title": "安排状态(已过期/等待中/运行中/任务已删除)"},
            {"name": "plannedTime", "title": "计划执行时间(时间维度)"},
        ],
    },
}

# 每个 cube 对应的宽表新鲜度列(用于返回 data_as_of)
FRESHNESS_COLUMN: Dict[str, Tuple[str, str]] = {
    "WorkOrder": ("mart_work_order_analysis", "refreshed_at"),
    "AlarmEvent": ("mart_alarm_event_analysis", "refreshed_at"),
    "QcExecution": ("mart_qc_execution_analysis", "synced_at"),
    "Inspection": ("mart_inspection_analysis", "synced_at"),
    "StationHealth": ("mart_station_device_health", "refreshed_at"),
    "StationDaily": ("mart_station_daily_profile", "refreshed_at"),
    "DeviceLifecycle": ("mart_device_lifecycle_analysis", "synced_at"),
    "QcArrangement": ("mart_qc_arrangement_analysis", "synced_at"),
    "StationAlarmLog": ("mart_station_alarm_log", "synced_at"),
    "QcTaskStatus": ("mart_qc_task_status_result", "synced_at"),
    "QcAirData": ("mart_qc_air_data_result", "synced_at"),
    "QcRunLog": ("mart_qc_run_log_result", "synced_at"),
    "StationEnvPower": ("mart_station_env_power", "synced_at"),
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
    lines.append("数据窗口: 2026-06-01 起。获取率/有效率/传输率是平台统计口径,不在本工具,"
                 "用 jiangsu_query_statistics。考核两率窗口内无实际填报。")
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


class JiangsuQueryMetricsTool(LLMTool):
    """经语义层查询江苏运维指标（口径唯一,免写SQL）。"""

    DEFAULT_LIMIT = 50
    MAX_LIMIT = 1000

    def __init__(self):
        self.tool_name = "jiangsu_query_metrics"
        function_schema = {
            "name": self.tool_name,
            "description": (
                "查询江苏运维指标(语义层,口径唯一):故障工单量/2h响应率/4h恢复率/重复故障率、"
                "告警量/未处理率/转工单率、质控合格率、巡检完成率/超期率、站点健康与风险分级、"
                "站点日趋势(工单/告警计数)、设备生命周期事件、质控任务安排与过期积压等。"
                "注意: 工单超期对故障单不适用(无计划完成时间,恒0),工单超期统计勿用本工具的 WorkOrder.overdueRate。"
                "传 measures+dimensions+时间范围即可,不需要写SQL;"
                "同一问题的数字与 execute_jiangsu_mart_sql 口径一致。"
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
                        "description": "(可选)分组维度,如 ['WorkOrder.cityName']",
                    },
                    "time_dimension": {
                        "type": "string",
                        "description": "(可选)时间维度成员,如 'WorkOrder.createTime'",
                    },
                    "date_range": {
                        "description": "(可选)'last 7 days'等关键字,或 ['2026-09-01','2026-09-30']",
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
            description="查询江苏运维指标(语义层REST,口径唯一,免SQL)",
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
                    logger.warning("jiangsu_metric_definition_contract_violation", errors=contract_errors)
                return payload
            finally:
                await self._audit(context, describe_cube,
                                  {"describe_cube": describe_cube}, 0, status, error,
                                  int((time.monotonic() - started) * 1000))
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
        query["limit"] = min(limit or self.DEFAULT_LIMIT, self.MAX_LIMIT)

        started = time.monotonic()
        status, error, row_count = "ok", None, 0
        try:
            base_url = os.getenv("CUBE_API_URL", "http://127.0.0.1:4610/cubejs-api/v1")
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
                ),
            }
            contract_errors = validate_result("metric_query", payload)
            if contract_errors:
                logger.warning("jiangsu_metric_result_contract_violation", errors=contract_errors)
            return payload
        except Exception as exc:  # noqa: BLE001
            status = "error"
            error = f"{type(exc).__name__}: {exc}"
            logger.warning("jiangsu_query_metrics_failed", error=error)
            return {"success": False, "data": [], "summary": f"查询失败: {error}"}
        finally:
            await self._audit(context, cube, query, row_count, status, error,
                              int((time.monotonic() - started) * 1000))

    async def _data_as_of(self, cube: str) -> Optional[str]:
        """宽表新鲜度(与 SQL 工具同源);失败不阻塞查询。"""
        try:
            import asyncpg
            dsn = os.getenv("OPS_MART_DATABASE_URL", "")
            if not dsn:
                return None
            table, column = FRESHNESS_COLUMN[cube]
            conn = await asyncpg.connect(dsn)
            try:
                return await conn.fetchval(
                    f"SELECT max({column})::text FROM jiangsu_mart.{table}")
            finally:
                await conn.close()
        except Exception:  # noqa: BLE001
            return None

    async def _quality_status(self, cube: str) -> Tuple[str, List[Dict[str, str]]]:
        """Read the latest DQ gate results without blocking a metric query."""
        table_info = FRESHNESS_COLUMN.get(cube)
        dsn = os.getenv("OPS_MART_DATABASE_URL", "")
        if not table_info or not dsn:
            return "unknown", []
        try:
            import asyncpg
            conn = await asyncpg.connect(dsn)
            try:
                rows = await conn.fetch(
                    """
                    SELECT DISTINCT ON (check_name) check_name, status, detail
                    FROM jiangsu_sync.dq_results
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
            logger.warning("jiangsu_query_metrics_quality_unavailable", error=str(exc))
            return "unknown", []

    async def _audit(self, context, cube, query, row_count, status, error,
                     duration_ms) -> None:
        """Best-effort 审计;失败只记日志。"""
        try:
            import asyncpg
            app_dsn = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")
            if not app_dsn:
                return
            conn = await asyncpg.connect(app_dsn)
            try:
                await conn.execute(
                    """INSERT INTO jiangsu_sync.query_audit
                       (user_id, agent_mode, tool, dataset, params, rows_returned,
                        truncated, duration_ms, error)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
                    str(getattr(context, "user_id", "") or "") if context else "",
                    str(getattr(context, "agent_mode", "") or "") if context else "",
                    self.tool_name,
                    f"cube:{cube}" if cube else "cube:?",
                    json.dumps({"query": query, "status": status},
                               ensure_ascii=False, default=str)[:4000],
                    row_count,
                    False,
                    duration_ms,
                    error,
                )
            finally:
                await conn.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("jiangsu_metrics_audit_failed", error=str(exc))
