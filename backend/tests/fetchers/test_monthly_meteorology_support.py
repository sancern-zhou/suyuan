import csv
import json
from datetime import date
from pathlib import Path

import pytest

from app.fetchers.consultation.monthly_meteorology_support import (
    METEOROLOGY_YOY_METRICS,
    MonthlyMeteorologySupport,
)


@pytest.fixture(autouse=True)
def disable_auto_yoy_by_default(monkeypatch):
    monkeypatch.setenv("CMA_METEOROLOGY_DISABLE_AUTO_YOY", "true")
    monkeypatch.delenv("CMA_METEOROLOGY_YOY_STATS_FILE", raising=False)


def test_meteorology_support_writes_manifest_and_unavailable_yoy_stats(tmp_path, monkeypatch):
    generator = MonthlyMeteorologySupport(2026, 5, output_dir=tmp_path)
    monkeypatch.setattr(generator, "_resolve_source_url_from_page", lambda url: None)

    manifest_path = generator.generate()

    stats_path = tmp_path / "meteorology_yoy_stats_202605.csv"
    assert manifest_path == tmp_path / "meteorology_support_202605.json"
    assert manifest_path.exists()
    assert stats_path.exists()

    with open(stats_path, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert [row["metric"] for row in rows] == [metric["metric"] for metric in METEOROLOGY_YOY_METRICS]
    assert all(row["available"] == "false" for row in rows)
    assert all(row["missing_reason"] for row in rows)

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["source"] == "中央气象台/中国气象局"
    assert manifest["period"] == "2026年05月"
    assert manifest["yoy_stats"]["file"] == "meteorology_yoy_stats_202605.csv"
    assert manifest["yoy_stats"]["available"] is False
    assert manifest["yoy_stats"]["data_source"] == "广东省气象局观测数据（自动抓取计算）"
    assert manifest["yoy_stats"]["statistical_scope"] == "广东省全省口径，21个地市城市月值平均"
    assert manifest["yoy_stats"]["calculation_notes"]["low_wind_days"] == "小风日数按日均风速 < 2.0 m/s 统计"
    assert manifest["yoy_stats"]["calculation_notes"]["precipitation_days"] == "降水日数按日降水量 >= 0.1 mm 统计"
    assert manifest["yoy_stats"]["calculation_notes"]["precipitation"] == "降水量为城市月累计降水量的全省平均"
    assert set(manifest["maps"]) == {"temperature_anomaly", "precipitation_anomaly_percent"}
    assert manifest["maps"]["temperature_anomaly"]["available"] is False
    assert manifest["maps"]["precipitation_anomaly_percent"]["available"] is False
    assert "summary" not in manifest


def test_meteorology_support_auto_fetches_and_calculates_yoy_stats(tmp_path, monkeypatch):
    monkeypatch.delenv("CMA_METEOROLOGY_YOY_STATS_FILE", raising=False)
    monkeypatch.delenv("CMA_METEOROLOGY_DISABLE_AUTO_YOY", raising=False)

    class FakeWeatherClient:
        @classmethod
        def query_weather(cls, city_name, begin_time, end_time):
            year = int(begin_time[:4])
            if year == 2026:
                return [
                    {
                        "cityName": city_name,
                        "stationCode": "S1",
                        "timePoint": "2026-05-01 00:00",
                        "temperature": 30,
                        "windSpeed": 1,
                        "precipitation1h": 0.2,
                        "sunshineDuration": 2,
                    },
                    {
                        "cityName": city_name,
                        "stationCode": "S1",
                        "timePoint": "2026-05-01 01:00",
                        "temperature": 32,
                        "windSpeed": 3,
                        "precipitation1h": 0.3,
                        "sunshineDuration": 4,
                    },
                    {
                        "cityName": city_name,
                        "stationCode": "S1",
                        "timePoint": "2026-05-02 00:00",
                        "temperature": 28,
                        "windSpeed": 1,
                        "precipitation1h": 0,
                        "sunshineDuration": 1,
                    },
                    {
                        "cityName": city_name,
                        "stationCode": "S1",
                        "timePoint": "2026-05-02 01:00",
                        "temperature": 30,
                        "windSpeed": 1,
                        "precipitation1h": 0,
                        "sunshineDuration": 1,
                    },
                ]
            return [
                {
                    "cityName": city_name,
                    "stationCode": "S1",
                    "timePoint": "2025-05-01 00:00",
                    "temperature": 28,
                    "windSpeed": 2,
                    "precipitation1h": 0.1,
                    "sunshineDuration": 1,
                },
                {
                    "cityName": city_name,
                    "stationCode": "S1",
                    "timePoint": "2025-05-01 01:00",
                    "temperature": 30,
                    "windSpeed": 2,
                    "precipitation1h": 0.1,
                    "sunshineDuration": 2,
                },
                {
                    "cityName": city_name,
                    "stationCode": "S1",
                    "timePoint": "2025-05-02 00:00",
                    "temperature": 26,
                    "windSpeed": 2,
                    "precipitation1h": 0,
                    "sunshineDuration": 1,
                },
                {
                    "cityName": city_name,
                    "stationCode": "S1",
                    "timePoint": "2025-05-02 01:00",
                    "temperature": 28,
                    "windSpeed": 2,
                    "precipitation1h": 0,
                    "sunshineDuration": 1,
                },
            ]

    generator = MonthlyMeteorologySupport(
        2026,
        5,
        output_dir=tmp_path,
        weather_client=FakeWeatherClient,
        city_names=["广州"],
    )
    monkeypatch.setattr(generator, "_resolve_source_url_from_page", lambda url: None)

    manifest_path = generator.generate()

    stats_path = tmp_path / "meteorology_yoy_stats_202605.csv"
    with open(stats_path, "r", encoding="utf-8-sig") as f:
        rows = {row["metric"]: row for row in csv.DictReader(f)}

    assert rows["气温"]["available"] == "true"
    assert rows["气温"]["current_value"] == "30"
    assert rows["气温"]["last_year_value"] == "28"
    assert rows["气温"]["yoy_change"] == "2"
    assert rows["日照时数"]["current_value"] == "8"
    assert rows["风速"]["current_value"] == "1.5"
    assert rows["小风日数"]["current_value"] == "1"
    assert rows["降水量"]["current_value"] == "0.5"
    assert rows["降水日数"]["current_value"] == "1"

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["yoy_stats"]["available"] is True


def test_meteorology_support_defaults_to_consultation_file_dir(monkeypatch):
    generator = MonthlyMeteorologySupport(2026, 5)
    monkeypatch.setattr(generator, "_resolve_source_url_from_page", lambda url: None)

    assert generator.output_dir == Path("/tmp/A会商文件/2026年05月")


def test_meteorology_support_downloads_configured_maps(tmp_path, monkeypatch):
    generator = MonthlyMeteorologySupport(2026, 5, output_dir=tmp_path)
    monkeypatch.setattr(
        generator,
        "map_sources",
        {
            "temperature_anomaly": "https://weather.cma.cn/example/temp.png",
            "precipitation_anomaly_percent": "https://weather.cma.cn/example/precip.jpg",
        },
    )

    def fake_download(url, output_path):
        output_path.write_bytes(f"fake image from {url}".encode("utf-8"))
        return True, None

    monkeypatch.setattr(generator, "_download_image", fake_download)

    manifest_path = generator.generate()

    temp_image = tmp_path / "temperature_anomaly_map_202605.png"
    precip_image = tmp_path / "precipitation_anomaly_percent_map_202605.jpg"
    assert temp_image.exists()
    assert precip_image.exists()

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["maps"]["temperature_anomaly"]["available"] is True
    assert manifest["maps"]["temperature_anomaly"]["file"] == temp_image.name
    assert manifest["maps"]["precipitation_anomaly_percent"]["available"] is True
    assert manifest["maps"]["precipitation_anomaly_percent"]["file"] == precip_image.name


def test_meteorology_support_resolves_first_image_from_nmc_page(tmp_path, monkeypatch):
    generator = MonthlyMeteorologySupport(2026, 5, output_dir=tmp_path)
    html = '''
    <img id="imgpath" data-img="https://image.nmc.cn/product/2026/06/05/WEAP/medium/temp.JPG?v=1">
    '''
    monkeypatch.setattr(generator, "_fetch_page", lambda url: html)

    resolved = generator._resolve_source_url_from_page("https://www.nmc.cn/example.html")

    assert resolved == "https://image.nmc.cn/product/2026/06/05/WEAP/medium/temp.JPG?v=1"


def test_meteorology_support_resolves_mobile_precipitation_data_src(tmp_path, monkeypatch):
    generator = MonthlyMeteorologySupport(2026, 5, output_dir=tmp_path)
    html = '''
    <img src="https://image.nmc.cn/assets/site/mobile/img/nmc_logo_white.png">
    <img data-src="https://image.nmc.cn/product/2026/06/06/GISP/medium/SEVP_NMC_GISP_S99_ERDP30_ACHN_L88_PB_20260606000000000.jpg?v=1">
    <img data-src="https://image.nmc.cn/product/2026/06/07/GISP/medium/SEVP_NMC_GISP_S99_ERDP30_ACHN_L88_PB_20260607000000000.jpg?v=1">
    '''
    monkeypatch.setattr(generator, "_fetch_page", lambda url: html)

    resolved = generator._resolve_source_url_from_page("https://m.nmc.cn/publish/observations/precipitation-30pa.html")

    assert resolved == "https://image.nmc.cn/product/2026/06/07/GISP/medium/SEVP_NMC_GISP_S99_ERDP30_ACHN_L88_PB_20260607000000000.jpg?v=1"


def test_meteorology_support_download_image_creates_parent_directory(tmp_path, monkeypatch):
    generator = MonthlyMeteorologySupport(2026, 5, output_dir=tmp_path)

    class FakeResponse:
        headers = {"content-type": "image/jpeg"}
        content = b"fake image"

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url):
            return FakeResponse()

    monkeypatch.setattr("app.fetchers.consultation.monthly_meteorology_support.httpx.Client", FakeClient)

    output_path = tmp_path / "nested" / "image.jpg"
    success, error = generator._download_image("https://image.nmc.cn/example.jpg", output_path)

    assert success is True
    assert error is None
    assert output_path.exists()


