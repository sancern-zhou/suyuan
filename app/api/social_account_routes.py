"""
社交账号管理API路由

提供多微信账号的CRUD操作、QR码获取、状态查询等功能
"""

import asyncio
import httpx
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/social/accounts", tags=["social-accounts"])


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

    Returns:
        ChannelManager实例或None
    """
    try:
        # 从FastAPI app.state获取
        from app.main import app
        return getattr(app.state, 'channel_manager', None)
    except Exception as e:
        logger.error("failed_to_get_channel_manager", error=str(e))
        return None


def load_config():
    """加载社交配置"""
    from config.social_config import load_social_config
    return load_social_config()


def save_config(config):
    """保存社交配置"""
    from config.social_config import save_social_config
    return save_social_config(config)


# ============================================================================
# API端点
# ============================================================================

@router.get("", response_model=List[AccountResponse])
async def list_accounts():
    """
    获取所有社交账号列表

    Returns:
        账号列表
    """
    manager = get_channel_manager()
    if not manager:
        raise HTTPException(status_code=404, detail="Channel manager not found")

    accounts = []
    for channel_key, channel in manager.channels.items():
        # 解析渠道类型和实例ID
        if ":" in channel_key:
            channel_type, instance_id = channel_key.split(":", 1)
        else:
            channel_type, instance_id = channel_key, "default"

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
async def create_weixin_account(account: AccountCreate):
    """
    创建新的微信账号

    Args:
        account: 账号创建请求

    Returns:
        创建的账号信息
    """
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


@router.get("/weixin/{account_id}/qrcode")
async def get_weixin_qrcode(account_id: str):
    """
    获取微信账号登录QR码图片

    Args:
        account_id: 账号ID

    Returns:
        QR码图片文件
    """
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


@router.get("/weixin/{account_id}/status", response_model=AccountStatus)
async def get_weixin_status(account_id: str):
    """
    获取微信账号登录状态

    Args:
        account_id: 账号ID

    Returns:
        账号状态信息
    """
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
async def start_weixin_account(account_id: str):
    """
    启动微信账号（执行登录流程）

    Args:
        account_id: 账号ID

    Returns:
        操作结果
    """
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
async def stop_weixin_account(account_id: str):
    """
    停止微信账号

    Args:
        account_id: 账号ID

    Returns:
        操作结果
    """
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
async def delete_weixin_account(account_id: str):
    """
    删除微信账号

    Args:
        account_id: 账号ID

    Returns:
        操作结果
    """
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


@router.post("/weixin/{account_id}/refresh-qrcode")
async def refresh_weixin_qrcode(account_id: str):
    """
    刷新微信账号QR码（重新获取新的QR码）

    Args:
        account_id: 账号ID

    Returns:
        操作结果
    """
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
    """自动创建账号请求"""
    temp_id: str


class FinalizeRequest(BaseModel):
    """完成账号创建请求"""
    name: str


@router.post("/weixin/auto-create")
async def auto_create_account(request: AutoCreateRequest):
    """
    自动创建临时账号并启动（用于扫码登录流程）

    Args:
        request: 自动创建请求

    Returns:
        创建的账号信息
    """
    manager = get_channel_manager()
    if not manager:
        raise HTTPException(status_code=404, detail="Channel manager not found")

    # 1. 加载配置
    config = load_config()

    # 2. 检查ID是否已存在
    existing_ids = [acc.id for acc in config.weixin.accounts]
    if request.temp_id in existing_ids:
        logger.info("temp_account_already_exists", temp_id=request.temp_id)
        # 账号已存在，直接返回
        channel_key = f"weixin:{request.temp_id}"
        channel = manager.channels.get(channel_key)
        if channel:
            return {
                "account_id": request.temp_id,
                "name": getattr(channel.config, "name", f"临时账号-{request.temp_id}"),
                "status": "already_exists",
                "qr_code_available": getattr(channel, "_current_qr_code_path", None) is not None
            }
        else:
            # 配置中存在但渠道未启动，尝试创建并启动
            account_config = next(acc for acc in config.weixin.accounts if acc.id == request.temp_id)
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
                "account_id": request.temp_id,
                "name": account_config.name,
                "status": "restarted",
                "qr_code_available": getattr(channel, "_current_qr_code_path", None) is not None
            }

    # 3. 创建临时账号配置
    from config.social_config import WeixinAccountConfig
    temp_account = WeixinAccountConfig(
        id=request.temp_id,
        name=f"临时账号-{request.temp_id}",  # 临时名称，稍后更新
        base_url="https://ilinkai.weixin.qq.com",
        token="",
        enabled=True,
        allow_from=["*"],
        auto_start=True
    )

    # 4. 添加到配置（临时）
    config.weixin.accounts.append(temp_account)
    if not save_config(config):
        logger.error("failed_to_save_config", temp_id=request.temp_id)
        raise HTTPException(status_code=500, detail="Failed to save configuration")

    # 5. 创建并启动渠道
    try:
        logger.info("creating_weixin_channel", temp_id=request.temp_id)
        channel = manager._create_weixin_channel(temp_account)
        channel_key = f"weixin:{request.temp_id}"
        manager.channels[channel_key] = channel

        # ✅ 注册到 AgentBridge（用于获取机器人账号）
        if manager.agent_bridge:
            manager.agent_bridge.register_channel(channel)
            logger.info("channel_registered_to_agent_bridge", channel_name=channel_key)

        logger.info("channel_created", temp_id=request.temp_id, channel_key=channel_key)

        # ✅ 异步任务：生成二维码并等待登录
        async def login_and_start():
            try:
                logger.info("starting_login_async", temp_id=request.temp_id)

                # 初始化HTTP客户端
                channel._client = httpx.AsyncClient(
                    timeout=httpx.Timeout(60, connect=30),
                    follow_redirects=True,
                )
                channel._running = True

                # 只生成二维码，不等待扫码完成
                try:
                    qrcode_id = await channel._init_qr_login()
                    logger.info("qrcode_generated", temp_id=request.temp_id, qrcode_id=qrcode_id)
                except Exception as e:
                    logger.error("qrcode_generation_failed", temp_id=request.temp_id, error=str(e), exc_info=True)

                # 启动轮询（start方法会继续等待扫码并完成登录）
                await channel.start()

            except Exception as e:
                logger.error("login_async_failed", temp_id=request.temp_id, error=str(e), exc_info=True)

        # 立即创建异步任务，不等待
        asyncio.create_task(login_and_start())

        # 等待二维码就绪（最多5秒）
        try:
            logger.info("waiting_for_qrcode", temp_id=request.temp_id)
            await asyncio.wait_for(channel._qr_code_ready.wait(), timeout=5.0)
            logger.info(
                "qrcode_ready",
                temp_id=request.temp_id,
                qr_path=str(getattr(channel, "_current_qr_code_path", None))
            )
        except asyncio.TimeoutError:
            logger.warning(
                "qrcode_ready_timeout",
                temp_id=request.temp_id,
                timeout_seconds=5.0
            )

        logger.info(
            "temp_account_auto_created",
            temp_id=request.temp_id,
            channel_key=channel_key
        )

        return {
            "account_id": request.temp_id,
            "name": temp_account.name,
            "status": "created",
            "qr_code_available": getattr(channel, "_current_qr_code_path", None) is not None
        }

    except Exception as e:
        logger.error(
            "failed_to_auto_create_account",
            temp_id=request.temp_id,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Failed to auto-create account: {str(e)}")


@router.post("/weixin/{account_id}/finalize")
async def finalize_account(account_id: str, request: FinalizeRequest):
    """
    完成账号创建（扫码登录成功后调用）

    Args:
        account_id: 账号ID
        request: 完成请求（包含显示名称）

    Returns:
        操作结果
    """
    manager = get_channel_manager()
    if not manager:
        raise HTTPException(status_code=404, detail="Channel manager not found")

    channel_key = f"weixin:{account_id}"
    channel = manager.channels.get(channel_key)

    if not channel:
        raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found")

    # 1. 获取 bot_account 和 token
    bot_account = getattr(channel, "bot_account", None)
    if not bot_account:
        logger.warning("bot_account_not_found", account_id=account_id)
        bot_account = f"weixin_{account_id}"

    # ✅ 获取 token 并保存到配置文件
    token = getattr(channel, "_token", None)
    if token:
        logger.info("Saving token to config file", account_id=account_id, token_preview=token[:20])

    # 2. 更新配置中的账号名称和 token
    config = load_config()
    for acc in config.weixin.accounts:
        if acc.id == account_id:
            acc.name = request.name
            if token:  # ✅ 保存 token
                acc.token = token
            break

    save_config(config)

    # 3. 更新渠道配置
    channel.config.name = request.name
    channel.display_name = request.name

    logger.info(
        "account_finalized",
        account_id=account_id,
        name=request.name,
        bot_account=bot_account
    )

    return {
        "message": "Account finalized successfully",
        "account_id": account_id,
        "name": request.name,
        "bot_account": bot_account
    }


@router.post("/reload")
async def reload_channels():
    """
    重新加载所有渠道配置（支持动态增删账户）

    - 停止已删除的账户
    - 启动新添加的账户
    - 保留仍在运行的账户
    - 清理无效的状态文件

    Returns:
        操作结果
    """
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
