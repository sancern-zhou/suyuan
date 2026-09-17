"""Demo data tools for the Jiangsu operations-analysis scenarios.

These tools return a fixed, pre-built August-2026 dataset (see
``demo_data/august_2026.json``) covering business domains the platform does
not expose through real APIs yet: operation plans, personnel certificates,
performance two-rates, operation approvals, door remote-open logs, standard
materials, QC pass-rate statistics and attendance sign-ins.  Every tool marks
its output as demo data so reports can disclose the data source.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.jiangsu.demo_data import demo_section, load_demo_dataset

logger = structlog.get_logger(__name__)

_DEMO_NOTE = "演示数据（2026-08 预设数据集，非平台真实接口）"


def _match(value: Any, expected: str | None) -> bool:
    if not expected:
        return True
    return str(value or "").find(expected.strip()) >= 0


class _JiangsuDemoDataTool(LLMTool):
    """Base class for demo-dataset backed read-only query tools."""

    section_key: str = ""

    def __init__(
        self,
        *,
        name: str,
        description: str,
        function_schema: dict[str, Any],
    ) -> None:
        super().__init__(
            name=name,
            description=description,
            category=ToolCategory.QUERY,
            version="1.0.0",
            function_schema=function_schema,
            requires_context=False,
        )

    def _build_result(
        self,
        rows: list[dict[str, Any]],
        *,
        query: dict[str, Any],
        label: str,
    ) -> dict[str, Any]:
        meta = load_demo_dataset().get("meta") or {}
        return {
            "status": "success" if rows else "empty",
            "success": True,
            "data": rows,
            "metadata": {
                "source": "jiangsu_demo_static_dataset",
                "demo": True,
                "dataset_id": meta.get("dataset_id"),
                "period": meta.get("period"),
                "endpoint": f"demo_data/august_2026.json#{self.section_key}",
                "query": query,
                "record_count": len(rows),
                "queried_at": meta.get("generated_at"),
            },
            "summary": (
                f"{label}查询完成（{_DEMO_NOTE}）：返回 {len(rows)} 条。"
                "该数据为演示预设数据，不代表平台真实记录。"
            ),
        }


class JiangsuDemoOperationPlansTool(_JiangsuDemoDataTool):
    """运维计划管理（演示）：计划类型、应执行次数、执行次数。"""

    section_key = "operation_plans"

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_demo_operation_plans",
            description="查询江苏运维计划管理演示数据：站点月度运维计划、计划类型、应执行/已执行次数；支持按站点、城市、单位、计划类型过滤。",
            function_schema={
                "name": "jiangsu_demo_operation_plans",
                "description": "读取 2026-08 运维计划演示数据集（固定编造数据，用于场景演示）。",
                "parameters": {"type": "object", "properties": {
                    "station_code": {"type": "string", "description": "可选站点编码。"},
                    "city_name": {"type": "string", "description": "可选城市名称，支持模糊匹配。"},
                    "operation_unit": {"type": "string", "description": "可选运维单位名称，支持模糊匹配。"},
                    "plan_type": {"type": "string", "description": "可选计划类型。"},
                }, "required": []},
            },
        )

    async def execute(self, context=None, station_code: str | None = None, city_name: str | None = None,
                      operation_unit: str | None = None, plan_type: str | None = None, **_: Any) -> dict[str, Any]:
        rows = demo_section(self.section_key)
        rows = [
            row for row in rows
            if _match(row.get("station_code"), station_code)
            and _match(row.get("city_name"), city_name)
            and _match(row.get("operation_unit"), operation_unit)
            and _match(row.get("plan_type"), plan_type)
        ]
        return self._build_result(rows, query={
            "station_code": station_code, "city_name": city_name,
            "operation_unit": operation_unit, "plan_type": plan_type,
        }, label="运维计划")


class JiangsuDemoAttendanceSigninsTool(_JiangsuDemoDataTool):
    """运维考勤签到（演示）：签到站点、时间、经纬度、距站距离。"""

    section_key = "attendance_signins"

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_demo_attendance_signins",
            description="查询江苏运维考勤签到演示数据：签到人员、站点、时间、经纬度、距站点距离；支持按人员、站点、单位、时间范围过滤。",
            function_schema={
                "name": "jiangsu_demo_attendance_signins",
                "description": "读取 2026-08 运维考勤签到演示数据集（固定编造数据，真实考勤接口 8 月无数据时用于演示）。",
                "parameters": {"type": "object", "properties": {
                    "user_name": {"type": "string", "description": "可选人员姓名，支持模糊匹配。"},
                    "station_code": {"type": "string", "description": "可选站点编码。"},
                    "unit_name": {"type": "string", "description": "可选运维单位名称，支持模糊匹配。"},
                    "start_time": {"type": "string", "description": "可选起始时间 YYYY-MM-DD HH:mm:ss。"},
                    "end_time": {"type": "string", "description": "可选结束时间 YYYY-MM-DD HH:mm:ss。"},
                }, "required": []},
            },
        )

    async def execute(self, context=None, user_name: str | None = None, station_code: str | None = None,
                      unit_name: str | None = None, start_time: str | None = None,
                      end_time: str | None = None, **_: Any) -> dict[str, Any]:
        rows = demo_section(self.section_key)

        def in_range(row: dict[str, Any]) -> bool:
            ts = str(row.get("sign_in_time") or "").replace("T", " ")
            if start_time and ts < start_time.replace("T", " ").replace("T", " "):
                return False
            if end_time and ts > end_time.replace("T", " "):
                return False
            return True

        rows = [
            row for row in rows
            if _match(row.get("user_name"), user_name)
            and _match(row.get("station_code"), station_code)
            and _match(row.get("unit_name"), unit_name)
            and in_range(row)
        ]
        return self._build_result(rows, query={
            "user_name": user_name, "station_code": station_code,
            "unit_name": unit_name, "start_time": start_time, "end_time": end_time,
        }, label="运维考勤签到")


class JiangsuDemoPersonnelCertificatesTool(_JiangsuDemoDataTool):
    """人员证书（演示）：上岗证编号、发证/有效期、状态。"""

    section_key = "personnel_certificates"

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_demo_personnel_certificates",
            description="查询江苏运维人员持证情况演示数据：是否持证、上岗证编号、发证日期、有效期、状态（有效/已过期/30天内到期/无证）；支持按人员、单位、状态过滤。",
            function_schema={
                "name": "jiangsu_demo_personnel_certificates",
                "description": "读取运维人员证书演示数据集（固定编造数据，人员姓名为虚构）。",
                "parameters": {"type": "object", "properties": {
                    "person_name": {"type": "string", "description": "可选人员姓名，支持模糊匹配。"},
                    "unit_name": {"type": "string", "description": "可选运维单位名称，支持模糊匹配。"},
                    "status": {"type": "string", "description": "可选证书状态：有效/已过期/30天内到期/无证。"},
                }, "required": []},
            },
        )

    async def execute(self, context=None, person_name: str | None = None, unit_name: str | None = None,
                      status: str | None = None, **_: Any) -> dict[str, Any]:
        rows = demo_section(self.section_key)
        rows = [
            row for row in rows
            if _match(row.get("person_name"), person_name)
            and _match(row.get("unit_name"), unit_name)
            and _match(row.get("status"), status)
        ]
        return self._build_result(rows, query={
            "person_name": person_name, "unit_name": unit_name, "status": status,
        }, label="人员证书")


class JiangsuDemoPerformanceTwoRatesTool(_JiangsuDemoDataTool):
    """绩效两率得分（演示）：数据获取率、数据有效率、质控合格率、两率得分。"""

    section_key = "performance_two_rates"

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_demo_performance_two_rates",
            description="查询江苏站点绩效两率演示数据：数据获取率、数据有效率、质控合格率、两率得分及达标情况；支持按站点、城市、单位、是否达标过滤。",
            function_schema={
                "name": "jiangsu_demo_performance_two_rates",
                "description": "读取站点绩效两率演示数据集（固定编造数据）。",
                "parameters": {"type": "object", "properties": {
                    "station_code": {"type": "string", "description": "可选站点编码。"},
                    "city_name": {"type": "string", "description": "可选城市名称，支持模糊匹配。"},
                    "operation_unit": {"type": "string", "description": "可选运维单位名称，支持模糊匹配。"},
                    "below_threshold_only": {"type": "boolean", "description": "仅返回低于考核阈值的站点。", "default": False},
                }, "required": []},
            },
        )

    async def execute(self, context=None, station_code: str | None = None, city_name: str | None = None,
                      operation_unit: str | None = None, below_threshold_only: bool = False, **_: Any) -> dict[str, Any]:
        rows = demo_section(self.section_key)
        rows = [
            row for row in rows
            if _match(row.get("station_code"), station_code)
            and _match(row.get("city_name"), city_name)
            and _match(row.get("operation_unit"), operation_unit)
            and (row.get("below_threshold") if below_threshold_only else True)
        ]
        return self._build_result(rows, query={
            "station_code": station_code, "city_name": city_name,
            "operation_unit": operation_unit, "below_threshold_only": below_threshold_only,
        }, label="绩效两率")


class JiangsuDemoQcPassRateStatsTool(_JiangsuDemoDataTool):
    """合格率统计（演示）：站点月度质控合格率与近 3 月趋势。"""

    section_key = "qc_pass_rate_stats"

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_demo_qc_pass_rate_stats",
            description="查询江苏站点质控合格率统计演示数据：当月质控试验次数、合格次数、近 3 月合格率趋势；支持按站点过滤。",
            function_schema={
                "name": "jiangsu_demo_qc_pass_rate_stats",
                "description": "读取站点质控合格率统计演示数据集（固定编造数据）。",
                "parameters": {"type": "object", "properties": {
                    "station_code": {"type": "string", "description": "可选站点编码。"},
                }, "required": []},
            },
        )

    async def execute(self, context=None, station_code: str | None = None, **_: Any) -> dict[str, Any]:
        rows = demo_section(self.section_key)
        rows = [row for row in rows if _match(row.get("station_code"), station_code)]
        return self._build_result(rows, query={"station_code": station_code}, label="质控合格率统计")


class JiangsuDemoOperationApprovalsTool(_JiangsuDemoDataTool):
    """运维报备审批单（演示）：计划性运维/校准/停电维护报备。"""

    section_key = "operation_approvals"

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_demo_operation_approvals",
            description="查询江苏运维报备审批单演示数据：计划性运维、校准作业、停电维护报备的申请人与审批状态；支持按站点、单位、类型过滤。",
            function_schema={
                "name": "jiangsu_demo_operation_approvals",
                "description": "读取运维报备审批单演示数据集（固定编造数据）。",
                "parameters": {"type": "object", "properties": {
                    "station_code": {"type": "string", "description": "可选站点编码。"},
                    "operation_unit": {"type": "string", "description": "可选运维单位名称，支持模糊匹配。"},
                    "apply_type": {"type": "string", "description": "可选报备类型。"},
                }, "required": []},
            },
        )

    async def execute(self, context=None, station_code: str | None = None,
                      operation_unit: str | None = None, apply_type: str | None = None, **_: Any) -> dict[str, Any]:
        rows = demo_section(self.section_key)
        rows = [
            row for row in rows
            if _match(row.get("station_code"), station_code)
            and _match(row.get("operation_unit"), operation_unit)
            and _match(row.get("apply_type"), apply_type)
        ]
        return self._build_result(rows, query={
            "station_code": station_code, "operation_unit": operation_unit, "apply_type": apply_type,
        }, label="运维报备审批单")


class JiangsuDemoDoorRemoteOpenLogsTool(_JiangsuDemoDataTool):
    """门禁远程开门操作日志（演示）：操作人、站点、时间、事由。"""

    section_key = "door_remote_open_logs"

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_demo_door_remote_open_logs",
            description="查询江苏门禁远程开门操作日志演示数据：操作人、站点、开门时间、操作类型与事由；支持按站点、操作人、时间范围过滤。",
            function_schema={
                "name": "jiangsu_demo_door_remote_open_logs",
                "description": "读取门禁远程开门操作日志演示数据集（固定编造数据）。",
                "parameters": {"type": "object", "properties": {
                    "station_code": {"type": "string", "description": "可选站点编码。"},
                    "operator_name": {"type": "string", "description": "可选操作人姓名，支持模糊匹配。"},
                    "start_time": {"type": "string", "description": "可选起始时间 YYYY-MM-DD HH:mm:ss。"},
                    "end_time": {"type": "string", "description": "可选结束时间 YYYY-MM-DD HH:mm:ss。"},
                }, "required": []},
            },
        )

    async def execute(self, context=None, station_code: str | None = None, operator_name: str | None = None,
                      start_time: str | None = None, end_time: str | None = None, **_: Any) -> dict[str, Any]:
        rows = demo_section(self.section_key)

        def in_range(row: dict[str, Any]) -> bool:
            ts = str(row.get("open_time") or "").replace("T", " ")
            if start_time and ts < start_time.replace("T", " "):
                return False
            if end_time and ts > end_time.replace("T", " "):
                return False
            return True

        rows = [
            row for row in rows
            if _match(row.get("station_code"), station_code)
            and _match(row.get("operator_name"), operator_name)
            and in_range(row)
        ]
        return self._build_result(rows, query={
            "station_code": station_code, "operator_name": operator_name,
            "start_time": start_time, "end_time": end_time,
        }, label="门禁远程开门日志")


class JiangsuDemoStandardMaterialsTool(_JiangsuDemoDataTool):
    """运维标准物质（演示）：标气/校准设备台账、有效期、库存状态。"""

    section_key = "standard_materials"

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_demo_standard_materials",
            description="查询江苏运维标准物质演示数据：标准气体、校准设备的编号、有效期、检定日期、库存状态；支持按单位、类别、状态过滤。",
            function_schema={
                "name": "jiangsu_demo_standard_materials",
                "description": "读取运维标准物质演示数据集（固定编造数据）。",
                "parameters": {"type": "object", "properties": {
                    "operation_unit": {"type": "string", "description": "可选运维单位名称，支持模糊匹配。"},
                    "category": {"type": "string", "description": "可选类别：标气/校准设备。"},
                    "status": {"type": "string", "description": "可选状态：正常/已过期/库存不足。"},
                }, "required": []},
            },
        )

    async def execute(self, context=None, operation_unit: str | None = None, category: str | None = None,
                      status: str | None = None, **_: Any) -> dict[str, Any]:
        rows = demo_section(self.section_key)
        rows = [
            row for row in rows
            if _match(row.get("operation_unit"), operation_unit)
            and _match(row.get("category"), category)
            and _match(row.get("status"), status)
        ]
        return self._build_result(rows, query={
            "operation_unit": operation_unit, "category": category, "status": status,
        }, label="运维标准物质")


DEMO_DATA_TOOLS: list[type[_JiangsuDemoDataTool]] = [
    JiangsuDemoOperationPlansTool,
    JiangsuDemoAttendanceSigninsTool,
    JiangsuDemoPersonnelCertificatesTool,
    JiangsuDemoPerformanceTwoRatesTool,
    JiangsuDemoQcPassRateStatsTool,
    JiangsuDemoOperationApprovalsTool,
    JiangsuDemoDoorRemoteOpenLogsTool,
    JiangsuDemoStandardMaterialsTool,
]
