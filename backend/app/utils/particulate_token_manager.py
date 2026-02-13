"""
颗粒物API Token管理器

实现功能：
1. Token获取与缓存
2. 自动过期刷新
3. 401响应自动重试
4. 配置热更新
"""

import os
import time
import yaml
import logging
import requests
from typing import Optional, Dict, Any
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件（确保环境变量可用）
load_dotenv()

logger = logging.getLogger(__name__)


class ParticulateTokenManager:
    """
    颗粒物API Token管理器

    参考 vanna广东省颗粒物 项目的实现
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化Token管理器

        Args:
            config_path: 配置文件路径，默认为 backend/config/external_api_config.yaml
        """
        if config_path is None:
            # 默认配置路径（backend/config/external_api_config.yaml）
            current_dir = Path(__file__).parent
            # 从 app/utils 向上两级到 backend，然后进入 config
            config_path = current_dir.parent.parent / "config" / "external_api_config.yaml"

        self.config_path = Path(config_path)
        self.logger = logger

        # Token缓存
        self._token: Optional[str] = None
        self._token_expire_time: float = 0  # Token过期时间戳

        # 配置缓存
        self._cfg: Dict[str, Any] = {}
        self._cfg_mtime: float = 0

        # 首次加载配置
        self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """
        加载配置文件

        Returns:
            配置字典
        """
        if not self.config_path.exists():
            self.logger.error(f"[TokenManager] 配置文件不存在: {self.config_path}")
            return {}

        try:
            # 记录文件修改时间
            self._cfg_mtime = self.config_path.stat().st_mtime

            with open(self.config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}

            api_cfg = cfg.get("external_api", {})

            # 环境变量替换
            def replace_env(value):
                """递归替换环境变量占位符 ${VAR_NAME}"""
                if isinstance(value, str):
                    if value.startswith("${") and value.endswith("}"):
                        env_var = value[2:-1]
                        return os.getenv(env_var, value)
                    return value
                elif isinstance(value, dict):
                    return {k: replace_env(v) for k, v in value.items()}
                    return value
                elif isinstance(value, list):
                    return [replace_env(item) for item in value]
                return value

            self._cfg = replace_env(api_cfg)

            self.logger.debug(
                f"[TokenManager] 配置已加载: base_url={self._cfg.get('base_url')}, "
                f"username={self._cfg.get('username', 'N/A')}"
            )

            return self._cfg

        except Exception as e:
            self.logger.error(f"[TokenManager] 加载配置失败: {e}")
            return {}

    def _maybe_reload_config(self):
        """
        检测配置文件变化并自动重载
        """
        try:
            if self.config_path.exists():
                current_mtime = self.config_path.stat().st_mtime
                if current_mtime != self._cfg_mtime:
                    self.logger.info("[TokenManager] 检测到配置文件变化，重新加载...")
                    self._load_config()
                    # 配置变化时清除token，强制重新获取
                    self._token = None
                    self._token_expire_time = 0
        except Exception as e:
            self.logger.debug(f"[TokenManager] 配置重载检查失败: {e}")

    def get_token(self) -> Optional[str]:
        """
        获取有效的Token

        如果Token不存在或即将过期，自动刷新

        Returns:
            有效的Token字符串，失败返回None
        """
        self._maybe_reload_config()

        # 检查是否支持override_token（调试用）
        override_token = self._cfg.get("override_token")
        if override_token:
            if self._token != override_token:
                self.logger.warning("[TokenManager] 使用 override_token 覆盖当前Token")
            self._token = override_token
            return self._token

        # 检查Token是否有效
        if self._token and time.time() < self._token_expire_time:
            # Token仍然有效
            return self._token

        # Token无效或即将过期，刷新
        return self._refresh_token()

    def invalidate_token(self):
        """
        使当前Token失效

        用于401响应后强制刷新Token
        """
        self.logger.warning("[TokenManager] Token已失效，将强制刷新")
        self._token = None
        self._token_expire_time = 0

    def _refresh_token(self) -> Optional[str]:
        """
        刷新Token

        Returns:
            新Token字符串，失败返回None
        """
        self.logger.info("[TokenManager] 开始刷新Token...")

        base_url = self._cfg.get("base_url")
        token_endpoint = self._cfg.get("endpoints", {}).get("token")

        if not base_url or not token_endpoint:
            self.logger.error("[TokenManager] 缺少 base_url 或 token_endpoint 配置")
            return None

        url = f"{base_url.rstrip('/')}{token_endpoint}"
        username = self._cfg.get("username")
        password = self._cfg.get("password")
        sys_code = self._cfg.get("vocs_sys_code") or self._cfg.get("sys_code") or "SunSup"

        if not username or not password:
            self.logger.error("[TokenManager] 缺少 username 或 password 配置")
            return None

        headers = {
            "SysCode": sys_code,
            "syscode": sys_code,
        }

        try:
            # 尝试GET请求（首选方式）
            self.logger.debug(f"[TokenManager] GET {url} with username={username}")

            response = requests.get(
                url,
                params={"UserName": username, "Pwd": password},
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("success") and data.get("result"):
                    self._token = data["result"]

                    # 计算过期时间
                    cache_time = self._cfg.get("token_cache_time", 1800)
                    refresh_buffer = self._cfg.get("token_refresh_buffer", 300)
                    actual_cache_time = cache_time - refresh_buffer

                    self._token_expire_time = time.time() + actual_cache_time

                    self.logger.info(
                        f"[TokenManager] Token获取成功 (有效期: {actual_cache_time}秒, "
                        f"过期时间: {time.ctime(self._token_expire_time)})"
                    )
                    return self._token
                else:
                    self.logger.warning(f"[TokenManager] GET请求失败: {data}")
            else:
                self.logger.warning(f"[TokenManager] GET HTTP错误: {response.status_code}")

            # 尝试POST请求（备用方式）
            self.logger.debug("[TokenManager] 尝试使用POST获取Token")
            response2 = requests.post(
                url,
                data={"UserName": username, "Pwd": password},
                headers=headers,
                timeout=10
            )

            if response2.status_code == 200:
                data2 = response2.json()
                if data2.get("success") and data2.get("result"):
                    self._token = data2["result"]

                    cache_time = self._cfg.get("token_cache_time", 1800)
                    refresh_buffer = self._cfg.get("token_refresh_buffer", 300)
                    actual_cache_time = cache_time - refresh_buffer

                    self._token_expire_time = time.time() + actual_cache_time

                    self.logger.info("[TokenManager] Token获取成功 (POST方式)")
                    return self._token
                else:
                    self.logger.warning(f"[TokenManager] POST请求失败: {data2}")
            else:
                self.logger.warning(f"[TokenManager] POST HTTP错误: {response2.status_code}")

        except requests.exceptions.Timeout:
            self.logger.error("[TokenManager] Token请求超时")
        except requests.exceptions.ConnectionError as e:
            self.logger.error(f"[TokenManager] Token请求连接错误: {e}")
        except Exception as e:
            self.logger.error(f"[TokenManager] Token获取异常: {e}")

        return None

    def get_auth_headers(self) -> Dict[str, str]:
        """
        获取包含Token的认证请求头

        Returns:
            包含Authorization的请求头字典
        """
        token = self.get_token()
        if not token:
            raise Exception("无法获取API Token，请检查认证配置")

        sys_code = self._cfg.get("vocs_sys_code") or self._cfg.get("sys_code") or "SunSup"

        return {
            "Authorization": f"Bearer {token}",
            "SysCode": sys_code,
            "syscode": sys_code,
            "Content-Type": "application/json"
        }

    def get_base_url(self) -> str:
        """获取API基础URL"""
        self._maybe_reload_config()
        return self._cfg.get("base_url", "").rstrip("/")

    def get_endpoint(self, endpoint_name: str) -> Optional[str]:
        """
        获取指定端点的路径

        Args:
            endpoint_name: 端点名称（如 ionic_analysis, carbon_analysis）

        Returns:
            端点路径，失败返回None
        """
        self._maybe_reload_config()
        return self._cfg.get("endpoints", {}).get(endpoint_name)

    def is_token_valid(self) -> bool:
        """
        检查当前Token是否有效

        Returns:
            Token是否有效
        """
        return (
            self._token is not None
            and time.time() < self._token_expire_time
        )


# 全局单例
_token_manager: Optional[ParticulateTokenManager] = None


def get_particulate_token_manager() -> ParticulateTokenManager:
    """
    获取全局Token管理器实例（单例模式）

    Returns:
        Token管理器实例
    """
    global _token_manager
    if _token_manager is None:
        _token_manager = ParticulateTokenManager()
    return _token_manager


def reset_token_manager():
    """重置全局Token管理器（主要用于测试）"""
    global _token_manager
    _token_manager = None
