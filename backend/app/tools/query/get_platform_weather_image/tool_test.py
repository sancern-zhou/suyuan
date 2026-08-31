import base64
from pathlib import Path

import pytest

from app.services.data_registry import DataRegistryService
from app.services.image_cache import ImageCache
from app.tools.query.get_platform_weather_image import tool as weather_image_module
from app.tools.query.get_platform_weather_image.tool import (
    GetPlatformWeatherImageTool,
    build_weather_image_url,
)


def test_builds_exact_urls_from_known_examples():
    assert (
        build_weather_image_url(
            "forecast_trajectory",
            date="20260610",
            time="广州",
        )
        == "http://10.10.10.112:8313/1013/20260610/10128010120260610.gif"
    )
    assert (
        build_weather_image_url(
            "forecast_trajectory",
            date="20260610",
            time="东莞",
        )
        == "http://10.10.10.112:8313/1013/20260610/10128160120260610.gif"
    )
    assert (
        build_weather_image_url(
            "forecast_trajectory",
            date="20260610",
            time="南昌",
        )
        == "http://10.10.10.112:8313/1013/20260610/10124010120260610.gif"
    )
    assert (
        build_weather_image_url(
            "forecast_trajectory",
            date="20260610",
            time="101281701",
        )
        == "http://10.10.10.112:8313/1013/20260610/10128170120260610.gif"
    )
    assert (
        build_weather_image_url(
            "backward_trajectory",
            date="20260610",
            time="南昌,20260608",
        )
        == "http://10.10.10.112:8313/1014/20260610/10124010120260608.gif"
    )
    assert (
        build_weather_image_url(
            "backward_trajectory",
            date="20260610",
            time="101240101,2026-06-08",
        )
        == "http://10.10.10.112:8313/1014/20260610/10124010120260608.gif"
    )
    assert (
        build_weather_image_url(
            "national_precip_forecast",
            date="20260609",
            time="024",
        )
        == "http://10.10.10.112:8313/1012/20260609/--%2B--%2B--%2B--%2B024%2B--%2B--.png"
    )
    assert (
        build_weather_image_url(
            "hourly_precip_forecast",
            date="20260609",
            time="06",
        )
        == "http://10.10.10.112:8313/1023/20260609/00%2B--%2B--%2B--%2B06%2B--%2B--.png"
    )
    assert (
        build_weather_image_url(
            "visibility",
            date="20260609",
            time="15",
        )
        == "http://10.10.10.112:8313/1034/20260609/--%2B--%2B--%2B--%2B--%2B15%2B00.png"
    )
    assert (
        build_weather_image_url(
            "radar_mosaic",
            date="20260609",
            time="15:12",
        )
        == "http://10.10.10.112:8313/1041/20260609/--%2B--%2BACHN%2B--%2B--%2B15%2B12.png"
    )
    assert (
        build_weather_image_url(
            "rainfall_24h",
            date="20260609",
            time="06",
        )
        == "http://10.10.10.112:8313/1051/20260609/--%2B--%2B--%2B--%2B--%2B06%2B--.png"
    )
    assert (
        build_weather_image_url(
            "hourly_wind_field",
            date="20260609",
            time="07",
        )
        == "http://10.10.10.112:8313/1052/20260609/--%2B--%2B--%2B--%2B--%2B07%2B--.png"
    )
    assert (
        build_weather_image_url(
            "radar_composite_reflectivity",
            date="20260609",
            time="001",
        )
        == "http://10.10.10.112:8313/2111/20260609/00%2B--%2BEBREF_ACHN_LN0_PB%2B--%2B001%2B--%2B--.png"
    )
    assert (
        build_weather_image_url(
            "precipitable_water",
            date="20260609",
            time="000",
        )
        == "http://10.10.10.112:8313/2111/20260609/00%2B--%2BERFA_ACHN_L00_PB%2B--%2B000%2B--%2B--.png"
    )
    assert (
        build_weather_image_url(
            "max_10m_wind_speed_24h",
            date="20260609",
            time="024",
        )
        == "http://10.10.10.112:8313/2111/20260609/00%2B--%2BEDSMAX_ACHN_L10M_P9%2B--%2B024%2B--%2B--.png"
    )
    assert (
        build_weather_image_url(
            "precip_forecast_24h",
            date="20260609",
            time="024",
        )
        == "http://10.10.10.112:8313/2111/20260609/00%2B--%2BER24_ACHN_L88_PB%2B--%2B024%2B--%2B--.png"
    )
    assert (
        build_weather_image_url(
            "grapes_gfs_radar_reflectivity",
            date="20260609",
            time="003",
        )
        == "http://10.10.10.112:8313/2112/20260609/00%2B--%2B--%2B--%2B003%2B--%2B--.png"
    )
    assert (
        build_weather_image_url(
            "national_max_temperature_forecast",
            date="20260609",
            time="024",
        )
        == "http://10.10.10.112:8313/2114/20260609/--%2B--%2BETM%2B--%2B024%2B--%2B--.png"
    )
    assert (
        build_weather_image_url(
            "national_min_temperature_forecast",
            date="20260609",
            time="024",
        )
        == "http://10.10.10.112:8313/2114/20260609/--%2B--%2BETN%2B--%2B024%2B--%2B--.png"
    )


