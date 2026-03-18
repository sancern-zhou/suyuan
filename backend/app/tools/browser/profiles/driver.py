"""Profile Driver

Handles profile lifecycle operations (start, stop, restart).
"""
import structlog
from typing import Optional
from playwright.sync_api import Browser, BrowserContext, Page, Playwright

from .config import BrowserProfile

logger = structlog.get_logger()


class ProfileDriver:
    """Profile lifecycle driver

    Manages starting and stopping browser instances for profiles.
    """

    def __init__(self, playwright: Playwright):
        """Initialize profile driver

        Args:
            playwright: Playwright instance
        """
        self._playwright = playwright

    def start_profile(self, profile: BrowserProfile) -> Browser:
        """Start browser for profile

        Args:
            profile: BrowserProfile configuration

        Returns:
            Playwright Browser instance

        Raises:
            RuntimeError: If profile fails to start
        """
        logger.info(
            "[PROFILE_DRIVER] Starting profile",
            profile=profile.name,
            user_data_dir=profile.user_data_dir,
            is_remote=profile.is_remote
        )

        try:
            if profile.is_remote and profile.cdp_port:
                # Connect to remote browser via CDP
                cdp_url = f"http://localhost:{profile.cdp_port}"
                logger.info("[PROFILE_DRIVER] Connecting to remote browser", cdp_url=cdp_url)
                browser = self._playwright.chromium.connect_over_cdp(cdp_url)
            else:
                # Launch new browser instance
                launch_args = profile.get_launch_args()
                logger.info(
                    "[PROFILE_DRIVER] Launching browser",
                    headless=launch_args.get("headless", False),
                    user_data_dir=launch_args.get("user_data_dir")
                )

                # Remove user_data_dir from args as it's passed separately
                browser = self._playwright.chromium.launch(
                    headless=launch_args.get("headless", False),
                    args=launch_args.get("args", [])
                )

            profile.running = True
            logger.info("[PROFILE_DRIVER] Profile started successfully", profile=profile.name)

            return browser

        except Exception as e:
            logger.error(
                "[PROFILE_DRIVER] Failed to start profile",
                profile=profile.name,
                error=str(e)
            )
            raise RuntimeError(f"Failed to start profile {profile.name}: {str(e)}") from e

    def stop_profile(self, profile: BrowserProfile, browser: Browser) -> bool:
        """Stop browser for profile

        Args:
            profile: BrowserProfile configuration
            browser: Browser instance to stop

        Returns:
            True if stopped successfully
        """
        logger.info("[PROFILE_DRIVER] Stopping profile", profile=profile.name)

        try:
            if browser:
                browser.close()

            profile.running = False
            logger.info("[PROFILE_DRIVER] Profile stopped successfully", profile=profile.name)

            return True

        except Exception as e:
            logger.error(
                "[PROFILE_DRIVER] Failed to stop profile",
                profile=profile.name,
                error=str(e)
            )
            return False

    def create_context(
        self,
        browser: Browser,
        profile: BrowserProfile,
        storage_state: Optional[str] = None
    ) -> BrowserContext:
        """Create browser context for profile

        Args:
            browser: Browser instance
            profile: BrowserProfile configuration
            storage_state: Path to storage state file

        Returns:
            BrowserContext instance
        """
        logger.info(
            "[PROFILE_DRIVER] Creating context",
            profile=profile.name,
            has_storage_state=storage_state is not None
        )

        context_args = {
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "ignore_https_errors": True,
        }

        if storage_state:
            context_args["storage_state"] = storage_state

        context = browser.new_context(**context_args)

        logger.info("[PROFILE_DRIVER] Context created", profile=profile.name)

        return context

    def create_page(self, context: BrowserContext) -> Page:
        """Create new page in context

        Args:
            context: BrowserContext instance

        Returns:
            Page instance
        """
        page = context.new_page()
        return page
