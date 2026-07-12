from __future__ import annotations

from typing import Protocol

from app.knowledge_base.graph_extraction.models import (
    GraphDocumentChunk,
    GraphExtractionResult,
    GraphExtractionSchema,
    GraphSourceFile,
)


class DocumentParserProvider(Protocol):
    async def parse(self, source_file: GraphSourceFile) -> list[GraphDocumentChunk]: ...


class GraphExtractorProvider(Protocol):
    async def extract(
        self,
        chunks: list[GraphDocumentChunk],
        schema: GraphExtractionSchema,
        **kwargs,
    ) -> GraphExtractionResult: ...
