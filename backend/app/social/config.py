"""Social platform configuration management."""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from pathlib import Path
import yaml


@dataclass
class SocialChannelConfig:
    """Configuration for a single social channel."""

    enabled: bool = False
    allow_from: List[str] = None
    streaming: bool = False

    # Platform-specific fields
    app_id: Optional[str] = None  # QQ
    secret: Optional[str] = None  # QQ, DingTalk, WeCom
    app_key: Optional[str] = None  # DingTalk
    app_secret: Optional[str] = None  # DingTalk
    corp_id: Optional[str] = None  # WeCom
    agent_id: Optional[str] = None  # WeCom

    # WeChat multi-instance accounts
    accounts: List[Any] = None  # List of WeixinAccountConfig objects

    def __post_init__(self):
        if self.allow_from is None:
            self.allow_from = ["*"]
        if self.accounts is None:
            self.accounts = []

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SocialChannelConfig':
        """Create from dictionary."""
        # Parse accounts field for WeChat multi-instance support
        accounts_data = data.get('accounts', [])
        accounts = []
        if accounts_data:
            # Convert dict accounts to WeixinAccountConfig objects
            for account_dict in accounts_data:
                if isinstance(account_dict, dict):
                    # Create a simple object to hold account config
                    from types import SimpleNamespace
                    accounts.append(SimpleNamespace(**account_dict))

        return cls(
            enabled=data.get('enabled', False),
            allow_from=data.get('allow_from', ['*']),
            streaming=data.get('streaming', False),
            app_id=data.get('app_id'),
            secret=data.get('secret'),
            app_key=data.get('app_key'),
            app_secret=data.get('app_secret'),
            corp_id=data.get('corp_id'),
            agent_id=data.get('agent_id'),
            accounts=accounts
        )


@dataclass
class SocialGlobalConfig:
    """Global social platform configuration."""

    send_progress: bool = True
    send_tool_hints: bool = False
    send_max_retries: int = 3

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SocialGlobalConfig':
        """Create from dictionary."""
        return cls(
            send_progress=data.get('send_progress', True),
            send_tool_hints=data.get('send_tool_hints', False),
            send_max_retries=data.get('send_max_retries', 3)
        )


@dataclass
class SocialConfig:
    """Complete social platform configuration."""

    qq: SocialChannelConfig = None
    weixin: SocialChannelConfig = None
    dingtalk: SocialChannelConfig = None
    wecom: SocialChannelConfig = None
    channels: SocialGlobalConfig = None

    def __post_init__(self):
        if self.qq is None:
            self.qq = SocialChannelConfig()
        if self.weixin is None:
            self.weixin = SocialChannelConfig()
        if self.dingtalk is None:
            self.dingtalk = SocialChannelConfig()
        if self.wecom is None:
            self.wecom = SocialChannelConfig()
        if self.channels is None:
            self.channels = SocialGlobalConfig()

    @classmethod
    def load_from_yaml(cls, path: str) -> 'SocialConfig':
        """
        Load configuration from YAML file.

        Args:
            path: Path to YAML configuration file

        Returns:
            SocialConfig instance
        """
        config_path = Path(path)

        if not config_path.exists():
            # Return default configuration
            return cls()

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if data is None:
                data = {}

            return cls(
                qq=SocialChannelConfig.from_dict(data.get('qq', {})),
                weixin=SocialChannelConfig.from_dict(data.get('weixin', {})),
                dingtalk=SocialChannelConfig.from_dict(data.get('dingtalk', {})),
                wecom=SocialChannelConfig.from_dict(data.get('wecom', {})),
                channels=SocialGlobalConfig.from_dict(data.get('channels', {}))
            )
        except Exception as e:
            import structlog
            logger = structlog.get_logger()
            logger.warning("Failed to load social config, using defaults", error=str(e))
            return cls()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'qq': self.qq.__dict__,
            'weixin': self.weixin.__dict__,
            'dingtalk': self.dingtalk.__dict__,
            'wecom': self.wecom.__dict__,
            'channels': self.channels.__dict__
        }
