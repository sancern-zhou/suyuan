"""
PDF conversion service - Convert Office documents to PDF for frontend preview
"""
from contextlib import contextmanager
from pathlib import Path
from app.tools.office.soffice import run_soffice
import tempfile
import shutil
import uuid
import logging
from zipfile import ZipFile, ZIP_DEFLATED
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)
WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{WORD_NS}}}"
ET.register_namespace("w", WORD_NS)

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
                "pages": 10,
                "size": 12345
            }
        """
        try:
            pdf_id = f"{uuid.uuid4()}"
            pdf_path = self.output_dir / f"{pdf_id}.pdf"

            with self._office_pdf_source(Path(office_file_path)) as conversion_source:
                # Use LibreOffice to convert
                result = run_soffice([
                    "--headless",
                    "--convert-to", "pdf",
                    "--outdir", str(self.output_dir),
                    str(conversion_source)
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
                "pages": self._get_pdf_page_count(pdf_path),
                "size": pdf_path.stat().st_size
            }

        except Exception as e:
            logger.error(f"PDF conversion error: {e}", exc_info=True)
            raise

    async def rebuild_pdf(self, pdf_id: str, office_file_path: str) -> dict:
        """
        Rebuild a missing cached PDF while preserving its stable cache id.
        """
        try:
            pdf_path = self.get_pdf_path(pdf_id)

            with self._office_pdf_source(Path(office_file_path)) as conversion_source:
                result = run_soffice([
                    "--headless",
                    "--convert-to", "pdf",
                    "--outdir", str(self.output_dir),
                    str(conversion_source)
                ])

            if result.returncode != 0:
                logger.error(f"LibreOffice PDF rebuild failed: {result.stderr}")
                raise Exception(f"PDF rebuild failed: {result.stderr}")

            converted_files = [
                path
                for path in self.output_dir.glob("*.pdf")
                if path.name != f"{pdf_id}.pdf"
            ]
            if not converted_files:
                raise Exception("No PDF file generated during rebuild")

            converted_pdf = max(converted_files, key=lambda p: p.stat().st_mtime)
            shutil.move(str(converted_pdf), str(pdf_path))

            return {
                "pdf_id": pdf_id,
                "pdf_path": str(pdf_path),
                "pages": self._get_pdf_page_count(pdf_path),
                "size": pdf_path.stat().st_size
            }

        except Exception as e:
            logger.error(f"PDF rebuild error: {e}", exc_info=True)
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

    @contextmanager
    def _office_pdf_source(self, office_file_path: Path):
        if office_file_path.suffix.lower() != ".docx":
            yield office_file_path
            return

        tmp_path = None
        try:
            with ZipFile(office_file_path) as archive:
                document_xml = archive.read("word/document.xml")
                patched_xml = self._patch_docx_for_pdf_preview(document_xml)

            with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp_file:
                tmp_path = Path(tmp_file.name)

            self._write_docx_with_document_xml(office_file_path, patched_xml, tmp_path)
            yield tmp_path
        except Exception as e:
            logger.warning(
                "docx_pdf_preview_normalization_failed",
                extra={"office_file_path": str(office_file_path), "error": str(e)},
            )
            yield office_file_path
        finally:
            if tmp_path is not None and tmp_path.exists():
                tmp_path.unlink()

    def _patch_docx_for_pdf_preview(self, document_xml: bytes) -> bytes:
        root = ET.fromstring(document_xml)

        def normalize_preview_paragraph(paragraph) -> None:
            ppr = paragraph.find(f"{W}pPr")
            if ppr is None:
                return

            pstyle = ppr.find(f"{W}pStyle")
            if pstyle is not None and pstyle.get(f"{W}val") == "Compact":
                ppr.remove(pstyle)

            spacing = ppr.find(f"{W}spacing")
            if spacing is not None and spacing.get(f"{W}lineRule") == "exact":
                ppr.remove(spacing)

        for table in root.findall(f".//{W}tbl"):
            for paragraph in table.findall(f".//{W}p"):
                normalize_preview_paragraph(paragraph)

        for paragraph in root.findall(f".//{W}p"):
            if (
                paragraph.find(f".//{W}drawing") is not None
                or paragraph.find(f".//{W}pict") is not None
            ):
                normalize_preview_paragraph(paragraph)

        return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    def _write_docx_with_document_xml(
        self,
        source_path: Path,
        document_xml: bytes,
        output_path: Path,
    ) -> None:
        with ZipFile(source_path) as source_zip, ZipFile(output_path, "w", compression=ZIP_DEFLATED) as output_zip:
            for item in source_zip.infolist():
                if item.filename.endswith("/"):
                    output_zip.writestr(item, b"")
                    continue
                if item.filename == "word/document.xml":
                    output_zip.writestr(item, document_xml)
                else:
                    output_zip.writestr(item, source_zip.read(item.filename))


# Global singleton
pdf_converter = PDFConverter()
