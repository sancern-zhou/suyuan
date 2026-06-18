from __future__ import annotations

from app.agent.cognition.models import DocumentChunk, SourceFile


class TextParserProvider:
    """Plain-text parser used as the local fallback parser for the spike."""

    def __init__(self, max_chars: int = 1200) -> None:
        self.max_chars = max_chars

    async def parse(self, source_file: SourceFile) -> list[DocumentChunk]:
        text = source_file.path.read_text(encoding="utf-8")
        return await self.parse_text(source_file=source_file, text=text)

    async def parse_text(self, source_file: SourceFile, text: str) -> list[DocumentChunk]:
        paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
        if not paragraphs and text.strip():
            paragraphs = [text.strip()]

        chunks: list[DocumentChunk] = []
        for paragraph_index, paragraph in enumerate(paragraphs, start=1):
            for part in self._split_paragraph(paragraph):
                chunk_index = len(chunks)
                chunks.append(
                    DocumentChunk(
                        chunk_id=f"{source_file.file_id}:chunk:{chunk_index}",
                        map_id=source_file.map_id,
                        source_file_id=source_file.file_id,
                        chunk_index=chunk_index,
                        text=part,
                        location=f"paragraph {paragraph_index}",
                    )
                )
        return chunks

    def _split_paragraph(self, paragraph: str) -> list[str]:
        if len(paragraph) <= self.max_chars:
            return [paragraph]
        return [
            paragraph[start : start + self.max_chars].strip()
            for start in range(0, len(paragraph), self.max_chars)
            if paragraph[start : start + self.max_chars].strip()
        ]

