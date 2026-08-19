from types import SimpleNamespace

import pytest

from app.knowledge_base.scene_discovery import SceneDiscoveryService, select_representative_chunks


class FakeJsonLLM:
    def __init__(self, payload):
        self.payload = payload
        self.last_prompt = ""

    async def call_llm_with_json_response(self, prompt, max_retries=2):
        self.last_prompt = prompt
        return self.payload


class FakeChunks:
    async def list_by_document(self, document_id):
        return [
            SimpleNamespace(
                id=f"{document_id}-c1",
                chunk_index=0,
                content="企业A拥有空压机，空压机是主要噪声源。",
                section_path=["企业信息"],
            )
        ]


@pytest.mark.asyncio
async def test_discovery_uses_goal_questions_and_representative_chunks():
    llm = FakeJsonLLM(
        {
            "business_objects": [
                {"key": "enterprise", "name": "企业", "description": "被监管企业", "aliases": []},
                {"key": "noise_source", "name": "噪声源", "description": "产生噪声的对象", "aliases": ["声源"]},
            ],
            "business_logic": [
                {
                    "key": "enterprise_has_noise_source",
                    "statement": "企业拥有噪声源",
                    "source_key": "enterprise",
                    "relation_key": "has_noise_source",
                    "target_key": "noise_source",
                    "policy": "allowed",
                }
            ],
            "ignored_content": ["页眉页脚"],
            "diagnostics": {"coverage": "sufficient", "uncertainties": []},
        }
    )
    service = SceneDiscoveryService(llm=llm, chunk_repository=FakeChunks())
    draft = await service.discover(
        kb_id="kb1",
        scene_goal="分析企业噪声投诉与整改闭环",
        desired_questions=["企业有哪些主要噪声源？"],
        documents=[SimpleNamespace(id="doc1", filename="代表性文档.md")],
    )
    assert draft.source_document_ids == ["doc1"]
    assert draft.business_objects[1].aliases == ["声源"]
    assert "企业有哪些主要噪声源" in llm.last_prompt
    assert "代表性文档" in llm.last_prompt
    assert "只能使用 ASCII 小写英文字母、数字和下划线" in llm.last_prompt
    assert "source_key、target_key 必须精确引用某个 business_objects.key" in llm.last_prompt
    assert "diagnostics 必须是 JSON 对象，不能是数组" in llm.last_prompt


def test_representative_chunk_selection_is_bounded_and_keeps_first_chunk():
    chunks = [
        SimpleNamespace(id=f"c{i}", chunk_index=i, content="x" * 20, section_path=[])
        for i in range(10)
    ]
    selected = select_representative_chunks(chunks, max_chunks=3, max_chars=45)
    assert [chunk.id for chunk in selected] == ["c0", "c3"]
