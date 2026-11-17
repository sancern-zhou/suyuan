"""企业微信客户联系回调 + 绑定管理 API。

回调端点（GET/POST ``{prefix}/callback``）面向企业微信服务器：网关中间件
只对该精确路径做配置驱动放行（wecom_token 配置后才开），签名校验与
AES 解密在路由内完成（企微回调必须加密，伪造请求过不了验签）。

管理端点（``{prefix}/admin/*``）走正常网关鉴权：生成绑定二维码（联系我
方式，state=bind:<账号>）、查看/删除绑定、渠道状态。

群发任务创建后需运营成员在企业微信客户端手动点「发送」（平台设计），
本路由只负责绑定维护与任务前置数据。
"""

from __future__ import annotations

from typing import Optional
from xml.etree.ElementTree import Element  # noqa: TC003 - only for type hints

import structlog
from defusedxml import ElementTree as SafeET
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.auth.dependencies import optional_current_user
from app.auth.models import CurrentUser
from app.social.wecom.crypto import WecomCrypto, WecomCryptoError
from config.settings import settings

logger = structlog.get_logger(__name__)

router = APIRouter(prefix=settings.wecom_api_prefix, tags=["wecom"])

# 联系我二维码 state 前缀（add_external_contact 事件原样带回）。
_STATE_PREFIX = "bind:"


def _crypto() -> WecomCrypto:
    if not settings.wecom_token.strip() or not settings.wecom_aes_key.strip():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="wecom_callback_disabled"
        )
    return WecomCrypto(
        settings.wecom_token.strip(),
        settings.wecom_aes_key.strip(),
        receive_id=settings.wecom_corpid.strip(),
    )


def _xml_text(root: Element, tag: str) -> str:
    node = root.find(tag)
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def _account_from_state(state: str) -> str:
    return state[len(_STATE_PREFIX):].strip() if state.startswith(_STATE_PREFIX) else ""


async def _handle_event_xml(plain_xml: str) -> None:
    from app.social.wecom.bindings import WecomBindingStore

    try:
        root = SafeET.fromstring(plain_xml.encode("utf-8"))
    except Exception:
        logger.warning("wecom_callback_xml_invalid", size=len(plain_xml))
        return
    if _xml_text(root, "MsgType") != "event":
        return
    event = _xml_text(root, "Event")
    if event != "change_external_contact":
        return
    change_type = _xml_text(root, "ChangeType")
    external_userid = _xml_text(root, "ExternalUserID")
    member = _xml_text(root, "UserID")
    if not external_userid:
        return
    if change_type == "add_external_contact":
        account = _account_from_state(_xml_text(root, "State"))
        if not account:
            logger.info(
                "wecom_follow_without_state",
                external_userid=external_userid,
                member=member,
            )
            return
        row = await WecomBindingStore().bind(
            account, external_userid, owner=member
        )
        logger.info(
            "wecom_bound",
            account=account,
            external_userid=external_userid,
            owner=row.get("owner"),
        )
        return
    if change_type in ("del_external_contact", "del_follow_user"):
        account = await WecomBindingStore().mark_unbound(external_userid)
        logger.info(
            "wecom_unbound",
            external_userid=external_userid,
            account=account,
            change_type=change_type,
        )


@router.get("/callback")
async def verify_callback_url(
    msg_signature: str = Query(""),
    timestamp: str = Query(""),
    nonce: str = Query(""),
    echostr: str = Query(""),
) -> PlainTextResponse:
    """企业微信服务器 URL 验证：验签 + 解密 echostr 后回显明文。"""
    crypto = _crypto()
    if not crypto.verify(msg_signature, timestamp, nonce, echostr):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="signature_mismatch"
        )
    try:
        plain = crypto.decrypt(echostr)
    except WecomCryptoError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=f"decrypt_failed: {exc}"
        ) from exc
    return PlainTextResponse(plain)


@router.post("/callback")
async def receive_callback_event(
    request: Request,
    msg_signature: str = Query(""),
    timestamp: str = Query(""),
    nonce: str = Query(""),
) -> PlainTextResponse:
    """接收企业微信加密事件推送，按需更新绑定状态。"""
    crypto = _crypto()
    try:
        envelope = SafeET.fromstring(await request.body())
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_xml"
        )
    encrypt = _xml_text(envelope, "Encrypt")
    if not encrypt or not crypto.verify(msg_signature, timestamp, nonce, encrypt):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="signature_mismatch"
        )
    try:
        plain = crypto.decrypt(encrypt)
    except WecomCryptoError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=f"decrypt_failed: {exc}"
        ) from exc
    await _handle_event_xml(plain)
    return PlainTextResponse("success")


async def require_wecom_admin(
    user: Optional[CurrentUser] = Depends(optional_current_user),
) -> CurrentUser:
    if user is None or not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="wecom_admin_only"
        )
    return user


class BindQrcodeRequest(BaseModel):
    account: str


@router.post("/admin/bind-qrcode")
async def create_bind_qrcode(
    payload: BindQrcodeRequest,
    _: CurrentUser = Depends(require_wecom_admin),
) -> dict:
    """为 App 账号生成「联系我」二维码（发给目标用户，微信扫码加好友即绑定）。"""
    from app.social.app_identity import _accounts
    from app.social.wecom.bindings import normalize_account
    from app.social.wecom.client import get_wecom_client

    account = normalize_account(payload.account)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_account"
        )
    entry = _accounts().get(account)
    if not entry or str(entry.get("status", "active")).lower() != "active":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="unknown_account"
        )
    client = get_wecom_client()
    if not client.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="wecom_disabled"
        )
    try:
        result = await client.create_bind_qrcode(f"{_STATE_PREFIX}{account}")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"qrcode_failed: {exc}"
        ) from exc
    return {"account": account, **result}


@router.get("/admin/bindings")
async def list_bindings(
    _: CurrentUser = Depends(require_wecom_admin),
) -> dict:
    from app.social.wecom.bindings import WecomBindingStore

    bindings = await WecomBindingStore().list_bindings()
    return {"bindings": bindings, "count": len(bindings)}


@router.delete("/admin/bindings/{account}")
async def delete_binding(
    account: str,
    _: CurrentUser = Depends(require_wecom_admin),
) -> dict:
    from app.social.wecom.bindings import WecomBindingStore

    removed = await WecomBindingStore().unbind(account)
    return {"account": account, "removed": removed}


@router.get("/admin/status")
async def channel_status(
    _: CurrentUser = Depends(require_wecom_admin),
) -> dict:
    from app.social.wecom.bindings import WecomBindingStore
    from app.social.wecom.client import get_wecom_client

    client = get_wecom_client()
    bindings = await WecomBindingStore().list_bindings()
    return {
        "enabled": client.enabled,
        "corpid_configured": bool(settings.wecom_corpid.strip()),
        "member_configured": bool(settings.wecom_default_member.strip()),
        "callback_configured": bool(
            settings.wecom_token.strip() and settings.wecom_aes_key.strip()
        ),
        "callback_path": f"{settings.wecom_api_prefix.rstrip('/')}/callback",
        "binding_count": len(bindings),
        "bound_count": sum(
            1 for row in bindings if row.get("status") == "bound"
        ),
    }
