import pytest

from app.tools.knowledge.knowledge_graph_build.tool import KnowledgeGraphBuildTool


class Task:
    id = "task-1"
    status = "queued"


class FakeService:
    async def run(self, task_id):
        return Task()

    async def _mark_task_failed(self, task_id, error):
        self.finished = {"status": "failed", "last_error": error}

    async def create_task(self, kb_id, mode="pending"):
        self.kb_id, self.mode = kb_id, mode
        return Task()

    async def get_status(self, **kwargs):
        return Task()


@pytest.mark.asyncio
async def test_build_requires_one_kb_and_returns_traceable_task(monkeypatch):
    service = FakeService()
    tool = KnowledgeGraphBuildTool(service=service)
    monkeypatch.setattr("asyncio.create_task", lambda coro: coro.close())
    result = await tool.execute(action="build", knowledge_base_ids=["kb-1"], mode="pending")
    assert result["success"] is True
    assert result["data"] == {"task_id": "task-1", "knowledge_base_id": "kb-1", "status": "queued"}
    assert service.kb_id == "kb-1"


@pytest.mark.asyncio
async def test_build_rejects_cross_kb_or_implicit_scope():
    result = await KnowledgeGraphBuildTool(service=FakeService()).execute(
        action="build", knowledge_base_ids=["kb-1", "kb-2"]
    )
    assert result["data"]["error"] == "knowledge_base_ids_must_contain_one"


@pytest.mark.asyncio
async def test_background_runner_marks_failed_task(monkeypatch):
    class Broken(FakeService):
        async def run(self, task_id):
            raise RuntimeError("boom")
    service = Broken()
    tool = KnowledgeGraphBuildTool(service=service)
    pending = []
    def capture(coro):
        pending.append(coro)
        return object()
    monkeypatch.setattr("asyncio.create_task", capture)
    result = await tool.execute(action="build", knowledge_base_ids=["kb-1"])
    assert result["success"] is True
    await pending[0]
    assert service.finished["status"] == "failed"
