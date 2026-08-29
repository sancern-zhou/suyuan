"""City air quality forecast fetcher backed by the air-quality APP API.

Ported from the retired standalone Windows service (APP监听). One request per
city returns current air quality, the coming days of daily forecasts, a 24
hour AQI trend and hourly weather. Results are upserted into the legacy XcAiDb
tables (CurrentAirQuality / WeatherForecast7Day / AQITrend24H / HourlyWeather)
that query tools and the Open-Meteo calibration provider already consume.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

import pyodbc
import requests
import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.tools.query.query_xcai_city_history.sql_client import get_sql_server_client

logger = structlog.get_logger()

CITY_AQ_FORECAST_URL = "https://epapi.moji.com/json/home/homePage"
CITY_AQ_FORECAST_PACKAGE_NAME = "com.cnemc.aqi"
CITY_AQ_FORECAST_REQUEST_TIMEOUT = 30
CITY_AQ_FORECAST_REQUEST_DELAY_RANGE = (1.5, 3.5)
CITY_AQ_FORECAST_MAX_ATTEMPTS = 3
CITY_AQ_FORECAST_RETRY_BACKOFF_SECONDS = 5.0

CITY_AQ_FORECAST_USER_AGENTS = (
    "Mozilla/5.0 (Linux; Android 13; SM-A536E) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; SM-G9910) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
)

CITY_AQ_FORECAST_CITIES: dict[str, str] = {
    "110000": "北京市",
    "120000": "天津市",
    "130100": "石家庄市",
    "130200": "唐山市",
    "130300": "秦皇岛市",
    "130400": "邯郸市",
    "130500": "邢台市",
    "130600": "保定市",
    "130700": "张家口市",
    "130800": "承德市",
    "130900": "沧州市",
    "131000": "廊坊市",
    "131100": "衡水市",
    "140100": "太原市",
    "140200": "大同市",
    "140300": "阳泉市",
    "140400": "长治市",
    "140500": "晋城市",
    "140600": "朔州市",
    "140700": "晋中市",
    "140800": "运城市",
    "140900": "忻州市",
    "141000": "临汾市",
    "141100": "吕梁市",
    "150100": "呼和浩特市",
    "150200": "包头市",
    "150300": "乌海市",
    "150400": "赤峰市",
    "150500": "通辽市",
    "150600": "鄂尔多斯市",
    "150700": "呼伦贝尔市",
    "150800": "巴彦淖尔市",
    "150900": "乌兰察布市",
    "152200": "兴安盟",
    "152500": "锡林郭勒盟",
    "152900": "阿拉善盟",
    "210100": "沈阳市",
    "210200": "大连市",
    "210300": "鞍山市",
    "210400": "抚顺市",
    "210500": "本溪市",
    "210600": "丹东市",
    "210700": "锦州市",
    "210800": "营口市",
    "210900": "阜新市",
    "211000": "辽阳市",
    "211100": "盘锦市",
    "211200": "铁岭市",
    "211300": "朝阳市",
    "211400": "葫芦岛市",
    "220100": "长春市",
    "220200": "吉林市",
    "220300": "四平市",
    "220400": "辽源市",
    "220500": "通化市",
    "220600": "白山市",
    "220700": "松原市",
    "220800": "白城市",
    "222400": "延边朝鲜族自治州",
    "230100": "哈尔滨市",
    "230200": "齐齐哈尔市",
    "230300": "鸡西市",
    "230400": "鹤岗市",
    "230500": "双鸭山市",
    "230600": "大庆市",
    "230700": "伊春市",
    "230800": "佳木斯市",
    "230900": "七台河市",
    "231000": "牡丹江市",
    "231100": "黑河市",
    "231200": "绥化市",
    "232700": "大兴安岭地区",
    "310000": "上海市",
    "320100": "南京市",
    "320200": "无锡市",
    "320300": "徐州市",
    "320400": "常州市",
    "320500": "苏州市",
    "320600": "南通市",
    "320700": "连云港市",
    "320800": "淮安市",
    "320900": "盐城市",
    "321000": "扬州市",
    "321100": "镇江市",
    "321200": "泰州市",
    "321300": "宿迁市",
    "330100": "杭州市",
    "330200": "宁波市",
    "330300": "温州市",
    "330400": "嘉兴市",
    "330500": "湖州市",
    "330600": "绍兴市",
    "330700": "金华市",
    "330800": "衢州市",
    "330900": "舟山市",
    "331000": "台州市",
    "331100": "丽水市",
    "340100": "合肥市",
    "340200": "芜湖市",
    "340300": "蚌埠市",
    "340400": "淮南市",
    "340500": "马鞍山市",
    "340600": "淮北市",
    "340700": "铜陵市",
    "340800": "安庆市",
    "341000": "黄山市",
    "341100": "滁州市",
    "341200": "阜阳市",
    "341300": "宿州市",
    "341500": "六安市",
    "341600": "亳州市",
    "341700": "池州市",
    "341800": "宣城市",
    "350100": "福州市",
    "350200": "厦门市",
    "350300": "莆田市",
    "350400": "三明市",
    "350500": "泉州市",
    "350600": "漳州市",
    "350700": "南平市",
    "350800": "龙岩市",
    "350900": "宁德市",
    "360100": "南昌市",
    "360200": "景德镇市",
    "360300": "萍乡市",
    "360400": "九江市",
    "360500": "新余市",
    "360600": "鹰潭市",
    "360700": "赣州市",
    "360800": "吉安市",
    "360900": "宜春市",
    "361000": "抚州市",
    "361100": "上饶市",
    "370100": "济南市",
    "370200": "青岛市",
    "370300": "淄博市",
    "370400": "枣庄市",
    "370500": "东营市",
    "370600": "烟台市",
    "370700": "潍坊市",
    "370800": "济宁市",
    "370900": "泰安市",
    "371000": "威海市",
    "371100": "日照市",
    "371200": "莱芜市",
    "371300": "临沂市",
    "371400": "德州市",
    "371500": "聊城市",
    "371600": "滨州市",
    "371700": "菏泽市",
    "410100": "郑州市",
    "410200": "开封市",
    "410300": "洛阳市",
    "410400": "平顶山市",
    "410500": "安阳市",
    "410600": "鹤壁市",
    "410700": "新乡市",
    "410800": "焦作市",
    "410900": "濮阳市",
    "411000": "许昌市",
    "411100": "漯河市",
    "411200": "三门峡市",
    "411300": "南阳市",
    "411400": "商丘市",
    "411500": "信阳市",
    "411600": "周口市",
    "411700": "驻马店市",
    "419001": "济源市",
    "420100": "武汉市",
    "420200": "黄石市",
    "420300": "十堰市",
    "420500": "宜昌市",
    "420600": "襄阳市",
    "420700": "鄂州市",
    "420800": "荆门市",
    "420900": "孝感市",
    "421000": "荆州市",
    "421100": "黄冈市",
    "421200": "咸宁市",
    "421300": "随州市",
    "422800": "恩施土家族苗族自治州",
    "429004": "仙桃市",
    "429005": "潜江市",
    "429006": "天门市",
    "429021": "神农架林区",
    "430100": "长沙市",
    "430200": "株洲市",
    "430300": "湘潭市",
    "430400": "衡阳市",
    "430500": "邵阳市",
    "430600": "岳阳市",
    "430700": "常德市",
    "430800": "张家界市",
    "430900": "益阳市",
    "431000": "郴州市",
    "431100": "永州市",
    "431200": "怀化市",
    "431300": "娄底市",
    "433100": "湘西土家族苗族自治州",
    "440100": "广州市",
    "440200": "韶关市",
    "440300": "深圳市",
    "440400": "珠海市",
    "440500": "汕头市",
    "440600": "佛山市",
    "440700": "江门市",
    "440800": "湛江市",
    "440900": "茂名市",
    "441200": "肇庆市",
    "441300": "惠州市",
    "441400": "梅州市",
    "441500": "汕尾市",
    "441600": "河源市",
    "441700": "阳江市",
    "441800": "清远市",
    "441900": "东莞市",
    "442000": "中山市",
    "445100": "潮州市",
    "445200": "揭阳市",
    "445300": "云浮市",
    "450100": "南宁市",
    "450200": "柳州市",
    "450300": "桂林市",
    "450400": "梧州市",
    "450500": "北海市",
    "450600": "防城港市",
    "450700": "钦州市",
    "450800": "贵港市",
    "450900": "玉林市",
    "451000": "百色市",
    "451100": "贺州市",
    "451200": "河池市",
    "451300": "来宾市",
    "451400": "崇左市",
    "460100": "海口市",
    "460200": "三亚市",
    "469001": "五指山市",
    "469002": "琼海市",
    "469005": "文昌市",
    "469006": "万宁市",
    "469007": "东方市",
    "469021": "定安县",
    "469022": "屯昌县",
    "469023": "澄迈县",
    "469024": "临高县",
    "469025": "白沙黎族自治县",
    "469026": "昌江黎族自治县",
    "469027": "乐东黎族自治县",
    "469028": "陵水黎族自治县",
    "469029": "保亭黎族苗族自治县",
    "469030": "琼中黎族苗族自治县",
    "500000": "重庆市",
    "510100": "成都市",
    "510300": "自贡市",
    "510400": "攀枝花市",
    "510500": "泸州市",
    "510600": "德阳市",
    "510700": "绵阳市",
    "510800": "广元市",
    "510900": "遂宁市",
    "511000": "内江市",
    "511100": "乐山市",
    "511300": "南充市",
    "511400": "眉山市",
    "511500": "宜宾市",
    "511600": "广安市",
    "511700": "达州市",
    "511800": "雅安市",
    "511900": "巴中市",
    "512000": "资阳市",
    "513200": "阿坝藏族羌族自治州",
    "513300": "甘孜藏族自治州",
    "513400": "凉山彝族自治州",
    "520100": "贵阳市",
    "520200": "六盘水市",
    "520300": "遵义市",
    "520400": "安顺市",
    "520500": "毕节市",
    "520600": "铜仁市",
    "522300": "黔西南布依族苗族自治州",
    "522600": "黔东南苗族侗族自治州",
    "522700": "黔南布依族苗族自治州",
    "530100": "昆明市",
    "530300": "曲靖市",
    "530400": "玉溪市",
    "530500": "保山市",
    "530600": "昭通市",
    "530700": "丽江市",
    "530800": "普洱市",
    "530900": "临沧市",
    "532300": "楚雄彝族自治州",
    "532500": "红河哈尼族彝族自治州",
    "532600": "文山壮族苗族自治州",
    "532800": "西双版纳傣族自治州",
    "532900": "大理白族自治州",
    "533100": "德宏傣族景颇族自治州",
    "533300": "怒江傈僳族自治州",
    "533400": "迪庆藏族自治州",
    "540100": "拉萨市",
    "540200": "日喀则市",
    "540300": "昌都市",
    "540400": "林芝市",
    "540500": "山南市",
    "540600": "那曲市",
    "542500": "阿里地区",
    "610100": "西安市",
    "610200": "铜川市",
    "610300": "宝鸡市",
    "610400": "咸阳市",
    "610500": "渭南市",
    "610600": "延安市",
    "610700": "汉中市",
    "610800": "榆林市",
    "610900": "安康市",
    "611000": "商洛市",
    "620100": "兰州市",
    "620200": "嘉峪关市",
    "620300": "金昌市",
    "620400": "白银市",
    "620500": "天水市",
    "620600": "武威市",
    "620700": "张掖市",
    "620800": "平凉市",
    "620900": "酒泉市",
    "621000": "庆阳市",
    "621100": "定西市",
    "621200": "陇南市",
    "622900": "临夏回族自治州",
    "623000": "甘南藏族自治州",
    "630100": "西宁市",
    "630200": "海东市",
    "632200": "海北藏族自治州",
    "632300": "黄南藏族自治州",
    "632500": "海南藏族自治州",
    "632600": "果洛藏族自治州",
    "632700": "玉树藏族自治州",
    "632800": "海西蒙古族藏族自治州",
    "640100": "银川市",
    "640200": "石嘴山市",
    "640300": "吴忠市",
    "640400": "固原市",
    "640500": "中卫市",
    "650100": "乌鲁木齐市",
    "650200": "克拉玛依市",
    "650400": "吐鲁番市",
    "650500": "哈密市",
    "652300": "昌吉回族自治州",
    "652700": "博尔塔拉蒙古自治州",
    "652800": "巴音郭楞蒙古自治州",
    "652900": "阿克苏地区",
    "653000": "克孜勒苏柯尔克孜自治州",
    "653100": "喀什地区",
    "653200": "和田地区",
    "654000": "伊犁哈萨克自治州",
    "654200": "塔城地区",
    "654300": "阿勒泰地区",
    "659001": "石河子市",
    "659002": "阿拉尔市",
    "659003": "图木舒克市",
    "659004": "五家渠市",
    "659005": "北屯市",
    "659006": "铁门关市",
    "659007": "双河市",
    "659008": "可克达拉市",
    "659009": "昆玉市",
    "659010": "胡杨河市",
    "659011": "新星市",
}


def build_city_forecast_payload(city_id: str) -> dict[str, Any]:
    """Build the request body the air-quality APP sends for one city."""
    return {
        "common": {
            "identifier": "",
            "app_version": "25040404",
            "os_version": "32",
            "device": "SM-A536E",
            "platform": "Android",
            "pid": "40001",
            "language": "CN",
            "uid": random.randint(40, 99),
            "width": 900,
            "height": 1600,
            "snsid": 100000908,
            "package_name": CITY_AQ_FORECAST_PACKAGE_NAME,
        },
        "params": {"cityId": city_id},
    }


def normalize_forecast_day(value: Any, today: date) -> date | None:
    """Parse 'MM/DD' style forecast dates, inferring a plausible year."""
    if not value:
        return None
    text = (
        str(value)
        .strip()
        .replace(".", "/")
        .replace("-", "/")
        .replace("年", "/")
        .replace("月", "/")
        .replace("日", "")
    )
    parts = [part for part in text.split("/") if part]
    if len(parts) < 2:
        return None
    try:
        parsed = date(today.year, int(parts[0]), int(parts[1]))
    except ValueError:
        return None
    if (today - parsed).days > 15:
        parsed = date(today.year + 1, parsed.month, parsed.day)
    return parsed


def parse_current_air_quality_params(city_id: str, payload: dict[str, Any]) -> list[Any] | None:
    """Build MERGE parameters for CurrentAirQuality from an API payload."""
    current = payload.get("current") or {}
    if not current:
        return None
    today = current.get("today") or {}
    tomorrow = current.get("tomorrow") or {}

    fields = (
        current.get("aqi"),
        current.get("pm25"),
        current.get("pm10"),
        current.get("o3"),
        current.get("so2"),
        current.get("no2"),
        current.get("co"),
        current.get("aqiLevel"),
        current.get("maxPollution"),
        current.get("tips"),
        current.get("tipsLevel"),
        current.get("condition"),
        current.get("temperature"),
        current.get("windPowder"),
        current.get("humidity"),
        current.get("time"),
        payload.get("cityCenterLongitude"),
        payload.get("cityCenterLatitude"),
        today.get("condition"),
        today.get("minAqi"),
        today.get("maxAqi"),
        today.get("maxPollution"),
        today.get("conditionIco"),
        today.get("temp"),
        today.get("tips"),
        today.get("tipsLevel"),
        tomorrow.get("condition"),
        tomorrow.get("minAqi"),
        tomorrow.get("maxAqi"),
        tomorrow.get("maxPollution"),
        tomorrow.get("conditionIco"),
        tomorrow.get("temp"),
        tomorrow.get("tips"),
        tomorrow.get("tipsLevel"),
    )
    return [city_id, *fields, city_id, *fields]


def parse_forecast_7day_params(
    city_id: str,
    city_name: str,
    payload: dict[str, Any],
    today: date,
) -> list[tuple[Any, ...]]:
    """Build MERGE parameters for WeatherForecast7Day from an API payload."""
    rows: list[tuple[Any, ...]] = []
    for item in payload.get("forecastWeatherData7") or []:
        time_point = normalize_forecast_day(item.get("day"), today)
        if time_point is None:
            logger.warning(
                "city_air_quality_forecast_day_unparsed", city_id=city_id, day=item.get("day")
            )
            continue
        rows.append(
            (
                city_id,
                city_name,
                datetime(time_point.year, time_point.month, time_point.day),
                item.get("dayTitle"),
                item.get("minAqi"),
                item.get("maxAqi"),
                item.get("maxPollution"),
                item.get("condition"),
                item.get("conditionIco"),
                item.get("temp"),
                item.get("windLevel"),
                item.get("windDir"),
            )
        )
    return rows


def parse_trend_24h_params(city_id: str, payload: dict[str, Any]) -> list[tuple[Any, ...]]:
    """Build MERGE parameters for AQITrend24H from an API payload."""
    rows: list[tuple[Any, ...]] = []
    for item in (payload.get("trendList24aqi") or {}).get("list") or []:
        value = item.get("value")
        rows.append(
            (
                city_id,
                item.get("time"),
                int(value) if value not in (None, "") else None,
                item.get("id"),
            )
        )
    return rows


def parse_hourly_weather_params(city_id: str, payload: dict[str, Any]) -> list[tuple[Any, ...]]:
    """Build MERGE parameters for HourlyWeather from an API payload."""
    rows: list[tuple[Any, ...]] = []
    for item in payload.get("hourlys") or []:
        rows.append((city_id, item.get("time"), item.get("temp"), item.get("ico")))
    return rows


class CityAirQualityForecastClient:
    """HTTP client for the air-quality APP home page API."""

    def __init__(
        self, base_url: str = CITY_AQ_FORECAST_URL, session: requests.Session | None = None
    ):
        self.base_url = base_url
        self.session = session or requests.Session()

    def fetch_city(self, city_id: str) -> dict[str, Any]:
        headers = {
            "User-Agent": random.choice(CITY_AQ_FORECAST_USER_AGENTS),
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
        }
        response = self.session.post(
            self.base_url,
            json=build_city_forecast_payload(city_id),
            headers=headers,
            timeout=CITY_AQ_FORECAST_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise RuntimeError(
                f"city forecast API returned code={payload.get('code')} message={payload.get('message')}"
            )
        return payload


MERGE_CURRENT_AIR_QUALITY_SQL = """
MERGE CurrentAirQuality AS target
USING (SELECT ? AS CityID) AS source
ON target.CityID = source.CityID
WHEN MATCHED THEN
    UPDATE SET
        AQI = ?, PM25 = ?, PM10 = ?, O3 = ?, SO2 = ?, NO2 = ?, CO = ?,
        AQILevel = ?, MaxPollution = ?, Tips = ?, TipsLevel = ?,
        WeatherCondition = ?, Temperature = ?, WindPower = ?, Humidity = ?,
        RecordTime = ?, UpdateTime = GETDATE(),
        CityCenterLongitude = ?, CityCenterLatitude = ?,
        TodayCondition = ?, TodayMinAqi = ?, TodayMaxAqi = ?, TodayMaxPollution = ?,
        TodayConditionIco = ?, TodayTemp = ?, TodayTips = ?, TodayTipsLevel = ?,
        TomorrowCondition = ?, TomorrowMinAqi = ?, TomorrowMaxAqi = ?, TomorrowMaxPollution = ?,
        TomorrowConditionIco = ?, TomorrowTemp = ?, TomorrowTips = ?, TomorrowTipsLevel = ?
