"""Screenshot Action Handler (SYNC version)

Handler for screenshot operation (image capture with description)
"""
import structlog
import base64
from datetime import datetime

from ..config import config
from app.services.image_cache import get_image_cache

logger = structlog.get_logger()


def handle_screenshot(
    manager,
    session_id: str = "default",
    **kwargs
) -> dict:
    """Capture page screenshot with AI description (SYNC version)

    Args:
        manager: BrowserManager instance
        session_id: Session identifier

    Returns:
        {
            "image_id": str,  # Image ID for retrieval
            "image_url": str,  # Full URL to access the image (for LLM)
            "markdown_image": str,  # Markdown format image link (for LLM)
            "description": str,  # Text description of the page
            "url": str,  # Page URL
            "title": str  # Page title
        }
    """
    page = manager.get_active_page(session_id)

    # Get page info
    url = page.url
    title = page.title()

    # Capture screenshot as bytes
    screenshot_bytes = page.screenshot(
        full_page=kwargs.get("full_page", False),
        type="png"
    )

    # Convert to base64
    base64_data = base64.b64encode(screenshot_bytes).decode("utf-8")

    # Save to image cache
    image_cache = get_image_cache()
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    image_id = f"screenshot_{timestamp}"
    image_cache.save(base64_data, chart_id=image_id)

    # Generate description from page content
    description = _generate_page_description(page)

    # Build full URL (like particulate_visualizer.py)
    image_relative_path = f"/api/image/{image_id}"
    image_url = f"{config.BACKEND_HOST}{image_relative_path}"

    # Generate markdown image format (for LLM output)
    markdown_image = f"![{title}]({image_url})"

    logger.info(
        "browser_screenshot",
        session_id=session_id,
        image_id=image_id,
        url=url,
        title=title,
        size_kb=len(screenshot_bytes) / 1024
    )

    return {
        "image_id": image_id,
        "image_url": image_url,
        "markdown_image": markdown_image,
        "description": description,
        "url": url,
        "title": title
    }


def _generate_page_description(page) -> str:
    """Generate text description of page content

    Args:
        page: Playwright Page instance

    Returns:
        Text description
    """
    try:
        # Get page structure
        description = page.evaluate("""() => {
            const body = document.body;

            // Count elements
            const images = body.querySelectorAll('img').length;
            const links = body.querySelectorAll('a').length;
            const forms = body.querySelectorAll('form').length;
            const tables = body.querySelectorAll('table').length;
            const headings = body.querySelectorAll('h1, h2, h3, h4, h5, h6').length;

            // Get main heading
            const h1 = body.querySelector('h1');
            const mainHeading = h1 ? h1.innerText.trim() : '';

            // Get meta description
            const metaDesc = document.querySelector('meta[name="description"]');
            const metaContent = metaDesc ? metaDesc.getAttribute('content') : '';

            return {
                title: document.title,
                heading: mainHeading,
                description: metaContent,
                structure: {
                    images: images,
                    links: links,
                    forms: forms,
                    tables: tables,
                    headings: headings
                }
            };
        }""")

        # Format description
        parts = []
        if description.get("title"):
            parts.append(f"标题: {description['title']}")
        if description.get("heading"):
            parts.append(f"主标题: {description['heading']}")
        if description.get("description"):
            parts.append(f"描述: {description['description']}")

        struct = description.get("structure", {})
        parts.append(f"页面包含: {struct.get('images', 0)}张图片, {struct.get('links', 0)}个链接, {struct.get('forms', 0)}个表单, {struct.get('tables', 0)}个表格, {struct.get('headings', 0)}个标题")

        return " | ".join(parts)

    except Exception as e:
        logger.warning("page_description_failed", error=str(e))
        return f"页面描述生成失败: {str(e)}"
