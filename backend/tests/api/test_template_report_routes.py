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
    class ReportAgent:
        # Deliberately reject the retired message/agent_mode keyword arguments.
        async def analyze(self, *, user_query, manual_mode):
            assert manual_mode == "report"
            assert "2026-10-01" in user_query
            assert "模板章节" in user_query
            yield {"type": "start", "data": {"session_id": "report-session"}}
            yield {"type": "streaming_text", "data": {"chunk": "下载报告"}}
            yield {
                "type": "complete",
                "data": {"answer": "下载报告", "session_id": "report-session"},
            }

    monkeypatch.setattr(report_generation, "get_react_agent", ReportAgent)
    app = FastAPI()
    app.include_router(report_generation.router, prefix="/api")
    with TestClient(app) as client:
        yield client, app
    AppStatus.should_exit_event = None


def assert_report_stream(response):
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = [frame for frame in response.text.split("\n\n") if frame.strip()]
    assert sum(frame.startswith("event: start\n") for frame in frames) == 1
    assert sum(frame.startswith("event: complete\n") for frame in frames) == 1
    complete = next(frame for frame in frames if frame.startswith("event: complete\n"))
    assert json.loads(complete.split("data: ", 1)[1]) == {
        "answer": "下载报告", "session_id": "report-session"
    }
    assert "fatal_error" not in response.text


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

    class FailedAgent:
        async def analyze(self, *, user_query, manual_mode):
            yield {"type": "start", "data": {"session_id": "failed"}}
            raise RuntimeError("report data unavailable")

    monkeypatch.setattr(report_generation, "get_react_agent", FailedAgent)
    response = client.post("/api/report/generate-from-template-agent", json={
        "template_content": "# 模板章节",
        "target_time_range": {"start": "2026-10-01", "end": "2026-10-16"},
    })
    assert "event: fatal_error\n" in response.text
    assert "event: complete\n" not in response.text
    assert "report data unavailable" in response.text