WHEN NOT MATCHED THEN
    INSERT (CityID, AQI, PM25, PM10, O3, SO2, NO2, CO, AQILevel, MaxPollution, Tips, TipsLevel,
           WeatherCondition, Temperature, WindPower, Humidity, RecordTime,
           CityCenterLongitude, CityCenterLatitude,
           TodayCondition, TodayMinAqi, TodayMaxAqi, TodayMaxPollution, TodayConditionIco, TodayTemp, TodayTips, TodayTipsLevel,
           TomorrowCondition, TomorrowMinAqi, TomorrowMaxAqi, TomorrowMaxPollution, TomorrowConditionIco, TomorrowTemp, TomorrowTips, TomorrowTipsLevel)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
"""

MERGE_AQI_TREND_24H_SQL = """
MERGE AQITrend24H AS target
USING (SELECT ? AS CityID, ? AS Time, ? AS AQIValue, ? AS SequenceID, CAST(GETDATE() AS DATE) AS UpdateDate) AS source
ON target.CityID = source.CityID AND target.Time = source.Time AND target.UpdateDate = source.UpdateDate
WHEN MATCHED THEN
    UPDATE SET AQIValue = source.AQIValue, SequenceID = source.SequenceID, UpdateTime = GETDATE()
WHEN NOT MATCHED THEN
    INSERT (CityID, Time, AQIValue, SequenceID)
    VALUES (source.CityID, source.Time, source.AQIValue, source.SequenceID);
