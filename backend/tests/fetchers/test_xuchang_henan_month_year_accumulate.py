import json
from datetime import datetime
from pathlib import Path

import pytest

from app.fetchers.xuchang_henan_month_year_accumulate import (
    HenanCityAccumulateStorage,
    XuchangHenanMonthYearAccumulateFetcher,
    build_db_records,
    write_json,
)


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeSession:
    headers: dict = {}

    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append(url)
        return FakeResponse(self.payloads.pop(0))


class FakeCursor:
    def __init__(self):
        self.executes = []

    def execute(self, sql, *params):
        self.executes.append((sql, params))

    def close(self):
        return None


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        return None


def _ranking_payload(city_rows):
    return {
        "flag": True,
        "count": len(city_rows),
        "start": "2026-08-01",
        "end": "2026-08-17",
        "lastStart": "2025-08",
        "days": 17,
        "lastyear": [{"city": "郑州", "zong": "6.101", "pm25": 25.1}],
        "ratio": ["0.100", "-0.050", "0.000"],
        "data": city_rows,
    }


def _city_rows():
    return [
        {
            "city": "郑州",
            "zong": "5.447",
            "pm25": 21.6,
            "pm10": 33.2,
            "so2": "4",
            "no2": "12",
            "co": 0.62,
            "o3": "153",
            "cnt": "17",
            "pmcnt": "17",
            "isprocity": "1",
            "zhzsbhl": "5.6%",
            "bhl": "0.235",
            "o3cbts": "0",
            "zdwrts": "0",
        },
        {
            "city": "许昌",
            "zong": "5.206",
            "pm25": 20.1,
            "pm10": 35.4,
            "so2": "5",
            "no2": "13",
            "co": 0.7,
            "o3": "150",
            "cnt": "17",
            "pmcnt": "17",
            "isprocity": "1",
            "zhzsbhl": "-2.1%",
            "bhl": "-0.084",
            "o3cbts": "1",
            "zdwrts": "0",
        },
        {
            "city": "市平均",
            "zong": "4.932",
            "pm25": 18.0,
            "pm10": 31.6,
            "so2": "5",
            "no2": "11",
            "co": 0.6,
            "o3": "143",
            "cnt": "17",
            "pmcnt": "17",
            "isprocity": "0",
            "zhzsbhl": "1.0%",
            "bhl": "0.020",
            "o3cbts": "0",
            "zdwrts": "0",
        },
    ]


def test_fetcher_is_registered_in_scheduler_factory(monkeypatch):
    from app.fetchers import create_scheduler
    from config.settings import settings

    monkeypatch.setattr(settings, "project_id", "xuchang")
    scheduler = create_scheduler()

    fetcher = scheduler.get_fetcher("xuchang_henan_month_year_accumulate_fetcher")

    assert fetcher is not None
    assert fetcher.schedule == "40 7 * * *"


def test_build_db_records_parses_metrics_rank_and_lastyear():
    records = build_db_records(
        kind="monthly",
        period="2026-08",
        payload=_ranking_payload(_city_rows()),
        fetched_at=datetime(2026, 8, 18, 7, 40, 0),
    )

    assert [record["city"] for record in records] == ["郑州", "许昌", "市平均"]
    zhengzhou = records[0]
    assert zhengzhou["city_rank"] == 1
    assert zhengzhou["zong"] == 5.447
    assert zhengzhou["pm25"] == 21.6
    assert zhengzhou["is_pro_city"] == 1
    assert zhengzhou["zong_change_rate"] == "5.6%"
    assert zhengzhou["change_rate"] == pytest.approx(0.235)
    assert zhengzhou["ratio"] == pytest.approx(0.100)
    assert zhengzhou["o3_exceed_days"] == 0
    assert zhengzhou["valid_days"] == 17
    assert zhengzhou["stat_start"] == "2026-08-01"
    assert json.loads(zhengzhou["lastyear_json"])["zong"] == "6.101"
    xuchang = records[1]
    assert xuchang["city_rank"] == 2
    assert xuchang["ratio"] == pytest.approx(-0.050)
    assert xuchang["lastyear_json"] is None
    average = records[2]
    assert average["is_pro_city"] == 0


