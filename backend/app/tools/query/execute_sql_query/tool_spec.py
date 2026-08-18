from app.tools.query.execute_sql_query.tool import ExecuteSQLQueryTool


def test_execute_sql_query_schema_embeds_reusable_frequent_table_contracts():
    description = ExecuteSQLQueryTool().get_function_schema()["description"]

    assert "查询这些表时直接生成SQL，不要先调用describe_table" in description
    assert "城市名称和行政区代码从当前项目上下文或用户长期记忆获取" in description
    assert "本工具不内置特定项目的地理信息" in description
    assert "不得把模板变量原样写入SQL" in description
    assert "许昌" not in description
    assert "411000" not in description

    assert "CurrentAirQuality" in description
    assert "CityID = '{city_code}'" in description
    assert "没有cityname、Area、CityCode" in description

    assert "CityAQIPublishHistory" in description
    assert "Area = N'{city_name}'或CityCode = {city_code}" in description
    assert "PM2_5，不是PM25" in description

    assert "dat_station_hour" in description
    assert "city_area_code = '{city_code}'" in description
    assert "污染物字段使用小写" in description

    assert "WeatherForecast7Day" in description
    assert "cityname仅用于此预报表" in description

    assert "HenanCityAccumulateRanking" in description
    assert "period_type区分monthly（月累计）/yearly（年累计）" in description
    assert "城市字段为city" in description
    assert "排名为city_rank" in description


def test_execute_sql_query_schema_keeps_describe_table_for_unlisted_fields():
    description = ExecuteSQLQueryTool().get_function_schema()["description"]

    assert "仅当需要契约未列出的字段，或数据库返回字段错误时，才调用describe_table" in description
