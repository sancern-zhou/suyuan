from app.tools.query.get_observed_meteorology.tool import (
    GetObservedMeteorologyTool,
    build_hour_spi_url,
    parse_city_options,
    parse_hour_spi_table,
)


CITY_JSON = """
[
  {"StationCode":"54161","CityCode":"101060101","CityName":"长春","CityNamePY":"changchun","ProvinceAJC":"AJL","Trajectories":false,"Lon":null,"Lat":null},
  {"StationCode":"54172","CityCode":"101060201","CityName":"吉林","CityNamePY":"jilin","ProvinceAJC":"AJL","Trajectories":false,"Lon":null,"Lat":null}
]
"""


HTML = """
<table class="data-table display">
  <thead>
    <tr>
      <th>城市</th><th>时间</th><th>风向(deg)</th><th>风速(m/s)</th>
      <th>气压(hPa)</th><th>气温(°C)</th><th>降雨量(mm)</th><th>湿度(%)</th><th>体感温度(°C)</th><th>操作</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>南昌</td><td>2026-06-12 00:00</td><td>96.000</td><td>1.200</td>
      <td>1007.000</td><td>26.500</td><td>0.000</td><td>67.000</td><td>26.500</td><td>纠正</td>
    </tr>
    <tr>
      <td>南昌</td><td>2026-06-12 01:00</td><td></td><td>0.800</td>
      <td>1006.000</td><td>25.500</td><td>0.100</td><td>70.000</td><td>25.500</td><td>纠正</td>
    </tr>
  </tbody>
</table>
<div class='data-pager-left'><span class='data-pager-left-number'>1/3</span></div>
"""


def test_parse_city_options_from_ajax_json():
    cities = parse_city_options(CITY_JSON)

    assert cities["长春"]["city_code"] == "101060101"
    assert cities["长春"]["station_code"] == "54161"
    assert cities["吉林"]["province_ajc"] == "AJL"


def test_parse_hour_spi_table_standardizes_weather_fields():
    parsed = parse_hour_spi_table(HTML)

    assert parsed["page_count"] == 3
    assert len(parsed["records"]) == 2
    first = parsed["records"][0]
    assert first["city"] == "南昌"
    assert first["timestamp"] == "2026-06-12 00:00:00"
    assert first["measurements"]["wind_direction_10m"] == 96.0
    assert first["measurements"]["wind_speed_10m"] == 1.2
    assert first["measurements"]["surface_pressure"] == 1007.0
    assert first["measurements"]["temperature_2m"] == 26.5
    assert first["measurements"]["precipitation"] == 0.0
    assert first["measurements"]["relative_humidity_2m"] == 67.0
    assert "wind_direction_10m" not in parsed["records"][1]["measurements"]


def test_build_hour_spi_url_encodes_parameters():
    url = build_hour_spi_url(
        base_url="http://10.10.10.137:18405",
        province_ajc="AJX",
        city_code="101240101",
        start_time="2026-06-12 00:00",
        end_time="2026-06-13 00:00",
        page_index=2,
        page_size=50,
    )

    assert url.startswith("http://10.10.10.137:18405/Meteorology/HourSpiData?")
    assert "province=AJX" in url
    assert "city=101240101" in url
    assert "startTime=2026-06-12+00%3A00" in url
    assert "pageIndex=2" in url
    assert "pageSize=50" in url


def test_schema_describes_city_and_district_targets_without_province_requirement():
    schema = GetObservedMeteorologyTool().function_schema
    properties = schema["parameters"]["properties"]

    assert "city_name" in properties
    assert "district_name" in properties
    assert "location_name" in properties
    assert "province_name" not in properties
    assert "province_ajc" not in properties
    assert schema["parameters"]["required"] == ["start_time", "end_time"]


def test_resolve_location_discovers_province_from_city_name():
    class Client:
        def fetch_home(self):
            return '<select id="province"><option value="AJL">吉林省</option></select>'

        def fetch_cities(self, province_ajc):
            assert province_ajc == "AJL"
            return parse_city_options(CITY_JSON)

    tool = GetObservedMeteorologyTool()
    province, city_code, meta = tool._resolve_location(
        client=Client(),
        province_ajc=None,
        province_name=None,
        city_code=None,
        city_name="长春市",
    )

    assert province == "AJL"
    assert city_code == "101060101"
    assert meta["city_name"] == "长春"


def test_resolve_location_reports_missing_area_in_user_terms():
    class Client:
        def fetch_home(self):
            raise AssertionError("province directory should not be requested without a target")

    tool = GetObservedMeteorologyTool()
    try:
        tool._resolve_location(
            client=Client(),
            province_ajc=None,
            province_name=None,
            city_code=None,
            city_name=None,
        )
    except ValueError as exc:
        assert "city_name 或 city_code" in str(exc)
        assert "无需提供省份内部编码" in str(exc)
    else:
        raise AssertionError("expected missing-area validation error")
