from __future__ import annotations

from app.knowledge_base.graph_extraction.models import GraphDocumentChunk, GraphSourceFile
from app.knowledge_base.graph_extraction.providers.text_parser import TextParserProvider


class PdfParserProvider:
    """PDF parser for knowledge graph source documents."""

    provider_name = "pdf"

    def __init__(self, max_chars: int = 4000) -> None:
        self.max_chars = max_chars

    async def parse(self, source_file: GraphSourceFile) -> list[GraphDocumentChunk]:
        text = self._extract_with_pdfplumber(source_file)
        if not text.strip():
            text = self._extract_with_pypdf(source_file)
        if not text.strip():
            raise RuntimeError(f"PDF文件未提取到可用于构建认知地图的文本：{source_file.filename}")
        return await TextParserProvider(max_chars=self.max_chars).parse_text(
            source_file=source_file,
            text=text,
        )

    def _extract_with_pdfplumber(self, source_file: GraphSourceFile) -> str:
        try:
            import pdfplumber
        except ImportError:
            return ""

        pages = []
        with pdfplumber.open(source_file.storage_path) as pdf:
            for index, page in enumerate(pdf.pages, start=1):
                page_text = page.extract_text() or ""
                if page_text.strip():
                    pages.append(f"[page {index}]\n{page_text.strip()}")
        return "\n\n".join(pages)

    def _extract_with_pypdf(self, source_file: GraphSourceFile) -> str:
        try:
            import pypdf
        except ImportError as exc:
            raise RuntimeError(
                "PDF解析需要安装 pdfplumber 或 pypdf"
            ) from exc

        pages = []
        with source_file.path.open("rb") as pdf_file:
            reader = pypdf.PdfReader(pdf_file)
            if getattr(reader, "is_encrypted", False):
                try:
                    reader.decrypt("")
                except Exception as exc:
                    raise RuntimeError(f"PDF文件已加密，无法解析：{source_file.filename}") from exc
            for index, page in enumerate(reader.pages, start=1):
                page_text = page.extract_text() or ""
                if page_text.strip():
                    pages.append(f"[page {index}]\n{page_text.strip()}")
        return "\n\n".join(pages)
