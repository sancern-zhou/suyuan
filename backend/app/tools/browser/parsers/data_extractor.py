"""
Data Extractor

Structured data extraction from web pages (tables, lists, forms, etc.)
"""
import structlog
from typing import Any, Dict, List
from playwright.sync_api import Page

from ..config import config

logger = structlog.get_logger()


class DataExtractor:
    """Extract structured data from web pages

    Supports:
    - Tables
    - Lists (ul/ol)
    - Forms
    - Links
    - Images
    """

    @staticmethod
    def extract_table(page: Page, selector: str = "table") -> Dict[str, Any]:
        """Extract table data

        Args:
            page: Playwright page instance
            selector: CSS selector for table element

        Returns:
            {
                "type": "table",
                "rows": list,
                "row_count": int,
                "column_count": int
            }
        """
        table_data = page.eval_on_selector_all(
            selector,
            """(tables) => {
                if (!tables || tables.length === 0) return null;

                const table = tables[0];
                const rows = [];

                // Extract rows
                const tableRows = table.querySelectorAll('tr');
                for (let i = 0; i < Math.min(tableRows.length, 100); i++) {
                    const row = tableRows[i];
                    const cells = row.querySelectorAll('td, th');
                    const rowData = [];

                    for (const cell of cells) {
                        rowData.push(cell.textContent.trim());
                    }

                    if (rowData.length > 0) {
                        rows.push(rowData);
                    }
                }

                return {
                    rows: rows,
                    row_count: rows.length,
                    column_count: rows.length > 0 ? rows[0].length : 0
                };
            }"""
        )

        if not table_data:
            return {
                "type": "table",
                "error": "Table not found or empty"
            }

        logger.info(
            "extracted_table",
            rows=table_data["row_count"],
            columns=table_data["column_count"]
        )

        return {
            "type": "table",
            **table_data
        }

    @staticmethod
    def extract_list(page: Page, selector: str = "ul, ol") -> Dict[str, Any]:
        """Extract list data

        Args:
            page: Playwright page instance
            selector: CSS selector for list element

        Returns:
            {
                "type": "list",
                "items": list,
                "count": int,
                "list_type": str ("ul" or "ol")
            }
        """
        list_data = page.eval_on_selector_all(
            selector,
            """(lists) => {
                if (!lists || lists.length === 0) return null;

                const list = lists[0];
                const items = [];
                const listType = list.tagName.toLowerCase();

                // Extract list items
                const listItems = list.querySelectorAll('li');
                for (let i = 0; i < Math.min(listItems.length, 50); i++) {
                    items.push(listItems[i].textContent.trim());
                }

                return {
                    items: items.filter(item => item),
                    count: items.length,
                    list_type: listType
                };
            }"""
        )

        if not list_data:
            return {
                "type": "list",
                "error": "List not found or empty"
            }

        logger.info("extracted_list", count=list_data["count"])

        return {
            "type": "list",
            **list_data
        }

    @staticmethod
    def extract_form(page: Page, selector: str = "form") -> Dict[str, Any]:
        """Extract form data

        Args:
            page: Playwright page instance
            selector: CSS selector for form element

        Returns:
            {
                "type": "form",
                "fields": list,
                "action": str,
                "method": str
            }
        """
        form_data = page.eval_on_selector_all(
            selector,
            """(forms) => {
                if (!forms || forms.length === 0) return null;

                const form = forms[0];
                const fields = [];

                // Extract input fields
                const inputs = form.querySelectorAll('input, textarea, select');
                for (const input of inputs) {
                    const field = {
                        tag: input.tagName.toLowerCase(),
                        type: input.type || 'text',
                        name: input.name || input.id || '',
                        id: input.id || '',
                        placeholder: input.placeholder || '',
                        value: input.value || '',
                        required: input.required || false
                    };

                    if (field.tag === 'select') {
                        const options = Array.from(input.options).map(opt => ({
                            value: opt.value,
                            text: opt.text
                        }));
                        field.options = options;
                    }

                    fields.push(field);
                }

                return {
                    fields: fields.filter(f => f.name || f.id),
                    action: form.action || '',
                    method: form.method || 'GET'
                };
            }"""
        )

        if not form_data:
            return {
                "type": "form",
                "error": "Form not found or empty"
            }

        logger.info("extracted_form", field_count=len(form_data["fields"]))

        return {
            "type": "form",
            **form_data
        }

    @staticmethod
    def extract_links(page: Page, selector: str = "a") -> Dict[str, Any]:
        """Extract all links

        Args:
            page: Playwright page instance
            selector: CSS selector for links (default: "a")

        Returns:
            {
                "type": "links",
                "links": list,
                "count": int
            }
        """
        links_data = page.eval_on_selector_all(
            selector,
            f"""(links) => {{
                if (!links || links.length === 0) return {{}};

                const result = [];
                const maxLinks = {config.MAX_LINKS};

                for (let i = 0; i < Math.min(links.length, maxLinks); i++) {{
                    const link = links[i];
                    const text = link.textContent.trim();
                    const href = link.href;

                    if (text && href) {{
                        result.push({{ text, href }});
                    }}
                }}

                return {{
                    links: result,
                    count: result.length
                }};
            }}"""
        )

        logger.info("extracted_links", count=links_data.get("count", 0))

        return {
            "type": "links",
            **links_data
        }

    @staticmethod
    def extract_images(page: Page, selector: str = "img") -> Dict[str, Any]:
        """Extract all images

        Args:
            page: Playwright page instance
            selector: CSS selector for images (default: "img")

        Returns:
            {
                "type": "images",
                "images": list,
                "count": int
            }
        """
        images_data = page.eval_on_selector_all(
            selector,
            f"""(images) => {{
                if (!images || images.length === 0) return {{}};

                const result = [];
                const maxImages = {config.MAX_LINKS};

                for (let i = 0; i < Math.min(images.length, maxImages); i++) {{
                    const img = images[i];
                    const src = img.src;
                    const alt = img.alt || '';
                    const title = img.title || '';

                    if (src) {{
                        result.push({{ src, alt, title }});
                    }}
                }}

                return {{
                    images: result,
                    count: result.length
                }};
            }}"""
        )

        logger.info("extracted_images", count=images_data.get("count", 0))

        return {
            "type": "images",
            **images_data
        }