def test_rejects_times_outside_product_schedule():
    with pytest.raises(ValueError, match="未知预测轨迹图城市"):
        build_weather_image_url(
            "forecast_trajectory",
            date="20260610",
            time="不存在",
        )

    with pytest.raises(ValueError, match="后向轨迹图 time 应为"):
        build_weather_image_url(
            "backward_trajectory",
            date="20260610",
            time="南昌",
        )

    with pytest.raises(ValueError, match="06, 12, 18, 24"):
        build_weather_image_url(
            "hourly_precip_forecast",
            date="20260609",
            time="05",
        )

    with pytest.raises(ValueError, match="6分钟"):
        build_weather_image_url(
            "radar_mosaic",
            date="20260609",
            time="15:13",
        )

    with pytest.raises(ValueError, match="不能晚于 07"):
        build_weather_image_url(
            "hourly_wind_field",
            date="20260609",
            time="08",
        )

    with pytest.raises(ValueError, match="001 到 072"):
        build_weather_image_url(
            "radar_composite_reflectivity",
            date="20260609",
            time="073",
        )

    with pytest.raises(ValueError, match="000 到 072"):
        build_weather_image_url(
            "precipitable_water",
            date="20260609",
            time="073",
        )

    with pytest.raises(ValueError, match="024, 048, 072"):
        build_weather_image_url(
            "max_10m_wind_speed_24h",
            date="20260609",
            time="012",
        )

    with pytest.raises(ValueError, match="024 到 072"):
        build_weather_image_url(
            "precip_forecast_24h",
            date="20260609",
            time="023",
        )

    with pytest.raises(ValueError, match="003 到 240.*3小时"):
        build_weather_image_url(
            "grapes_gfs_radar_reflectivity",
            date="20260609",
            time="004",
        )

    with pytest.raises(ValueError, match="024 到 240.*24小时"):
        build_weather_image_url(
            "national_max_temperature_forecast",
            date="20260609",
            time="049",
        )


def test_schema_points_to_tool_specific_guide_name():
    schema = GetPlatformWeatherImageTool().get_function_schema()

    description = schema["description"]
    assert "GET_PLATFORM_WEATHER_IMAGE_GUIDE.md" in description
    assert "TOOL_SKILL.md" not in description
    properties = schema["parameters"]["properties"]
    assert set(properties) == {"product", "date", "time", "download"}
    assert schema["parameters"]["required"] == ["product", "time"]
    assert len(__import__("json").dumps(schema, ensure_ascii=False, separators=(",", ":"))) < 650


@pytest.mark.asyncio
async def test_execute_accepts_unified_time_parameter_without_type_specific_fields(tmp_path):
    tool = GetPlatformWeatherImageTool(output_root=tmp_path)

    result = await tool.execute(
        product="radar_mosaic",
        date="20260609",
        time="15:12",
        download=False,
    )

    assert result["success"] is True
    assert result["data"]["image_url"] is None
    assert result["data"]["image_id"] is None
    assert result["data"]["local_path"] == str(tmp_path / "radar_mosaic" / "20260609" / "1512.png")


