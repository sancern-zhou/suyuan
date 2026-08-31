from app.tools.query.execute_sql_query.tool import ExecuteSQLQueryTool


def test_execute_sql_query_schema_embeds_reusable_frequent_table_contracts():
    description = ExecuteSQLQueryTool().get_function_schema()["description"]

    assert "查询这些表时直接生成SQL，不要先调用describe_table" in description
    assert "城市名称和行政区代码从当前项目上下文或用户长期记忆获取" in description
    assert "本工具不内置特定项目的地理信息" in description
    assert "不得把模板变量原样写入SQL" in description
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

    assert "dat_zhongda_station_minute" in description
    assert "dat_zhongda_station_hour" in description
    assert "data_table_type = 'Act'" in description
    assert "NO浓度列名是no_val" in description
    assert "-99为平台无效值" in description

    assert "dat_zhongda_station_day" in description
    assert "时间为data_date（DATE类型）" in description
    assert "dat_zhongda_city_hour" in description
    assert "dat_zhongda_city_day" in description
    assert "SubstitutionBack" in description
    assert "城市表由平台聚合任务生成，可能为空" in description
    assert "2026-01-01起为'155th'" in description
    assert "用错规划期会返回空" in description

    assert "优先查询中大平台表（dat_zhongda_*）" in description
    assert "中大源为审核后数据" in description
    assert "本表仅作补充" in description

    assert "WeatherForecast7Day" in description
    assert "cityname仅用于此预报表" in description

    assert "XuchangNmcHourlyWeatherForecast" in description
    assert "优先查询NMC气象预报数据" in description
    assert "Open-Meteo预报数据（OpenMeteoAirQualityForecast72h）作为补充" in description
    assert "禁止把它当作气象预报来源" in description
    assert "气象字段：temperature（℃）" in description
    assert "3小时间隔" in description

    assert "HenanCityAccumulateRanking" in description
    assert "period_type区分monthly（月累计）/yearly（年累计）" in description
    assert "城市字段为city" in description
    assert "排名为city_rank" in description


def test_execute_sql_query_schema_keeps_describe_table_for_unlisted_fields():
    description = ExecuteSQLQueryTool().get_function_schema()["description"]

    assert "仅当需要契约未列出的字段，或数据库返回字段错误时，才调用describe_table" in description
