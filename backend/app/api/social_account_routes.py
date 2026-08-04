"""
社交账号管理API路由

提供多微信账号的CRUD操作、QR码获取、状态查询等功能
"""

import asyncio
import httpx
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path
import structlog

from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser
from app.social.binding_service import (
    SocialBindingConflict,
    SocialBindingService,
    get_social_binding_service,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/social/accounts", tags=["social-accounts"])

_channel_manager_override = None


def set_channel_manager_override(manager):
    """Set the in-process channel manager used by worker internal APIs."""
    global _channel_manager_override
    _channel_manager_override = manager


# ============================================================================
# 请求/响应模型
# ============================================================================

class AccountCreate(BaseModel):
    """创建账号请求"""
    id: str
    name: str
    base_url: str = "https://ilinkai.weixin.qq.com"
    allow_from: List[str] = ["*"]
    auto_start: bool = True


class AccountResponse(BaseModel):
    """账号响应"""
    id: str
    name: str
    type: str  # "weixin", "qq", etc.
    enabled: bool
    running: bool
    bot_account: Optional[str] = None
    login_status: str  # "logged_out", "waiting_scan", "logged_in"
    qr_code_available: bool = False


class AccountStatus(BaseModel):
    """账号状态"""
    account_id: str
    running: bool
    logged_in: bool
    bot_account: Optional[str] = None
    qr_code_available: bool = False


# ============================================================================
# 工具函数
# ============================================================================

def get_channel_manager():
    """
    获取ChannelManager实例

    如果main.py未初始化（社交平台未启用），则延迟创建
    一个最小化的ChannelManager，用于账号管理API。

    Returns:
        ChannelManager实例或None
    """
    if _channel_manager_override is not None:
        return _channel_manager_override

    try:
        # 从FastAPI app.state获取
        from app.main import app
        manager = getattr(app.state, 'channel_manager', None)
        if manager is not None:
            return manager

        # 延迟初始化：创建最小化的ChannelManager
        from app.social.config import SocialConfig
        from app.social.message_bus import MessageBus
        from app.channels.manager import ChannelManager

        social_config = SocialConfig.load_from_yaml(
            getattr(app.state, 'social_config_path', 'backend/config/social_config.yaml')
        )
        message_bus = MessageBus()
        manager = ChannelManager(
            config=social_config,
            bus=message_bus,
            agent_bridge=None
        )

        # 保存到app.state，供后续复用
        app.state.channel_manager = manager
        app.state.message_bus = message_bus
        app.state.social_config = social_config

        logger.info("channel_manager_lazy_initialized")
        return manager

    except Exception as e:
        logger.error("failed_to_get_channel_manager", error=str(e), exc_info=True)
        return None


def load_config():
    """加载社交配置"""
    from config.social_config import load_social_config
    return load_social_config()


def save_config(config):
    """保存社交配置"""
    from config.social_config import save_social_config
    return save_social_config(config)


async def _owned_account_id(
    identifier: str,
    user: CurrentUser,
    bindings: SocialBindingService,
) -> str:
    """Resolve a scan task or finalized account without exposing foreign IDs."""
    try:
        task = await bindings.require_scan_task(identifier, user)
        return task.account_id
    except HTTPException as exc:
        if exc.status_code != 404:
            raise

    binding = await bindings.active_for_account(identifier)
    if binding is None or (not user.is_admin and binding.platform_user_id != user.id):
        raise HTTPException(status_code=404, detail="weixin_account_not_found")
    return binding.account_id


async def _cleanup_temporary_account(
    account_id: str,
    bindings: SocialBindingService,
) -> None:
    manager = get_channel_manager()
    if manager:
        channel_key = f"weixin:{account_id}"
        channel = manager.channels.pop(channel_key, None)
        if channel:
            try:
                await channel.stop()
            except Exception as exc:
                logger.warning("temporary_channel_stop_failed", account_id=account_id, error=str(exc))

    config = load_config()
    original_count = len(config.weixin.accounts)
    config.weixin.accounts = [acc for acc in config.weixin.accounts if acc.id != account_id]
    if len(config.weixin.accounts) != original_count:
        save_config(config)
    await bindings.deactivate_account(account_id)


async def _require_active_scan_task(
    task_id: str,
    user: CurrentUser,
    bindings: SocialBindingService,
):
    task = await bindings.require_scan_task(task_id, user)
    if task.status != "confirmed" and task.expires_at < datetime.utcnow():
        await bindings.mark_scan_status(task_id, user, "expired")
        await _cleanup_temporary_account(task.account_id, bindings)
        raise HTTPException(status_code=410, detail="weixin_scan_expired")
    return task


# ============================================================================
# API端点
# ============================================================================

@router.get("", response_model=List[AccountResponse])
async def list_accounts(
    user: CurrentUser = Depends(require_current_user),
    bindings: SocialBindingService = Depends(get_social_binding_service),
):
    """
    获取所有社交账号列表

    Returns:
        账号列表
    """
    manager = get_channel_manager()
    if not manager:
        raise HTTPException(status_code=404, detail="Channel manager not found")

    visible_bindings = await bindings.list_visible(user)
    visible_accounts = {binding.account_id for binding in visible_bindings}
    accounts = []
    for channel_key, channel in manager.channels.items():
        # 解析渠道类型和实例ID
        if ":" in channel_key:
            channel_type, instance_id = channel_key.split(":", 1)
        else:
            channel_type, instance_id = channel_key, "default"
        if instance_id not in visible_accounts:
            continue

        # 获取配置
        config = getattr(channel, 'config', None)

        accounts.append({
            "id": instance_id,
            "name": getattr(config, "name", f"{channel_type.title()} Account"),
            "type": channel_type,
            "enabled": getattr(config, "enabled", True),
            "running": channel.is_running,
            "bot_account": getattr(channel, "bot_account", None),
            "login_status": "logged_in" if getattr(channel, "_token", None) else "logged_out",
            "qr_code_available": getattr(channel, "_current_qr_code_path", None) is not None
        })

    logger.info("accounts_listed", count=len(accounts))
    return accounts


@router.post("/weixin", response_model=AccountResponse)
async def create_weixin_account(
    account: AccountCreate,
    user: CurrentUser = Depends(require_current_user),
):
    """
    创建新的微信账号

    Args:
        account: 账号创建请求

    Returns:
        创建的账号信息
    """
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="admin_required")
    # 1. 加载配置
    config = load_config()

    # 2. 检查ID是否重复
    existing_ids = [acc.id for acc in config.weixin.accounts]
    if account.id in existing_ids:
        raise HTTPException(status_code=400, detail=f"Account ID '{account.id}' already exists")

    # 3. 添加账号到配置
    from config.social_config import WeixinAccountConfig
    new_account = WeixinAccountConfig(**account.model_dump())
    config.weixin.accounts.append(new_account)

    # 4. 保存配置
    if not save_config(config):
        raise HTTPException(status_code=500, detail="Failed to save configuration")

    # 5. 创建渠道实例
    manager = get_channel_manager()
    if manager:
        try:
            channel = manager._create_weixin_channel(new_account)
            channel_key = f"weixin:{account.id}"
            manager.channels[channel_key] = channel

            # ✅ 注册到 AgentBridge（用于获取机器人账号）
            if manager.agent_bridge:
                manager.agent_bridge.register_channel(channel)
                logger.info("channel_registered_to_agent_bridge", channel_name=channel_key)

            # 6. 自动启动（如果配置了）
            if account.auto_start:
                await channel.login()
                await channel.start()

            logger.info(
                "weixin_account_created",
                account_id=account.id,
                name=account.name,
                auto_started=account.auto_start
            )

            return {
                "id": account.id,
                "name": account.name,
                "type": "weixin",
                "enabled": True,
                "running": channel.is_running,
                "bot_account": getattr(channel, "bot_account", None),
                "login_status": "logged_out",
                "qr_code_available": getattr(channel, "_current_qr_code_path", None) is not None
            }

        except Exception as e:
            logger.error("failed_to_create_channel", account_id=account.id, error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to create channel: {str(e)}")

    return {
        "id": account.id,
        "name": account.name,
        "type": "weixin",
        "enabled": True,
        "running": False,
        "bot_account": None,
        "login_status": "logged_out",
        "qr_code_available": False
    }


@router.get("/weixin/{task_id}/qrcode")
async def get_weixin_qrcode(
    task_id: str,
    user: CurrentUser = Depends(require_current_user),
    bindings: SocialBindingService = Depends(get_social_binding_service),
):
    """
    获取微信账号登录QR码图片

    Args:
        account_id: 账号ID

    Returns:
        QR码图片文件
    """
    task = await _require_active_scan_task(task_id, user, bindings)
    account_id = task.account_id
    manager = get_channel_manager()
    if not manager:
        raise HTTPException(status_code=404, detail="Channel manager not found")

    channel_key = f"weixin:{account_id}"
    channel = manager.channels.get(channel_key)

    if not channel:
        raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found")

    qr_path = getattr(channel, "_current_qr_code_path", None)
    if not qr_path or not Path(qr_path).exists():
        raise HTTPException(status_code=404, detail="No QR code available. Please start the account first.")

    logger.info("qrcode_fetched", account_id=account_id, path=str(qr_path))
    return FileResponse(qr_path, media_type="image/png")


@router.get("/weixin/{task_id}/status", response_model=AccountStatus)
async def get_weixin_status(
    task_id: str,
    user: CurrentUser = Depends(require_current_user),
    bindings: SocialBindingService = Depends(get_social_binding_service),
):
    """
    获取微信账号登录状态

    Args:
        account_id: 账号ID

    Returns:
        账号状态信息
    """
    task = await _require_active_scan_task(task_id, user, bindings)
    account_id = task.account_id
    manager = get_channel_manager()
    if not manager:
        raise HTTPException(status_code=404, detail="Channel manager not found")

    channel_key = f"weixin:{account_id}"
    channel = manager.channels.get(channel_key)

    if not channel:
        raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found")

    has_token = bool(getattr(channel, "_token", None))
    is_running = channel.is_running
    qr_path = getattr(channel, "_current_qr_code_path", None)

    return {
        "account_id": account_id,
        "running": is_running,
        "logged_in": has_token,
        "bot_account": getattr(channel, "bot_account", None),
        "qr_code_available": qr_path is not None and Path(qr_path).exists()
    }


@router.post("/weixin/{account_id}/start")
async def start_weixin_account(
    account_id: str,
    user: CurrentUser = Depends(require_current_user),
    bindings: SocialBindingService = Depends(get_social_binding_service),
):
    """
    启动微信账号（执行登录流程）

    Args:
        account_id: 账号ID

    Returns:
        操作结果
    """
    account_id = await _owned_account_id(account_id, user, bindings)
    manager = get_channel_manager()
    if not manager:
        raise HTTPException(status_code=404, detail="Channel manager not found")

    channel_key = f"weixin:{account_id}"
    channel = manager.channels.get(channel_key)

    if not channel:
        raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found")

    if channel.is_running:
        return {"message": "Account already running"}

    try:
        await channel.login(force=False)
        await channel.start()

        logger.info("weixin_account_started", account_id=account_id)
        return {"message": "Account started successfully", "account_id": account_id}

    except Exception as e:
        logger.error("failed_to_start_account", account_id=account_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to start account: {str(e)}")


@router.post("/weixin/{account_id}/stop")
async def stop_weixin_account(
    account_id: str,
    user: CurrentUser = Depends(require_current_user),
    bindings: SocialBindingService = Depends(get_social_binding_service),
):
    """
    停止微信账号

    Args:
        account_id: 账号ID

    Returns:
        操作结果
    """
    account_id = await _owned_account_id(account_id, user, bindings)
    manager = get_channel_manager()
    if not manager:
        raise HTTPException(status_code=404, detail="Channel manager not found")

    channel_key = f"weixin:{account_id}"
    channel = manager.channels.get(channel_key)

    if not channel:
        raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found")

    try:
        await channel.stop()

        logger.info("weixin_account_stopped", account_id=account_id)
        return {"message": "Account stopped successfully", "account_id": account_id}

    except Exception as e:
        logger.error("failed_to_stop_account", account_id=account_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to stop account: {str(e)}")


@router.delete("/weixin/{account_id}")
async def delete_weixin_account(
    account_id: str,
    user: CurrentUser = Depends(require_current_user),
    bindings: SocialBindingService = Depends(get_social_binding_service),
):
    """
    删除微信账号

    Args:
        account_id: 账号ID

    Returns:
        操作结果
    """
    account_id = await _owned_account_id(account_id, user, bindings)
    manager = get_channel_manager()
    if not manager:
        raise HTTPException(status_code=404, detail="Channel manager not found")

    # 1. 停止渠道
    channel_key = f"weixin:{account_id}"
    channel = manager.channels.get(channel_key)

    if channel:
        try:
            await channel.stop()
        except Exception as e:
            logger.warning("failed_to_stop_channel", account_id=account_id, error=str(e))

        del manager.channels[channel_key]

    # 2. 从配置中删除
    config = load_config()
    original_count = len(config.weixin.accounts)
    config.weixin.accounts = [acc for acc in config.weixin.accounts if acc.id != account_id]

    if len(config.weixin.accounts) == original_count:
        raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found in configuration")

    if not save_config(config):
        raise HTTPException(status_code=500, detail="Failed to save configuration")

    await bindings.deactivate_account(account_id)

    # 3. 清理状态文件
    state_dir = Path(f"backend_data_registry/social/weixin/{account_id}")
    if state_dir.exists():
        import shutil
        try:
            shutil.rmtree(state_dir)
            logger.info("state_files_cleaned", account_id=account_id, path=str(state_dir))
        except Exception as e:
            logger.warning("failed_to_clean_state_files", account_id=account_id, error=str(e))

    logger.info("weixin_account_deleted", account_id=account_id)
    return {"message": "Account deleted successfully", "account_id": account_id}


@router.post("/weixin/{task_id}/refresh-qrcode")
async def refresh_weixin_qrcode(
    task_id: str,
    user: CurrentUser = Depends(require_current_user),
    bindings: SocialBindingService = Depends(get_social_binding_service),
):
    """
    刷新微信账号QR码（重新获取新的QR码）

    Args:
        account_id: 账号ID

    Returns:
        操作结果
    """
    task = await _require_active_scan_task(task_id, user, bindings)
    account_id = task.account_id
    manager = get_channel_manager()
    if not manager:
        raise HTTPException(status_code=404, detail="Channel manager not found")

    channel_key = f"weixin:{account_id}"
    channel = manager.channels.get(channel_key)

    if not channel:
        raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found")

    try:
        # 重新获取QR码
        qrcode_id, scan_url = await channel._fetch_qr_code()
        channel._save_qr_code_image(scan_url, qrcode_id)

        logger.info("qrcode_refreshed", account_id=account_id, qrcode_id=qrcode_id)
        return {
            "message": "QR code refreshed successfully",
            "qrcode_id": qrcode_id,
            "account_id": account_id
        }

    except Exception as e:
        logger.error("failed_to_refresh_qrcode", account_id=account_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to refresh QR code: {str(e)}")


# ============================================================================
# 简化流程API（扫码自动创建账号）
# ============================================================================

class AutoCreateRequest(BaseModel):
    """The server derives scan ownership from the authenticated session."""


class FinalizeRequest(BaseModel):
    """Finalize uses only QR-confirmed server state."""


@router.post("/weixin/auto-create")
async def auto_create_account(
    request: AutoCreateRequest | None = None,
    user: CurrentUser = Depends(require_current_user),
    bindings: SocialBindingService = Depends(get_social_binding_service),
):
    """
    自动创建临时账号并启动（用于扫码登录流程）

    Args:
        request: 自动创建请求

    Returns:
        创建的账号信息
    """
    task = await bindings.create_scan_task(user)
    account_id = task.account_id
    manager = get_channel_manager()
    if not manager:
        raise HTTPException(status_code=404, detail="Channel manager not found")

    # 1. 加载配置
    config = load_config()

    # 2. 检查ID是否已存在
    existing_ids = [acc.id for acc in config.weixin.accounts]
    if account_id in existing_ids:
        logger.info("temp_account_already_exists", account_id=account_id)
        # 账号已存在，直接返回
        channel_key = f"weixin:{account_id}"
        channel = manager.channels.get(channel_key)
        if channel:
            return {
                "task_id": task.id,
                "account_id": account_id,
                "name": getattr(channel.config, "name", user.display_name),
                "platform_user_id": user.id,
                "platform_username": user.username,
                "platform_display_name": user.display_name,
                "status": "already_exists",
                "qr_code_available": getattr(channel, "_current_qr_code_path", None) is not None
            }
        else:
            # 配置中存在但渠道未启动，尝试创建并启动
            account_config = next(acc for acc in config.weixin.accounts if acc.id == account_id)
            channel = manager._create_weixin_channel(account_config)
            manager.channels[channel_key] = channel

            # ✅ 注册到 AgentBridge（用于获取机器人账号）
            if manager.agent_bridge:
                manager.agent_bridge.register_channel(channel)
                logger.info("channel_registered_to_agent_bridge", channel_name=channel_key)

            # 启动并等待二维码就绪
            try:
                await asyncio.wait_for(channel._qr_code_ready.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pass

            await channel.start()
            return {
                "task_id": task.id,
                "account_id": account_id,
                "name": account_config.name,
                "platform_user_id": user.id,
                "platform_username": user.username,
                "platform_display_name": user.display_name,
                "status": "restarted",
                "qr_code_available": getattr(channel, "_current_qr_code_path", None) is not None
            }

    # 3. 创建临时账号配置
    from config.social_config import WeixinAccountConfig
    temp_account = WeixinAccountConfig(
        id=account_id,
        name=user.display_name or user.username,
        base_url="https://ilinkai.weixin.qq.com",
        token="",
        enabled=True,
        allow_from=["*"],
        auto_start=True
    )

    # 4. 添加到配置（临时）
    config.weixin.accounts.append(temp_account)
    if not save_config(config):
        logger.error("failed_to_save_config", account_id=account_id)
        raise HTTPException(status_code=500, detail="Failed to save configuration")

    # 5. 创建并启动渠道
    try:
        logger.info("creating_weixin_channel", account_id=account_id)
        channel = manager._create_weixin_channel(temp_account)
        channel_key = f"weixin:{account_id}"
        manager.channels[channel_key] = channel

        # ✅ 注册到 AgentBridge（用于获取机器人账号）
        if manager.agent_bridge:
            manager.agent_bridge.register_channel(channel)
            logger.info("channel_registered_to_agent_bridge", channel_name=channel_key)

        logger.info("channel_created", account_id=account_id, channel_key=channel_key)

        # ✅ 异步任务：生成二维码并等待登录
        async def login_and_start():
            try:
                logger.info("starting_login_async", account_id=account_id)

                # 初始化HTTP客户端
                channel._client = httpx.AsyncClient(
                    timeout=httpx.Timeout(60, connect=30),
                    follow_redirects=True,
                )
                channel._running = True

                # 只生成二维码，不等待扫码完成
                try:
                    qrcode_id = await channel._init_qr_login()
                    logger.info("qrcode_generated", account_id=account_id, qrcode_id=qrcode_id)
                except Exception as e:
                    logger.error("qrcode_generation_failed", account_id=account_id, error=str(e), exc_info=True)

                # 启动轮询（start方法会继续等待扫码并完成登录）
                await channel.start()

            except Exception as e:
                logger.error("login_async_failed", account_id=account_id, error=str(e), exc_info=True)

        # 立即创建异步任务，不等待
        asyncio.create_task(login_and_start())

        # 等待二维码就绪（最多5秒）
        try:
            logger.info("waiting_for_qrcode", account_id=account_id)
            await asyncio.wait_for(channel._qr_code_ready.wait(), timeout=5.0)
            logger.info(
                "qrcode_ready",
                account_id=account_id,
                qr_path=str(getattr(channel, "_current_qr_code_path", None))
            )
        except asyncio.TimeoutError:
            logger.warning(
                "qrcode_ready_timeout",
                account_id=account_id,
                timeout_seconds=5.0
            )

        logger.info(
            "temp_account_auto_created",
            account_id=account_id,
            channel_key=channel_key
        )

        return {
            "task_id": task.id,
            "account_id": account_id,
            "name": temp_account.name,
            "platform_user_id": user.id,
            "platform_username": user.username,
            "platform_display_name": user.display_name,
            "status": "created",
            "qr_code_available": getattr(channel, "_current_qr_code_path", None) is not None
        }

    except Exception as e:
        logger.error(
            "failed_to_auto_create_account",
            account_id=account_id,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Failed to auto-create account: {str(e)}")


@router.post("/weixin/{task_id}/finalize")
async def finalize_account(
    task_id: str,
    request: FinalizeRequest | None = None,
    user: CurrentUser = Depends(require_current_user),
    bindings: SocialBindingService = Depends(get_social_binding_service),
):
    """
    完成账号创建（扫码登录成功后调用）

    Args:
        account_id: 账号ID
        request: 完成请求（包含显示名称）

    Returns:
        操作结果
    """
    task = await _require_active_scan_task(task_id, user, bindings)
    account_id = task.account_id
    manager = get_channel_manager()
    if not manager:
        raise HTTPException(status_code=404, detail="Channel manager not found")

    channel_key = f"weixin:{account_id}"
    channel = manager.channels.get(channel_key)

    if not channel:
        raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found")

    bot_account = getattr(channel, "bot_account", None)
    scanner_user_id = getattr(channel, "scanner_user_id", "")
    if not scanner_user_id or not bot_account:
        raise HTTPException(status_code=409, detail="weixin_scan_not_confirmed")

    previous = await bindings.active_for_platform_user(user.id)
    try:
        binding = await bindings.activate(
            task_id=task.id,
            user=user,
            account_id=account_id,
            ilink_user_id=scanner_user_id,
            bot_account=bot_account,
        )
    except SocialBindingConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    token = getattr(channel, "_token", None)
    config = load_config()
    for acc in config.weixin.accounts:
        if acc.id == account_id:
            acc.name = user.display_name or user.username
            if token:
                acc.token = token
        elif previous and acc.id == previous.account_id and previous.account_id != account_id:
            acc.enabled = False

    save_config(config)

    if previous and previous.account_id != account_id:
        old_channel = manager.channels.get(f"weixin:{previous.account_id}")
        if old_channel:
            await old_channel.stop()

    channel.config.name = user.display_name or user.username
    channel.display_name = user.display_name or user.username

    logger.info(
        "account_finalized",
        account_id=account_id,
        platform_user_id=user.id,
        bot_account=bot_account
    )

    return {
        "message": "Account finalized successfully",
        **binding.model_dump(mode="json"),
    }


@router.post("/reload")
async def reload_channels(
    user: CurrentUser = Depends(require_current_user),
):
    """
    重新加载所有渠道配置（支持动态增删账户）

    - 停止已删除的账户
    - 启动新添加的账户
    - 保留仍在运行的账户
    - 清理无效的状态文件

    Returns:
        操作结果
    """
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="admin_required")
    manager = get_channel_manager()
    if not manager:
        raise HTTPException(status_code=404, detail="Channel manager not found")

    old_count = len(manager.channels)

    await manager.reload_channels()

    new_count = len(manager.channels)

    logger.info(
        "channels_reloaded",
        old_count=old_count,
        new_count=new_count
    )

    return {
        "message": "Channels reloaded successfully",
        "old_count": old_count,
        "new_count": new_count
    }