@pytest.mark.asyncio
async def test_execute_downloads_image_to_fixed_product_directory(tmp_path):
    class FakeResponse:
        status_code = 200
        content = b"png-bytes"
        headers = {"content-type": "image/png"}

        def raise_for_status(self):
            return None

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url):
            self.url = url
            return FakeResponse()

    tool = GetPlatformWeatherImageTool(output_root=tmp_path, client_factory=lambda **kwargs: FakeClient())

    result = await tool.execute(
        product="national_precip_forecast",
        date="20260609",
        time="024",
    )

    assert result["success"] is True
    assert result["data"]["image_url"] == "/api/image/weather_platform_national_precip_forecast_20260609_024"
    assert result["data"]["image_id"] == "weather_platform_national_precip_forecast_20260609_024"
    assert result["data"]["source_url"] == (
        "http://10.10.10.112:8313/1012/20260609/--%2B--%2B--%2B--%2B024%2B--%2B--.png"
    )
    assert result["visuals"][0]["type"] == "image"
    assert result["visuals"][0]["image_url"] == result["data"]["image_url"]
    local_path = Path(result["data"]["local_path"])
    assert local_path == tmp_path / "national_precip_forecast" / "20260609" / "024.png"
    assert local_path.read_bytes() == b"png-bytes"
    assert result["refs"]["files"] == [
        {
            "path": str(local_path),
            "type": "image",
            "format": "png",
            "usage": "tool_input",
            "preferred_for": ["read_file"],
        }
    ]
    assert result["refs"]["visuals"] == [
        {
            "id": "weather_platform_national_precip_forecast_20260609_024",
            "type": "image",
            "title": "20260609 全国降水量预报图 024",
            "image_url": "/api/image/weather_platform_national_precip_forecast_20260609_024",
            "local_path": str(local_path),
            "tool_path": str(local_path),
        }
    ]
    assert result["refs"]["urls"] == [
        {
            "url": "/api/image/weather_platform_national_precip_forecast_20260609_024",
            "usage": "display",
            "source": "image_url",
        },
        {
            "url": "http://10.10.10.112:8313/1012/20260609/--%2B--%2B--%2B--%2B024%2B--%2B--.png",
            "usage": "source",
            "source": "source_url",
        },
    ]
    assert result["llm_resume"]["tool_hint"] == (
        f"Use read_file(path='{local_path}', as_multimodal_attachment=true) "
        "to inspect this image."
    )


@pytest.mark.asyncio
async def test_execute_returns_full_url_and_local_path_when_download_disabled(tmp_path):
    tool = GetPlatformWeatherImageTool(output_root=tmp_path)

    result = await tool.execute(
        product="visibility",
        date="20260609",
        time="15",
        download=False,
    )

    assert result["success"] is True
    assert result["data"]["image_url"] is None
    assert result["data"]["image_id"] is None
    assert result["data"]["local_path"] == str(tmp_path / "visibility" / "20260609" / "15.png")
    assert result["data"]["downloaded"] is False
    assert result["data"]["visuals"] == []
    assert result["refs"]["files"][0]["path"] == str(tmp_path / "visibility" / "20260609" / "15.png")
    assert result["refs"]["urls"] == [
        {
            "url": "http://10.10.10.112:8313/1034/20260609/--%2B--%2B--%2B--%2B--%2B15%2B00.png",
            "usage": "source",
            "source": "source_url",
        }
    ]


@pytest.mark.asyncio
async def test_execute_forecast_trajectory_uses_city_name_and_gif_extension(tmp_path):
    tool = GetPlatformWeatherImageTool(output_root=tmp_path)

    result = await tool.execute(
        product="forecast_trajectory",
        date="20260610",
        time="广州",
        download=False,
    )

    assert result["success"] is True
    assert result["data"]["product_name"] == "城市预测轨迹图"
    assert result["data"]["time_key"] == "101280101"
    assert result["data"]["local_path"] == str(tmp_path / "forecast_trajectory" / "20260610" / "101280101.gif")


@pytest.mark.asyncio
async def test_execute_backward_trajectory_uses_city_and_trajectory_date(tmp_path):
    tool = GetPlatformWeatherImageTool(output_root=tmp_path)

    result = await tool.execute(
        product="backward_trajectory",
        date="20260610",
        time="南昌,20260608",
        download=False,
    )

    assert result["success"] is True
    assert result["data"]["product_name"] == "城市后向轨迹图"
    assert result["data"]["time_key"] == "101240101_20260608"
    assert result["data"]["local_path"] == str(
        tmp_path / "backward_trajectory" / "20260610" / "101240101_20260608.gif"
    )


