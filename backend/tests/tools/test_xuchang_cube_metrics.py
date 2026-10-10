"""Tests for the xuchang_cube_metrics semantic-layer query tool."""

import base64
import hashlib
import hmac
import json
from types import SimpleNamespace

import pytest

from app.tools.query.xuchang_cube_metrics.tool import (
    CATALOG,
    XuchangCubeMetricsTool,
    _make_token,
)


def test_catalog_covers_all_seven_cubes_with_chinese_titles():
    assert set(CATALOG) == {
        "SsfbCityHour", "SsfbCityDay", "SsfbCityRanking",
        "SsfbSiteHour", "SsfbSiteDay",
        "TownHour", "TownDay",
    }
    for cube, parts in CATALOG.items():
        assert parts["measures"], cube
        assert parts["dimensions"], cube
        for member in parts["measures"] + parts["dimensions"]:
            assert member["title"], (cube, member["name"])


def test_make_token_is_signed_hs256():
    secret = "unit-test-secret"
    token = _make_token(secret)
    header_b64, payload_b64, sig_b64 = token.split(".")

    def b64decode(data):
        return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))

    assert json.loads(b64decode(header_b64))["alg"] == "HS256"
    payload = json.loads(b64decode(payload_b64))
    import time as _time

    assert 0 < payload["exp"] - _time.time() <= 300
    expected = hmac.new(
        secret.encode(), f"{header_b64}.{payload_b64}".encode(), hashlib.sha256
    ).digest()
    assert b64decode(sig_b64) == expected


def test_validate_rejects_cross_cube_query():
    tool = XuchangCubeMetricsTool()
    cube, err = tool._validate(
        measures=["SsfbCityRanking.rankPm25"],
        dimensions=["SsfbCityDay.city"],
        time_dimension=None,
        filters=[],
    )
    assert cube is None
    assert "跨了" in err


def test_validate_rejects_unknown_members_and_operators():
    tool = XuchangCubeMetricsTool()
    _, err = tool._validate(["SsfbCityRanking.nonsense"], [], None, [])
    assert "未知度量" in err
    _, err = tool._validate(
        ["SsfbCityRanking.rankPm25"], [], None,
        [{"member": "SsfbCityRanking.period", "operator": "regex", "values": ["x"]}],
    )
    assert "不支持的过滤操作符" in err


def test_validate_accepts_single_cube_query():
    tool = XuchangCubeMetricsTool()
    cube, err = tool._validate(
        measures=["SsfbCityRanking.rankPm25", "SsfbCityRanking.avgPm25"],
        dimensions=["SsfbCityRanking.city"],
        time_dimension=None,
        filters=[
            {"member": "SsfbCityRanking.periodType", "operator": "equals",
             "values": ["monthly"]},
        ],
    )
    assert cube == "SsfbCityRanking"
    assert err is None


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_execute_returns_rows(monkeypatch):
    captured = {}

    class _FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["query"] = json["query"]
            captured["auth"] = headers["Authorization"]
            return _FakeResponse({
                "data": [
                    {"SsfbCityRanking.city": "许昌市",
                     "SsfbCityRanking.rankPm25": {"value": 7},
                     "SsfbCityRanking.avgPm25": {"value": 3.42}},
                ],
            })

    monkeypatch.setattr(
        "app.tools.query.xuchang_cube_metrics.tool.httpx.AsyncClient", _FakeClient
    )
    monkeypatch.setenv("CUBE_API_SECRET", "unit-secret")
    monkeypatch.setenv("CUBE_API_URL", "http://127.0.0.1:4610/cubejs-api/v1")

    tool = XuchangCubeMetricsTool()
    result = await tool.execute(
        measures=["SsfbCityRanking.rankPm25", "SsfbCityRanking.avgPm25"],
        dimensions=["SsfbCityRanking.city"],
        filters=[
            {"member": "SsfbCityRanking.periodType", "operator": "equals",
             "values": ["monthly"]},
            {"member": "SsfbCityRanking.period", "operator": "equals",
             "values": ["2026-10"]},
        ],
        order={"SsfbCityRanking.rankPm25": "asc"},
    )

    assert result["success"] is True
    assert result["data"][0]["SsfbCityRanking.rankPm25"] == 7
    # dict 包装值被解包为标量
    assert result["data"][0]["SsfbCityRanking.avgPm25"] == 3.42
    assert "1 行" in result["summary"]
    assert captured["query"]["limit"] == 50
    assert captured["auth"].count(".") == 2


@pytest.mark.asyncio
async def test_execute_reports_semantic_layer_error(monkeypatch):
    class _FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json=None, headers=None):
            return _FakeResponse(
                {"error": "boom"}, status_code=500
            )

    monkeypatch.setattr(
        "app.tools.query.xuchang_cube_metrics.tool.httpx.AsyncClient", _FakeClient
    )
    monkeypatch.setenv("CUBE_API_SECRET", "unit-secret")

    tool = XuchangCubeMetricsTool()
    result = await tool.execute(measures=["SsfbCityDay.avgPm25"])

    assert result["success"] is False
    assert "语义层" in result["summary"]


@pytest.mark.asyncio
async def test_execute_requires_secret(monkeypatch):
    monkeypatch.delenv("CUBE_API_SECRET", raising=False)
    tool = XuchangCubeMetricsTool()
    result = await tool.execute(measures=["SsfbCityDay.avgPm25"])
    assert result["success"] is False
    assert "CUBE_API_SECRET" in result["summary"]
