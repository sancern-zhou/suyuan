from datetime import date

import pytest

from app.services.tenders.models import (
    NoticeType,
    PipelineRunResult,
    TenderCandidate,
    TenderFilterDecision,
    TenderNotice,
)
from app.services.tenders.repository import SQLServerTenderRepository


class FakeCursor:
    def __init__(self):
        self.statements = []
        self.rowcount = 0
        self.fetchone_values = []

    def execute(self, sql, *params):
        self.statements.append((sql, params))
        if sql.lstrip().upper().startswith("INSERT"):
            self.rowcount = 1
        elif sql.lstrip().upper().startswith("UPDATE"):
            self.rowcount = 0
        return self

    def fetchone(self):
        if self.fetchone_values:
            return self.fetchone_values.pop(0)
        return None


class FakeConnection:
    def __init__(self):
        self.cursor_obj = FakeCursor()
        self.commits = 0
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_save_candidate_inserts_and_reports_new(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(
        "app.services.tenders.repository.pyodbc.connect",
        lambda *_args, **_kwargs: connection,
    )
    repository = SQLServerTenderRepository(connection_string="driver=fake")

    is_new = await repository.save_candidate(
        TenderCandidate(
            title="生态环境局监测项目招标公告",
            url="https://example.com/notice/1",
            notice_type=NoticeType.TENDER,
            keyword="生态环境局",
            publish_date=date(2026, 6, 30),
            raw_list_text="列表文本",
            metadata={"area_name": "广东-广州"},
        )
    )

    assert is_new is True
    assert connection.commits == 1
    sql, params = connection.cursor_obj.statements[0]
    assert "INSERT INTO tender_candidates" in sql
    assert params[0][0] == "生态环境局监测项目招标公告"
    assert params[0][1] == "https://example.com/notice/1"


@pytest.mark.asyncio
async def test_update_candidate_decision_sets_accepted_status(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(
        "app.services.tenders.repository.pyodbc.connect",
        lambda *_args, **_kwargs: connection,
    )
    repository = SQLServerTenderRepository(connection_string="driver=fake")

    await repository.update_candidate_decision(
        TenderCandidate(title="公告", url="https://example.com/1"),
        TenderFilterDecision(
            is_relevant=True,
            reason="命中环境业务",
            confidence=0.91,
            decision_source="llm",
        ),
    )

    sql, params = connection.cursor_obj.statements[0]
    assert "UPDATE tender_candidates" in sql
    assert params[0][0] == "accepted"
    assert params[0][1] == "命中环境业务"
    assert params[0][3] == "llm"


@pytest.mark.asyncio
async def test_save_notice_updates_then_inserts_when_missing(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(
        "app.services.tenders.repository.pyodbc.connect",
        lambda *_args, **_kwargs: connection,
    )
    repository = SQLServerTenderRepository(connection_string="driver=fake")

    await repository.save_notice(
        TenderNotice(
            title="生态环境监测项目中标公告",
            url="https://example.com/notice/2",
            notice_type=NoticeType.WINNING_BID,
            raw_content="详情正文",
            project_name="生态环境监测项目",
            purchaser="某生态环境局",
            publish_date=date(2026, 6, 30),
            key_requirements=["监测服务"],
            attachment_urls=["https://example.com/a.pdf"],
            structured_json={"project_name": "生态环境监测项目"},
        )
    )

    update_sql, _update_params = connection.cursor_obj.statements[0]
    insert_sql, insert_params = connection.cursor_obj.statements[1]
    assert "UPDATE tender_notices" in update_sql
    assert "INSERT INTO tender_notices" in insert_sql
    assert insert_params[0][0] == "生态环境监测项目中标公告"
    assert insert_params[0][1] == "https://example.com/notice/2"


@pytest.mark.asyncio
async def test_create_and_finish_run(monkeypatch):
    connection = FakeConnection()
    connection.cursor_obj.fetchone_values.append((42,))
    monkeypatch.setattr(
        "app.services.tenders.repository.pyodbc.connect",
        lambda *_args, **_kwargs: connection,
    )
    repository = SQLServerTenderRepository(connection_string="driver=fake")

    run_id = await repository.create_run(
        target_date=date(2026, 6, 30),
        keywords=["生态环境局"],
        notice_types=[NoticeType.TENDER],
    )
    await repository.finish_run(
        run_id,
        PipelineRunResult(total_candidates=3, saved_notices=1, errors=["detail failed"]),
    )

    assert run_id == 42
    assert "INSERT INTO tender_fetch_runs" in connection.cursor_obj.statements[0][0]
    finish_sql, finish_params = connection.cursor_obj.statements[1]
    assert "UPDATE tender_fetch_runs" in finish_sql
    assert finish_params[0][0] == 3
    assert finish_params[0][4] == 1
    assert finish_params[0][6] == "partial_failed"
