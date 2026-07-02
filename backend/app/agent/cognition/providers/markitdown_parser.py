from __future__ import annotations

from app.agent.cognition.models import DocumentChunk, SourceFile
from app.agent.cognition.providers.text_parser import TextParserProvider


class MarkItDownParserProvider:
    """Optional MarkItDown-backed parser.

    The adapter keeps the external dependency behind the provider boundary. If
    MarkItDown is not installed, local text parsing remains available.
    """

    provider_name = "markitdown"

    def __init__(self, max_chars: int = 1200) -> None:
        self.max_chars = max_chars

    async def parse(self, source_file: SourceFile) -> list[DocumentChunk]:
        try:
            from markitdown import MarkItDown
        except ImportError as exc:
            raise RuntimeError(
                "MarkItDownParserProvider requires the optional 'markitdown' package"
            ) from exc

        converter = MarkItDown()
        result = converter.convert(source_file.storage_path)
        text = getattr(result, "text_content", None) or str(result)
        return await TextParserProvider(max_chars=self.max_chars).parse_text(
            source_file=source_file,
            text=text,
        )

