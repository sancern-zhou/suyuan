from app.tools.query.execute_postgres_sql_query.tool import ExecutePostgresSQLQueryTool
from app.utils.sql_validator import SQLValidator

OPS_TABLES = ["working_orders", "working_order_details"]


def test_validator_accepts_case_when_and_union_select():
    validator = SQLValidator(max_limit=1000, allowed_tables=OPS_TABLES)

    sql = """
        SELECT WORKINGORDERID, CASE WHEN DDWORKINGORDERSTATUS = N'Finish' THEN 1 ELSE 0 END AS done
        FROM working_orders
        UNION ALL
        SELECT WORKINGORDERID, 0 AS done
        FROM working_order_details
    """

    is_valid, error = validator.validate(sql)

    assert is_valid, error


def test_validator_normalizes_markdown_sql_code_fence():
    validator = SQLValidator(max_limit=1000, allowed_tables=OPS_TABLES)

    sql = """
```sql
SELECT WORKINGORDERID
FROM working_orders
```
"""

    is_valid, error = validator.validate(sql)

    assert is_valid, error


def test_validator_accepts_single_outer_parentheses_around_select():
    validator = SQLValidator(max_limit=1000, allowed_tables=OPS_TABLES)

    sql = "(SELECT WORKINGORDERID FROM working_orders)"

    is_valid, error = validator.validate(sql)

    assert is_valid, error


def test_validator_still_rejects_multiple_statements_after_normalization():
    validator = SQLValidator(max_limit=1000, allowed_tables=OPS_TABLES)

    sql = """
```sql
SELECT WORKINGORDERID FROM working_orders;
SELECT WORKINGORDERDETAILID FROM working_order_details;
```
"""

    is_valid, error = validator.validate(sql)

    assert not is_valid
    assert error == "不能执行多条SQL语句"


def test_execute_postgres_sql_query_allows_up_to_1000_rows():
    tool = ExecutePostgresSQLQueryTool()

    assert tool.sql_validator.max_limit == 1000
    assert "1000" in tool.function_schema["parameters"]["properties"]["limit"]["description"]


def test_execute_postgres_sql_query_allows_app_and_sound_tables():
    tool = ExecutePostgresSQLQueryTool()

    for sql in (
        "SELECT * FROM sys_user LIMIT 1",
        "SELECT * FROM permit_licenses LIMIT 1",
        "SELECT * FROM dat_station_hour_2025 LIMIT 1",
        "SELECT * FROM noise_1m_2025_1771a_src LIMIT 1",
    ):
        is_valid, error = tool.sql_validator.validate(sql)
        assert is_valid, f"{sql}: {error}"


def test_execute_postgres_sql_query_rejects_unknown_table():
    tool = ExecutePostgresSQLQueryTool()

    is_valid, error = tool.sql_validator.validate(
        "SELECT * FROM HenanCityAccumulateRanking LIMIT 1"
    )

    assert not is_valid
    assert "henancityaccumulateranking" in error.lower()
