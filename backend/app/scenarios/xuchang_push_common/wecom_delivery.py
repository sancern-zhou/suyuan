"""企业微信客户联系投递层：角色受众 → 绑定 external_userid → 群发任务。

与微信群 RPA 队列（xuchang_station_deviation/wechat_push_queue）平行的
渠道：身份复用 APP 账号受众组（audiences.py 不改），external_userid 是
账号的附加绑定（social 目录 wecom_bindings.json，绑定靠「联系我」二维码
state=bind:<账号>，用户微信扫码加企微成员好友即完成，无任何订阅授权）。

企业群发任务创建后**需运营成员在企业微信客户端手动点「发送」**客户才能
收到（平台设计，API 无法代替）：这里按 owner 成员分组创建任务（任务的
客户必须是发送成员自己的客户）并 best-effort 提醒成员处理。群发文本上限
2048 字节（UTF-8），超限字节安全截断并追加提示。本渠道整体由调用方
try/except 隔离，失败不影响微信群/APP 渠道。
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from app.scenarios.xuchang_push_common.audiences import resolve_audience_accounts
from config.settings import settings

logger = structlog.get_logger()

# 企业群发 text 内容上限（字节，UTF-8）。
CONTENT_LIMIT_BYTES = 2048
_TRUNCATE_SUFFIX = "……（内容过长已截断，完整通报见微信群/系统）"


def clip_content(content: str, *, limit_bytes: int = CONTENT_LIMIT_BYTES) -> str:
    """UTF-8 字节安全截断，不撕裂多字节字符，预留截断提示。"""
    text = str(content or "").strip()
    budget = limit_bytes - len(_TRUNCATE_SUFFIX.encode("utf-8"))
    if len(text.encode("utf-8")) <= limit_bytes:
        return text
    clipped = text.encode("utf-8")[:budget].decode("utf-8", errors="ignore").rstrip()
    return clipped + _TRUNCATE_SUFFIX


async def push_wecom_report(
    kind: str,
    *,
    title: str,
    content: str,
    roles: list[str] | tuple[str, ...] | None = None,
    accounts: list[str] | None = None,
    client: Any | None = None,
    binding_store: Any | None = None,
) -> dict[str, Any]:
    """向受众组的企业微信绑定客户创建点对点群发任务。

    返回聚合结果（enabled/tasks/recipients/skipped/failed）；单任务失败
    不中断其余任务，异常向上抛出由调用方隔离。
    """
    from app.social.wecom.bindings import WecomBindingStore, normalize_account
    from app.social.wecom.client import get_wecom_client

    if client is None:
        client = get_wecom_client()
    store = binding_store or WecomBindingStore()

    result: dict[str, Any] = {
        "enabled": bool(client.enabled),
        "kind": kind,
        "tasks": [],
        "recipients": 0,
        "skipped": 0,
        "failed": 0,
    }
    if not client.enabled:
        return result

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
        logger.info("wecom_audience_empty", kind=kind)
        return result

    # 群发任务的客户必须是发送成员自己的客户：按绑定 owner 分组。
    grouped: dict[str, list[str]] = {}
    fallback_member = settings.wecom_default_member.strip()
    for account in audience:
        row = await store.get(account)
        if not row or not str(row.get("external_userid") or "").strip():
            result["skipped"] += 1
            continue
        if str(row.get("status")) != "bound":
            result["skipped"] += 1
            continue
        owner = str(row.get("owner") or "").strip() or fallback_member
        grouped.setdefault(owner, []).append(str(row["external_userid"]))
    if not grouped:
        logger.info("wecom_no_bound_recipients", kind=kind, audience=len(audience))
        return result

    text = clip_content(f"{title}\n{content}" if title else content)
    for sender, external_userids in grouped.items():
        try:
            task = await client.add_group_msg_task(
                sender=sender,
                external_userids=external_userids,
                content=text,
            )
        except Exception as exc:
            result["failed"] += 1
            logger.warning(
                "wecom_group_msg_task_failed",
                kind=kind,
                sender=sender,
                recipients=len(external_userids),
                error=str(exc)[:300],
            )
            continue
        result["tasks"].append(
            {"sender": sender, "msgid": task.get("msgid"), "recipients": len(external_userids)}
        )
        result["recipients"] += len(external_userids)
        # 运营成员需在企微客户端手动确认发送：best-effort 提醒一次。
        try:
            if task.get("msgid"):
                await client.remind_group_msg_send(str(task["msgid"]))
        except Exception as exc:
            logger.info("wecom_remind_failed", msgid=task.get("msgid"), error=str(exc)[:200])
    if result["tasks"]:
        for account in audience:
            row = await store.get(account)
            if row and str(row.get("status")) == "bound":
                await store.record_push(account)
    return result
