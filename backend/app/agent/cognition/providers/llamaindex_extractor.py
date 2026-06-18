from __future__ import annotations

from app.agent.cognition.models import CognitiveSchema, DocumentChunk, ExtractionResult


class LlamaIndexPropertyGraphExtractorProvider:
    """Optional LlamaIndex Property Graph adapter placeholder.

    This provider intentionally exposes the project-level contract first. The
    concrete LlamaIndex wiring can evolve without changing callers.
    """

    provider_name = "llamaindex_property_graph"

    async def extract(
        self,
        chunks: list[DocumentChunk],
        schema: CognitiveSchema,
    ) -> ExtractionResult:
        try:
            import llama_index.core  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "LlamaIndexPropertyGraphExtractorProvider requires optional "
                "'llama-index' packages. Use LocalRuleBasedExtractorProvider "
                "for offline Spike runs."
            ) from exc

        raise NotImplementedError(
            "LlamaIndex adapter dependency is available, but the concrete "
            "schema-guided extraction mapping has not been enabled in this Spike."
        )
