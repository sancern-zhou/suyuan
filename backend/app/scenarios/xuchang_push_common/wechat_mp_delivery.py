"""微信公众号订阅通知投递层：角色受众 → 绑定 openid → 订阅通知。

与微信群 RPA 队列（xuchang_station_deviation/wechat_push_queue）平行的
第三渠道：身份复用 APP 账号受众组（audiences.py 不改），公众号 openid
是账号的附加绑定（social 目录 wechat_mp_bindings.json，绑定靠扫码
qrscene_bind:<账号>）。订阅通知模板只放 5 个左右短字段，这里只发摘要
提醒，完整通报仍走微信群/APP；本渠道整体 try/except 隔离，失败不影响
其他渠道。

模板配置（场景 kind → template_id + 字段 key 顺序）查找顺序与
push_audiences.json 同款约定：
    1. 环境变量 XUCHANG_WECHAT_MP_TEMPLATES 指向的 JSON 路径
    2. 数据登记目录下的 wechat_mp_templates.json
文件缺失或场景未配置 template_id 时跳过公众号渠道并记日志（不视为错误）。
field_keys 按申请到的模板字段顺序配置（如 thing1/time2/phrase3），
调用方按语义顺序传入 fields 值列表，两者按位 zip。
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from app.scenarios.xuchang_push_common.audiences import resolve_audience_accounts
from app.utils.path_config import get_data_registry

logger = structlog.get_logger()

TEMPLATES_FILE_ENV = "XUCHANG_WECHAT_MP_TEMPLATES"
TEMPLATES_FILE_NAME = "wechat_mp_templates.json"

# 微信侧"用户未订阅/拒收"错误码：回写绑定状态，避免反复空发。
ERRCODE_NOT_SUBSCRIBED = "43101"
ERRCODE_UNFOLLOWED = "43104"


def load_wechat_mp_templates(
    registry_root: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """加载场景 → 模板配置（template_id + field_keys）。缺失返回空表。"""
    candidates: list[Path] = []
    env_path = os.getenv(TEMPLATES_FILE_ENV)
    if env_path:
        candidates.append(Path(env_path))
    try:
        candidates.append(
            Path(registry_root) / TEMPLATES_FILE_NAME
            if registry_root is not None
            else get_data_registry() / TEMPLATES_FILE_NAME
        )
    except Exception:  # pragma: no cover - registry 未配置时视为未配置模板
        pass
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError):
            continue
        if isinstance(data, dict):
            return {
                str(kind): value
                for kind, value in data.items()
                if isinstance(value, dict) and str(value.get("template_id") or "").strip()
            }
    return {}


def _zip_fields(
    field_keys: list[str], values: list[str], kind: str
) -> dict[str, str]:
    fields = {
        key: str(value)[:40]
        for key, value in zip(field_keys, values)
        if str(key).strip() and str(value or "").strip()
    }
    if len(field_keys) != len(values):
        logger.warning(
            "wechat_mp_fields_length_mismatch",
            kind=kind,
            field_keys=len(field_keys),
            values=len(values),
        )
    return fields


async def push_wechat_mp_notice(
    kind: str,
    *,
    fields: list[str],
    roles: list[str] | tuple[str, ...] | None = None,
    accounts: list[str] | None = None,
    client: Any | None = None,
    binding_store: Any | None = None,
    registry_root: Path | None = None,
) -> dict[str, Any]:
    """向受众组的公众号绑定用户发送一条订阅通知摘要。

    返回聚合结果（enabled/configured/sent/failed/skipped），异常向上抛出
    由调用方隔离；单用户失败只计入 failed，不中断其余用户。
    """
    from app.social.wechat_mp.bindings import WechatMpBindingStore, normalize_account
    from app.social.wechat_mp.client import get_wechat_mp_client

    if client is None:
        client = get_wechat_mp_client()
    store = binding_store or WechatMpBindingStore()

    result: dict[str, Any] = {
        "enabled": bool(client.enabled),
        "configured": False,
        "kind": kind,
        "sent": 0,
        "failed": 0,
        "skipped": 0,
    }
    if not client.enabled:
        return result

    templates = await asyncio.to_thread(load_wechat_mp_templates, registry_root)
    entry = templates.get(kind)
    template_id = str((entry or {}).get("template_id") or "").strip()
    field_keys = [str(k).strip() for k in (entry or {}).get("field_keys") or [] if str(k).strip()]
    if not template_id or not field_keys:
        logger.info("wechat_mp_template_not_configured", kind=kind)
        return result
    result["configured"] = True
    result["template_id"] = template_id

    audience: list[str] = []
    if accounts:
        for account in accounts:
            name = normalize_account(account)
            if name and name not in audience:
                audience.append(name)
    if roles:
        audience_ids = await asyncio.to_thread(resolve_audience_accounts, list(roles))
        for user_id in audience_ids:
            name = normalize_account(user_id)
            if name and name not in audience:
                audience.append(name)
    if not audience:
        logger.info("wechat_mp_audience_empty", kind=kind)
        return result
    result["audience"] = len(audience)

    recipients: list[tuple[str, dict[str, str]]] = []
    openids: dict[str, str] = {}  # openid → account
    for account in audience:
        row = await store.get(account)
        if not row or not str(row.get("openid") or "").strip():
            result["skipped"] += 1
            continue
        if str(row.get("status")) != "bound":
            result["skipped"] += 1
            continue
        templates_state = row.get("templates")
        if isinstance(templates_state, dict) and templates_state.get(template_id) == "reject":
            result["skipped"] += 1
            continue
        openid = str(row["openid"])
        recipients.append((openid, _zip_fields(field_keys, fields, kind)))
        openids[openid] = account
    if not recipients:
        logger.info("wechat_mp_no_bound_recipients", kind=kind, audience=len(audience))
        return result

    send_results = await client.send_subscribe_batch(
        template_id=template_id, recipients=recipients
    )
    for row in send_results:
        openid = str(row.get("openid") or "")
        account = openids.get(openid, "")
        errcode = str(row.get("errcode"))
        if errcode == "0":
            result["sent"] += 1
            if account:
                await store.record_push(account)
        elif errcode == ERRCODE_UNFOLLOWED:
            result["failed"] += 1
            await store.mark_unsubscribed(openid)
        elif errcode == ERRCODE_NOT_SUBSCRIBED:
            result["failed"] += 1
            await store.record_template_state(openid, template_id, "reject")
        else:
            result["failed"] += 1
        if errcode != "0":
            logger.warning(
                "wechat_mp_notice_rejected",
                kind=kind,
                account=account,
                errcode=errcode,
                errmsg=str(row.get("errmsg"))[:120],
            )
    return result


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def first_notice_line(message: str, *, limit: int = 20) -> str:
    """通报首行做摘要字段（订阅通知短字段有长度限制）。"""
    for line in (message or "").splitlines():
        text = line.strip()
        if text:
            return text[:limit]
    return ""