def test_meteorology_support_uses_current_official_page_on_target_product_date(tmp_path, monkeypatch):
    generator = MonthlyMeteorologySupport(2026, 5, output_dir=tmp_path, reference_date=date(2026, 6, 1))
    monkeypatch.setattr(
        generator,
        "map_sources",
        {"precipitation_anomaly_percent": "https://weather.cma.cn/example/precip.jpg"},
    )
    monkeypatch.setattr(
        generator,
        "_resolve_source_url_from_page",
        lambda page_url: "https://image.nmc.cn/product/2026/06/01/GISP/medium/temp.jpg",
    )

    downloaded = []

    def fake_download(url, output_path):
        downloaded.append(url)
        output_path.write_bytes(b"fake image")
        return True, None

    monkeypatch.setattr(generator, "_download_image", fake_download)

    manifest_path = generator.generate()

    expected_url = "https://image.nmc.cn/product/2026/06/01/GISP/medium/temp.jpg"
    assert expected_url in downloaded
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["target_product_date"] == "2026-06-01"
    assert manifest["maps"]["temperature_anomaly"]["source_url"] == expected_url


def test_meteorology_support_uses_current_official_page_after_target_date(tmp_path, monkeypatch):
    generator = MonthlyMeteorologySupport(2026, 5, output_dir=tmp_path, reference_date=date(2026, 6, 7))
    monkeypatch.setattr(
        generator,
        "_resolve_source_url_from_page",
        lambda page_url: "https://image.nmc.cn/product/2026/06/07/GISP/medium/current.jpg",
    )

    downloaded = []

    def fake_download(url, output_path):
        downloaded.append(url)
        output_path.write_bytes(b"fake image")
        return True, None

    monkeypatch.setattr(generator, "_download_image", fake_download)

    manifest_path = generator.generate()

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["maps"]["temperature_anomaly"]["available"] is True
    assert manifest["maps"]["temperature_anomaly"]["source_url"] == downloaded[0]
    assert manifest["maps"]["temperature_anomaly"]["file"] == "temperature_anomaly_map_202605.jpg"