"""

MERGE_WEATHER_FORECAST_7DAY_SQL = """
MERGE WeatherForecast7Day AS target
USING (SELECT ? AS CityCode, ? AS cityname, ? AS TimePoint, ? AS DayTitle, ? AS MinAqi, ? AS MaxAqi, ? AS MaxPollution,
              ? AS WeatherCondition, ? AS ConditionIco, ? AS Temperature, ? AS WindLevel, ? AS WindDirection,
              CAST(GETDATE() AS DATE) AS UpdateDate) AS source
ON target.CityCode = source.CityCode AND target.TimePoint = source.TimePoint AND target.UpdateDate = source.UpdateDate
WHEN MATCHED THEN
    UPDATE SET cityname = source.cityname, DayTitle = source.DayTitle, MinAqi = source.MinAqi, MaxAqi = source.MaxAqi,
              MaxPollution = source.MaxPollution, WeatherCondition = source.WeatherCondition,
              ConditionIco = source.ConditionIco, Temperature = source.Temperature,
              WindLevel = source.WindLevel, WindDirection = source.WindDirection, UpdateTime = GETDATE()
WHEN NOT MATCHED THEN
    INSERT (CityCode, cityname, DayTitle, TimePoint, MinAqi, MaxAqi, MaxPollution,
           WeatherCondition, ConditionIco, Temperature, WindLevel, WindDirection)
    VALUES (source.CityCode, source.cityname, source.DayTitle, source.TimePoint, source.MinAqi, source.MaxAqi, source.MaxPollution,
           source.WeatherCondition, source.ConditionIco, source.Temperature, source.WindLevel, source.WindDirection);
