from __future__ import annotations

from typing import Protocol

from app.agent.cognition.models import (
    CognitiveMapQuery,
    CognitiveMapView,
    CognitiveSchema,
    DocumentChunk,
    ExtractionResult,
    SourceFile,
)


class DocumentParserProvider(Protocol):
    async def parse(self, source_file: SourceFile) -> list[DocumentChunk]:
        ...


class GraphExtractorProvider(Protocol):
    async def extract(
        self,
        chunks: list[DocumentChunk],
        schema: CognitiveSchema,
    ) -> ExtractionResult:
        ...


class GraphRetrieverProvider(Protocol):
    async def retrieve_view(self, request: CognitiveMapQuery) -> CognitiveMapView:
        ...

