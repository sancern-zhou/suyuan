"""Extract Action Handler (SYNC version)

Handler for extract operation (structured data extraction)
"""
import structlog

from ..parsers.data_extractor import DataExtractor

logger = structlog.get_logger()


def handle_extract(
    manager,
    selector: str = None,
    extract_type: str = "links",
    session_id: str = "default",
    **kwargs
) -> dict:
    """Extract structured data from page (SYNC version)

    Args:
        manager: BrowserManager instance
        selector: CSS selector for element to extract from
        extract_type: Type of data to extract (table/list/form/links/images)
        session_id: Session identifier

    Returns:
        Type-specific data structure with extracted content
    """
    page = manager.get_active_page(session_id)

    # Set default selector based on type
    if not selector:
        default_selectors = {
            "table": "table",
            "list": "ul, ol",
            "form": "form",
            "links": "a",
            "images": "img"
        }
        selector = default_selectors.get(extract_type, "a")

    # Extract based on type
    extractor = DataExtractor()

    if extract_type == "table":
        result = extractor.extract_table(page, selector)
    elif extract_type == "list":
        result = extractor.extract_list(page, selector)
    elif extract_type == "form":
        result = extractor.extract_form(page, selector)
    elif extract_type == "links":
        result = extractor.extract_links(page, selector)
    elif extract_type == "images":
        result = extractor.extract_images(page, selector)
    else:
        raise ValueError(f"Unknown extract_type: {extract_type}")

    logger.info(
        "browser_action_extract",
        session_id=session_id,
        extract_type=extract_type,
        selector=selector,
        success="error" not in result
    )

    return result
