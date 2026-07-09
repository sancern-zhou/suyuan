from app.agent.prompts.tool_registry import get_tool_order
from app.tools import create_global_tool_registry
from app.tools.query.execute_sql_query.tool import ExecuteTenderSQLQueryTool


def test_tender_sql_tool_schema_uses_tender_defaults():
    tool = ExecuteTenderSQLQueryTool()

    schema = tool.get_function_schema()

    assert tool.name == "execute_tender_sql_query"
    assert tool.default_database == "XcAiDb"
    assert schema["name"] == "execute_tender_sql_query"
    assert schema["parameters"]["properties"]["database"]["enum"] == ["XcAiDb", "AirPollutionAnalysis"]
    assert "tender_notices" in schema["description"]


def test_tender_sql_tool_allows_tender_tables():
    tool = ExecuteTenderSQLQueryTool()

    valid, error = tool.sql_validator.validate(
        "SELECT TOP 10 id, title FROM tender_notices ORDER BY publish_date DESC"
    )

    assert valid is True
    assert error == ""


def test_tender_sql_tool_rejects_non_tender_tables():
    tool = ExecuteTenderSQLQueryTool()

    valid, error = tool.sql_validator.validate("SELECT TOP 10 * FROM working_orders")

    assert valid is False
    assert "表名不在白名单中" in error
    assert "working_orders" in error


def test_tender_sql_tool_rejects_mutating_sql():
    tool = ExecuteTenderSQLQueryTool()

    valid, error = tool.sql_validator.validate("DELETE FROM tender_notices")

    assert valid is False
    assert "只允许SELECT查询" in error


def test_tender_sql_tool_is_registered_globally():
    registry = create_global_tool_registry()

    assert registry.get_tool("execute_tender_sql_query") is not None


def test_tender_sql_tool_is_available_in_assistant_mode():
    assert "execute_tender_sql_query" in get_tool_order("assistant")