@pytest.mark.asyncio
async def test_execute_reads_latest_nmc_surface_weather_chart_from_registry(tmp_path, monkeypatch):
    registry = DataRegistryService(base_dir=str(tmp_path / "registry"))
    image_cache = ImageCache(cache_dir=str(tmp_path / "images"))
    Path(image_cache.cache_dir).mkdir(parents=True, exist_ok=True)
    source_path = tmp_path / "weather" / "nmc_weather_chart_20260808120000.jpg"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"jpeg-bytes")
    cached = image_cache.save(base64.b64encode(b"jpeg-bytes").decode(), chart_id="nmc_chart_test")
    entry = registry.register_payload(
        schema="nmc_weather_chart",
        version="v1",
        payload={
            "product": "中国地面基本天气分析",
            "display_time": "08/08 20:00",
            "image_url": "https://image.nmc.cn/product/chart.JPG",
            "local_path": str(source_path),
            "image": cached,
        },
    )
    monkeypatch.setattr(weather_image_module, "data_registry", registry)

    result = await GetPlatformWeatherImageTool(output_root=tmp_path).execute(
        product="nmc_surface_weather_chart",
        time="latest",
    )

    assert result["success"] is True
    assert result["data"]["product_name"] == "中国地面天气形势图"
    assert result["data"]["data_id"] == entry.data_id
    assert result["data"]["image_url"] == "/api/image/nmc_chart_test"
    assert result["visuals"][0]["type"] == "image"
    assert result["refs"]["data"][0]["data_id"] == entry.data_id


def _register_nmc_chart(
    registry: DataRegistryService,
    image_cache: ImageCache,
    tmp_path: Path,
    *,
    timestamp: str,
    display_time: str,
):
    source_path = tmp_path / "weather" / f"nmc_weather_chart_{timestamp}.jpg"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"jpeg-bytes")
    cached = image_cache.save(
        base64.b64encode(b"jpeg-bytes").decode(), chart_id=f"nmc_chart_{timestamp}"
    )
    return registry.register_payload(
        schema="nmc_weather_chart",
        version="v1",
        payload={
            "product": "中国地面基本天气分析",
            "display_time": display_time,
            "image_url": (
                "https://image.nmc.cn/product/2026/08/31/WESA/"
                f"SEVP_NMC_WESA_SFER_EGH_ACWP_L00_P9_{timestamp}000.JPG?v=1"
            ),
            "local_path": str(source_path),
            "image": cached,
        },
    )


def _setup_nmc_registry(tmp_path, monkeypatch):
    registry = DataRegistryService(base_dir=str(tmp_path / "registry"))
    image_cache = ImageCache(cache_dir=str(tmp_path / "images"))
    Path(image_cache.cache_dir).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(weather_image_module, "data_registry", registry)
    return registry, image_cache


@pytest.mark.asyncio
async def test_execute_nmc_chart_date_with_latest_returns_requested_date_not_newest(tmp_path, monkeypatch):
    registry, image_cache = _setup_nmc_registry(tmp_path, monkeypatch)
    entry = _register_nmc_chart(
        registry, image_cache, tmp_path, timestamp="20260808120000", display_time="08/08 20:00"
    )
    _register_nmc_chart(
        registry, image_cache, tmp_path, timestamp="20260831120000", display_time="08/31 20:00"
    )

    result = await GetPlatformWeatherImageTool(output_root=tmp_path).execute(
        product="nmc_surface_weather_chart",
        date="2026-08-08",
        time="latest",
    )

    assert result["success"] is True
    assert result["data"]["data_id"] == entry.data_id
    assert result["data"]["time_key"] == "08/08 20:00"


@pytest.mark.asyncio
async def test_execute_nmc_chart_uncached_date_returns_not_found_with_hint(tmp_path, monkeypatch):
    registry, image_cache = _setup_nmc_registry(tmp_path, monkeypatch)
    _register_nmc_chart(
        registry, image_cache, tmp_path, timestamp="20260831120000", display_time="08/31 20:00"
    )

    result = await GetPlatformWeatherImageTool(output_root=tmp_path).execute(
        product="nmc_surface_weather_chart",
        date="20260719",
        time="latest",
    )

    assert result["success"] is False
    assert result["status"] == "not_found"
    assert "20260719" in result["error"]
    assert "20260831" in result["error"]
    assert "无法回填" in result["summary"]


@pytest.mark.asyncio
async def test_execute_nmc_chart_specific_time_still_filters_within_date(tmp_path, monkeypatch):
    registry, image_cache = _setup_nmc_registry(tmp_path, monkeypatch)
    _register_nmc_chart(
        registry, image_cache, tmp_path, timestamp="20260808120000", display_time="08/08 20:00"
    )

    matched = await GetPlatformWeatherImageTool(output_root=tmp_path).execute(
        product="nmc_surface_weather_chart",
        date="20260808",
        time="20:00",
    )
    assert matched["success"] is True

    missed = await GetPlatformWeatherImageTool(output_root=tmp_path).execute(
        product="nmc_surface_weather_chart",
        date="20260808",
        time="08:00",
    )
    assert missed["success"] is False
    assert missed["status"] == "not_found"
