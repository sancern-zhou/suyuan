#!/usr/bin/env python
"""江苏运维平台处置写回闭环联调脚本（仅测试环境使用）。

用法（在部署服务器、backend 目录、激活 backend_py311 后执行）：

  # 1. 创建测试工单（标题带联调标记、无 App 推送、一般紧急度）
  python scripts/jiangsu_platform_writeback_rehearsal.py create --station-code 3018A

  # 2a. 推荐：让运维单位在平台/App 正常处理，直至工单到达“省中心审核”
  # 2b. 或自动驱动中间节点（需要先用源库/ODS 查出 mtc_fault.id）：
  #   select id from mtc_fault where working_order_code = 'FA...';
  python scripts/jiangsu_platform_writeback_rehearsal.py drive --code FA... --fault-id <mtc_fault.id>

  # 3. 工单到达省中心审核后，验证写回（走 platform_workflow.submit_review_decision）：
  python scripts/jiangsu_platform_writeback_rehearsal.py write --code FA... --action approve
  python scripts/jiangsu_platform_writeback_rehearsal.py write --code FA... --action reject

  # 4. 任意时刻核对平台侧工单状态：
  python scripts/jiangsu_platform_writeback_rehearsal.py status --code FA...

  # 5. 运维告警工单联调（走真实派单链路：平台类型映射 + 先关联后建单）：
  python scripts/jiangsu_platform_writeback_rehearsal.py alarm-create \
    --station-code 3018A --order-type InstrumentFault
  python scripts/jiangsu_platform_writeback_rehearsal.py status --code YJ... \
    --order-type InstrumentFault

前置：环境需开启 JIANGSU_PLATFORM_WRITEBACK_ENABLED=true。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

WORKFLOW_PATH = "operation/WflWorkFlow/GetWorkFlowByUser"
LIST_PATH = "operation/WorkingOrder/GetMtcWorkingOrderPagedListAsync"
DETAIL_PATH = "operation/FaultOrder/GetWorkingOrderInfoByUniqueCode"
RECEIVE_PATH = "operation/WorkingOrder/ReceiveOrderAsync"
SAVE_PATH = "operation/FaultOrder/SaveOrderAsync"
CREATE_PATH = "operation/FaultOrder/CreateAsync"

MARK = "【闭环联调测试】"


def _api():
    from app.tools.jiangsu.fault_diagnosis import _JiangsuAuthenticatedApi

    return _JiangsuAuthenticatedApi(source="ops")


async def _order_row(api, code: str, order_type: str = "Fault") -> dict:
    from app.tools.jiangsu.alarm_order_types import platform_order_type_params

    payload = await api.get(LIST_PATH, [
        *platform_order_type_params(order_type),
        ("MaxResultCount", "10"), ("SkipCount", "0"),
        ("WorkingOrderCode", code),
    ])
    items = (payload.get("result") or {}).get("items") or []
    for row in items:
        if str(row.get("workingOrderCode") or "").strip() == code:
            return row
    raise SystemExit(f"平台未找到工单 {code}")


def _print_row(label: str, row: dict) -> None:
    print(label, json.dumps({
        key: row.get(key) for key in
        ("id", "workingOrderCode", "orderStatus", "workFlowStatus", "currentPoint")
    }, ensure_ascii=False))


async def create(args) -> None:
    from app.tools.jiangsu.fault_diagnosis import _resolve_station_rows
    from app.tools.jiangsu.work_order_dispatch import (
        _fetch_station_devices,
        resolve_created_order_code,
    )

    rows = await _resolve_station_rows(None, None, None, station_code=args.station_code)
    if not rows:
        raise SystemExit(f"未解析到站点 {args.station_code}")
    station = rows[0]
    api = _api()
    devices = await _fetch_station_devices(api, station["station_code"])
    if not devices:
        raise SystemExit(f"站点 {station['station_code']} 无设备台账")
    device = devices[0]
    title = f"{MARK}{station.get('station_name') or args.station_code} 处置写回链路验证"
    payload = {
        "orderType": "Fault",
        "orderTitle": title,
        "orderContent": "【事件描述】处置写回闭环联调测试工单，验证省中心审核节点通过/打回写回。",
        "otherContent": "闭环联调测试：AI 审核写回链路验证，可 ignore。",
        "urgencyType": "Normal",
        "deviceId": device["device_id"],
        "stationCodes": [station["station_code"]],
        "checkTask": ["other"],
        "planFinishTime": (datetime.now() + timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S"),
        "issuedType": [],
    }
    await api.post(CREATE_PATH, payload)
    code = await resolve_created_order_code(
        unique_code=station.get("unique_code") or "",
        order_title=title,
        created_after=datetime.now(),
    )
    print("测试工单已创建:", code or "（工单号回查失败，请用 status 子命令按标题在平台核对）")


async def drive(args) -> None:
    """自动驱动 故障处理 → 运维单位审核 两个中间节点（需要 mtc_fault.id）。"""
    api = _api()
    row = await _order_row(api, args.code)
    order_id = int(row["id"])
    workflow = await api.get(WORKFLOW_PATH, [("Type", "Fault")])
    steps = {
        str(step.get("formCode")): step
        for step in (workflow.get("result") or {}).get("stepList") or []
        if isinstance(step, dict) and step.get("formCode")
    }
    for form_code in ("FaultProcess", "FaultReview"):
        row = await _order_row(api, args.code)
        _print_row(f"[{form_code}] 提交前:", row)
        current_point = str(row.get("currentPoint") or "")
        step = steps.get(form_code)
        if step is None or str(step.get("guid")) != current_point:
            print(f"  跳过：工单当前不在 {form_code} 节点")
            continue
        if str(row.get("workFlowStatus")) in {"ToAssign", "ToAccept"}:
            await api.get(RECEIVE_PATH, [("Id", str(order_id))])
            print("  已领取节点")
        payload = {
            "guid": step.get("guid"),
            "workflowId": row.get("workFlowId") or step.get("workflowId"),
            "taskName": step.get("taskName"),
            "formCode": form_code,
            "taskPreviousId": step.get("taskPreviousId"),
            "taskNextId": step.get("taskNextId"),
            "roleId": step.get("roleId"),
            "status": True,
            "orderDetailDto": {
                "workingOrderCode": args.code,
                "processStep": form_code,
                "processStatus": True,
                "submitRemark": "闭环联调：中间节点自动驱动通过",
                "isSubmit": True,
                "isCancel": False,
            },
        }
        if form_code == "FaultProcess":
            payload["orderDetailDto"]["faultProcessType"] = 1
            payload["orderDetailDto"]["faultDto"] = {
                "id": args.fault_id, "isRemote": 0, "faultDeviceId": row.get("deviceId"),
                "workingOrderCode": args.code,
            }
        await api.post(SAVE_PATH, payload)
        print(f"  {form_code} 提交成功")
    row = await _order_row(api, args.code)
    _print_row("驱动完成:", row)


async def write(args) -> None:
    from app.tools.jiangsu.platform_workflow import submit_review_decision

    approved = args.action == "approve"
    result = await submit_review_decision(
        args.code,
        action="confirm" if approved else "reject",
        approved=approved,
        comment="闭环联调：审核节点通过" if approved else "闭环联调：退回，处置记录不完整",
    )
    print("写回结果:", json.dumps(result, ensure_ascii=False, default=str))
    api = _api()
    row = await _order_row(api, args.code)
    _print_row("平台状态:", row)


async def alarm_create(args) -> None:
    """走真实派单链路建一张运维告警工单，验证类型映射与关联去重。"""
    from app.tools.jiangsu.platform_workflow import create_smart_event_dispatch_order

    title = f"{MARK}{args.station_code} {args.order_type} 告警工单联调"
    result = await create_smart_event_dispatch_order(
        event_id="rehearsal",
        site_id=args.station_code,
        title=title,
        description="运维告警工单联调：验证平台类型枚举、先关联后建单与工单号回查。",
        order_type=args.order_type,
        event_start_time=datetime.now().astimezone().isoformat(),
    )
    print("派单结果:", json.dumps(result, ensure_ascii=False, default=str))
    if result.get("work_order_code"):
        api = _api()
        _print_row("平台状态:", await _order_row(api, result["work_order_code"], args.order_type))


async def status(args) -> None:
    api = _api()
    row = await _order_row(api, args.code, args.order_type)
    _print_row("平台状态:", row)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create", help="创建测试工单")
    p.add_argument("--station-code", required=True, help="平台站点编码，如 3018A")
    p = sub.add_parser("drive", help="自动驱动故障处理/运维单位审核节点")
    p.add_argument("--code", required=True)
    p.add_argument("--fault-id", type=int, required=True, help="mtc_fault 主键（源库/ODS 查询）")
    p = sub.add_parser("write", help="省中心审核节点写回（通过/打回）")
    p.add_argument("--code", required=True)
    p.add_argument("--action", choices=["approve", "reject"], required=True)
    p = sub.add_parser("status", help="查询平台工单状态")
    p.add_argument("--code", required=True)
    p.add_argument("--order-type", default="Fault",
                   choices=["Fault", "PersonIntrusion", "FogCannon", "InstrumentFault"])
    p = sub.add_parser("alarm-create", help="创建运维告警工单（真实派单链路）")
    p.add_argument("--station-code", required=True, help="平台站点编码，如 3018A")
    p.add_argument("--order-type", required=True,
                   choices=["PersonIntrusion", "FogCannon", "InstrumentFault"])
    args = parser.parse_args()
    asyncio.run({
        "create": create, "drive": drive, "write": write, "status": status,
        "alarm-create": alarm_create,
    }[args.command](args))


if __name__ == "__main__":
    main()
