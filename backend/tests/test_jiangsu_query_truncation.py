"""两个查询通道都必须显式告知结果是否被 LIMIT 截断（避免清单静默少报）。"""

import pytest

from app.tools.query.jiangsu_cube_metrics.tool import JiangsuQueryMetricsTool
from app.tools.query.jiangsu_ops_sql_query.tool import ExecuteJiangsuOpsSQLQueryTool


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    async def fetch(self, *args, **kwargs):
        return self._rows

    async def fetchval(self, *args, **kwargs):
        return "2026-10-19 00:00:00"

    async def execute(self, *args, **kwargs):
        return "OK"

    async def close(self):
        return None


def _prepare_mart_tool(monkeypatch, rows):
    tool = ExecuteJiangsuOpsSQLQueryTool()
    tool._mart_dsn = lambda: "postgresql://fake"

    async def fake_connect(*args, **kwargs):
        return _FakeConn(rows)

    async def no_audit(*args, **kwargs):
        return None

    async def no_quality_checks(conn, datasets):
        return []

    monkeypatch.setattr("app.tools.query.jiangsu_ops_sql_query.tool.asyncpg.connect", fake_connect)
    monkeypatch.setattr(tool, "_audit", no_audit)
    monkeypatch.setattr(tool, "_quality_checks", no_quality_checks)
    return tool


@pytest.mark.asyncio
async def test_mart_sql_reports_truncated_when_extra_row_returned(monkeypatch):
    tool = _prepare_mart_tool(monkeypatch, [{"x": i} for i in range(3)])

    result = await tool._execute_sql(
        "SELECT x FROM mart_work_order_analysis", limit=2, context=None
    )

    assert result["success"] is True
    assert result["truncated"] is True
    assert result["count"] == 2
    assert result["limit"] == 2
    assert len(result["data"]) == 2
    assert "结果被截断" in result["summary"]


@pytest.mark.asyncio
async def test_mart_sql_not_truncated_when_result_fits(monkeypatch):
    tool = _prepare_mart_tool(monkeypatch, [{"x": i} for i in range(2)])

    result = await tool._execute_sql(
        "SELECT x FROM mart_work_order_analysis", limit=2, context=None
    )

    assert result["truncated"] is False
    assert result["count"] == 2
    assert "结果被截断" not in result["summary"]


class _FakeResponse:
    status_code = 200
    text = ""

    def __init__(self, count):
        self._count = count

    def json(self):
        return {"data": [{"WorkOrder.count": {"value": i}} for i in range(self._count)]}


class _FakeClient:
    count = 0

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        return _FakeResponse(_FakeClient.count)


def _prepare_metrics_tool(monkeypatch, rows_returned):
    _FakeClient.count = rows_returned
    tool = JiangsuQueryMetricsTool()

    async def no_audit(*args, **kwargs):
        return None

    async def data_as_of(cube):
        return "2026-10-19 00:00:00"

    async def quality_status(cube):
        return "ok", []

    monkeypatch.setenv("CUBE_API_SECRET", "test-secret")
    monkeypatch.setattr("app.tools.query.jiangsu_cube_metrics.tool.httpx.AsyncClient", _FakeClient)
    monkeypatch.setattr(tool, "_audit", no_audit)
    monkeypatch.setattr(tool, "_data_as_of", data_as_of)
    monkeypatch.setattr(tool, "_quality_status", quality_status)
    return tool


@pytest.mark.asyncio
async def test_metrics_reports_truncated_when_extra_row_returned(monkeypatch):
    tool = _prepare_metrics_tool(monkeypatch, rows_returned=3)

    result = await tool.execute(measures=["WorkOrder.count"], limit=2)

    assert result["success"] is True
    assert result["truncated"] is True
    assert result["count"] == 2
    assert result["limit"] == 2
    assert "结果被截断" in result["summary"]


@pytest.mark.asyncio
async def test_metrics_not_truncated_when_result_fits(monkeypatch):
    tool = _prepare_metrics_tool(monkeypatch, rows_returned=2)

    result = await tool.execute(measures=["WorkOrder.count"], limit=2)

    assert result["truncated"] is False
    assert result["count"] == 2
    assert "结果被截断" not in result["summary"]
