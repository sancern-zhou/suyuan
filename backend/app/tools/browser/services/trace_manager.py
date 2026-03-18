"""Trace Manager Service

Provides trace debugging functionality for Playwright.
"""
import os
import structlog
from typing import Optional
from datetime import datetime
from playwright.sync_api import BrowserContext

logger = structlog.get_logger()


class TraceManager:
    """Trace debugging manager

    Manages Playwright trace recording for debugging.
    """

    def __init__(self, trace_dir: str = "backend_data_registry/traces"):
        """Initialize trace manager

        Args:
            trace_dir: Directory for trace files
        """
        self.trace_dir = trace_dir
        self.active_traces = {}  # context -> trace_path
        os.makedirs(self.trace_dir, exist_ok=True)
        logger.info("[TRACE_MANAGER] Initialized", trace_dir=trace_dir)

    def start_trace(self, context: BrowserContext, name: str, title: str = "Trace") -> str:
        """Start trace recording for context

        Args:
            context: Playwright BrowserContext
            name: Trace name
            title: Trace title

        Returns:
            Trace file path
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        trace_name = f"{name}_{timestamp}"
        trace_path = os.path.join(self.trace_dir, f"{trace_name}.zip")

        try:
            context.tracing.start(screenshots=True, snapshots=True)
            self.active_traces[id(context)] = {
                "path": trace_path,
                "name": trace_name,
                "title": title
            }

            logger.info(
                "[TRACE_MANAGER] Trace started",
                context_id=id(context),
                name=trace_name,
                path=trace_path
            )

            return trace_path

        except Exception as e:
            logger.error("[TRACE_MANAGER] Failed to start trace", error=str(e))
            raise

    def stop_trace(self, context: BrowserContext) -> Optional[str]:
        """Stop trace recording for context

        Args:
            context: Playwright BrowserContext

        Returns:
            Trace file path if stopped, None if no active trace
        """
        context_id = id(context)

        if context_id not in self.active_traces:
            logger.warning("[TRACE_MANAGER] No active trace for context", context_id=context_id)
            return None

        trace_info = self.active_traces[context_id]
        trace_path = trace_info["path"]

        try:
            context.tracing.stop(path=trace_path)

            logger.info(
                "[TRACE_MANAGER] Trace stopped",
                context_id=context_id,
                path=trace_path
            )

            del self.active_traces[context_id]
            return trace_path

        except Exception as e:
            logger.error("[TRACE_MANAGER] Failed to stop trace", error=str(e))
            # Clean up even on error
            if context_id in self.active_traces:
                del self.active_traces[context_id]
            raise

    def start_chunk(self, context: BrowserContext, title: str) -> bool:
        """Start a new trace chunk

        Args:
            context: Playwright BrowserContext
            title: Chunk title

        Returns:
            True if chunk started
        """
        if id(context) not in self.active_traces:
            logger.warning("[TRACE_MANAGER] No active trace for chunk", context_id=id(context))
            return False

        try:
            context.tracing.start_chunk(title=title)

            logger.info(
                "[TRACE_MANAGER] Chunk started",
                context_id=id(context),
                title=title
            )

            return True

        except Exception as e:
            logger.error("[TRACE_MANAGER] Failed to start chunk", error=str(e))
            return False

    def list_traces(self) -> list:
        """List all trace files

        Returns:
            List of trace file information
        """
        try:
            traces = []
            for filename in os.listdir(self.trace_dir):
                if filename.endswith(".zip"):
                    filepath = os.path.join(self.trace_dir, filename)
                    stat = os.stat(filepath)
                    traces.append({
                        "filename": filename,
                        "path": os.path.abspath(filepath),
                        "size_kb": round(stat.st_size / 1024, 2),
                        "created": datetime.fromtimestamp(stat.st_ctime).isoformat()
                    })

            # Sort by creation time (newest first)
            traces.sort(key=lambda x: x["created"], reverse=True)

            return traces

        except Exception as e:
            logger.error("[TRACE_MANAGER] Failed to list traces", error=str(e))
            return []
