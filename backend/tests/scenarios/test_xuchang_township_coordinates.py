from datetime import datetime

from app.scenarios.xuchang_daily_review import township_hourly


class _Client:
    def query_all(self, *_args, **_kwargs):
        return {
            "rows": [
                {
                    "code": "1107B",
                    "name": "长葛市和尚桥镇",
                    "timepoint": "2026-08-05 11:00:00",
                    "pm2_5": 45,
                    "pm10": 50,
                    "so2": 2,
                    "no2": 10,
                    "co": 0.7,
                    "o3": 80,
                    "aqi": 60,
                },
                {
                    "code": "unknownB",
                    "name": "未登记乡镇站",
                    "timepoint": "2026-08-05 11:00:00",
                    "pm2_5": 20,
                },
            ]
        }


def test_township_hourly_rows_attach_catalog_coordinates(monkeypatch):
    result = township_hourly.load_township_hourly_rows(
        datetime(2026, 8, 5, 11), datetime(2026, 8, 5, 12),
        client_factory=lambda: _Client(),
    )

    by_name = {row["name"]: row for row in result["rows"]}
    mapped = by_name["长葛市和尚桥镇"]
    assert mapped["lon"] == 113.8019
    assert mapped["lat"] == 34.2052
    assert mapped["coordinate_source"].endswith("township_coordinates.tsv")
    assert by_name["未登记乡镇站"]["lon"] is None
    assert result["coordinate_count"] == 1
