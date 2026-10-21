from __future__ import annotations

from app.knowledge_base.graph_extraction.providers.llamaindex_extractor import (
    LlamaIndexPropertyGraphExtractorProvider,
)
from app.knowledge_base.graph_extraction.providers.local_extractor import LocalRuleBasedExtractorProvider




def create_extractor_provider(name: str | None = None, llm=None):
    provider_name = (name or "local").strip().lower()
    if provider_name == "local":
        return LocalRuleBasedExtractorProvider()
    if provider_name == "llamaindex":
        return LlamaIndexPropertyGraphExtractorProvider(llm=llm)
    raise ValueError(f"Unknown knowledge graph extractor provider: {name}")
