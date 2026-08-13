import pytest

from app.knowledge_base.chunking_strategies import CHUNKING_STRATEGIES
from app.knowledge_base.document_processor import DocumentProcessor, LLMMode
from app.knowledge_base.schemas import LLMModeEnum


def test_llm_chunking_catalog_only_exposes_online_mode():
    assert set(CHUNKING_STRATEGIES["llm"]["llm_modes"]) == {"online"}
    assert list(LLMMode) == [LLMMode.ONLINE]
    assert list(LLMModeEnum) == [LLMModeEnum.ONLINE]


def test_legacy_local_qwen_chunking_methods_are_removed():
    assert not hasattr(DocumentProcessor, "_call_local_llm")
    assert not hasattr(DocumentProcessor, "_llm_chunk_segment")


@pytest.mark.asyncio
async def test_document_processor_rejects_retired_local_llm_mode(monkeypatch):
    processor = DocumentProcessor()

    async def retired_local_call(prompt):
        return "retired"

    monkeypatch.setattr(
        processor,
        "_call_local_llm",
        retired_local_call,
        raising=False,
    )

    with pytest.raises(ValueError, match="Unsupported LLM mode: local"):
        await processor._call_llm_api("test", "local")


@pytest.mark.asyncio
async def test_chunk_with_llm_does_not_swallow_retired_local_mode():
    processor = DocumentProcessor()

    with pytest.raises(ValueError, match="Unsupported LLM mode: local"):
        await processor.chunk_with_llm("测试文档内容", llm_mode="local")
