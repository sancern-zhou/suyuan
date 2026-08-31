import asyncio

from app.knowledge_base.document_processor import DocumentProcessor


def test_llm_fallback_prefers_markdown_for_structured_content(monkeypatch):
    processor = DocumentProcessor.__new__(DocumentProcessor)
    captured = {}

    async def fake_llm_single_pass(*args, **kwargs):
        raise RuntimeError("llm down")

    async def fake_generate_doc_context(*args, **kwargs):
        return {"title": "空气质量标准2026", "doc_type": "国家标准", "main_topics": ["表格"]}

    async def fake_llm_segment(*args, **kwargs):
        raise RuntimeError("segment down")

    def fake_chunk_sync(content, strategy, chunk_size, chunk_overlap):
        captured["strategy"] = strategy
        captured["chunk_size"] = chunk_size
        captured["chunk_overlap"] = chunk_overlap
        return [
            {
                "id": "chunk_0",
                "content": "### 表1 环境空气污染物基本项目浓度限值",
                "metadata": {"type": "paragraph"},
            }
        ]

    def fake_split_large_chunks(chunks, max_size=900):
        captured["split_max_size"] = max_size
        return chunks

    monkeypatch.setattr(DocumentProcessor, "_llm_chunk_single_pass", fake_llm_single_pass)
    monkeypatch.setattr(
        DocumentProcessor,
        "_generate_doc_context_for_chunking",
        fake_generate_doc_context,
    )
    monkeypatch.setattr(
        DocumentProcessor,
        "_llm_chunk_segment_with_context",
        fake_llm_segment,
    )
    monkeypatch.setattr(processor, "_chunk_sync", fake_chunk_sync)
    monkeypatch.setattr(processor, "_split_large_chunks", fake_split_large_chunks)

    chunks = asyncio.run(
        processor.chunk_with_llm(
            content=(
                "### 表1 环境空气污染物基本项目浓度限值\n\n"
                "| 污染物 | 1小时平均 | 24小时平均 | 年平均 |\n"
                "| SO2 | 350 | 150 | 60 |\n"
            ),
            chunk_size=1200,
            filename="空气质量标准2026_逐页转录.md",
            llm_mode="online",
        )
    )

    assert captured["strategy"] == "markdown"
    assert captured["split_max_size"] == 1800
    assert chunks[0]["content"].startswith("### 表1")


def test_split_large_chunk_content_preserves_raw_table_rows():
    processor = DocumentProcessor()
    content = (
        "[表格 - 第1页]\n"
        "污染物 | 1小时平均 | 24小时平均 | 年平均\n"
        "SO2 | 350 | 150 | 60\n"
        "NO2 | 200 | 80 | 40\n"
        "PM10 | 150 | 75 | 35\n"
        "O3 | 160 | 80 | 100\n"
    )

    parts = processor._split_large_chunk_content(content, max_size=80)

    assert len(parts) >= 2
    assert all(part.startswith("[表格 - 第1页]") for part in parts)
    assert all("污染物 | 1小时平均 | 24小时平均 | 年平均" in part for part in parts)
    assert any("SO2 | 350 | 150 | 60" in part for part in parts)
    assert any("O3 | 160 | 80 | 100" in part for part in parts)


def test_split_large_chunk_content_keeps_flat_table_markers_intact():
    processor = DocumentProcessor()
    content = "[表格]\nSO2 350 150 60\nNO2 200 80 40\nPM10 150 75 35\n"

    parts = processor._split_large_chunk_content(content, max_size=12)

    assert parts == [content]


def test_merge_small_chunks_keeps_table_chunks_independent():
    processor = DocumentProcessor()
    chunks = [
        {"id": "c0", "content": "前言", "metadata": {"type": "paragraph"}},
        {
            "id": "c1",
            "content": "[表格]\n| A | B |\n| --- | --- |\n| 1 | 2 |",
            "metadata": {"type": "table"},
        },
        {"id": "c2", "content": "正文主体" * 100, "metadata": {"type": "paragraph"}},
    ]

    merged = processor._merge_small_chunks(chunks, min_size=150)

    assert len(merged) == 3
    assert merged[1]["metadata"]["type"] == "table"
    assert merged[1]["content"].startswith("[表格]")
    assert merged[0]["content"] == "前言"
    assert merged[2]["content"].startswith("正文主体")
