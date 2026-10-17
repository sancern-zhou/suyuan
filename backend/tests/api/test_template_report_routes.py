"""Template reports use the current Agent contract, without a legacy engine."""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sse_starlette.sse import AppStatus

from app.api import report_generation
from app.db.database import get_db


@pytest.fixture
def report_client(monkeypatch):
    AppStatus.should_exit_event = None
    from app.auth.models import CurrentUser
    from app.auth.dependencies import require_current_user
    from app.conversations.dependencies import get_conversation_catalog
    from app.api import agent
    from fastapi.responses import StreamingResponse
    user = CurrentUser(id="report-owner", username="owner", display_name="Owner")
    catalog = object()
    async def standard_analyze(request, raw_request, user, catalog):
        assert request.mode == "report"
        assert request.skill_ids == [] and request.context_refs == []
        assert "2026-10-01" in request.query and "模板章节" in request.query
        assert user.id == "report-owner" and catalog is expected_catalog
        assert raw_request.url.path.startswith("/api/report/")
        return StreamingResponse(iter([
            'data: ' + json.dumps({"type": "start", "data": {"session_id": "report-session"}}) + '\n\n',
            'data: ' + json.dumps({"type": "complete", "data": {"answer": "下载报告", "session_id": "report-session"}}) + '\n\n',
        ]), media_type="text/event-stream")
    expected_catalog = catalog
    monkeypatch.setattr(agent, "analyze_stream", standard_analyze)
    app = FastAPI()
    app.include_router(report_generation.router, prefix="/api")
    app.dependency_overrides[require_current_user] = lambda: user
    app.dependency_overrides[get_conversation_catalog] = lambda: catalog
    with TestClient(app) as client:
        yield client, app
    AppStatus.should_exit_event = None


def assert_report_stream(response):
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = [json.loads(frame.removeprefix("data: ")) for frame in response.text.split("\n\n") if frame.strip()]
    assert [frame["type"] for frame in frames] == ["start", "complete"]
    assert frames[-1]["data"] == {"answer": "下载报告", "session_id": "report-session"}


def test_json_template_uses_current_agent_and_single_terminal_event(report_client):
    client, _ = report_client
    assert_report_stream(client.post("/api/report/generate-from-template-agent", json={
        "template_content": "# 模板章节",
        "target_time_range": {"start": "2026-10-01", "end": "2026-10-16"},
    }))


def test_uploaded_template_uses_the_same_agent_path(report_client):
    client, _ = report_client
    assert_report_stream(client.post(
        "/api/report/generate-from-template-file",
        data={"start": "2026-10-01", "end": "2026-10-16"},
        files={"file": ("template.md", "# 模板章节".encode(), "text/markdown")},
    ))


def test_saved_template_generation_resolves_template_instead_of_returning_404(report_client):
    client, app = report_client
    template_id = uuid4()

    class SavedTemplateDB:
        async def get(self, model, identity):
            assert model is report_generation.ReportTemplate
            assert identity == template_id
            return SimpleNamespace(is_active=True, content="# 模板章节")

    app.dependency_overrides[get_db] = SavedTemplateDB
    assert_report_stream(client.post(f"/api/report/templates/{template_id}/generate", json={
        "time_range": {"start": "2026-10-01", "end": "2026-10-16"}
    }))


@pytest.mark.parametrize("template", [None, SimpleNamespace(is_active=False)])
def test_missing_or_inactive_saved_templates_are_rejected(report_client, template):
    client, app = report_client

    class SavedTemplateDB:
        async def get(self, model, identity):
            return template

    app.dependency_overrides[get_db] = SavedTemplateDB
    response = client.post(f"/api/report/templates/{uuid4()}/generate", json={
        "time_range": {"start": "2026-10-01", "end": "2026-10-16"}
    })
    assert response.status_code == 404


def test_agent_failure_has_no_synthetic_success_event(report_client, monkeypatch):
    client, _ = report_client

    from app.api import agent
    from fastapi.responses import StreamingResponse
    async def failed_standard_analyze(*args, **kwargs):
        return StreamingResponse(iter(['data: {"type":"fatal_error","data":{"error":"report data unavailable"}}\n\n']), media_type="text/event-stream")
    monkeypatch.setattr(agent, "analyze_stream", failed_standard_analyze)
    response = client.post("/api/report/generate-from-template-agent", json={
        "template_content": "# 模板章节",
        "target_time_range": {"start": "2026-10-01", "end": "2026-10-16"},
    })
    assert '"type":"fatal_error"' in response.text
    assert '"type":"complete"' not in response.text
    assert "report data unavailable" in response.text
