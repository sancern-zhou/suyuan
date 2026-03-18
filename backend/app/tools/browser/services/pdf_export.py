"""PDF Export Service

Exports pages or elements to PDF format.
"""
import os
import structlog
from typing import Optional, Dict, List
from datetime import datetime
from playwright.sync_api import Page

logger = structlog.get_logger()


class PDFExporter:
    """PDF export service

    Exports browser pages to PDF format.
    Only supports Chromium browser.
    """

    def __init__(self, output_dir: str = "backend_data_registry/pdfs"):
        """Initialize PDF exporter

        Args:
            output_dir: Directory for PDF output
        """
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        logger.info("[PDF_EXPORTER] Initialized", output_dir=output_dir)

    def export_page(
        self,
        page: Page,
        output_path: Optional[str] = None,
        format: str = "A4",
        print_background: bool = True,
        landscape: bool = False
    ) -> Dict:
        """Export page to PDF

        Args:
            page: Playwright Page instance
            output_path: Output file path (auto-generated if None)
            format: Paper format (A4, A3, A0, etc.)
            print_background: Print background graphics
            landscape: Landscape orientation

        Returns:
            {
                "pdf_path": str,
                "pdf_id": str,
                "size_kb": float
            }
        """
        try:
            # Generate file path if not provided
            if not output_path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                pdf_id = f"page_{timestamp}"
                output_path = os.path.join(self.output_dir, f"{pdf_id}.pdf")
            else:
                pdf_id = os.path.basename(output_path).replace(".pdf", "")

            # Export PDF
            pdf_bytes = page.pdf(
                path=output_path,
                format=format,
                print_background=print_background,
                landscape=landscape
            )

            file_size_kb = len(pdf_bytes) / 1024

            logger.info(
                "[PDF_EXPORTER] Page exported",
                pdf_id=pdf_id,
                path=output_path,
                size_kb=round(file_size_kb, 2)
            )

            return {
                "pdf_path": os.path.abspath(output_path),
                "pdf_id": pdf_id,
                "size_kb": round(file_size_kb, 2)
            }

        except Exception as e:
            logger.error("[PDF_EXPORTER] Failed to export page", error=str(e))
            raise

    def export_element(
        self,
        page: Page,
        selector: str,
        output_path: Optional[str] = None
    ) -> Dict:
        """Export specific element to PDF

        Args:
            page: Playwright Page instance
            selector: CSS selector for element
            output_path: Output file path (auto-generated if None)

        Returns:
            {
                "pdf_path": str,
                "pdf_id": str,
                "size_kb": float
            }
        """
        try:
            element = page.locator(selector).first

            # Scroll to element
            element.scroll_into_view_if_needed()

            # Get element bounding box
            box = element.bounding_box()

            if not box:
                raise ValueError(f"Element not found: {selector}")

            # Generate file path if not provided
            if not output_path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                pdf_id = f"element_{timestamp}"
                output_path = os.path.join(self.output_dir, f"{pdf_id}.pdf")
            else:
                pdf_id = os.path.basename(output_path).replace(".pdf", "")

            # Export element (using clip)
            pdf_bytes = page.pdf(
                path=output_path,
                print_background=True,
                clip=box
            )

            file_size_kb = len(pdf_bytes) / 1024

            logger.info(
                "[PDF_EXPORTER] Element exported",
                pdf_id=pdf_id,
                selector=selector,
                path=output_path,
                size_kb=round(file_size_kb, 2)
            )

            return {
                "pdf_path": os.path.abspath(output_path),
                "pdf_id": pdf_id,
                "size_kb": round(file_size_kb, 2)
            }

        except Exception as e:
            logger.error(
                "[PDF_EXPORTER] Failed to export element",
                selector=selector,
                error=str(e)
            )
            raise

    def list_pdfs(self) -> list:
        """List all exported PDFs

        Returns:
            List of PDF file information
        """
        try:
            pdfs = []
            for filename in os.listdir(self.output_dir):
                if filename.endswith(".pdf"):
                    filepath = os.path.join(self.output_dir, filename)
                    stat = os.stat(filepath)
                    pdfs.append({
                        "filename": filename,
                        "path": os.path.abspath(filepath),
                        "size_kb": round(stat.st_size / 1024, 2),
                        "created": datetime.fromtimestamp(stat.st_ctime).isoformat()
                    })

            # Sort by creation time (newest first)
            pdfs.sort(key=lambda x: x["created"], reverse=True)

            return pdfs

        except Exception as e:
            logger.error("[PDF_EXPORTER] Failed to list PDFs", error=str(e))
            return []
