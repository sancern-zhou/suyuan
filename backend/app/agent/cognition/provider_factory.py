from __future__ import annotations

from app.agent.cognition.providers.llamaindex_extractor import (
    LlamaIndexPropertyGraphExtractorProvider,
)
from app.agent.cognition.providers.local_extractor import LocalRuleBasedExtractorProvider
from app.agent.cognition.providers.markitdown_parser import MarkItDownParserProvider
from app.agent.cognition.providers.text_parser import TextParserProvider


def create_parser_provider(name: str | None = None):
    provider_name = (name or "text").strip().lower()
    if provider_name == "text":
        return TextParserProvider()
    if provider_name == "markitdown":
        return MarkItDownParserProvider()
    raise ValueError(f"Unknown cognitive map parser provider: {name}")


def create_extractor_provider(name: str | None = None, llm=None):
    provider_name = (name or "local").strip().lower()
    if provider_name == "local":
        return LocalRuleBasedExtractorProvider()
    if provider_name == "llamaindex":
        return LlamaIndexPropertyGraphExtractorProvider(llm=llm)
    raise ValueError(f"Unknown cognitive map extractor provider: {name}")
