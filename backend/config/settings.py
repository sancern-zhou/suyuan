"""
Application settings and configuration management.
"""
from typing import List, Optional, Dict, Any, Literal
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator
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
    project_id: str = Field(
        default="default",
        validation_alias="PROJECT",
        pattern=r"^[a-z][a-z0-9_-]*$",
        description="Deployment manifest selected from projects/<id>/project.yaml",
    )
    app_role: str = Field(
        default="web",
        description="Application role: web, worker, or all. Web workers must not start background schedulers.",
    )
    sse_heartbeat_interval_seconds: float = Field(
        default=15.0,
        gt=0,
        description="Interval between transparent SSE comment heartbeats",
    )
    sse_send_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        description="Maximum duration of one SSE socket send operation",
    )

    # Backend URL Configuration (用于生成图片等资源的完整URL)
    backend_host: str = Field(
        default="http://localhost:8000",
        description="Backend server host URL (for generating image URLs)"
    )
    share_signing_secret: Optional[str] = Field(
        default=None,
        description="Secret used to sign scoped share grants",
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

    # Company Gateway Authentication
    auth_mode: Literal["company", "mock"] = Field(
        default="company",
        description="Authentication mode; mock is restricted to non-production development",
    )
    auth_sys_code: str = Field(default="SUYUAN", description="Company system code")
    auth_platform_sys_code: str = Field(
        default="JCXT",
        description="Application code sent to the company authentication service",
    )
    auth_service_url: str = Field(
        default="",
        description="Internal or gateway base URL for the company authentication service",
    )
    auth_login_path: str = Field(
        default="/auth/token/authentication",
        description="Company username/password authentication path",
    )
    auth_current_user_path: str = Field(
        default="/auth/account/getCurrentUser",
        description="Company current-user lookup path",
    )
    auth_logout_path: str = Field(
        default="/auth/token/logout",
        description="Company logout path",
    )
    auth_admin_role_codes: str = Field(
        default="",
        description="Comma-separated company role codes treated as Suyuan administrators",
    )
    auth_identity_cache_ttl_seconds: int = Field(
        default=60,
        ge=1,
        le=3600,
        description="Maximum Redis lifetime for resolved company identities",
    )
    auth_identity_cache_key_prefix: str = Field(
        default="suyuan:auth:",
        description="Redis prefix for authentication state",
    )
    auth_ws_ticket_ttl_seconds: int = Field(
        default=30,
        ge=5,
        le=120,
        description="Single-use WebSocket ticket lifetime",
    )
    auth_share_grant_ttl_seconds: int = Field(
        default=600,
        ge=30,
        le=86400,
        description="Signed anonymous share grant lifetime",
    )
    auth_docs_public: bool = Field(
        default=False,
        description="Allow anonymous Swagger/OpenAPI access",
    )
    auth_mock_user_id: str = Field(default="local-developer")
    auth_mock_username: str = Field(default="local-developer")
    auth_mock_display_name: str = Field(default="本地开发用户")
    auth_mock_role_codes: str = Field(default="")

    # Gateway routing and trust boundary
    gateway_api_prefix: str = Field(default="/api/suyuan")
    trusted_gateway_networks: str = Field(
        default="127.0.0.1/32,::1/128,10.10.204.0/24",
        description="Immediate socket-peer networks allowed to call company-auth mode",
    )

    # Nacos service registration
    nacos_server_addresses: str = Field(default="http://10.10.204.80:8848")
    nacos_namespace: str = Field(default="normcraft-ai")
    nacos_group: str = Field(default="DEFAULT_GROUP")
    nacos_service_name: str = Field(default="suyuan-agent")
    nacos_cluster_name: str = Field(default="DEFAULT")
    nacos_register_enabled: bool = Field(default=True)
    nacos_instance_enabled: bool = Field(default=True)
    nacos_instance_ip: str = Field(default="127.0.0.1")
    nacos_instance_port: int = Field(default=8000, ge=1, le=65535)
    nacos_username: str = Field(default="nacos")
    nacos_password: str = Field(default="")
    nacos_access_key: str = Field(default="")
    nacos_secret_key: str = Field(default="")

    @staticmethod
    def _split_unique_csv(value: str) -> List[str]:
        return list(dict.fromkeys(item.strip() for item in value.split(",") if item.strip()))

    @property
    def auth_admin_role_codes_set(self) -> set[str]:
        return set(self._split_unique_csv(self.auth_admin_role_codes))

    @property
    def auth_mock_role_codes_set(self) -> set[str]:
        return set(self._split_unique_csv(self.auth_mock_role_codes))

    @property
    def trusted_gateway_networks_list(self) -> List[str]:
        return self._split_unique_csv(self.trusted_gateway_networks)

    @property
    def nacos_server_addresses_list(self) -> List[str]:
        return self._split_unique_csv(self.nacos_server_addresses)

    @model_validator(mode="after")
    def validate_authentication_safety(self):
        if self.environment.strip().lower() != "production":
            return self

        if self.auth_mode == "mock":
            raise ValueError("production cannot enable mock authentication")
        if not self.nacos_register_enabled:
            raise ValueError("production requires Nacos registration")
        if not self.auth_service_url.strip():
            raise ValueError("production requires AUTH_SERVICE_URL")
        if not (self.share_signing_secret or "").strip():
            raise ValueError("production requires a share-signing secret")

        networks = set(self.trusted_gateway_networks_list)
        if not networks or networks.intersection({"*", "0.0.0.0/0", "::/0"}):
            raise ValueError("production requires a restricted trusted gateway network")
        return self

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
        description="LLM provider: openai, anthropic, deepseek, minimax, mimo, agnes, glm, bailian"
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
    openai_api_mode: str = Field(
        default="chat_completions",
        description="OpenAI API protocol mode: chat_completions"
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
    deepseek_api_mode: str = Field(
        default="anthropic_messages",
        description="DeepSeek API protocol mode: anthropic_messages or chat_completions"
    )

    bailian_api_key: Optional[str] = Field(default=None, description="Alibaba Cloud Bailian Token Plan API key")
    bailian_base_url: str = Field(
        default="https://token-plan.cn-beijing.maas.aliyuncs.com/apps/anthropic",
        description="Alibaba Cloud Bailian Anthropic-compatible API base URL",
    )
    bailian_model: str = Field(
        default="qwen3.8-max-preview",
        description="Default Bailian model used by Auto mode",
    )
    bailian_api_mode: str = Field(
        default="anthropic_messages",
        description="Bailian API protocol mode: anthropic_messages",
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
    minimax_api_mode: str = Field(
        default="anthropic_messages",
        description="MiniMax API protocol mode: anthropic_messages or chat_completions"
    )

    mimo_api_key: Optional[str] = Field(default=None, description="Xiaomi Mimo API key")
    mimo_base_url: str = Field(
        default="https://api.xiaomimimo.com/anthropic",
        description="Xiaomi Mimo Anthropic-compatible API base URL"
    )
    mimo_model: str = Field(
        default="mimo-v2-pro",
        description="Xiaomi Mimo model name"
    )
    mimo_api_mode: str = Field(
        default="anthropic_messages",
        description="Mimo API protocol mode: anthropic_messages or chat_completions"
    )
    agnes_api_key: Optional[str] = Field(default=None, description="Agnes API key")
    agnes_base_url: str = Field(
        default="https://apihub.agnes-ai.com/v1",
        description="Agnes OpenAI-compatible API base URL"
    )
    agnes_model: str = Field(
        default="agnes-2.0-flash",
        description="Agnes model name"
    )
    agnes_api_mode: str = Field(
        default="chat_completions",
        description="Agnes API protocol mode: chat_completions"
    )
    voice_mimo_base_url: str = Field(
        default="https://api.xiaomimimo.com/v1",
        description="Xiaomi Mimo OpenAI-compatible base URL for ASR/TTS"
    )
    voice_asr_model: str = Field(
        default="mimo-v2.5-asr",
        description="Voice ASR model name"
    )
    voice_tts_model: str = Field(
        default="mimo-v2.5-tts",
        description="Voice TTS model name"
    )
    voice_tts_voice: str = Field(
        default="冰糖",
        description="Default TTS voice"
    )
    voice_asr_timeout_seconds: float = Field(
        default=30.0,
        description="Timeout in seconds for voice ASR requests"
    )
    voice_tts_timeout_seconds: float = Field(
        default=45.0,
        description="Timeout in seconds for voice TTS requests"
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
    glm_api_mode: str = Field(
        default="anthropic_messages",
        description="GLM API protocol mode: anthropic_messages or chat_completions"
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
        default="minimax/MiniMax-M3,deepseek/deepseek-v4-flash",
        description="Comma-separated fallback models, e.g. agnes/agnes-2.0-flash,deepseek/deepseek-v4-flash"
    )
    llm_flash_models: str = Field(
        default="bailian/qwen3.6-flash,minimax/MiniMax-M3,deepseek/deepseek-v4-flash",
        description="Comma-separated Flash model priority chain, e.g. agnes/agnes-2.0-flash,deepseek/deepseek-v4-flash"
    )
    llm_pro_models: str = Field(
        default="bailian/deepseek-v4-pro,minimax/MiniMax-M3,deepseek/deepseek-v4-pro",
        description="Comma-separated Pro model priority chain, e.g. agnes/agnes-2.0-flash,deepseek/deepseek-v4-pro"
    )
    llm_multimodal_models: str = Field(
        default="bailian/qwen3.8-max-preview,mimo/mimo-v2-pro,agnes/agnes-2.0-flash,minimax/MiniMax-M3",
        description="Comma-separated multimodal model priority chain used by all Agent modes"
    )
    llm_failover_cooldown_seconds: int = Field(
        default=60,
        description="Cooldown seconds for transiently failing LLM providers"
    )

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
    agent_steering_redis_prefix: str = Field(
        default="suyuan:agent:steering",
        description="Redis key prefix for cross-worker active-run steering",
    )
    agent_steering_ttl_seconds: int = Field(
        default=7200,
        ge=60,
        description="TTL for active-run steering metadata and pending inputs",
    )

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

    # Tender Information Fetcher Configuration
    tender_fetcher_enabled: bool = Field(
        default=True,
        description="Enable daily tender information fetcher"
    )
    tender_fetcher_schedule: str = Field(
        default="30 2 * * *",
        description="Cron schedule for tender information fetcher"
    )
    tender_keywords: str = Field(
        default="生态环境局,环境监测中心,生态环境厅,环境监测站,生态环境分局,环境监控中心,污染源在线监控,空气自动站,水质自动站,VOCs走航,噪声自动监测",
        description="Comma-separated tender search keywords"
    )
    tender_notice_types: str = Field(
        default="tender,winning_bid",
        description="Comma-separated tender notice types"
    )
    tender_max_pages: int = Field(
        default=0,
        description="Qianlima pages to crawl; 0 means complete target-date crawl"
    )
    qianlima_base_url: str = Field(
        default="https://www.qianlima.com",
        description="Qianlima base URL"
    )
    qianlima_storage_state: str = Field(
        default="backend_data_registry/tenders/qianlima_storage_state.json",
        description="Qianlima Playwright storage state path"
    )
    qianlima_username: Optional[str] = Field(
        default=None,
        description="Qianlima username for optional login"
    )
    qianlima_password: Optional[str] = Field(
        default=None,
        description="Qianlima password for optional login"
    )
    qianlima_accounts: Optional[str] = Field(
        default=None,
        description="Comma-separated Qianlima account pool: username:password,..."
    )
    qianlima_proxy_server: Optional[str] = Field(
        default=None,
        description="Proxy server for Qianlima detail browser requests"
    )
    qianlima_proxy_username: Optional[str] = Field(
        default=None,
        description="Proxy username for Qianlima detail browser requests"
    )
    qianlima_proxy_password: Optional[str] = Field(
        default=None,
        description="Proxy password for Qianlima detail browser requests"
    )
    tender_llm_api_key: Optional[str] = Field(
        default=None,
        description="OpenAI-compatible API key for tender LLM screening and extraction"
    )
    tender_llm_base_url: Optional[str] = Field(
        default=None,
        description="OpenAI-compatible base URL for tender LLM"
    )
    tender_llm_model: Optional[str] = Field(
        default=None,
        description="Model name for tender LLM"
    )
    tender_llm_concurrency: int = Field(
        default=5,
        description="Max concurrent tender LLM detail requests for the primary provider"
    )
    tender_secondary_llm_api_key: Optional[str] = Field(
        default=None,
        description="OpenAI-compatible API key for secondary tender detail LLM"
    )
    tender_secondary_llm_base_url: Optional[str] = Field(
        default=None,
        description="OpenAI-compatible base URL for secondary tender detail LLM"
    )
    tender_secondary_llm_model: str = Field(
        default="qwen3.6-flash",
        description="Model name for secondary tender screening and detail LLM"
    )
    tender_secondary_llm_concurrency: int = Field(
        default=5,
        description="Max concurrent tender LLM detail requests for the secondary provider"
    )

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
                "api_mode": self.openai_api_mode,
            }
        elif self.llm_provider == "deepseek":
            return {
                "provider": "deepseek",
                "api_key": self.deepseek_api_key,
                "base_url": self.deepseek_base_url,
                "model": self.deepseek_model,
                "api_mode": self.deepseek_api_mode,
            }
        elif self.llm_provider == "bailian":
            return {
                "provider": "bailian",
                "api_key": self.bailian_api_key,
                "base_url": self.bailian_base_url,
                "model": self.bailian_model,
                "api_mode": self.bailian_api_mode,
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
                "api_mode": self.minimax_api_mode,
            }
        elif self.llm_provider == "mimo":
            return {
                "provider": "mimo",
                "api_key": self.mimo_api_key,
                "base_url": self.mimo_base_url,
                "model": self.mimo_model,
                "api_mode": self.mimo_api_mode,
            }
        elif self.llm_provider == "agnes":
            return {
                "provider": "agnes",
                "api_key": self.agnes_api_key or self.tender_secondary_llm_api_key,
                "base_url": self.agnes_base_url,
                "model": self.agnes_model,
                "api_mode": self.agnes_api_mode,
            }
        elif self.llm_provider == "glm":
            return {
                "provider": "glm",
                "api_key": self.glm_api_key,
                "base_url": self.glm_base_url,
                "anthropic_base_url": self.glm_anthropic_base_url,
                "model": self.glm_model,
                "api_mode": self.glm_api_mode,
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
