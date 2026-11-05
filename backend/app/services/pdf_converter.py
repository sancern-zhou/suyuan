"""
PDF conversion service - Convert Office documents to PDF for frontend preview
"""
import asyncio
from contextlib import contextmanager
from pathlib import Path
from app.tools.office.soffice import run_soffice
import tempfile
import shutil
import uuid
import logging
from zipfile import ZipFile, ZIP_DEFLATED
from xml.etree import ElementTree as ET

# soffice 在 Windows 上偶发启动挂死（0 CPU 不退出）；转换必须丢进线程并带
# 超时，否则会把整个 web 进程的事件循环一起卡死（2026-10-28 事故）。
_SOFFICE_TIMEOUT_SECONDS = 120

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

    @staticmethod
    async def _convert_with_soffice(conversion_source: Path, workdir: Path):
        """Run LibreOffice off the event loop, with a hard timeout.

        run_soffice 是同步阻塞调用；soffice 挂死时若无超时/无线程隔离，
        整个进程的所有请求都会停摆。
        """
        return await asyncio.to_thread(
            run_soffice,
            [
                "--headless",
                # UserInstallation 必须是合法 file:// URI（正斜杠），
                # 直接拼 Windows 反斜杠路径会让 soffice 启动异常。
                "-env:UserInstallation={}".format(workdir.as_uri()),
                "--convert-to", "pdf",
                "--outdir", str(workdir),
                str(conversion_source)
            ],
            timeout=_SOFFICE_TIMEOUT_SECONDS,
        )

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

            # 在独享临时目录内转换：输出目录共享时，并发转换（或 soffice
            # 单实例让位导致本无产出）会因"挑目录里最新的 pdf"拿到别的
            # 文档的转换结果，造成 A 文档预览显示 B 文档内容。
            with tempfile.TemporaryDirectory(
                prefix=".convert-", dir=self.output_dir
            ) as workdir:
                with self._office_pdf_source(Path(office_file_path)) as conversion_source:
                    # Use LibreOffice to convert
                    result = await self._convert_with_soffice(
                        conversion_source, Path(workdir)
                    )

                if result.returncode != 0:
                    logger.error(f"LibreOffice conversion failed: {result.stderr}")
                    raise Exception(f"PDF conversion failed: {result.stderr}")

                produced = self._produced_pdf(Path(workdir))
                shutil.move(str(produced), str(pdf_path))

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

            with tempfile.TemporaryDirectory(
                prefix=".convert-", dir=self.output_dir
            ) as workdir:
                with self._office_pdf_source(Path(office_file_path)) as conversion_source:
                    result = await self._convert_with_soffice(
                        conversion_source, Path(workdir)
                    )

                if result.returncode != 0:
                    logger.error(f"LibreOffice PDF rebuild failed: {result.stderr}")
                    raise Exception(f"PDF rebuild failed: {result.stderr}")

                produced = self._produced_pdf(Path(workdir))
                shutil.move(str(produced), str(pdf_path))

            return {
                "pdf_id": pdf_id,
                "pdf_path": str(pdf_path),
                "pages": self._get_pdf_page_count(pdf_path),
                "size": pdf_path.stat().st_size
            }

        except Exception as e:
            logger.error(f"PDF rebuild error: {e}", exc_info=True)
            raise

    @staticmethod
    def _produced_pdf(workdir: Path) -> Path:
        """Return the single PDF produced inside this call's private workdir."""
        produced = [
            path
            for path in workdir.glob("*.pdf")
            if path.is_file() and path.stat().st_size > 0
        ]
        if not produced:
            raise Exception("No PDF file generated")
        return max(produced, key=lambda p: p.stat().st_mtime)

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
