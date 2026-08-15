from __future__ import annotations

from contextlib import contextmanager

from app.services import ops_work_order_audit_engine as engine


class _Cursor:
    pass


class _Connection:
    def cursor(self) -> _Cursor:
        return _Cursor()

    def rollback(self) -> None:
        return None

    def __enter__(self) -> "_Connection":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None


@contextmanager
def _fake_connection():
    yield _Connection()


def test_fetch_dataset_allows_limit_3000(monkeypatch):
    queries: list[str] = []

    def fake_rows(cursor, sql, params=None):
        queries.append(sql)
        return []

    monkeypatch.setattr(engine, "connect", _fake_connection)
    monkeypatch.setattr(engine, "rows", fake_rows)

    dataset = engine.fetch_dataset(engine.WorkOrderDatasetFilter(limit=3000))

    assert dataset["query_info"]["limit"] == 3000
    assert "SELECT TOP 3000" in queries[0]


def test_fetch_dataset_caps_limit_above_3000(monkeypatch):
    queries: list[str] = []

    def fake_rows(cursor, sql, params=None):
        queries.append(sql)
        return []

    monkeypatch.setattr(engine, "connect", _fake_connection)
    monkeypatch.setattr(engine, "rows", fake_rows)

    dataset = engine.fetch_dataset(engine.WorkOrderDatasetFilter(limit=5000))

    assert dataset["query_info"]["limit"] == 3000
    assert "SELECT TOP 3000" in queries[0]
