import asyncio
import json

from app.knowledge_base.document_processor import DocumentProcessor


def test_single_pass_prompt_requires_faithful_source_text(monkeypatch):
    processor = DocumentProcessor.__new__(DocumentProcessor)
    captured = {}

    async def fake_call(prompt, llm_mode):
        captured["prompt"] = prompt
        return json.dumps(
            {
                "doc_context": {"title": "测试文档"},
                "chunks": [
                    {
                        "content": "第一条 原文不得总结。",
                        "topic": "测试",
                        "type": "paragraph",
                        "section": "第一条",
                    }
                ],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(processor, "_call_llm_api", fake_call)
    chunks = asyncio.run(
        processor._llm_chunk_single_pass(
            content="第一条 原文不得总结。",
            chunk_size=1200,
            filename="测试.txt",
            llm_mode="online",
        )
    )

    assert chunks[0]["content"] == "第一条 原文不得总结。"
    assert "禁止总结、概括、释义、压缩" in captured["prompt"]
    assert "无法确定是否属于噪声时必须保留" in captured["prompt"]
    assert "短条款必须保留" in captured["prompt"]
    assert "逐字/逐字母拆行" in captured["prompt"]
    assert "恢复为标准 LaTeX" in captured["prompt"]
    assert "无法确定结构时保留原始字符顺序，不得猜测" in captured["prompt"]


def test_contextual_prompt_does_not_drop_short_source_chunks(monkeypatch):
    processor = DocumentProcessor.__new__(DocumentProcessor)
    captured = {}

    async def fake_call(prompt, llm_mode):
        captured["prompt"] = prompt
        return json.dumps(
            {
                "chunks": [
                    {
                        "content": "短条款。",
                        "topic": "短条款",
                        "type": "paragraph",
                        "section": "1.1",
                    }
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(processor, "_call_llm_api", fake_call)
    chunks = asyncio.run(
        processor._llm_chunk_segment_with_context(
            segment="1.1 短条款。",
            chunk_size=1200,
            doc_context={"title": "测试文档"},
            segment_index=0,
            total_segments=1,
            llm_mode="online",
        )
    )

    assert chunks[0]["content"] == "短条款。"
    assert "不得省略任何正文段落" in captured["prompt"]
    assert "不得为了满足长度而删减或语义改写原文" in captured["prompt"]
    assert "逐字/逐字母拆行" in captured["prompt"]
    assert "一个字、字母、数字或公式符号单独占一行" in captured["prompt"]


def test_ocr_prompt_requires_layout_and_formula_recovery():
    prompt = DocumentProcessor.OCR_PROMPT_DEFAULT

    assert "错误断行" in prompt
    assert "一个汉字、一个英文字母、一个数字或一个公式符号单独占一行" in prompt
    assert "使用标准 LaTeX" in prompt
    assert "分式、根号、上下标" in prompt
    assert "禁止总结、概括、改写、删减或补充原文信息" in prompt
    assert "不得猜测" in prompt
