"""Browser Tool Configuration"""
from typing import List
import os

class BrowserConfig:
    """Browser configuration settings"""

    # Browser launch settings
    HEADLESS = False  # Run in headless mode

    # 🔥 使用 Playwright 内置 Chromium（稳定可靠）
    USE_SYSTEM_CHROME = False  # 设为 False 使用内置浏览器
    # CHROME_CDP_URL = "http://localhost:9222"  # 不需要

    BROWSER_ARGS: List[str] = [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-blink-features=AutomationControlled'
        # 移除了绕过检测的参数，使用内置浏览器不需要
    ]

    # Timeout settings
    DEFAULT_TIMEOUT = 30000  # 30 seconds
    NAVIGATION_TIMEOUT = 60000  # 60 seconds

    # Content limits
    MAX_SNAPSHOT_LENGTH = 10000  # Max characters for text snapshot
    MAX_LINKS = 100  # Max links/images to extract

    # Backend URL for image access
    BACKEND_HOST = os.getenv("BACKEND_HOST", "http://localhost:8000")

    # Wait conditions configuration
    WAIT_DEFAULT_TIMEOUT = 10000  # 10 seconds
    WAIT_MIN_TIMEOUT = 500  # 500ms
    WAIT_MAX_TIMEOUT = 120000  # 120 seconds
    WAIT_FN_ENABLED = False  # JavaScript function wait (disabled by default for security)

config = BrowserConfig()
