"""File Handler Service

Handles file upload and download operations.
"""
import os
import structlog
from typing import Optional, Dict
from playwright.sync_api import Page
from app.utils.path_config import get_data_registry

logger = structlog.get_logger()


class FileHandler:
    """File operation handler

    Manages file uploads and downloads in browser automation.
    """

    def __init__(self, download_dir: str = None):
        """Initialize file handler

        Args:
            download_dir: Directory for downloads
        """
        self.download_dir = download_dir or str(get_data_registry() / "downloads")
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
        click_context=None,
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
        click_context = click_context or page

        try:
            with page.expect_download(timeout=timeout) as download_info:
                if selector:
                    click_context.locator(selector).click(timeout=timeout)
                    logger.info("[FILE_HANDLER] Clicked download button", selector=selector)

            download = download_info.value
            filename = download.suggested_filename
            save_path = os.path.join(self.download_dir, filename)
            download.save_as(save_path)

            result = {
                "download_path": os.path.abspath(save_path),
                "filename": filename,
                "size_kb": round(os.path.getsize(save_path) / 1024, 2)
            }

            logger.info(
                "[FILE_HANDLER] Download complete",
                filename=filename,
                path=save_path
            )

            return result
        except Exception as e:
            logger.error("[FILE_HANDLER] Download failed", error=str(e))
            raise

    def upload_file(
        self,
        page: Page,
        selector: str,
        file_path: str,
        context=None
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

        context = context or page

        try:
            # Set file input
            file_input = context.locator(selector)
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
