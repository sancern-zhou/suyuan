"""File Operations Action Handler (SYNC version)

Handler for file upload and download operations.
"""
import structlog
from app.tools.resource_declarations import file_resource

from ..services.file_handler import FileHandler
from ..refs.ref_resolver import get_global_resolver
from ..services.frame_target import FrameTarget, resolve_frame

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
    ref: str = None,
    timeout: int = 30000,
    session_id: str = "default",
    frame_url: str = None,
    frame_name: str = None,
    frame_index: int = None,
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
    ref_target = FrameTarget.from_ref(ref)
    target_frame_index = ref_target.frame_index if ref_target.frame_index is not None else frame_index
    context = resolve_frame(page, frame_url=frame_url, frame_name=frame_name, frame_index=target_frame_index)

    # Setup download handling
    handler.setup_download(page, timeout)

    # Wait for download
    if ref and not selector:
        ref_info = get_global_resolver().get_ref_info(ref)
        selector = ref_info.get("selector") if ref_info else None
        if not selector:
            raise ValueError(f"Download ref '{ref}' does not have a selector")

    result = handler.wait_for_download(page, selector=selector, click_context=context, timeout=timeout)
    if result.get("download_path"):
        result["resources"] = [
            file_resource(result["download_path"], tool_name="browser")
        ]

    logger.info(
        "[FILE_OPS] Download completed",
        filename=result["filename"],
        size_kb=result["size_kb"]
    )

    return result


def handle_upload(
    manager,
    selector: str = None,
    file_path: str = None,
    session_id: str = "default",
    ref: str = None,
    frame_url: str = None,
    frame_name: str = None,
    frame_index: int = None,
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
    ref_target = FrameTarget.from_ref(ref)
    target_frame_index = ref_target.frame_index if ref_target.frame_index is not None else frame_index
    context = resolve_frame(page, frame_url=frame_url, frame_name=frame_name, frame_index=target_frame_index)

    if ref and not selector:
        ref_info = get_global_resolver().get_ref_info(ref)
        selector = ref_info.get("selector") if ref_info else None
        if not selector:
            raise ValueError(f"Upload ref '{ref}' does not have a selector")
    if not selector:
        raise ValueError("selector or ref is required for upload action")
    if not file_path:
        raise ValueError("file_path is required for upload action")

    result = handler.upload_file(page, selector, file_path, context=context)

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
