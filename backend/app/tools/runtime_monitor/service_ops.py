"""服务级操作工具（P0 自主重启 / 健康核实）。

restart_service 的放行链（缺一不可，全部运行时硬校验）：
1. 门禁：仅运行监控定时任务上下文可调用；
2. 实时判级：调用 severity.classify_current_severity() 对**当时**的数据
   重新判级，P0 才放行——即使 prompt 被注入或模型声称重大，规则不命中
   就不执行；结果与理由随返回，供推送时向人解释"为什么重启了"；
3. 缰绳：Redis 冷却（同 service 10 分钟）+ 每日上限（5 次），与应用侧
   独立于守护进程侧的再兜底；
4. 执行：请求宿主机维护守护进程（restart → 健康等待 → 不健康自动回滚
   git 快照并再重启）；守护进程不可达时拒绝动作而非盲报成功。

verify_service_health 供修复后核实与 P1 流程"修复+测试已完成，等待人
决定重启"的证据采集，无 P0 门禁（只读探测）。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Dict

import structlog

from app.tools.base import LLMTool, ToolCategory

logger = structlog.get_logger(__name__)

RESTART_COOLDOWN_SECONDS = 600
RESTART_DAILY_LIMIT = 5
_ALLOWED_SERVICES = {"web", "worker", "all"}


def _daemon_endpoint() -> tuple[str, str]:
    """返回 (base_url, token)；未配置 token 时返回 ("", "") 表示不可用。"""
    from config.settings import settings

    base = str(
        os.getenv("MAINTENANCE_DAEMON_URL")
        or getattr(settings, "maintenance_daemon_url", "")
        or "http://host.docker.internal:8013"
    ).rstrip("/")
    token = str(
        os.getenv("MAINTENANCE_DAEMON_TOKEN")
        or getattr(settings, "maintenance_daemon_token", "")
        or ""
    )
    return base, token


def _post(base: str, token: str, path: str, payload: dict, timeout: int = 240) -> dict:
    request = urllib.request.Request(
        base + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-maintenance-token": token,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _get(base: str, token: str, path: str, timeout: int = 30) -> dict:
    request = urllib.request.Request(
        base + path, headers={"x-maintenance-token": token}, method="GET"
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _gate_scheduled_context(context) -> str | None:
    scheduled = getattr(context, "scheduled_task_context", None)
    if isinstance(scheduled, dict) and scheduled.get("task_id"):
        return None
    return "当前不是定时任务执行上下文，不能执行服务级操作"


def acquire_source_snapshot(label: str = "") -> dict:
    """让守护进程对当前仓库打 git 快照（供回滚）。

    供源码修复授权路径在首次写源码前调用；守护进程不可达时返回失败，
    调用方应拒绝继续修改源码（没有快照的源码修改等于不可回滚）。
    """
    base, token = _daemon_endpoint()
    if not token:
        return {"success": False, "error": "维护守护进程未配置 token"}
    try:
        result = _post(base, token, "/snapshot", {"label": label}, timeout=60)
        result["success"] = True
        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("source_snapshot_failed", error=str(exc))
        return {"success": False, "error": f"快照请求失败：{exc}"}


async def _check_restart_reins(service: str) -> str | None:
    from app.monitoring.anomaly_emitter import get_redis_client

    try:
        client = get_redis_client()
        acquired = await client.set(
            f"monitor:svcrestart:cd:{service}", "1",
            nx=True, ex=RESTART_COOLDOWN_SECONDS,
        )
        if not acquired:
            return f"{service} 处于重启冷却期（{RESTART_COOLDOWN_SECONDS // 60} 分钟内最多一次）"
        day_key = (
            f"monitor:svcrestart:day:{service}:{datetime.now().strftime('%Y%m%d')}"
        )
        used = int(await client.incr(day_key))
        if used == 1:
            await client.expire(day_key, 86400)
        if used > RESTART_DAILY_LIMIT:
            return (
                f"{service} 今日重启已达上限（{RESTART_DAILY_LIMIT} 次），"
                "连续重启无效，需人工介入"
            )
        return None
    except Exception as exc:  # noqa: BLE001 - 缰绳不可用时拒绝动手
        return f"重启缰绳（Redis）不可用，为避免失去约束拒绝执行：{exc}"


class RestartServiceTool(LLMTool):
    """Restart web/worker via the host maintenance daemon (P0-gated)."""

    def __init__(self):
        function_schema = {
            "name": "restart_service",
            "description": (
                "重启 web/worker 服务（P0 级故障的最终处置动作）。"
                "仅运行监控任务可调用；工具内部会用确定性规则对当前实时数据"
                "重新判级，只有 P0（抓取器大面积瘫痪/任务失败风暴/会话错误风暴）"
                "才放行，并携带冷却与每日次数上限；重启后自动核实健康，"
                "不健康则自动回滚修复前的 git 快照。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "enum": ["web", "worker", "all"],
                        "description": "要重启的服务",
                    },
                    "reason": {
                        "type": "string",
                        "description": "重启理由（将写入日志与推送通报）",
                    },
                    "snapshot_id": {
                        "type": "string",
                        "description": "修复前获取的 git 快照 ID（有源码修改时必传，供失败自动回滚）",
                    },
                },
                "required": ["service", "reason"],
            },
        }
        super().__init__(
            name="restart_service",
            description="重启服务（P0 硬门禁 + 缰绳 + 自动健康核实与回滚）",
            category=ToolCategory.TASK_MANAGEMENT,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True,
        )

    async def execute(self, context=None, service: str = "", reason: str = "",
                      snapshot_id: str = "", **kwargs) -> Dict[str, Any]:
        if gate := _gate_scheduled_context(context):
            return {"status": "failed", "success": False, "data": {}, "summary": gate}
        service = (service or "").strip().lower()
        if service not in _ALLOWED_SERVICES:
            return {
                "status": "failed", "success": False, "data": {},
                "summary": "service 必须是 web/worker/all",
            }
        if not (reason or "").strip():
            return {
                "status": "failed", "success": False, "data": {},
                "summary": "缺少 reason（重启必须留痕说明）",
            }

        # 门禁 1：实时重判 P0（不信任调用方声称）
        from app.monitoring.severity import classify_current_severity

        verdict = await classify_current_severity()
        if verdict["severity"] != "p0":
            return {
                "status": "failed",
                "success": False,
                "data": {"severity": verdict},
                "summary": (
                    f"实时判级为 {verdict['severity']}，未达 P0 自主重启标准，"
                    "不执行重启（如确认需要重启，请推送待人工确认）。"
                    f"判级依据：{'; '.join(verdict['reasons']) or '无 P0 规则命中'}"
                ),
            }

        # 门禁 2：缰绳
        rein = await _check_restart_reins(service)
        if rein:
            return {"status": "failed", "success": False, "data": {}, "summary": rein}

        # 门禁 3：守护进程可达且已配置
        base, token = _daemon_endpoint()
        if not token:
            return {
                "status": "failed", "success": False, "data": {},
                "summary": "维护守护进程未配置（MAINTENANCE_DAEMON_TOKEN 为空），无重启执行通道",
            }

        payload: dict = {"service": service, "reason": reason[:300]}
        if snapshot_id:
            payload["snapshot_id"] = snapshot_id
        try:
            result = _post(base, token, "/restart", payload)
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("error", "")
            except Exception:  # noqa: BLE001
                detail = str(exc)
            return {
                "status": "failed", "success": False, "data": {},
                "summary": f"守护进程拒绝重启：{detail}",
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "failed", "success": False, "data": {},
                "summary": f"守护进程不可达，未执行重启：{exc}",
            }

        logger.warning(
            "service_restarted",
            service=service,
            reason=reason[:200],
            severity_reasons=verdict["reasons"],
            result=result,
        )
        results = result.get("results") or []
        healthy = all(r.get("healthy") for r in results) if results else False
        rolled = any(r.get("rolled_back") for r in results)
        summary = (
            f"已重启 {service}（P0 依据：{'；'.join(verdict['reasons'])}）。"
            + ("重启后健康核实通过。" if healthy else "重启后健康核实未通过！")
            + (" 已自动回滚修复快照。" if rolled else "")
        )
        return {
            "status": "success",
            "success": True,
            "data": {"service": service, "healthy": healthy, "rolled_back": rolled, "results": results},
            "summary": summary,
        }


class VerifyServiceHealthTool(LLMTool):
    """Probe configured service health endpoints (read-only)."""

    def __init__(self):
        function_schema = {
            "name": "verify_service_health",
            "description": (
                "探测 web/worker 服务健康端点（只读）。用于修复后核实、"
                "以及向人提交'待生效'修复前的证据采集。"
            ),
            "parameters": {"type": "object", "properties": {}},
        }
        super().__init__(
            name="verify_service_health",
            description="探测服务健康端点（只读）",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True,
        )

    async def execute(self, context=None, **kwargs) -> Dict[str, Any]:
        if gate := _gate_scheduled_context(context):
            return {"status": "failed", "success": False, "data": {}, "summary": gate}
        base, token = _daemon_endpoint()
        if not token:
            # 无守护进程时退化为容器内本地探测
            probes = {
                "web": "http://127.0.0.1:8000/health",
                "worker": "http://127.0.0.1:8011/health",
            }
        else:
            try:
                status = _get(base, token, "/status")
                return {
                    "status": "success",
                    "success": True,
                    "data": status,
                    "summary": f"健康状态：{status.get('health')}",
                }
            except Exception as exc:  # noqa: BLE001
                return {
                    "status": "failed", "success": False, "data": {},
                    "summary": f"守护进程不可达：{exc}",
                }
        results = {}
        for name, url in probes.items():
            try:
                request = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(request, timeout=8) as response:
                    results[name] = "up" if 200 <= response.status < 300 else f"http {response.status}"
            except Exception as exc:  # noqa: BLE001
                results[name] = f"down: {exc}"[:80]
        all_up = all(v == "up" for v in results.values())
        return {
            "status": "success",
            "success": True,
            "data": results,
            "summary": "全部健康" if all_up else f"存在异常：{results}",
        }


restart_service_tool = RestartServiceTool()
verify_service_health_tool = VerifyServiceHealthTool()
