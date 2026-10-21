import json
from types import SimpleNamespace

import pytest

from app.knowledge_base.export_knowledge_base import KnowledgeBaseExporter
from app.knowledge_base.import_knowledge_base import KnowledgeBaseImporter


@pytest.mark.parametrize("tool", [KnowledgeBaseExporter, KnowledgeBaseImporter])
def test_retired_transfer_tools_refuse_default_use_before_side_effects(tool, monkeypatch):
    module = "app.knowledge_base." + ("export_knowledge_base" if tool is KnowledgeBaseExporter else "import_knowledge_base")
    monkeypatch.setattr(module + ".QdrantClient", lambda **kwargs: pytest.fail("must refuse before opening clients"))
    with pytest.raises(ValueError, match="legacy-only"):
        tool()


@pytest.mark.asyncio
async def test_legacy_import_rejects_typed_projection_before_database_writes(tmp_path):
    (tmp_path / "metadata.json").write_text(json.dumps({"knowledge_base": {"id": "kb"}}))
    (tmp_path / "vectors.jsonl").write_text(json.dumps({"payload": {"record_type": "chunk"}}))
    importer = KnowledgeBaseImporter.__new__(KnowledgeBaseImporter)
    result = await importer.import_knowledge_base(str(tmp_path))
    assert result["success"] is False
    assert "canonical facts" in result["errors"][0]


@pytest.mark.asyncio
async def test_legacy_export_rejects_canonical_facts_before_partial_export(tmp_path):
    class DB:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def scalar(self, statement, params):
            assert params == {"kb_id": "kb"}
            return 1
    exporter = KnowledgeBaseExporter.__new__(KnowledgeBaseExporter)
    exporter.export_dir = tmp_path
    exporter.timestamp = "test"
    exporter.db_session = DB
    result = await exporter.export_knowledge_base("kb")
    assert result["success"] is False
    assert "PostgreSQL backup" in result["errors"][0]
    assert not list(tmp_path.rglob("metadata.json"))
