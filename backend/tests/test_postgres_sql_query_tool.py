from app.agent.prompts.tool_registry import get_tool_order
from app.tools import create_global_tool_registry
from app.tools.query.execute_postgres_sql_query.tool import (
    MAX_LIMIT,
    ExecutePostgresSQLQueryTool,
)


def test_postgres_sql_tool_schema_is_limited_to_permit_tables():
    tool = ExecutePostgresSQLQueryTool()

    schema = tool.get_function_schema()

    assert tool.name == "execute_postgres_sql_query"
    assert schema["name"] == "execute_postgres_sql_query"
    assert schema["parameters"]["properties"]["describe_table"]["enum"] == [
        "permit_licenses",
        "permit_license_versions",
        "permit_pollution_details",
        "permit_documents",
    ]


def test_postgres_sql_tool_allows_permit_join_and_rejects_other_tables():
    tool = ExecutePostgresSQLQueryTool()

    valid, error = tool.sql_validator.validate(
        "SELECT l.enterprise_name, p.air_pollutant_types "
        "FROM permit_licenses l JOIN permit_pollution_details p ON p.license_id = l.id "
        "LIMIT 10"
    )
    assert valid is True
    assert error == ""

    valid, error = tool.sql_validator.validate("SELECT * FROM permit_crawl_runs LIMIT 10")
    assert valid is False
    assert "permit_crawl_runs" in error


def test_postgres_sql_tool_rejects_mutating_sql_and_uses_postgres_limit():
    tool = ExecutePostgresSQLQueryTool()

    valid, error = tool.sql_validator.validate("DELETE FROM permit_licenses")
    assert valid is False
    assert "只允许SELECT查询" in error

    safe_sql, error = tool._sanitize_limit("SELECT * FROM permit_licenses", 25)
    assert error is None
    assert safe_sql.endswith("LIMIT 25")

    safe_sql, error = tool._sanitize_limit("SELECT * FROM permit_licenses LIMIT 99999", 25)
    assert error is None
    assert safe_sql.endswith(f"LIMIT {MAX_LIMIT}")


def test_postgres_sql_tool_is_registered_and_available_to_query_agents():
    registry = create_global_tool_registry()

    assert registry.get_tool("execute_postgres_sql_query") is not None
    assert "execute_postgres_sql_query" in get_tool_order("assistant")
    assert "execute_postgres_sql_query" in get_tool_order("expert")
    assert "execute_postgres_sql_query" in get_tool_order("query")
    assert "execute_postgres_sql_query" in get_tool_order("report")