"""

MERGE_HOURLY_WEATHER_SQL = """
MERGE HourlyWeather AS target
USING (SELECT ? AS CityID, ? AS Time, ? AS Temperature, ? AS WeatherIco, CAST(GETDATE() AS DATE) AS UpdateDate) AS source
ON target.CityID = source.CityID AND target.Time = source.Time AND target.UpdateDate = source.UpdateDate
WHEN MATCHED THEN
    UPDATE SET Temperature = source.Temperature, WeatherIco = source.WeatherIco, UpdateTime = GETDATE()
WHEN NOT MATCHED THEN
    INSERT (CityID, Time, Temperature, WeatherIco)
    VALUES (source.CityID, source.Time, source.Temperature, source.WeatherIco);
"""

ENSURE_TABLES_SQL = (
    """
IF OBJECT_ID(N'dbo.CurrentAirQuality', N'U') IS NULL
BEGIN
    CREATE TABLE CurrentAirQuality (
        ID INT IDENTITY(1,1) PRIMARY KEY,
        CityID NVARCHAR(20) NOT NULL,
        AQI INT,
        PM25 FLOAT,
        PM10 FLOAT,
        O3 FLOAT,
        SO2 FLOAT,
        NO2 FLOAT,
        CO FLOAT,
        AQILevel INT,
        MaxPollution NVARCHAR(50),
        Tips NVARCHAR(500),
        TipsLevel INT,
        WeatherCondition NVARCHAR(100),
        Temperature NVARCHAR(10),
        WindPower NVARCHAR(50),
        Humidity NVARCHAR(10),
        RecordTime NVARCHAR(50),
        UpdateTime DATETIME DEFAULT GETDATE(),
        CityCenterLongitude FLOAT,
        CityCenterLatitude FLOAT,
        TodayCondition NVARCHAR(100),
        TodayMinAqi INT,
        TodayMaxAqi INT,
        TodayMaxPollution NVARCHAR(50),
        TodayConditionIco INT,
        TodayTemp NVARCHAR(50),
        TodayTips NVARCHAR(500),
        TodayTipsLevel INT,
        TomorrowCondition NVARCHAR(100),
        TomorrowMinAqi INT,
        TomorrowMaxAqi INT,
        TomorrowMaxPollution NVARCHAR(50),
        TomorrowConditionIco INT,
        TomorrowTemp NVARCHAR(50),
        TomorrowTips NVARCHAR(500),
        TomorrowTipsLevel INT,
        CONSTRAINT UK_CurrentAirQuality_City UNIQUE (CityID)
    );
    CREATE INDEX IX_CurrentAirQuality_UpdateTime ON CurrentAirQuality(UpdateTime);
    CREATE INDEX IX_CurrentAirQuality_AQI ON CurrentAirQuality(AQI);
