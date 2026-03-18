"""PDF Action Handler (SYNC version)

Handler for PDF export operations.
"""
import structlog
import os

from ..services.pdf_export import PDFExporter

logger = structlog.get_logger()

# Global PDF exporter instance
_pdf_exporter = None


def get_pdf_exporter() -> PDFExporter:
    """Get or create global PDF exporter instance"""
    global _pdf_exporter
    if _pdf_exporter is None:
        _pdf_exporter = PDFExporter()
    return _pdf_exporter


def handle_pdf(
    manager,
    action: str = "export",
    selector: str = None,
    format: str = "A4",
    print_background: bool = True,
    landscape: bool = False,
    session_id: str = "default",
    **kwargs
) -> dict:
    """Handle PDF export operations

    Args:
        manager: BrowserManager instance
        action: Operation (export/export_page/export_element/list)
        selector: CSS selector for element export
        format: Paper format (A4, A3, etc.)
        print_background: Print background graphics
        landscape: Landscape orientation
        session_id: Session identifier

    Returns:
        For export/export_page:
        {
            "pdf_path": str,
            "pdf_id": str,
            "size_kb": float
        }

        For export_element:
        {
            "pdf_path": str,
            "pdf_id": str,
            "size_kb": float,
            "selector": str
        }

        For list:
        {
            "pdfs": list
        }
    """
    exporter = get_pdf_exporter()
    page = manager.get_active_page(session_id)

    if action == "export" or action == "export_page":
        # Export entire page
        result = exporter.export_page(
            page=page,
            format=format,
            print_background=print_background,
            landscape=landscape
        )
        result["action"] = "export_page"
        return result

    elif action == "export_element":
        # Export specific element
        if not selector:
            raise ValueError("selector is required for export_element action")

        result = exporter.export_element(
            page=page,
            selector=selector
        )
        result["action"] = "export_element"
        result["selector"] = selector
        return result

    elif action == "list":
        # List all PDFs
        pdfs = exporter.list_pdfs()
        return {
            "action": "list",
            "pdfs": pdfs,
            "count": len(pdfs)
        }

    else:
        raise ValueError(f"Unknown PDF action: {action}. Valid: export, export_element, list")
