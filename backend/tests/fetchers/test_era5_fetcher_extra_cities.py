import pytest

from app.fetchers.weather.era5_fetcher import ERA5Fetcher, JIANGSU_CITY_POINTS


@pytest.mark.asyncio
async def test_era5_fetcher_includes_xuchang_city_point():
    fetcher = ERA5Fetcher()

    grid_points = await fetcher._get_target_grid_points()

    assert fetcher.extra_city_points["许昌市"] == {"lat": 34.036, "lon": 113.852}
    assert (34.0, 113.75) in grid_points


@pytest.mark.asyncio
async def test_era5_fetcher_includes_all_jiangsu_city_centers():
    fetcher = ERA5Fetcher()

    grid_points = await fetcher._get_target_grid_points()

    assert len(JIANGSU_CITY_POINTS) == 13
    assert set(JIANGSU_CITY_POINTS).issubset(fetcher.extra_city_points)

    for city, point in JIANGSU_CITY_POINTS.items():
        assert ERA5Fetcher._align_to_era5_grid(point["lat"], point["lon"]) in grid_points, city