END
""",
    """
IF OBJECT_ID(N'dbo.AQITrend24H', N'U') IS NULL
BEGIN
    CREATE TABLE AQITrend24H (
        ID INT IDENTITY(1,1) PRIMARY KEY,
        CityID NVARCHAR(20) NOT NULL,
        Time NVARCHAR(10) NOT NULL,
        AQIValue INT,
        SequenceID INT,
        UpdateDate DATE DEFAULT CAST(GETDATE() AS DATE),
        UpdateTime DATETIME DEFAULT GETDATE(),
        CONSTRAINT UK_AQITrend24H_CityTimeDate UNIQUE (CityID, Time, UpdateDate)
    );
    CREATE INDEX IX_AQITrend24H_CityID ON AQITrend24H(CityID);
    CREATE INDEX IX_AQITrend24H_UpdateDate ON AQITrend24H(UpdateDate);
END
""",
    """
IF OBJECT_ID(N'dbo.WeatherForecast7Day', N'U') IS NULL
BEGIN
    CREATE TABLE WeatherForecast7Day (
        ID INT IDENTITY(1,1) PRIMARY KEY,
        CityCode NVARCHAR(20) NOT NULL,
        cityname NVARCHAR(100) NOT NULL,
        DayTitle NVARCHAR(50),
        TimePoint DATETIME NOT NULL,
        MinAqi INT,
        MaxAqi INT,
        MaxPollution NVARCHAR(50),
        WeatherCondition NVARCHAR(100),
        ConditionIco INT,
        Temperature NVARCHAR(50),
        WindLevel NVARCHAR(10),
        WindDirection NVARCHAR(50),
        UpdateDate DATE DEFAULT CAST(GETDATE() AS DATE),
        UpdateTime DATETIME DEFAULT GETDATE(),
        CONSTRAINT UK_WeatherForecast7Day_CityDateUpdate UNIQUE (CityCode, TimePoint, UpdateDate)
    );
    CREATE INDEX IX_WeatherForecast7Day_CityCode ON WeatherForecast7Day(CityCode);
    CREATE INDEX IX_WeatherForecast7Day_cityname ON WeatherForecast7Day(cityname);
    CREATE INDEX IX_WeatherForecast7Day_TimePoint ON WeatherForecast7Day(TimePoint);
    CREATE INDEX IX_WeatherForecast7Day_UpdateDate ON WeatherForecast7Day(UpdateDate);
