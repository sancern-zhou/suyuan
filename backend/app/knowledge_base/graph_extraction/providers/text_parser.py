from __future__ import annotations

from app.knowledge_base.graph_extraction.models import GraphDocumentChunk, GraphSourceFile


class TextParserProvider:
    """Plain-text parser used as the local fallback parser for the spike."""

    def __init__(self, max_chars: int = 1200) -> None:
        self.max_chars = max_chars

    async def parse(self, source_file: GraphSourceFile) -> list[GraphDocumentChunk]:
        text = source_file.path.read_text(encoding="utf-8")
        return await self.parse_text(source_file=source_file, text=text)

    async def parse_text(self, source_file: GraphSourceFile, text: str) -> list[GraphDocumentChunk]:
        paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
        if not paragraphs and text.strip():
            paragraphs = [text.strip()]

        chunks: list[GraphDocumentChunk] = []
        packed_parts: list[str] = []
        packed_start = 0
        packed_end = 0

        def flush_packed() -> None:
            nonlocal packed_parts, packed_start, packed_end
            if not packed_parts:
                return
            chunk_index = len(chunks)
            chunks.append(
                GraphDocumentChunk(
                    chunk_id=f"{source_file.file_id}:chunk:{chunk_index}",
                    knowledge_base_id=source_file.knowledge_base_id,
                    source_file_id=source_file.file_id,
                    chunk_index=chunk_index,
                    text="\n\n".join(packed_parts),
                    location=self._location(packed_start, packed_end),
                )
            )
            packed_parts = []
            packed_start = 0
            packed_end = 0

        for paragraph_index, paragraph in enumerate(paragraphs, start=1):
            parts = self._split_paragraph(paragraph)
            if len(parts) > 1:
                flush_packed()
                for part in parts:
                    chunk_index = len(chunks)
                    chunks.append(
                        GraphDocumentChunk(
                            chunk_id=f"{source_file.file_id}:chunk:{chunk_index}",
                            knowledge_base_id=source_file.knowledge_base_id,
                            source_file_id=source_file.file_id,
                            chunk_index=chunk_index,
                            text=part,
                            location=f"paragraph {paragraph_index}",
                        )
                    )
                continue

            part = parts[0] if parts else ""
            candidate = "\n\n".join([*packed_parts, part]) if packed_parts else part
            if packed_parts and len(candidate) > self.max_chars:
                flush_packed()
            if not packed_parts:
                packed_start = paragraph_index
            packed_parts.append(part)
            packed_end = paragraph_index

        flush_packed()
        return chunks

    def _location(self, start: int, end: int) -> str:
        if start == end:
            return f"paragraph {start}"
        return f"paragraphs {start}-{end}"

    def _split_paragraph(self, paragraph: str) -> list[str]:
        if len(paragraph) <= self.max_chars:
            return [paragraph]
        return [
            paragraph[start : start + self.max_chars].strip()
            for start in range(0, len(paragraph), self.max_chars)
            if paragraph[start : start + self.max_chars].strip()
        ]
