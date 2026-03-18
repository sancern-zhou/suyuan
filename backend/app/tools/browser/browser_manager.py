"""Browser Manager - SYNC API version"""
import threading
import structlog
import os
from typing import Optional, Dict
from pathlib import Path
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page, Playwright

from .config import config

logger = structlog.get_logger()

class BrowserManager:
    """Manages browser lifecycle using Playwright SYNC API

    Thread-safe singleton pattern for browser instance management.
    """

    def __init__(self):
        self._browser: Optional[Browser] = None
        self._playwright_obj: Optional[sync_playwright] = None  # 🔥 保存上下文管理器对象
        self._playwright: Optional[Playwright] = None
        self._contexts: Dict[str, BrowserContext] = {}
        self._pages: Dict[str, Page] = {}
        self._lock = threading.Lock()
        self._is_started = False
        # 🔥 新增：登录状态持久化目录
        self._storage_dir = Path("backend_data/browser_storage")
        self._storage_dir.mkdir(parents=True, exist_ok=True)

    def get_browser(self) -> Browser:
        """Get or create browser instance (thread-safe)

        NOTE: Caller must hold self._lock when calling this method
        """
        logger.info("[BROWSER_MANAGER] get_browser called", is_started=self._is_started)

        # NOTE: Don't use lock here - caller should already hold it
        # This prevents deadlock when called from get_page()
        if not self._is_started:
            logger.info("[BROWSER_MANAGER] browser not started, calling _start_browser_internal()...")
            self._start_browser_internal()
            logger.info("[BROWSER_MANAGER] _start_browser_internal() completed")
        return self._browser

    def _start_browser_internal(self):
        """Start browser instance (internal method, no lock - caller must hold lock)"""
        if self._is_started:
            return

        logger.info(
            "[BROWSER_MANAGER] _start_browser_internal: Starting Playwright...",
            thread_id=threading.get_ident()
        )
        try:
            logger.info("[BROWSER_MANAGER] _start_browser_internal: Calling sync_playwright().start()...")
            # 🔥 正确使用上下文管理器，避免异步事件循环冲突
            self._playwright_obj = sync_playwright()
            self._playwright = self._playwright_obj.__enter__()
            logger.info("[BROWSER_MANAGER] _start_browser_internal: Playwright started successfully")

            # 🔥 检查是否使用系统 Chrome
            if config.USE_SYSTEM_CHROME:
                logger.info("[BROWSER_MANAGER] Connecting to system Chrome via CDP...")
                logger.info("[BROWSER_MANAGER] CDP URL: %s", config.CHROME_CDP_URL)
                logger.info("[BROWSER_MANAGER] IMPORTANT: Make sure Chrome is running with --remote-debugging-port=9222")

                try:
                    # 连接到已运行的系统 Chrome
                    self._browser = self._playwright.chromium.connect_over_cdp(config.CHROME_CDP_URL)
                    logger.info("[BROWSER_MANAGER] Connected to system Chrome successfully")
                except Exception as cdp_error:
                    logger.error("[BROWSER_MANAGER] Failed to connect to system Chrome", error=str(cdp_error))
                    logger.error("[BROWSER_MANAGER] Please run: chrome.exe --remote-debugging-port=9222")
                    raise RuntimeError(
                        f"Cannot connect to system Chrome at {config.CHROME_CDP_URL}. "
                        f"Please start Chrome with: chrome.exe --remote-debugging-port=9222"
                    ) from cdp_error
            else:
                # 使用 Playwright 自带的 Chromium
                logger.info("[BROWSER_MANAGER] _start_browser_internal: Launching Playwright Chromium...")
                logger.info("[BROWSER_MANAGER] _start_browser_internal: headless=%s, args=%s", config.HEADLESS, config.BROWSER_ARGS)
                self._browser = self._playwright.chromium.launch(
                    headless=config.HEADLESS,
                    args=config.BROWSER_ARGS
                )
                logger.info("[BROWSER_MANAGER] _start_browser_internal: Browser launched successfully")

            self._is_started = True
            logger.info("[BROWSER_MANAGER] _start_browser_internal: Browser start completed")
        except Exception as e:
            logger.error("[BROWSER_MANAGER] _start_browser_internal: Failed to start browser", error=str(e), error_type=type(e).__name__)
            raise

    def stop_browser(self) -> int:
        """Stop browser and cleanup resources

        Returns:
            Number of sessions closed
        """
        with self._lock:
            if not self._is_started:
                return 0

            # 关闭前自动保存所有 session 的登录状态
            sessions_closed = len(self._contexts)
            if sessions_closed > 0:
                logger.info(f"[BROWSER_MANAGER] Saving {sessions_closed} session(s) before shutdown")
                self._save_all_sessions()

            # Close all contexts
            for session_id, context in list(self._contexts.items()):
                try:
                    context.close()
                except Exception as e:
                    logger.warning(f"[BROWSER_MANAGER] Failed to close context {session_id}", error=str(e))

            # Close browser
            try:
                self._browser.close()
            except Exception as e:
                logger.warning("[BROWSER_MANAGER] Failed to close browser", error=str(e))

            # Stop playwright
            try:
                if self._playwright_obj is not None:
                    self._playwright_obj.__exit__(None, None, None)
                    self._playwright_obj = None
                elif self._playwright is not None:
                    self._playwright.stop()
            except Exception as e:
                logger.warning("[BROWSER_MANAGER] Failed to stop playwright", error=str(e))

            # Clear state
            self._browser = None
            self._playwright = None
            self._playwright_obj = None
            self._contexts = {}
            self._pages = {}
            self._is_started = False

            return sessions_closed

    def get_status(self) -> dict:
        """Get browser status

        Returns:
            Status dictionary with browser state info
        """
        with self._lock:
            return {
                "status": "running" if self._is_started else "stopped",
                "active_sessions": len(self._contexts),
                "active_pages": len(self._pages)
            }

    def get_active_page(self, session_id: str = "default") -> Page:
        """Get the active page (auto-switch to newest tab if multiple tabs exist)

        Args:
            session_id: Session identifier

        Returns:
            Playwright Page instance (the newest tab)
        """
        context = self._contexts.get(session_id)
        if not context:
            # Context not exists, create new one
            return self._get_or_create_page(session_id)

        pages = context.pages
        if not pages:
            # No pages in context, create new one
            return self._get_or_create_page(session_id)

        # Strategy: Always return the newest page (last one)
        active_page = pages[-1]

        # Check if page switched
        current_page = self._pages.get(session_id)
        if current_page != active_page:
            try:
                logger.info(
                    "[BROWSER_MANAGER] Auto-switched to new tab",
                    session_id=session_id,
                    old_url=current_page.url if current_page else "None",
                    new_url=active_page.url
                )
            except:
                logger.info("[BROWSER_MANAGER] Auto-switched to new tab", session_id=session_id)

            self._pages[session_id] = active_page
            try:
                active_page.bring_to_front()
            except:
                pass  # Page might be closed

        return active_page

    def _get_or_create_page(self, session_id: str = "default") -> Page:
        """Internal method: Get or create page for session (without auto-switch)

        Args:
            session_id: Session identifier

        Returns:
            Playwright Page instance
        """
        import threading

        logger.info(
            "[BROWSER_MANAGER] _get_or_create_page called",
            session_id=session_id,
            thread_id=threading.get_ident(),
            existing_sessions=list(self._contexts.keys())
        )

        with self._lock:
            # Return existing page if available
            if session_id in self._pages:
                logger.info("[BROWSER_MANAGER] returning existing page", session_id=session_id)
                return self._pages[session_id]

            # Create new context and page
            logger.info("[BROWSER_MANAGER] creating new browser context")

            logger.info("[BROWSER_MANAGER] calling get_browser()...")
            browser = self.get_browser()
            logger.info("[BROWSER_MANAGER] browser obtained successfully", browser_type=type(browser).__name__)

            if session_id not in self._contexts:
                logger.info("[BROWSER_MANAGER] creating new context", session_id=session_id)

                # 检查是否有已保存的登录状态
                storage_state_path = self._storage_dir / f"{session_id}_storage_state.json"
                storage_state = None
                if storage_state_path.exists():
                    storage_state = str(storage_state_path)
                    logger.info("[BROWSER_MANAGER] loading saved login state", path=storage_state)
                else:
                    logger.info("[BROWSER_MANAGER] no saved login state found, starting fresh", session_id=session_id)

                logger.info("[BROWSER_MANAGER] calling browser.new_context()...")
                context = browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    # 使用最新 Chrome User-Agent（Chromium 131）
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    ignore_https_errors=True,  # Ignore SSL certificate errors (for intranet self-signed certs)
                    storage_state=storage_state  # 加载已保存的登录状态
                )
                self._contexts[session_id] = context
                logger.info("[BROWSER_MANAGER] context created successfully")
            else:
                logger.info("[BROWSER_MANAGER] using existing context", session_id=session_id)
                context = self._contexts[session_id]

            logger.info("[BROWSER_MANAGER] creating new page")
            logger.info("[BROWSER_MANAGER] calling context.new_page()...")
            page = context.new_page()
            self._pages[session_id] = page
            logger.info("[BROWSER_MANAGER] page created successfully", page_type=type(page).__name__)

            return page

    def close_session(self, session_id: str) -> bool:
        """Close a session (context and pages)

        Args:
            session_id: Session identifier

        Returns:
            True if session was closed, False if not found
        """
        with self._lock:
            if session_id not in self._contexts:
                return False

            # Close context (closes all pages in it)
            try:
                self._contexts[session_id].close()
            except Exception:
                pass

            # Remove from tracking
            del self._contexts[session_id]
            if session_id in self._pages:
                del self._pages[session_id]

            return True

    def list_sessions(self) -> list:
        """List all active sessions

        Returns:
            List of session IDs
        """
        with self._lock:
            return list(self._contexts.keys())

    def save_session(self, session_id: str, _use_lock: bool = True) -> bool:
        """手动保存指定 session 的登录状态（cookies + localStorage）

        Args:
            session_id: Session identifier
            _use_lock: 是否使用锁（内部参数，避免死锁）

        Returns:
            True if saved successfully, False otherwise
        """
        # 🔥 避免死锁：如果已经在持有锁的状态下调用，不再获取锁
        if _use_lock:
            lock_context = self._lock
        else:
            from contextlib import nullcontext
            lock_context = nullcontext()

        with lock_context:
            if session_id not in self._contexts:
                logger.warning("[BROWSER_MANAGER] save_session failed: session not found", session_id=session_id)
                return False

            try:
                context = self._contexts[session_id]
                storage_state_path = self._storage_dir / f"{session_id}_storage_state.json"
                context.storage_state(path=str(storage_state_path))
                logger.info("[BROWSER_MANAGER] saved login state", session_id=session_id, path=str(storage_state_path))
                return True
            except Exception as e:
                logger.error("[BROWSER_MANAGER] failed to save login state", session_id=session_id, error=str(e))
                return False

    def _save_all_sessions(self) -> None:
        """保存所有 session 的登录状态（内部方法）

        在浏览器关闭前自动调用

        注意：此方法应该在已经持有 self._lock 的情况下调用，
        因此调用 save_session 时传递 _use_lock=False 避免死锁
        """
        for session_id in list(self._contexts.keys()):
            # 传递 _use_lock=False 避免死锁（因为 stop_browser 已经持有锁）
            self.save_session(session_id, _use_lock=False)
