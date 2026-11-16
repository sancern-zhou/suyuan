import pytest

from app.tools.query.execute_smart_event_sql_query.tool import (
    SMART_EVENT_SQL_TABLES,
    ExecuteSmartEventSQLQueryTool,
)


def _enable_db(monkeypatch, enabled=True):
    monkeypatch.setattr(
        "app.services.smart_event_db.smart_event_db_enabled", lambda: enabled
    )


def _patch_run(monkeypatch, rows, captured=None):
    async def fake_run(sql, params=None):
        if captured is not None:
            captured["sql"] = sql
            captured["params"] = params
        return rows

    monkeypatch.setattr(ExecuteSmartEventSQLQueryTool, "_run_sql", staticmethod(fake_run))


def test_schema_injects_event_center_tables_and_guidance():
    schema = ExecuteSmartEventSQLQueryTool().function_schema

    assert schema["name"] == "execute_smart_event_sql_query"
    assert set(schema["parameters"]["properties"]) == {"describe_table", "sql", "limit"}
    description = schema["description"]
    for table in SMART_EVENT_SQL_TABLES:
        assert table in description
    # 归并口径与状态滞后提醒必须注入，避免按事件行数误当原始告警数。
    assert "merged_alarm_ids" in description
    assert "task_reviews" in description


@pytest.mark.asyncio
async def test_rejects_non_whitelisted_table(monkeypatch):
    _enable_db(monkeypatch)
    _patch_run(monkeypatch, [{"n": 1}])

    result = await ExecuteSmartEventSQLQueryTool().execute(sql="SELECT * FROM base_device")

    assert result["success"] is False
    assert "白名单" in result["summary"]


@pytest.mark.asyncio
async def test_rejects_information_schema_discovery(monkeypatch):
    _enable_db(monkeypatch)
    _patch_run(monkeypatch, [])

    result = await ExecuteSmartEventSQLQueryTool().execute(
        sql="SELECT table_name FROM information_schema.tables"
    )

    assert result["success"] is False
    assert "information_schema" in result["summary"]


@pytest.mark.asyncio
async def test_rejects_write_statement(monkeypatch):
    _enable_db(monkeypatch)
    _patch_run(monkeypatch, [])

    result = await ExecuteSmartEventSQLQueryTool().execute(sql="DELETE FROM smart_events")

    assert result["success"] is False
    assert "SELECT" in result["summary"]


@pytest.mark.asyncio
async def test_appends_limit_and_returns_rows(monkeypatch):
    _enable_db(monkeypatch)
    captured = {}
    _patch_run(monkeypatch, [{"event_id": "e1", "site_name": "江宁站"}], captured)

    result = await ExecuteSmartEventSQLQueryTool().execute(
        sql="SELECT event_id, site_name FROM smart_events WHERE site_name = '江宁站'",
        limit=30,
    )

    assert result["success"] is True
    assert result["count"] == 1
    assert result["data"][0]["event_id"] == "e1"
    assert "LIMIT 30" in captured["sql"]


@pytest.mark.asyncio
async def test_describe_table_returns_whitelisted_columns(monkeypatch):
    _enable_db(monkeypatch)
    _patch_run(
        monkeypatch,
        [
            {"column_name": "event_id", "data_type": "character varying", "is_nullable": "NO"},
            {"column_name": "data", "data_type": "jsonb", "is_nullable": "NO"},
        ],
    )

    result = await ExecuteSmartEventSQLQueryTool().execute(describe_table="smart_events")

    assert result["success"] is True
    assert result["data"]["table_name"] == "smart_events"
    assert "event_id" in result["summary"]


@pytest.mark.asyncio
async def test_describe_table_rejects_unknown_table(monkeypatch):
    _enable_db(monkeypatch)

    result = await ExecuteSmartEventSQLQueryTool().execute(describe_table="users")

    assert result["success"] is False
    assert "白名单" in result["summary"]


@pytest.mark.asyncio
async def test_reports_when_event_db_disabled(monkeypatch):
    _enable_db(monkeypatch, enabled=False)

    result = await ExecuteSmartEventSQLQueryTool().execute(sql="SELECT event_id FROM smart_events")

    assert result["success"] is False
    assert "未启用" in result["summary"]