END
""",
    """
IF OBJECT_ID(N'dbo.HourlyWeather', N'U') IS NULL
BEGIN
    CREATE TABLE HourlyWeather (
        ID INT IDENTITY(1,1) PRIMARY KEY,
        CityID NVARCHAR(20) NOT NULL,
        Time NVARCHAR(10) NOT NULL,
        Temperature NVARCHAR(10),
        WeatherIco INT,
        UpdateDate DATE DEFAULT CAST(GETDATE() AS DATE),
        UpdateTime DATETIME DEFAULT GETDATE(),
        CONSTRAINT UK_HourlyWeather_CityTimeDate UNIQUE (CityID, Time, UpdateDate)
    );
    CREATE INDEX IX_HourlyWeather_CityID ON HourlyWeather(CityID);
    CREATE INDEX IX_HourlyWeather_UpdateDate ON HourlyWeather(UpdateDate);
END
""",
)


class CityAirQualitySQLStorage:
    """Upsert city forecast payloads into the legacy XcAiDb tables."""

    def __init__(self, sql_client=None):
        self.sql_client = sql_client or get_sql_server_client()
        self._connection: pyodbc.Connection | None = None

    def _get_connection(self) -> pyodbc.Connection:
        if self._connection is None:
            self._connection = pyodbc.connect(self.sql_client.connection_string, timeout=30)
            cursor = self._connection.cursor()
            try:
                self.ensure_tables(cursor)
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
            finally:
                cursor.close()
        return self._connection

    def reset_connection(self) -> None:
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception:
                pass
            self._connection = None

    def ensure_tables(self, cursor: pyodbc.Cursor) -> None:
        for statement in ENSURE_TABLES_SQL:
            cursor.execute(statement)

    def store_city(
        self,
        city_id: str,
        city_name: str,
        payload: dict[str, Any],
        fetched_at: datetime,
    ) -> dict[str, int]:
        """Store one city payload and return per-table saved row counts."""
        today = fetched_at.date()
        counts: dict[str, int] = {}

        current_params = parse_current_air_quality_params(city_id, payload)
        trend_rows = parse_trend_24h_params(city_id, payload)
        forecast_rows = parse_forecast_7day_params(city_id, city_name, payload, today)
        hourly_rows = parse_hourly_weather_params(city_id, payload)

        connection = self._get_connection()
        cursor = connection.cursor()
        try:
            if current_params:
                cursor.execute(MERGE_CURRENT_AIR_QUALITY_SQL, current_params)
                counts["CurrentAirQuality"] = 1
            if trend_rows:
                cursor.executemany(MERGE_AQI_TREND_24H_SQL, trend_rows)
                counts["AQITrend24H"] = len(trend_rows)
            if forecast_rows:
                cursor.executemany(MERGE_WEATHER_FORECAST_7DAY_SQL, forecast_rows)
                counts["WeatherForecast7Day"] = len(forecast_rows)
            if hourly_rows:
                cursor.executemany(MERGE_HOURLY_WEATHER_SQL, hourly_rows)
                counts["HourlyWeather"] = len(hourly_rows)
            connection.commit()
        except Exception:
            connection.rollback()
            self.reset_connection()
            raise
        finally:
            cursor.close()
        return counts

    def close(self) -> None:
        self.reset_connection()


class CityAirQualityForecastFetcher(DataFetcher):
    """Fetch nationwide city air quality forecasts from the air-quality APP API."""

    def __init__(
        self,
        client: CityAirQualityForecastClient | None = None,
        storage: CityAirQualitySQLStorage | None = None,
        cities: dict[str, str] | None = None,
        delay_factory: Callable[[], float] | None = None,
        now_factory: Callable[[], datetime] = datetime.now,
    ):
        super().__init__(
            name="city_air_quality_forecast_fetcher",
            description="全国城市未来5天空气质量预报抓取（空气质量发布APP接口）",
            schedule="30 7 * * *",
            version="1.0.0",
        )
        self.client = client or CityAirQualityForecastClient()
        self.storage = storage or CityAirQualitySQLStorage()
        self.cities = dict(cities or CITY_AQ_FORECAST_CITIES)
        self.delay_factory = delay_factory or (
            lambda: random.uniform(*CITY_AQ_FORECAST_REQUEST_DELAY_RANGE)
        )
        self.now_factory = now_factory

    async def fetch_and_store(self) -> dict[str, Any]:
        run_started = self.now_factory().replace(microsecond=0)
        run_id = run_started.strftime("%Y%m%d%H%M%S")
        saved_rows: dict[str, int] = {}
        failed_cities: dict[str, str] = {}
        total_cities = len(self.cities)
        processed = 0

        for city_id, city_name in self.cities.items():
            processed += 1
            progress = f"{processed}/{total_cities}"
            await asyncio.sleep(self.delay_factory())

            try:
                payload = await self._fetch_city_with_retry(city_id)
            except Exception as exc:
                failed_cities[city_id] = str(exc)
                logger.warning(
                    "city_air_quality_forecast_fetch_failed",
                    city_id=city_id,
                    city=city_name,
                    progress=progress,
                    error=str(exc),
                )
                continue

            try:
                counts = await asyncio.to_thread(
                    self.storage.store_city, city_id, city_name, payload, run_started
                )
            except Exception as exc:
                failed_cities[city_id] = str(exc)
                logger.warning(
                    "city_air_quality_forecast_store_failed",
                    city_id=city_id,
                    city=city_name,
                    progress=progress,
                    error=str(exc),
                )
                continue

            for table, count in counts.items():
                saved_rows[table] = saved_rows.get(table, 0) + count
            logger.info(
                "city_air_quality_forecast_city_stored",
                city_id=city_id,
                city=city_name,
                progress=progress,
                **counts,
            )

        try:
            self.storage.close()
        except Exception:
            pass

        succeeded = total_cities - len(failed_cities)
        if succeeded == 0:
            raise RuntimeError("All city air quality forecast fetches failed")

        if failed_cities:
            sample = sorted(failed_cities)[:10]
            logger.warning(
                "city_air_quality_forecast_failures",
                failed=len(failed_cities),
                sample=sample,
            )

        logger.info(
            "city_air_quality_forecast_run_complete",
            run_id=run_id,
            cities=succeeded,
            failed_cities=len(failed_cities),
            saved_rows=saved_rows,
        )
        return {
            "run_id": run_id,
            "cities": succeeded,
            "total_cities": total_cities,
            "failed_cities": len(failed_cities),
            "saved_rows": saved_rows,
        }

    async def _fetch_city_with_retry(self, city_id: str) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(CITY_AQ_FORECAST_MAX_ATTEMPTS):
            if attempt:
                backoff = CITY_AQ_FORECAST_RETRY_BACKOFF_SECONDS * (
                    2 ** (attempt - 1)
                ) + random.uniform(0, 3)
                await asyncio.sleep(backoff)
            try:
                return await asyncio.to_thread(self.client.fetch_city, city_id)
            except Exception as exc:
                last_error = exc
        assert last_error is not None
        raise last_error
