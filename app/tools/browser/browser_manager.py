"""
Browser Manager - Connection Pool and Session Management

Manages browser instances, contexts, and pages with:
- Connection pooling (single browser instance)
- Session isolation (multi-user support)
- Automatic lifecycle management
- Error recovery and cleanup

Uses Playwright SYNC API for Windows compatibility.
"""
from typing import Dict, Optional
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page, Playwright
import threading
import structlog
from datetime import datetime, timedelta

from .config import config

logger = structlog.get_logger()


class BrowserManager:
    """Browser connection and session manager (SYNC version)

    Uses Playwright sync API to avoid asyncio subprocess issues on Windows.
    All operations are synchronous and thread-safe.

    Features:
    - Single browser instance with multiple contexts
    - Session isolation (multi-user support)
    - Automatic lifecycle management
    - Error recovery and cleanup
    - Connection pooling

    Usage:
        manager = BrowserManager()
        page = manager.get_page(session_id="user_123")
        page.goto("https://example.com")
        manager.close_session("user_123")
    """

    def __init__(self):
        self._browser: Optional[Browser] = None
        self._contexts: Dict[str, BrowserContext] = {}
        self._pages: Dict[str, Page] = {}
        self._playwright: Optional[Playwright] = None
        self._lock = threading.Lock()
        self._session_metadata: Dict[str, Dict] = {}
        self._is_started = False

    def get_browser(self) -> Browser:
        """Get or create browser instance (thread-safe)

        Returns:
            Browser: Playwright browser instance
        """
        with self._lock:
            if not self._is_started:
                self._start_browser()

            if self._browser is None:
                raise RuntimeError("Browser not available")

            return self._browser

    def get_page(self, session_id: str = "default") -> Page:
        """Get or create page for session (thread-safe)

        Args:
            session_id: Session identifier (default: "default")

        Returns:
            Page: Playwright page instance
        """
        with self._lock:
            # Check session limits
            if len(self._contexts) >= config.MAX_SESSIONS:
                if session_id not in self._contexts:
                    # Clean up expired sessions
                    self._cleanup_expired_sessions()

                    # Still too many?
                    if len(self._contexts) >= config.MAX_SESSIONS:
                        raise RuntimeError(
                            f"Maximum sessions reached ({config.MAX_SESSIONS}). "
                            f"Please close some sessions first."
                        )

            # Get or create page
            if session_id not in self._pages:
                context = self._get_context(session_id)

                # Check page limit for session
                session_pages = [sid for sid in self._pages.keys() if sid.startswith(session_id)]
                if len(session_pages) >= config.MAX_PAGES_PER_SESSION:
                    raise RuntimeError(
                        f"Maximum pages per session reached ({config.MAX_PAGES_PER_SESSION})"
                    )

                page = context.new_page()
                self._pages[session_id] = page
                self._update_session_metadata(session_id)

                logger.info("page_created", session_id=session_id, total_pages=len(self._pages))

            # Update session activity
            self._update_session_metadata(session_id)

            return self._pages[session_id]

    def _get_context(self, session_id: str) -> BrowserContext:
        """Get or create browser context for session (thread-safe)

        Args:
            session_id: Session identifier

        Returns:
            BrowserContext: Playwright browser context
        """
        if session_id not in self._contexts:
            browser = self.get_browser()
            context = browser.new_context(
                viewport={
                    "width": config.VIEWPORT_WIDTH,
                    "height": config.VIEWPORT_HEIGHT
                },
                user_agent=config.USER_AGENT
            )
            self._contexts[session_id] = context

            logger.info(
                "context_created",
                session_id=session_id,
                total_contexts=len(self._contexts)
            )

        return self._contexts[session_id]

    def _start_browser(self):
        """Start browser instance (thread-safe)

        Launches Chromium browser with configured settings.
        """
        # Already started check
        if self._is_started:
            return

        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=config.HEADLESS,
                args=config.BROWSER_ARGS
            )

            self._is_started = True
            logger.info(
                "browser_started",
                headless=config.HEADLESS,
                args=config.BROWSER_ARGS
            )

        except Exception as e:
            logger.error("browser_start_failed", error=str(e))
            self._cleanup()
            raise RuntimeError(f"Failed to start browser: {str(e)}")

    def close_session(self, session_id: str):
        """Close session (context and pages) (thread-safe)

        Args:
            session_id: Session identifier
        """
        with self._lock:
            # Close all pages for this session
            pages_to_close = [
                (sid, page)
                for sid, page in list(self._pages.items())
                if sid == session_id or sid.startswith(f"{session_id}_")
            ]

            for sid, page in pages_to_close:
                try:
                    page.close()
                except Exception as e:
                    logger.warning("page_close_failed", session_id=sid, error=str(e))
                finally:
                    del self._pages[sid]

            # Close context
            if session_id in self._contexts:
                try:
                    self._contexts[session_id].close()
                except Exception as e:
                    logger.warning("context_close_failed", session_id=session_id, error=str(e))
                finally:
                    del self._contexts[session_id]

            # Remove metadata
            if session_id in self._session_metadata:
                del self._session_metadata[session_id]

            logger.info("session_closed", session_id=session_id)

    def close_all(self):
        """Close all sessions and browser (thread-safe)

        Performs complete cleanup of all resources.
        """
        with self._lock:
            logger.info("closing_all_sessions", total_sessions=len(self._contexts))

            # Close all sessions
            for session_id in list(self._contexts.keys()):
                # Release lock before recursive call
                self._lock.release()
                try:
                    self.close_session(session_id)
                finally:
                    self._lock.acquire()

            # Close browser
            if self._browser:
                try:
                    self._browser.close()
                except Exception as e:
                    logger.warning("browser_close_failed", error=str(e))
                finally:
                    self._browser = None

            # Stop playwright
            if self._playwright:
                try:
                    self._playwright.stop()
                except Exception as e:
                    logger.warning("playwright_stop_failed", error=str(e))
                finally:
                    self._playwright = None

            self._is_started = False
            logger.info("browser_closed")

    def _cleanup(self):
        """Cleanup resources (used in error handling)"""
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        finally:
            self._browser = None

        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        finally:
            self._playwright = None

        self._contexts.clear()
        self._pages.clear()
        self._session_metadata.clear()
        self._is_started = False

    def _update_session_metadata(self, session_id: str):
        """Update session metadata (last activity time)

        Args:
            session_id: Session identifier
        """
        self._session_metadata[session_id] = {
            "last_activity": datetime.now(),
            "created_at": self._session_metadata.get(session_id, {}).get(
                "created_at", datetime.now()
            )
        }

    def _cleanup_expired_sessions(self):
        """Cleanup expired sessions based on SESSION_TIMEOUT

        Removes sessions that have been inactive for longer than SESSION_TIMEOUT.
        """
        if not config.SESSION_TIMEOUT:
            return

        now = datetime.now()
        expired_sessions = []

        for session_id, metadata in list(self._session_metadata.items()):
            last_activity = metadata.get("last_activity", now)
            idle_time = (now - last_activity).total_seconds()

            if idle_time > config.SESSION_TIMEOUT:
                expired_sessions.append(session_id)

        for session_id in expired_sessions:
            logger.info(
                "session_expired",
                session_id=session_id,
                idle_seconds=int((now - self._session_metadata[session_id]["last_activity"]).total_seconds())
            )
            # Release lock before recursive call
            self._lock.release()
            try:
                self.close_session(session_id)
            finally:
                self._lock.acquire()

    def get_status(self) -> Dict:
        """Get browser manager status (thread-safe)

        Returns:
            Dict with status information
        """
        with self._lock:
            return {
                "browser_started": self._is_started,
                "browser_connected": self._browser is not None,
                "total_contexts": len(self._contexts),
                "total_pages": len(self._pages),
                "sessions": [
                    {
                        "session_id": sid,
                        "pages": len([p for sid2 in list(self._pages.keys()) if sid2 == sid or sid2.startswith(f"{sid}_")]),
                        "last_activity": metadata.get("last_activity").isoformat() if metadata.get("last_activity") else None
                    }
                    for sid, metadata in list(self._session_metadata.items())
                ]
            }
