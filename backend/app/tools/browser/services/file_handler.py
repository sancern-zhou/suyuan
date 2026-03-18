"""File Handler Service

Handles file upload and download operations.
"""
import os
import time
import structlog
from typing import Optional, Dict
from playwright.sync_api import Page

logger = structlog.get_logger()


class FileHandler:
    """File operation handler

    Manages file uploads and downloads in browser automation.
    """

    def __init__(self, download_dir: str = "backend_data_registry/downloads"):
        """Initialize file handler

        Args:
            download_dir: Directory for downloads
        """
        self.download_dir = download_dir
        os.makedirs(self.download_dir, exist_ok=True)
        logger.info("[FILE_HANDLER] Initialized", download_dir=download_dir)

    def setup_download(self, page: Page, download_timeout: int = 30000) -> str:
        """Setup download handling for page

        Args:
            page: Playwright Page instance
            download_timeout: Download timeout in milliseconds

        Returns:
            Download directory path
        """
        page.set_default_timeout(download_timeout)
        logger.debug(
            "[FILE_HANDLER] Download setup",
            download_dir=self.download_dir,
            timeout=download_timeout
        )
        return self.download_dir

    def wait_for_download(
        self,
        page: Page,
        selector: Optional[str] = None,
        timeout: int = 30000
    ) -> Dict:
        """Wait for file download to complete

        Args:
            page: Playwright Page instance
            selector: Download button selector (optional, will click if provided)
            timeout: Timeout in milliseconds

        Returns:
            {
                "download_path": str,
                "filename": str,
                "size_kb": float
            }
        """
        download_info = {"complete": False, "path": None, "filename": None}

        def handle_download(download):
            """Handle download event"""
            nonlocal download_info
            try:
                download_path = download.path()
                filename = download.suggested_filename

                # Save to downloads directory
                save_path = os.path.join(self.download_dir, filename)
                download.save_as(save_path)

                download_info = {
                    "complete": True,
                    "path": os.path.abspath(save_path),
                    "filename": filename,
                    "size_kb": round(os.path.getsize(save_path) / 1024, 2)
                }

                logger.info(
                    "[FILE_HANDLER] Download complete",
                    filename=filename,
                    path=save_path
                )

            except Exception as e:
                logger.error("[FILE_HANDLER] Download failed", error=str(e))
                download_info["error"] = str(e)

        # Register download handler
        page.on("download", handle_download)

        # Click download button if selector provided
        if selector:
            try:
                page.click(selector)
                logger.info("[FILE_HANDLER] Clicked download button", selector=selector)
            except Exception as e:
                logger.error("[FILE_HANDLER] Failed to click download button", error=str(e))
                page.remove_listener("download", handle_download)
                raise

        # Wait for download to complete
        start_time = time.time()
        timeout_seconds = timeout / 1000

        while not download_info["complete"]:
            if time.time() - start_time > timeout_seconds:
                page.remove_listener("download", handle_download)
                raise TimeoutError(f"Download timeout after {timeout}ms")

            if "error" in download_info:
                page.remove_listener("download", handle_download)
                raise Exception(download_info["error"])

            time.sleep(0.1)

        # Clean up listener
        page.remove_listener("download", handle_download)

        return {
            "download_path": download_info["path"],
            "filename": download_info["filename"],
            "size_kb": download_info["size_kb"]
        }

    def upload_file(
        self,
        page: Page,
        selector: str,
        file_path: str
    ) -> Dict:
        """Upload file

        Args:
            page: Playwright Page instance
            selector: File input selector
            file_path: Path to file to upload

        Returns:
            {
                "uploaded": bool,
                "file_path": str,
                "filename": str
            }
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            # Set file input
            file_input = page.locator(selector)
            file_input.set_input_files(file_path)

            filename = os.path.basename(file_path)

            logger.info(
                "[FILE_HANDLER] File uploaded",
                filename=filename,
                selector=selector
            )

            return {
                "uploaded": True,
                "file_path": os.path.abspath(file_path),
                "filename": filename
            }

        except Exception as e:
            logger.error("[FILE_HANDLER] Upload failed", error=str(e))
            raise

    def list_downloads(self) -> list:
        """List all downloaded files

        Returns:
            List of file information
        """
        try:
            files = []
            for filename in os.listdir(self.download_dir):
                filepath = os.path.join(self.download_dir, filename)
                if os.path.isfile(filepath):
                    stat = os.stat(filepath)
                    files.append({
                        "filename": filename,
                        "path": os.path.abspath(filepath),
                        "size_kb": round(stat.st_size / 1024, 2),
                        "created": stat.st_ctime
                    })

            # Sort by creation time (newest first)
            files.sort(key=lambda x: x["created"], reverse=True)

            return files

        except Exception as e:
            logger.error("[FILE_HANDLER] Failed to list downloads", error=str(e))
            return []
