from app.external_apis.nasa_firms_client import NASAFirmsClient


def test_default_query_date_uses_utc_date(monkeypatch) -> None:
    class FixedDateTime:
        @classmethod
        def utcnow(cls):
            from datetime import datetime

            return datetime(2026, 7, 8, 16, 30)

    monkeypatch.setattr("app.external_apis.nasa_firms_client.datetime", FixedDateTime)

    assert NASAFirmsClient()._default_query_date() == "2026-07-08"


def test_parse_csv_accepts_viirs_field_names() -> None:
    csv_text = "\n".join(
        [
            "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight",
            "35.1,111.2,334.3,0.61,0.53,2026-07-08,342,N20,VIIRS,n,2.0NRT,299.19,4.37,D",
        ]
    )

    rows = NASAFirmsClient()._parse_csv(csv_text)

    assert rows == [
        {
            "latitude": 35.1,
            "longitude": 111.2,
            "brightness": 334.3,
            "scan": 0.61,
            "track": 0.53,
            "acq_date": "2026-07-08",
            "acq_time": "342",
            "satellite": "N20",
            "confidence": 70,
            "version": "2.0NRT",
            "bright_t31": 299.19,
            "frp": 4.37,
            "daynight": "D",
        }
    ]
