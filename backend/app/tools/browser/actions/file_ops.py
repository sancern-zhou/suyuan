"""File Operations Action Handler (SYNC version)

Handler for file upload and download operations.
"""
import structlog

from ..services.file_handler import FileHandler

logger = structlog.get_logger()

# Global file handler instance
_file_handler = None


def get_file_handler() -> FileHandler:
    """Get or create global file handler instance"""
    global _file_handler
    if _file_handler is None:
        _file_handler = FileHandler()
    return _file_handler


def handle_download(
    manager,
    selector: str = None,
    timeout: int = 30000,
    session_id: str = "default",
    **kwargs
) -> dict:
    """Handle file download

    Args:
        manager: BrowserManager instance
        selector: Download button selector (optional)
        timeout: Timeout in milliseconds
        session_id: Session identifier

    Returns:
        {
            "download_path": str,
            "filename": str,
            "size_kb": float
        }
    """
    handler = get_file_handler()
    page = manager.get_active_page(session_id)

    # Setup download handling
    handler.setup_download(page, timeout)

    # Wait for download
    result = handler.wait_for_download(page, selector=selector, timeout=timeout)

    logger.info(
        "[FILE_OPS] Download completed",
        filename=result["filename"],
        size_kb=result["size_kb"]
    )

    return result


def handle_upload(
    manager,
    selector: str,
    file_path: str,
    session_id: str = "default",
    **kwargs
) -> dict:
    """Handle file upload

    Args:
        manager: BrowserManager instance
        selector: File input selector
        file_path: Path to file to upload
        session_id: Session identifier

    Returns:
        {
            "uploaded": bool,
            "file_path": str,
            "filename": str
        }
    """
    handler = get_file_handler()
    page = manager.get_active_page(session_id)

    result = handler.upload_file(page, selector, file_path)

    logger.info(
        "[FILE_OPS] Upload completed",
        filename=result["filename"],
        file_path=result["file_path"]
    )

    return result


def handle_list_files(
    manager,
    session_id: str = "default",
    **kwargs
) -> dict:
    """Handle list files operation

    Args:
        manager: BrowserManager instance (not used but kept for consistency)
        session_id: Session identifier (not used but kept for consistency)

    Returns:
        {
            "files": list,
            "count": int
        }
    """
    handler = get_file_handler()
    files = handler.list_downloads()

    return {
        "files": files,
        "count": len(files)
    }
