"""
Browser Tool Configuration

Configuration settings for browser automation tool.
"""
from typing import List, Optional


class BrowserConfig:
    """Browser tool configuration

    Settings:
    - Browser settings (headless, viewport)
    - Timeout settings
    - Content limits
    - Security options
    - Session management
    """

    # ========================================
    # Browser Settings
    # ========================================

    # Headless mode (no visible UI)
    HEADLESS: bool = True

    # Viewport size
    VIEWPORT_WIDTH: int = 1920
    VIEWPORT_HEIGHT: int = 1080

    # User agent
    USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    # Browser launch args
    BROWSER_ARGS: List[str] = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled"
    ]

    # ========================================
    # Timeout Settings
    # ========================================

    # Default timeout for actions (milliseconds)
    DEFAULT_TIMEOUT: int = 30000  # 30 seconds

    # Navigation timeout (milliseconds)
    NAVIGATION_TIMEOUT: int = 60000  # 60 seconds

    # Session timeout (seconds, auto-cleanup)
    SESSION_TIMEOUT: int = 3600  # 1 hour

    # ========================================
    # Content Limits
    # ========================================

    # Max text content length for snapshot
    MAX_CONTENT_LENGTH: int = 10000

    # Max links to extract
    MAX_LINKS: int = 20

    # Max table rows to extract
    MAX_TABLE_ROWS: int = 100

    # Max list items to extract
    MAX_LIST_ITEMS: int = 50

    # ========================================
    # Security
    # ========================================

    # URL whitelist (None = allow all)
    # Example: ["https://python.org", "https://docs.python.org"]
    URL_WHITELIST: Optional[List[str]] = None

    # Allowed URL schemes
    ALLOWED_SCHEMES: List[str] = ["http", "https"]

    # ========================================
    # Session Management
    # ========================================

    # Max concurrent sessions
    MAX_SESSIONS: int = 10

    # Max pages per session
    MAX_PAGES_PER_SESSION: int = 20

    # ========================================
    # Screenshot Settings
    # ========================================

    # Screenshot format
    SCREENSHOT_FORMAT: str = "png"

    # Screenshot quality (for jpeg, 1-100)
    SCREENSHOT_QUALITY: int = 90

    # Full page screenshot
    FULL_PAGE_SCREENSHOT: bool = False

    # ========================================
    # Retry Settings
    # ========================================

    # Max retry attempts for failed actions
    MAX_RETRIES: int = 2

    # Retry delay (milliseconds)
    RETRY_DELAY: int = 1000

    # ========================================
    # Logging
    # ========================================

    # Enable detailed logging
    VERBOSE_LOGGING: bool = False

    # Log page errors
    LOG_PAGE_ERRORS: bool = True


# Global config instance
config = BrowserConfig()
