import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.tools.system.read_data_registry.tool import ReadDataRegistryTool


def _write_records(path, count):
    start = datetime(2025, 1, 1)
    records = []
    for index in range(count):
        records.append({
            "timestamp": (start + timedelta(hours=index)).strftime("%Y-%m-%d %H:%M:%S"),
            "station_name": "test_station",
            "measurements": {
                "PM2_5": index
            }
        })
    path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")


@pytest.mark.asyncio
async def test_read_data_registry_rejects_large_detail_result(tmp_path):
    file_path = tmp_path / "dataset.json"
    _write_records(file_path, ReadDataRegistryTool.DEFAULT_MAX_RECORDS + 1)

    tool = ReadDataRegistryTool()
    result = await tool._load_from_data_registry(
        file_path=file_path,
        data_id="dataset",
        list_fields=False,
        time_range="2025-01-01 00:00:00,2025-12-31 23:59:59",
        fields=None,
        jq_filter=None,
    )

    assert result["success"] is False
    assert result["data"]["error_type"] == "too_many_records"
    assert result["data"]["filtered_records"] == ReadDataRegistryTool.DEFAULT_MAX_RECORDS + 1
    assert "缩小 time_range" in result["summary"]
    assert "content" not in result["data"]


@pytest.mark.asyncio
async def test_read_data_registry_allows_large_aggregate_result(tmp_path, monkeypatch):
    file_path = tmp_path / "dataset.json"
    _write_records(file_path, ReadDataRegistryTool.DEFAULT_MAX_RECORDS + 50)

    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="250\n", stderr="")

    monkeypatch.setattr("app.tools.system.read_data_registry.tool.subprocess.run", fake_run)

    tool = ReadDataRegistryTool()
    result = await tool._load_from_data_registry(
        file_path=file_path,
        data_id="dataset",
        list_fields=False,
        time_range="2025-01-01 00:00:00,2025-12-31 23:59:59",
        fields=None,
        jq_filter="length",
    )

    assert result["success"] is True
    assert result["data"] == 250
    assert result["metadata"]["data_type"] == "scalar"
    assert result["metadata"]["returned_records"] == 1
