"""Console Log Capture Service

Captures browser console logs (log, error, warning, info).
"""
import structlog
from typing import Dict, List
from datetime import datetime
from playwright.sync_api import Page

logger = structlog.get_logger()


class ConsoleCapture:
    """Console log capture service

    Captures console.log, console.error, console.warn, console.info
    from browser pages using JavaScript injection.
    """

    # JavaScript injection script for console capture
    CAPTURE_SCRIPT = """
    () => {
        if (!window.__consoleCaptured) {
            window.__consoleLogs = [];
            window.__consoleCaptured = true;
            window.__consoleMaxLogs = 1000;

            const originalLog = console.log;
            const originalError = console.error;
            const originalWarn = console.warn;
            const originalInfo = console.info;

            function capture(type, args) {
                const message = args.map(a => {
                    if (typeof a === 'object') {
                        try {
                            return JSON.stringify(a);
                        } catch (e) {
                            return String(a);
                        }
                    }
                    return String(a);
                }).join(' ');

                const logEntry = {
                    type: type,
                    text: message,
                    timestamp: new Date().toISOString(),
                    url: window.location.href
                };

                window.__consoleLogs.push(logEntry);

                // Limit log size
                if (window.__consoleLogs.length > window.__consoleMaxLogs) {
                    window.__consoleLogs.shift();
                }
            }

            console.log = (...args) => {
                capture('log', args);
                originalLog.apply(console, args);
            };
            console.error = (...args) => {
                capture('error', args);
                originalError.apply(console, args);
            };
            console.warn = (...args) => {
                capture('warning', args);
                originalWarn.apply(console, args);
            };
            console.info = (...args) => {
                capture('info', args);
                originalInfo.apply(console, args);
            };

            return true;
        }

        return false;
    }
    """

    def __init__(self):
        self.captured_pages = set()

    def enable_capture(self, page: Page) -> bool:
        """Enable console capture for page

        Args:
            page: Playwright Page instance

        Returns:
            True if capture was enabled, False if already enabled
        """
        try:
            # Inject capture script
            result = page.evaluate(self.CAPTURE_SCRIPT)
            self.captured_pages.add(id(page))

            logger.info(
                "[CONSOLE_CAPTURE] Enabled",
                page_id=id(page),
                already_enabled=(not result)
            )

            return result

        except Exception as e:
            logger.error(
                "[CONSOLE_CAPTURE] Failed to enable",
                page_id=id(page),
                error=str(e)
            )
            return False

    def get_logs(self, page: Page, clear: bool = False) -> Dict:
        """Get captured console logs

        Args:
            page: Playwright Page instance
            clear: Whether to clear logs after retrieval

        Returns:
            {
                "logs": [
                    {"type": "log", "text": "...", "timestamp": "..."},
                    {"type": "error", "text": "...", "timestamp": "..."}
                ],
                "count": int
            }
        """
        if id(page) not in self.captured_pages:
            return {
                "logs": [],
                "count": 0,
                "message": "Console capture not enabled for this page"
            }

        try:
            logs = page.evaluate("() => window.__consoleLogs || []")

            if clear:
                page.evaluate("() => window.__consoleLogs = []")
                logger.debug("[CONSOLE_CAPTURE] Logs cleared", page_id=id(page))

            # Count by type
            type_counts = {}
            for log in logs:
                log_type = log.get("type", "unknown")
                type_counts[log_type] = type_counts.get(log_type, 0) + 1

            logger.info(
                "[CONSOLE_CAPTURE] Retrieved logs",
                page_id=id(page),
                total_count=len(logs),
                type_counts=type_counts
            )

            return {
                "logs": logs,
                "count": len(logs),
                "type_counts": type_counts
            }

        except Exception as e:
            logger.error(
                "[CONSOLE_CAPTURE] Failed to get logs",
                page_id=id(page),
                error=str(e)
            )
            return {
                "logs": [],
                "count": 0,
                "error": str(e)
            }

    def clear_logs(self, page: Page) -> bool:
        """Clear captured console logs

        Args:
            page: Playwright Page instance

        Returns:
            True if cleared successfully
        """
        if id(page) not in self.captured_pages:
            return False

        try:
            page.evaluate("() => window.__consoleLogs = []")
            logger.debug("[CONSOLE_CAPTURE] Logs cleared", page_id=id(page))
            return True

        except Exception as e:
            logger.error(
                "[CONSOLE_CAPTURE] Failed to clear logs",
                page_id=id(page),
                error=str(e)
            )
            return False

    def disable_capture(self, page: Page) -> bool:
        """Disable console capture for page

        Args:
            page: Playwright Page instance

        Returns:
            True if disabled successfully
        """
        try:
            # Remove page from tracked set
            if id(page) in self.captured_pages:
                self.captured_pages.remove(id(page))

            logger.info("[CONSOLE_CAPTURE] Disabled", page_id=id(page))
            return True

        except Exception as e:
            logger.error(
                "[CONSOLE_CAPTURE] Failed to disable",
                page_id=id(page),
                error=str(e)
            )
            return False

    def is_enabled(self, page: Page) -> bool:
        """Check if console capture is enabled for page

        Args:
            page: Playwright Page instance

        Returns:
            True if enabled
        """
        return id(page) in self.captured_pages
