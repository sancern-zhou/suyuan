"""
Application settings and configuration management.
"""
from typing import List, Optional, Dict, Any
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
import yaml
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Application configuration settings."""

    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env", Path.cwd() / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Server Configuration
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")
    environment: str = Field(default="development", description="Environment name")
    debug: bool = Field(default=True, description="Debug mode")
    log_level: str = Field(default="DEBUG", description="Logging level")
    app_role: str = Field(
        default="web",
        description="Application role: web, worker, or all. Web workers must not start background schedulers.",
    )

    # Backend URL Configuration (用于生成图片等资源的完整URL)
    backend_host: str = Field(
        default="http://localhost:8000",
        description="Backend server host URL (for generating image URLs)"
    )
    signed_media_base_url: Optional[str] = Field(
        default=None,
        description="Public backend URL for temporary signed media links"
    )
    signed_media_secret: Optional[str] = Field(
        default=None,
        description="Secret used to sign temporary media URLs"
    )
    signed_media_ttl_seconds: int = Field(
        default=600,
        description="Temporary signed media URL lifetime in seconds"
    )
    media_object_store_enabled: bool = Field(
        default=False,
        description="Upload social media to an S3-compatible object store before sending to multimodal LLMs"
    )
    media_object_store_endpoint_url: Optional[str] = Field(
        default=None,
        description="S3-compatible object store endpoint URL"
    )
    media_object_store_access_key_id: Optional[str] = Field(
        default=None,
        description="S3-compatible object store access key ID"
    )
    media_object_store_secret_access_key: Optional[str] = Field(
        default=None,
        description="S3-compatible object store secret access key"
    )
    media_object_store_bucket: Optional[str] = Field(
        default=None,
        description="S3-compatible object store bucket"
    )
    media_object_store_region: str = Field(
        default="auto",
        description="S3-compatible object store region"
    )
    media_object_store_prefix: str = Field(
        default="social-media",
        description="Object key prefix for uploaded social media"
    )
    media_object_store_presign_ttl_seconds: int = Field(
        default=600,
        description="Object store presigned URL lifetime in seconds"
    )
    api_base_url: Optional[str] = Field(
        default=None,
        description="Frontend API base URL (for callback URLs, overrides auto-detection)"
    )

    # Frontend URL Configuration (用于生成分享链接)
    frontend_base_url: str = Field(
        default="http://localhost:5174",
        description="Frontend base URL (for generating share links)"
    )

    # CORS Configuration
    cors_origins: str = Field(
        default="http://localhost:5173,http://localhost:5174,http://localhost:5175,http://localhost:5176,http://localhost:5177",
        description="Allowed CORS origins (comma-separated)"
    )

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins string into list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    # External API Endpoints
    station_api_base_url: str = Field(
        default="http://180.184.91.74:9095",
        description="Station and district query API base URL"
    )
    monitoring_data_api_url: str = Field(
        default="http://180.184.91.74:9091",
        description="Monitoring data API URL"
    )
    vocs_data_api_url: str = Field(
        default="http://180.184.91.74:9092",
        description="VOCs component data API URL"
    )
    particulate_data_api_url: str = Field(
        default="http://180.184.91.74:9093",
        description="Particulate component data API URL"
    )
    meteorological_api_url: str = Field(
        default="http://180.184.30.94/api/AiDataService/ReportApplication/UserReportDataQuery/Query",
        description="Meteorological data API URL"
    )
    upwind_analysis_api_url: str = Field(
        default="http://180.184.91.74:9095",
        description="Upwind analysis API base URL (port 9095 for upwind-and-map)"
    )

    # API Keys
    meteorological_api_key: Optional[str] = Field(
        default=None,
        description="Meteorological API key"
    )
    amap_public_key: Optional[str] = Field(
        default=None,
        description="AMap (Gaode) public API key"
    )
    
    # NOAA HYSPLIT API Key
    # 获取方式: 发送邮件至 hysplit.support@noaa.gov 说明用途即可
    # 文档: https://www.ready.noaa.gov/READYmetapi.php
    noaa_hysplit_api_key: Optional[str] = Field(
        default=None,
        description="NOAA HYSPLIT READY API key (email hysplit.support@noaa.gov to obtain)"
    )

    # LLM Configuration
    llm_provider: str = Field(
        default="openai",
        description="LLM provider: openai, anthropic, deepseek, minimax, mimo, qwen, glm"
    )
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key")
    openai_base_url: str = Field(
        default="https://api.openai.com/v1",
        description="OpenAI API base URL"
    )
    openai_model: str = Field(
        default="gpt-4-turbo-preview",
        description="OpenAI model name"
    )

    deepseek_api_key: Optional[str] = Field(default=None, description="DeepSeek API key")
    deepseek_base_url: str = Field(
        default="https://api.deepseek.com/v1",
        description="DeepSeek API base URL"
    )
    deepseek_model: str = Field(
        default="deepseek-v4-flash",
        description="DeepSeek model name"
    )

    anthropic_api_key: Optional[str] = Field(default=None, description="Anthropic API key")
    anthropic_auth_token: Optional[str] = Field(default=None, description="Anthropic-compatible auth token")
    anthropic_base_url: Optional[str] = Field(default=None, description="Anthropic-compatible API base URL")
    anthropic_model: str = Field(
        default="claude-3-opus-20240229",
        description="Anthropic model name"
    )

    minimax_api_key: Optional[str] = Field(default=None, description="MiniMax API key")
    minimax_base_url: str = Field(
        default="https://api.minimaxi.com/v1",
        description="MiniMax OpenAI-compatible API base URL"
    )
    minimax_anthropic_base_url: str = Field(
        default="https://api.minimaxi.com/anthropic",
        description="MiniMax Anthropic-compatible API base URL"
    )
    minimax_model: str = Field(
        default="MiniMax-M3",
        description="MiniMax model name"
    )

    mimo_api_key: Optional[str] = Field(default=None, description="Xiaomi Mimo API key")
    mimo_base_url: str = Field(
        default="https://api.xiaomimimo.com/v1",
        description="Xiaomi Mimo API base URL"
    )
    mimo_model: str = Field(
        default="mimo-v2-pro",
        description="Xiaomi Mimo model name"
    )

    glm_api_key: Optional[str] = Field(default=None, description="GLM API key")
    glm_base_url: str = Field(
        default="https://open.bigmodel.cn/api/coding/paas/v4",
        description="GLM OpenAI-compatible API base URL"
    )
    glm_anthropic_base_url: Optional[str] = Field(
        default=None,
        description="GLM Anthropic-compatible API base URL"
    )
    glm_model: str = Field(
        default="glm-4.7",
        description="GLM model name"
    )

    # 报告模式配置
    report_mode_max_tokens: int = Field(
        default=8000,
        description="Max tokens for report mode (generate DOCX reports)"
    )

    # Anthropic Format Configuration (V3 - Anthropic native only)
    # 所有端点从环境变量读取，不再使用硬编码默认值
    anthropic_compatible_endpoints: Dict[str, str] = Field(
        default={},  # 空字典，强制从环境变量读取
        description="Providers with Anthropic-compatible endpoints (从环境变量读取)"
    )

    # LLM Temperature Configuration
    llm_temperature: float = Field(
        default=0.3,
        description="Default temperature for LLM generation"
    )
    llm_global_max_concurrency: int = Field(
        default=2,
        description="Concurrent LLM request limit per provider/model pool"
    )
    llm_request_timeout_seconds: float = Field(
        default=180.0,
        description="Timeout in seconds for LLM provider requests"
    )
    llm_fallbacks: str = Field(
        default="",
        description="Comma-separated fallback models, e.g. deepseek/deepseek-v4-flash,mimo/mimo-v2-pro"
    )
    llm_flash_models: str = Field(
        default="",
        description="Comma-separated Flash model priority chain, e.g. deepseek/deepseek-v4-flash,mimo/mimo-v2.5"
    )
    llm_pro_models: str = Field(
        default="",
        description="Comma-separated Pro model priority chain, e.g. mimo/mimo-v2.5-pro,deepseek/deepseek-v4-pro"
    )
    llm_multimodal_models: str = Field(
        default="mimo/mimo-v2.5,minimax/MiniMax-M3",
        description="Comma-separated Auto multimodal model priority chain"
    )
    llm_failover_cooldown_seconds: int = Field(
        default=60,
        description="Cooldown seconds for transiently failing LLM providers"
    )

    # 千问3配置
    qwen_api_key: Optional[str] = Field(default=None, description="Qwen3 API key")
    qwen_base_url: str = Field(
        default="https://public-1960182902053687299-iaaa.ksai.scnet.cn:58043/v1",
        description="Qwen3 API base URL"
    )
    qwen_model: str = Field(
        default="qwen3",
        description="Qwen3 model name"
    )
    qwen_vl_api_key: Optional[str] = Field(default=None, description="Qwen VL API key for OCR/image analysis")
    qwen_vl_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        description="Qwen VL OpenAI-compatible API base URL"
    )
    qwen_vl_model: str = Field(default="qwen-vl-ocr", description="Qwen OCR model name")
    qwen_vision_model: str = Field(default="qwen-vl-max", description="Qwen model for visual understanding tasks")
    mimo_vl_api_key: Optional[str] = Field(default=None, description="Mimo VL API key for flow visual checks")
    mimo_vl_base_url: Optional[str] = Field(
        default=None,
        description="Mimo VL OpenAI-compatible API base URL"
    )
    mimo_vl_model: str = Field(default="mimo-v2.5", description="Mimo VL model name")
    ops_attachment_root: Optional[str] = Field(default=None, description="Local root used to resolve /WebFiles attachments")
    attachment_root: Optional[str] = Field(default=None, description="Fallback local attachment root")
    ops_attachment_base_url: Optional[str] = Field(default=None, description="Base URL used to resolve /WebFiles attachments")
    attachment_base_url: Optional[str] = Field(default=None, description="Fallback attachment base URL")

    # 阿里云OCR配置
    aliyun_ocr_access_key_id: Optional[str] = Field(
        default=None,
        description="Alibaba Cloud OCR AccessKey ID"
    )
    aliyun_ocr_access_key_secret: Optional[str] = Field(
        default=None,
        description="Alibaba Cloud OCR AccessKey Secret"
    )

    # Redis Configuration
    redis_host: str = Field(default="localhost", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_db: int = Field(default=0, description="Redis database number")
    redis_password: Optional[str] = Field(default=None, description="Redis password")

    # Cache TTL (seconds)
    cache_ttl_config: int = Field(default=3600, description="Config cache TTL")
    cache_ttl_analysis: int = Field(default=1800, description="Analysis cache TTL")
    cache_ttl_weather: int = Field(default=600, description="Weather cache TTL")

    # Data Registry Configuration
    data_registry_dir: str = Field(
        default="backend_data_registry",
        description="Relative or absolute path for structured data registry storage"
    )

    # Analysis Parameters
    default_search_range_km: float = Field(
        default=5.0,
        description="Default search range in kilometers"
    )
    default_max_enterprises: int = Field(
        default=10,
        description="Default max enterprises to fetch"
    )
    default_top_n_enterprises: int = Field(
        default=10,
        description="Default top N enterprises to return"
    )
    wind_speed_low_threshold: float = Field(
        default=1.5,
        description="Wind speed threshold for calm conditions"
    )
    candidate_radius_km: float = Field(
        default=25.0,
        description="Candidate enterprise search radius"
    )
    nearby_stations_radius_km: float = Field(
        default=20.0,
        description="Nearby stations search radius in kilometers"
    )
    nearby_stations_max_results: int = Field(
        default=5,
        description="Maximum number of nearby stations to fetch"
    )
    sector_half_angle: float = Field(
        default=11.25,
        description="Wind sector half angle in degrees"
    )

    # Retry Configuration
    max_retries: int = Field(default=2, description="Maximum retry attempts")
    retry_interval_ms: int = Field(default=500, description="Retry interval in milliseconds")
    request_timeout_seconds: int = Field(default=30, description="HTTP request timeout")
    vocs_api_timeout_seconds: int = Field(default=120, description="VOCs API timeout (2 minutes for large data queries)")

    # SQL Server Configuration (History Database)
    sqlserver_host: str = Field(
        default="180.184.30.94",
        description="SQL Server host"
    )
    sqlserver_port: int = Field(
        default=1433,
        description="SQL Server port"
    )
    sqlserver_database: str = Field(
        default="XcAiDb",
        description="SQL Server database name"
    )
    sqlserver_user: str = Field(
        default="sa",
        description="SQL Server username"
    )
    sqlserver_password: str = Field(
        default="",
        description="SQL Server password"
    )
    sqlserver_driver: str = Field(
        default="ODBC Driver 17 for SQL Server",
        description="SQL Server ODBC driver name"
    )

    def model_post_init(self, __context) -> None:
        """
        Post-initialization hook to handle password with leading # character.

        WORKAROUND: .env files treat lines starting with # as comments.
        If password is empty after loading from .env, use the hardcoded value.
        This is a temporary solution until the .env parsing issue is resolved.
        """
        if not self.sqlserver_password or len(self.sqlserver_password.strip()) == 0:
            # Hardcoded password as fallback (SECURITY: Remove in production!)
            self.sqlserver_password = "#Ph981,6J2bOkWYT7p?5slH$I~g_0itR"
            import structlog
            logger = structlog.get_logger()
            logger.warning(
                "sqlserver_password_override",
                reason="Empty password in .env, using hardcoded fallback",
                message="SECURITY WARNING: Hardcoded password in use!"
            )

    @property
    def sqlserver_connection_string(self) -> str:
        """
        Construct SQL Server connection string.

        Note: Password is wrapped in braces to handle special characters
        like #, ?, $, etc. that have special meaning in ODBC connection strings.
        """
        return (
            f"DRIVER={{{self.sqlserver_driver}}};"
            f"SERVER={self.sqlserver_host},{self.sqlserver_port};"
            f"DATABASE={self.sqlserver_database};"
            f"UID={self.sqlserver_user};"
            f"PWD={{{self.sqlserver_password}}};"  # Wrap password in braces for special chars
            f"TrustServerCertificate=yes;"
        )

    # Query Template Configuration
    query_template_city_pollutant: str = Field(
        default="{city}市{pollutant}小时平均浓度，时间为{start_time}至{end_time}",
        description="City-level pollutant query template"
    )
    query_template_station_pollutant: str = Field(
        default="{station_name}站点的小时{pollutant}污染物浓度，时间为{start_time}至{end_time}",
        description="Station-level pollutant query template"
    )

    # Social Platform Configuration
    social_config_path: str = Field(
        default="config/social_config.yaml",
        description="Path to social platform configuration file"
    )
    social_enabled: bool = Field(
        default=False,
        description="Enable social platform integration"
    )
    social_worker_internal_host: str = Field(
        default="127.0.0.1",
        description="Host for the worker-only social account internal API"
    )
    social_worker_internal_port: int = Field(
        default=8011,
        description="Port for the worker-only social account internal API"
    )
    social_worker_internal_url: str = Field(
        default="http://127.0.0.1:8011",
        description="Base URL used by web processes to reach the social worker internal API"
    )
    social_worker_internal_token: str = Field(
        default="",
        description="Shared token for web-to-worker social account API calls"
    )

    @property
    def redis_url(self) -> str:
        """Construct Redis URL."""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    def get_llm_config(self) -> dict:
        """Get LLM configuration based on provider."""
        if self.llm_provider == "openai":
            return {
                "provider": "openai",
                "api_key": self.openai_api_key,
                "base_url": self.openai_base_url,
                "model": self.openai_model,
            }
        elif self.llm_provider == "deepseek":
            return {
                "provider": "deepseek",
                "api_key": self.deepseek_api_key,
                "base_url": self.deepseek_base_url,
                "model": self.deepseek_model,
            }
        elif self.llm_provider == "anthropic":
            return {
                "provider": "anthropic",
                "api_key": self.anthropic_api_key,
                "model": self.anthropic_model,
            }
        elif self.llm_provider == "minimax":
            return {
                "provider": "minimax",
                "api_key": self.minimax_api_key,
                "base_url": self.minimax_base_url,
                "model": self.minimax_model,
            }
        elif self.llm_provider == "mimo":
            return {
                "provider": "mimo",
                "api_key": self.mimo_api_key,
                "base_url": self.mimo_base_url,
                "model": self.mimo_model,
            }
        elif self.llm_provider == "qwen":
            return {
                "provider": "qwen",
                "api_key": self.qwen_api_key,
                "base_url": self.qwen_base_url,
                "model": self.qwen_model,
            }
        elif self.llm_provider == "glm":
            return {
                "provider": "glm",
                "api_key": self.glm_api_key,
                "base_url": self.glm_base_url,
                "anthropic_base_url": self.glm_anthropic_base_url,
                "model": self.glm_model,
            }
        else:
            raise ValueError(f"Unsupported LLM provider: {self.llm_provider}")

    def load_social_config(self) -> Dict[str, Any]:
        """
        Load social platform configuration from YAML file.

        Returns:
            Dictionary with channel configurations
        """
        config_path = Path(self.social_config_path)

        if not config_path.exists():
            # Return default empty config
            return {
                "qq": {"enabled": False, "allow_from": ["*"]},
                "weixin": {"enabled": False, "allow_from": ["*"]},
                "dingtalk": {"enabled": False, "allow_from": ["*"]},
                "channels": {
                    "send_progress": True,
                    "send_tool_hints": False,
                    "send_max_retries": 3
                }
            }

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            # Validate config structure
            if not isinstance(config, dict):
                raise ValueError("Invalid social config structure")

            return config
        except Exception as e:
            import structlog
            logger = structlog.get_logger()
            logger.warning("Failed to load social config, using defaults", error=str(e))
            return self.load_social_config()  # Return default config


# Global settings instance
settings = Settings()
