import pytest

from app.utils.sql_validator import SQLValidator


@pytest.mark.parametrize(
    "expression",
    [
        "EXTRACT(HOUR FROM observed_at)",
        "extract(day from observed_at)",
        "EXTRACT(\nMONTH\nFROM\nobserved_at)",
        "EXTRACT(HOUR FROM COALESCE(observed_at, created_at))",
    ],
)
def test_extract_operand_is_not_a_table(expression):
    validator = SQLValidator(allowed_tables=["observations"], allowed_table_prefixes=[])
    sql = f"SELECT {expression} FROM observations"

    assert validator.extract_tables(sql) == ["observations"]
    valid, error = validator.validate(sql)
    assert valid, error


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT EXTRACT(HOUR FROM observed_at) FROM private_records",
        "SELECT EXTRACT(HOUR FROM (SELECT observed_at FROM private_records)) FROM observations",
        "SELECT EXTRACT(HOUR FROM observations.observed_at) FROM observations JOIN private_records ON 1 = 1",
    ],
)
def test_extract_does_not_hide_unapproved_tables(sql):
    validator = SQLValidator(allowed_tables=["observations"], allowed_table_prefixes=[])

    assert "private_records" in validator.extract_tables(sql)
    valid, error = validator.validate(sql)
    assert not valid
    assert "private_records" in error
