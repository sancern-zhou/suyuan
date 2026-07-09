from app.tools.query.query_xcai_city_history.sql_client import normalize_city_names


def test_normalize_city_names_expands_short_city_name():
    assert normalize_city_names(["运城"]) == ["运城", "运城市"]


def test_normalize_city_names_keeps_full_city_name_without_duplicate():
    assert normalize_city_names(["运城市"]) == ["运城市"]


def test_normalize_city_names_preserves_non_city_suffixes():
    assert normalize_city_names(["阿勒泰地区", "伊犁哈萨克自治州"]) == [
        "阿勒泰地区",
        "伊犁哈萨克自治州",
    ]
