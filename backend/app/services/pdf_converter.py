"""
PDF conversion service - Convert Office documents to PDF for frontend preview
"""
from pathlib import Path
from app.tools.office.soffice import run_soffice
import tempfile
import shutil
import uuid
import logging

logger = logging.getLogger(__name__)

try:
    import pypdf
except ImportError:
    pypdf = None
    logger.warning("pypdf not installed, page count extraction will be limited")


class PDFConverter:
    def __init__(self):
        self.output_dir = Path(tempfile.gettempdir()) / "office_pdf_cache"
        self.output_dir.mkdir(exist_ok=True)

    async def convert_to_pdf(self, office_file_path: str) -> dict:
        """
        Convert Office document to PDF

        Args:
            office_file_path: Path to the Office document

        Returns:
            {
                "pdf_id": "unique-id",
                "pdf_path": "/path/to/pdf",
                "pdf_url": "/api/office/pdf/unique-id",
                "pages": 10,
                "size": 12345
            }
        """
        try:
            pdf_id = f"{uuid.uuid4()}"
            pdf_path = self.output_dir / f"{pdf_id}.pdf"

            # Use LibreOffice to convert
            result = run_soffice([
                "--headless",
                "--convert-to", "pdf",
                "--outdir", str(self.output_dir),
                office_file_path
            ])

            if result.returncode != 0:
                logger.error(f"LibreOffice conversion failed: {result.stderr}")
                raise Exception(f"PDF conversion failed: {result.stderr}")

            # Find the converted PDF and rename it
            converted_files = list(self.output_dir.glob("*.pdf"))
            if not converted_files:
                raise Exception("No PDF file generated")

            # Get the most recently modified PDF
            converted_pdf = max(converted_files, key=lambda p: p.stat().st_mtime)

            # Move to our target location
            shutil.move(str(converted_pdf), str(pdf_path))

            return {
                "pdf_id": pdf_id,
                "pdf_path": str(pdf_path),
                "pdf_url": f"/api/office/pdf/{pdf_id}",
                "pages": self._get_pdf_page_count(pdf_path),
                "size": pdf_path.stat().st_size
            }

        except Exception as e:
            logger.error(f"PDF conversion error: {e}", exc_info=True)
            raise

    def _get_pdf_page_count(self, pdf_path: Path) -> int:
        """Get the number of pages in the PDF"""
        if pypdf is None:
            return 0

        try:
            with open(pdf_path, 'rb') as f:
                reader = pypdf.PdfReader(f)
                return len(reader.pages)
        except Exception as e:
            logger.warning(f"Failed to get page count: {e}")
            return 0

    def cleanup_pdf(self, pdf_id: str) -> bool:
        """Clean up a PDF file"""
        try:
            pdf_path = self.output_dir / f"{pdf_id}.pdf"
            if pdf_path.exists():
                pdf_path.unlink()
                return True
            return False
        except Exception as e:
            logger.warning(f"Failed to cleanup PDF {pdf_id}: {e}")
            return False

    def get_pdf_path(self, pdf_id: str) -> Path:
        """Get the path to a PDF file"""
        return self.output_dir / f"{pdf_id}.pdf"

    def pdf_exists(self, pdf_id: str) -> bool:
        """Check if a PDF file exists"""
        return self.get_pdf_path(pdf_id).exists()


# Global singleton
pdf_converter = PDFConverter()