def test_storage_upserts_all_rows_with_merge(monkeypatch):
    import app.fetchers.xuchang_henan_month_year_accumulate as module

    records = build_db_records(
        kind="yearly",
        period="2026",
        payload=_ranking_payload(_city_rows()),
        fetched_at=datetime(2026, 8, 18, 7, 40, 0),
    )
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    monkeypatch.setattr(module.pyodbc, "connect", lambda *args, **kwargs: connection)

    saved = HenanCityAccumulateStorage(connection_string_factory=lambda: "DRIVER=fake").save(
        records
    )

    assert saved == 3
    assert connection.committed and not connection.rolled_back
    ensure_sql, _ = cursor.executes[0]
    assert "CREATE TABLE dbo.HenanCityAccumulateRanking" in ensure_sql
    assert "UX_HenanCityAccumulateRanking_PeriodCity" in ensure_sql
    upsert_calls = cursor.executes[1:]
    assert len(upsert_calls) == 3
    merge_sql, (params,) = upsert_calls[0]
    assert "MERGE dbo.HenanCityAccumulateRanking" in merge_sql
    assert params[0] == "yearly"
    assert params[1] == "2026"
    assert params[2] == "郑州"
    assert len(params) == 46


@pytest.mark.asyncio
async def test_fetch_and_store_persists_db_and_period_files(tmp_path: Path):
    session = FakeSession([_ranking_payload(_city_rows()), _ranking_payload(_city_rows())])
    saved_batches = []
    storage = HenanCityAccumulateStorage.__new__(HenanCityAccumulateStorage)
    storage.save = lambda records: saved_batches.append(records) or len(records)
    fetcher = XuchangHenanMonthYearAccumulateFetcher(
        session=session,
        now_factory=lambda: datetime(2026, 8, 18, 7, 40, 0),
        output_root_factory=lambda: tmp_path,
        storage=storage,
    )

    result = await fetcher.fetch_and_store()

    assert result["monthly"]["saved_rows"] == 3
    assert result["monthly"]["xuchang_rank"] == 2
    assert result["monthly"]["xuchang_zong"] == "5.206"
    assert [batch[0]["period_type"] for batch in saved_batches] == ["monthly", "yearly"]
    assert saved_batches[0][1]["city"] == "许昌"
    for kind, period in (("monthly", "2026-08"), ("yearly", "2026")):
        payload = json.loads((tmp_path / kind / f"{period}.json").read_text(encoding="utf-8"))
        assert payload["kind"] == kind
        assert payload["period"] == period
        assert payload["xuchang"]["rank"] == 2
    assert "month=2026-08" in session.calls[0]
    assert "start=2026-01-01" in session.calls[1] and "end=2026-08-17" in session.calls[1]


def test_fetch_retries_then_fails_on_unusable_payload(tmp_path: Path, monkeypatch):
    import app.fetchers.xuchang_henan_month_year_accumulate as module

    class BadSession:
        headers: dict = {}

        def __init__(self):
            self.calls = 0

        def get(self, url, timeout=None):
            self.calls += 1
            return FakeResponse({"flag": False, "data": []})

    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    session = BadSession()
    fetcher = XuchangHenanMonthYearAccumulateFetcher(
        session=session,
        now_factory=lambda: datetime(2026, 8, 18, 7, 40, 0),
        output_root_factory=lambda: tmp_path,
    )

    with pytest.raises(RuntimeError, match="city ranking fetch failed"):
        fetcher._fetch({"month": "2026-08"})

    assert session.calls == module.FETCH_RETRIES


def test_write_json_is_atomic_and_overwrites(tmp_path: Path):
    target = tmp_path / "monthly" / "2026-08.json"

    write_json(target, {"a": 1})
    write_json(target, {"a": 2})

    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 2}
    assert list(tmp_path.glob("monthly/.2026-08.json.*")) == []
