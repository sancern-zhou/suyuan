from __future__ import annotations

from app.agent.cognition.models import DocumentChunk, SourceFile
from app.agent.cognition.providers.text_parser import TextParserProvider
from app.routers.utils_docx import convert_docx_to_markdown


class DocxParserProvider:
    """DOCX parser backed by the project's python-docx conversion utility."""

    provider_name = "docx"

    def __init__(self, max_chars: int = 4000) -> None:
        self.max_chars = max_chars

    async def parse(self, source_file: SourceFile) -> list[DocumentChunk]:
        raw_bytes = source_file.path.read_bytes()
        text = convert_docx_to_markdown(raw_bytes)
        return await TextParserProvider(max_chars=self.max_chars).parse_text(
            source_file=source_file,
            text=text,
        )
