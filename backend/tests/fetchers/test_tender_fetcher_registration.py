from app.fetchers import create_scheduler
from app.fetchers.tenders import TenderInformationFetcher
from app.fetchers.xuchang_daily_attainment_forecast import (
    O3_8H_DAILY_LIMIT,
    PM25_DAILY_LIMIT,
    XuchangDailyAttainmentForecastFetcher,
    calculate_daily_attainment_prediction,
    decide_exceedance_notifications,
)
from app.fetchers.xuchang_annual_attainment_forecast import (
    XuchangAnnualAttainmentForecastFetcher,
    calculate_annual_attainment_prediction,
)
from datetime import datetime, timedelta


def test_tender_information_fetcher_is_registered_in_scheduler_factory():
    scheduler = create_scheduler()

    assert "tender_information_fetcher" in scheduler.fetchers


def test_tender_information_fetcher_is_registered_in_lifecycle(monkeypatch):
    from app.services import lifecycle_manager

    registered = []

    class FakeScheduler:
        def register(self, fetcher):
            registered.append(fetcher.name)

        def list_fetchers(self):
            return registered

        def start(self):
            return None

    monkeypatch.setattr(lifecycle_manager, "fetcher_scheduler", FakeScheduler())

    lifecycle_manager.initialize_fetchers()

    assert TenderInformationFetcher().name in registered
    assert XuchangDailyAttainmentForecastFetcher().name in registered
    assert XuchangAnnualAttainmentForecastFetcher().name in registered


def test_xuchang_daily_attainment_prediction_uses_observations_and_forecasts():
    analysis_time = datetime(2026, 8, 3, 3)
    forecasts = [
        {
            "forecast_time": analysis_time.replace(hour=0) + timedelta(hours=hour),
            "pm25": 70,
            "o3": 170,
        }
        for hour in range(24)
    ]
    observations = [
        {
            "TimePoint": analysis_time.replace(hour=hour),
            "PM2_5": 120,
            "O3": 180,
        }
        for hour in range(4)
    ]

    result = calculate_daily_attainment_prediction(
        analysis_time=analysis_time,
        observations=observations,
        forecasts=forecasts,
    )

    assert result.observed_hours == 4
    assert result.forecast_hours == 20
    assert result.hourly_rows[0]["source"] == "observation"
    assert result.pm25_daily_average == 78.3
    assert result.o3_8h_maximum == 175.0
    assert result.exceeded_pollutants == ["PM2.5", "O3_8H"]


def test_xuchang_daily_attainment_limit_values_are_not_exceedances():
    analysis_time = datetime(2026, 8, 3, 10)
    forecasts = [
        {
            "forecast_time": analysis_time.replace(hour=0) + timedelta(hours=hour),
            "pm25": PM25_DAILY_LIMIT,
            "o3": O3_8H_DAILY_LIMIT,
        }
        for hour in range(24)
    ]

    result = calculate_daily_attainment_prediction(
        analysis_time=analysis_time,
        observations=[],
        forecasts=forecasts,
    )

    assert result.is_attainment_predicted is True
    assert result.exceeded_pollutants == []


def test_xuchang_daily_attainment_notification_is_suppressed_until_turnaround():
    result = calculate_daily_attainment_prediction(
        analysis_time=datetime(2026, 8, 3, 10),
        observations=[],
        forecasts=[
            {
                "forecast_time": datetime(2026, 8, 3) + timedelta(hours=hour),
                "pm25": 90,
                "o3": 120,
            }
            for hour in range(24)
        ],
    )
    first, state = decide_exceedance_notifications(result, {})
    repeated, _ = decide_exceedance_notifications(result, state)

    improved = calculate_daily_attainment_prediction(
        analysis_time=datetime(2026, 8, 3, 11),
        observations=[],
        forecasts=[
            {
                "forecast_time": datetime(2026, 8, 3) + timedelta(hours=hour),
                "pm25": 84,
                "o3": 120,
            }
            for hour in range(24)
        ],
    )
    turnaround, _ = decide_exceedance_notifications(improved, state)

    assert [(item.pollutant, item.reason) for item in first] == [("PM2.5", "first_exceedance")]
    assert repeated == []
    assert [(item.pollutant, item.reason) for item in turnaround] == [
        ("PM2.5", "turnaround_opportunity")
    ]


def test_xuchang_daily_attainment_fetcher_is_registered_in_scheduler_factory():
    scheduler = create_scheduler()

    assert XuchangDailyAttainmentForecastFetcher().name in scheduler.fetchers


def test_xuchang_annual_attainment_prediction_returns_three_metric_ranges():
    current_rows = [
        {"TimePoint": f"2026-08-{day:02d}", "PM2_5_24h": 35, "O3_8h_24h": o3, "AQI": aqi}
        for day, o3, aqi in ((1, 100, 80), (2, 110, 120), (3, 120, 90), (4, 130, 110))
    ]
    historical_rows_by_year = {
        2021: [
            {"TimePoint": "2021-08-05", "PM2_5_24h": 25, "O3_8h_24h": 140, "AQI": 80},
            {"TimePoint": "2021-08-06", "PM2_5_24h": 25, "O3_8h_24h": 150, "AQI": 110},
        ],
        2022: [
            {"TimePoint": "2022-08-05", "PM2_5_24h": 15, "O3_8h_24h": 140, "AQI": 80},
            {"TimePoint": "2022-08-06", "PM2_5_24h": 15, "O3_8h_24h": 160, "AQI": 110},
        ],
        2023: [
            {"TimePoint": "2023-08-05", "PM2_5_24h": 35, "O3_8h_24h": 180, "AQI": 80},
            {"TimePoint": "2023-08-06", "PM2_5_24h": 35, "O3_8h_24h": 200, "AQI": 110},
        ],
    }

    result = calculate_annual_attainment_prediction(
        calculated_at=datetime(2026, 8, 5, 6, 35),
        cutoff_date=datetime(2026, 8, 4).date(),
        current_rows=current_rows,
        historical_rows_by_year=historical_rows_by_year,
    ).to_dict()

    assert result["historical_years"] == [2021, 2022, 2023]
    assert result["prediction_ranges"]["pm25_annual_average"] == {"lower": 28.3, "upper": 35.0}
    assert result["prediction_ranges"]["o3_8h_p90"] == {"lower": 145.0, "upper": 190.0}
    assert result["prediction_ranges"]["aqi_attainment_days"] == {"lower": 3, "upper": 3}
    assert result["prediction_ranges"]["aqi_attainment_rate"] == {"lower": 50.0, "upper": 50.0}


def test_xuchang_annual_attainment_fetcher_is_registered_in_scheduler_factory():
    scheduler = create_scheduler()

    assert XuchangAnnualAttainmentForecastFetcher().name in scheduler.fetchers
    assert XuchangAnnualAttainmentForecastFetcher().schedule == "35 6 1 * *"
