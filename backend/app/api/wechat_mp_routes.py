"""微信公众号（MP）服务端回调 + 绑定管理 API。

回调端点（GET/POST ``{prefix}/callback``）面向微信服务器：网关中间件只对
该精确路径做配置驱动的放行（wechat_mp_token 非空才开），真正的签名校验
（sha1(token, timestamp, nonce)）在路由内完成，伪造请求会在路由层被拒。

管理端点（``{prefix}/admin/*``）不参与中间件放行，走正常网关鉴权，要求
管理员身份：生成绑定二维码、查看/删除绑定、渠道状态。
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Optional
from xml.etree.ElementTree import Element  # noqa: TC003 - only for type hints

import structlog
from defusedxml import ElementTree as SafeET
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.auth.dependencies import optional_current_user
from app.auth.models import CurrentUser
from config.settings import settings

logger = structlog.get_logger(__name__)

router = APIRouter(prefix=settings.wechat_mp_api_prefix, tags=["wechat-mp"])

# EventKey prefixes produced by the bind QR code (scene_str = "bind:<account>").
_SCENE_PREFIXES = ("qrscene_bind:", "bind:")

_WELCOME_TEXT = (
    "绑定成功。本公众号将向您推送月度特征分析、企业核查线索周报等服务通知。"
    "若尚未授权订阅提醒，请在公众号内完成一次订阅授权，即可持续接收通知。"
)


def _verify_signature(signature: str, timestamp: str, nonce: str) -> bool:
    token = settings.wechat_mp_token
    if not token or not signature:
        return False
    expected = hashlib.sha1(
        "".join(sorted([token, timestamp, nonce])).encode("utf-8")
    ).hexdigest()
    return hmac.compare_digest(signature, expected)


def _xml_text(root: Element, tag: str) -> str:
    node = root.find(tag)
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def _account_from_scene(event_key: str) -> str:
    for prefix in _SCENE_PREFIXES:
        if event_key.startswith(prefix):
            account = event_key[len(prefix):].strip()
            return account
    return ""


async def _send_welcome(openid: str) -> None:
    from app.social.wechat_mp.client import get_wechat_mp_client

    client = get_wechat_mp_client()
    if not client.enabled:
        return
    try:
        await client.send_text_message(openid, _WELCOME_TEXT)
    except Exception as exc:
        logger.warning("wechat_mp_welcome_failed", openid=openid, error=str(exc))


async def _record_popup_states(root: Element, openid: str) -> None:
    """subscribe_msg_popup：用户对每个模板的 accept/reject 授权状态。"""
    from app.social.wechat_mp.bindings import WechatMpBindingStore

    popup = root.find("SubscribeMsgPopupEvent")
    if popup is None:
        return
    store = WechatMpBindingStore()
    for item in popup.iter("List"):
        template_id = _xml_text(item, "TemplateId")
        state = _xml_text(item, "SubscribeStatusString") or _xml_text(
            item, "SubscribeStatus"
        )
        if not template_id or not state:
            continue
        await store.record_template_state(openid, template_id, state)
        logger.info(
            "wechat_mp_template_state",
            openid=openid,
            template_id=template_id,
            state=state,
        )


def _log_sent_receipt(root: Element, openid: str) -> None:
    """subscribe_msg_sent：微信侧投递回执（errcode 0 为送达）。"""
    sent = root.find("SubscribeMsgSentEvent")
    if sent is None:
        return
    for item in sent.iter("List"):
        logger.info(
            "wechat_mp_sent_receipt",
            openid=openid,
            template_id=_xml_text(item, "TemplateId"),
            msg_id=_xml_text(item, "MsgID"),
            result=_xml_text(item, "SentResult")
            or _xml_text(item, "SubscribeStatusString"),
        )


async def _handle_callback_xml(body: bytes) -> None:
    from app.social.wechat_mp.bindings import WechatMpBindingStore

    try:
        root = SafeET.fromstring(body)
    except Exception:
        logger.warning("wechat_mp_callback_xml_invalid", size=len(body))
        return
    openid = _xml_text(root, "FromUserName")
    if _xml_text(root, "MsgType") != "event" or not openid:
        return
    event = _xml_text(root, "Event")
    if event in ("subscribe", "SCAN"):
        # Only scans of a bind QR code carry an account; a plain follow from
        # search is ignored (no identity to bind).
        account = _account_from_scene(_xml_text(root, "EventKey"))
        if not account:
            logger.info("wechat_mp_follow_without_scene", openid=openid)
            return
        row = await WechatMpBindingStore().bind(account, openid)
        logger.info("wechat_mp_bound", account=account, openid=openid, status=row.get("status"))
        await _send_welcome(openid)
        return
    if event == "unsubscribe":
        account = await WechatMpBindingStore().mark_unsubscribed(openid)
        logger.info("wechat_mp_unsubscribed", openid=openid, account=account)
        return
    if event == "subscribe_msg_popup":
        await _record_popup_states(root, openid)
        return
    if event == "subscribe_msg_sent":
        _log_sent_receipt(root, openid)


@router.get("/callback")
async def verify_callback_url(
    signature: str = Query(""),
    timestamp: str = Query(""),
    nonce: str = Query(""),
    echostr: str = Query(""),
) -> PlainTextResponse:
    """微信服务器 URL 有效性验证：签名通过即回显 echostr。"""
    if not _verify_signature(signature, timestamp, nonce):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="signature_mismatch"
        )
    return PlainTextResponse(echostr)


@router.post("/callback")
async def receive_callback_event(
    request: Request,
    signature: str = Query(""),
    timestamp: str = Query(""),
    nonce: str = Query(""),
) -> PlainTextResponse:
    """接收微信事件推送（明文 XML），按需更新绑定/订阅状态。"""
    if not _verify_signature(signature, timestamp, nonce):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="signature_mismatch"
        )
    body = await request.body()
    await _handle_callback_xml(body)
    return PlainTextResponse("success")


async def require_wechat_mp_admin(
    user: Optional[CurrentUser] = Depends(optional_current_user),
) -> CurrentUser:
    if user is None or not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="wechat_mp_admin_only"
        )
    return user


class BindQrcodeRequest(BaseModel):
    account: str
    expire_seconds: int = 2592000


@router.post("/admin/bind-qrcode")
async def create_bind_qrcode(
    payload: BindQrcodeRequest,
    _: CurrentUser = Depends(require_wechat_mp_admin),
) -> dict:
    """为指定 App 账号生成带参绑定二维码（发给目标用户微信扫码即绑定）。"""
    from app.social.app_identity import _accounts
    from app.social.wechat_mp.bindings import normalize_account
    from app.social.wechat_mp.client import get_wechat_mp_client

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
    client = get_wechat_mp_client()
    if not client.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="wechat_mp_disabled",
        )
    try:
        result = await client.create_bind_qrcode(
            f"bind:{account}", expire_seconds=payload.expire_seconds
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"qrcode_failed: {exc}"
        ) from exc
    return {"account": account, **result}


@router.get("/admin/bindings")
async def list_bindings(
    _: CurrentUser = Depends(require_wechat_mp_admin),
) -> dict:
    from app.social.wechat_mp.bindings import WechatMpBindingStore

    bindings = await WechatMpBindingStore().list_bindings()
    return {"bindings": bindings, "count": len(bindings)}


@router.delete("/admin/bindings/{account}")
async def delete_binding(
    account: str,
    _: CurrentUser = Depends(require_wechat_mp_admin),
) -> dict:
    from app.social.wechat_mp.bindings import WechatMpBindingStore

    removed = await WechatMpBindingStore().unbind(account)
    return {"account": account, "removed": removed}


@router.get("/admin/status")
async def channel_status(
    _: CurrentUser = Depends(require_wechat_mp_admin),
) -> dict:
    from app.social.wechat_mp.bindings import WechatMpBindingStore
    from app.social.wechat_mp.client import get_wechat_mp_client

    client = get_wechat_mp_client()
    bindings = await WechatMpBindingStore().list_bindings()
    return {
        "enabled": client.enabled,
        "app_id_configured": bool(settings.wechat_mp_app_id.strip()),
        "callback_configured": bool(settings.wechat_mp_token.strip()),
        "callback_path": f"{settings.wechat_mp_api_prefix.rstrip('/')}/callback",
        "binding_count": len(bindings),
        "bound_count": sum(
            1 for row in bindings if row.get("status") == "bound"
        ),
    }
