"""
社交平台配置模型

支持多微信账号配置
"""

from typing import List, Optional
from pydantic import BaseModel, Field
from pathlib import Path
import yaml


class WeixinAccountConfig(BaseModel):
    """单个微信账号配置"""
    id: str = Field(..., description="账号唯一标识")
    name: str = Field(..., description="显示名称")
    base_url: str = Field(default="https://ilinkai.weixin.qq.com", description="API基础URL")
    token: str = Field(default="", description="登录Token（自动保存）")
    enabled: bool = Field(default=True, description="是否启用")
    allow_from: List[str] = Field(default=["*"], description="允许的用户ID列表")
    auto_start: bool = Field(default=True, description="是否自动启动")

    # 运行时状态（不保存到配置文件）
    running: bool = Field(default=False, exclude=True)
    bot_account: Optional[str] = Field(default=None, exclude=True)
    login_status: str = Field(default="logged_out", exclude=True)


class WeixinConfig(BaseModel):
    """微信渠道配置（支持多账号）"""
    enabled: bool = Field(default=False, description="是否启用微信渠道")
    accounts: List[WeixinAccountConfig] = Field(default_factory=list, description="微信账号列表")


class ChannelGeneralConfig(BaseModel):
    """渠道通用配置"""
    send_progress: bool = True
    send_tool_hints: bool = False
    send_max_retries: int = 3


class SocialConfig(BaseModel):
    """社交平台总配置"""
    channels: ChannelGeneralConfig = Field(default_factory=ChannelGeneralConfig)
    qq: dict = Field(default_factory=lambda: {"enabled": False, "allow_from": ["*"]})
    weixin: WeixinConfig = Field(default_factory=WeixinConfig)
    dingtalk: dict = Field(default_factory=lambda: {"enabled": False, "allow_from": ["*"]})
    wecom: dict = Field(default_factory=lambda: {"enabled": False, "allow_from": ["*"]})


def load_social_config(config_path: str = "config/social_config.yaml") -> SocialConfig:
    """
    加载社交平台配置

    Args:
        config_path: 配置文件路径

    Returns:
        SocialConfig对象
    """
    config_file = Path(config_path)

    if not config_file.exists():
        # 返回默认配置
        return SocialConfig()

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        if not data:
            return SocialConfig()

        return SocialConfig(**data)

    except Exception as e:
        import structlog
        logger = structlog.get_logger()
        logger.error("failed_to_load_social_config", error=str(e), path=str(config_file))
        return SocialConfig()


def save_social_config(config: SocialConfig, config_path: str = "config/social_config.yaml") -> bool:
    """
    保存社交平台配置

    Args:
        config: SocialConfig对象
        config_path: 配置文件路径

    Returns:
        是否成功保存
    """
    config_file = Path(config_path)

    try:
        # 确保目录存在
        config_file.parent.mkdir(parents=True, exist_ok=True)

        # 转换为字典并保存
        data = config.model_dump()

        with open(config_file, 'w', encoding='utf-8') as f:
            yaml.safe_dump(data, f, allow_unicode=True, default_flow_style=False)

        return True

    except Exception as e:
        import structlog
        logger = structlog.get_logger()
        logger.error("failed_to_save_social_config", error=str(e), path=str(config_file))
        return False


def migrate_old_config(old_config_path: str = "config/social_config.yaml") -> bool:
    """
    迁移旧版配置到新格式

    旧格式：
    weixin:
      enabled: true
      token: "xxx"
      allow_from: ["*"]

    新格式：
    weixin:
      enabled: true
      accounts:
        - id: "account_1"
          name: "WeChat Account 1"
          token: "xxx"
          allow_from: ["*"]

    Args:
        old_config_path: 旧配置文件路径

    Returns:
        是否成功迁移
    """
    config_file = Path(old_config_path)

    if not config_file.exists():
        return False

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        if not data:
            return False

        # 检查是否需要迁移
        weixin_data = data.get('weixin', {})
        if 'accounts' not in weixin_data and 'token' in weixin_data:
            # 需要迁移
            old_weixin = weixin_data
            new_weixin = {
                'enabled': old_weixin.get('enabled', False),
                'accounts': [
                    {
                        'id': 'account_1',
                        'name': 'WeChat Account 1',
                        'base_url': old_weixin.get('base_url', 'https://ilinkai.weixin.qq.com'),
                        'token': old_weixin.get('token', ''),
                        'enabled': True,
                        'allow_from': old_weixin.get('allow_from', ['*']),
                        'auto_start': True
                    }
                ]
            }
            data['weixin'] = new_weixin

            # 备份旧配置
            backup_path = config_file.with_suffix('.yaml.bak')
            config_file.rename(backup_path)

            # 保存新配置
            with open(config_file, 'w', encoding='utf-8') as f:
                yaml.safe_dump(data, f, allow_unicode=True, default_flow_style=False)

            import structlog
            logger = structlog.get_logger()
            logger.info("old_config_migrated", backup_path=str(backup_path))
            return True

        return False

    except Exception as e:
        import structlog
        logger = structlog.get_logger()
        logger.error("failed_to_migrate_old_config", error=str(e))
        return False
