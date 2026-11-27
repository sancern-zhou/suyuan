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


def test_catalog_covers_all_cube_schema_names_with_chinese_titles():
    import re
    from pathlib import Path

    schema_root = Path(__file__).resolve().parents[3] / "projects/xuchang/data-ops/cube/schema"
    schema_cubes = set()
    for path in schema_root.glob("*.js"):
        schema_cubes.update(re.findall(r"cube\(`([^`]+)`", path.read_text(encoding="utf-8")))
    assert set(CATALOG) == schema_cubes
    for cube, parts in CATALOG.items():
        assert parts["measures"], cube
        assert parts["dimensions"], cube
        for member in parts["measures"] + parts["dimensions"]:
            assert member["title"], (cube, member["name"])


def test_generated_artifact_is_in_sync_with_schemas_and_registry():
    """防漂移：提交的 catalog.generated.json 必须等于生成器当前输出。"""
    import importlib.util
    from pathlib import Path

    generator_path = (
        Path(__file__).resolve().parents[3]
        / "projects/xuchang/data-ops/semantic/gen_semantic_artifacts.py"
    )
    spec = importlib.util.spec_from_file_location("gen_xuchang_catalog", generator_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    artifact_path = Path(__file__).resolve().parents[2] / "app/tools/query/xuchang_cube_metrics/catalog.generated.json"
    committed = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert committed == module.build()


def test_tool_description_is_slim_and_routes_to_describe():
    """描述只留路由与红线（预算帽 2500），成员目录不内联。"""
    import json as _json

    schema = XuchangCubeMetricsTool().get_function_schema()
    size = len(_json.dumps(schema, ensure_ascii=False))
    assert size < 2500, f"schema {size} 超历史膨胀帽"
    assert "【语义目录】" not in schema["description"]
    assert "describe_cube='cubes'" in schema["description"]


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
    _, err = tool._validate(
        ["SsfbCountyHour.avgPm25"], [], "SsfbCountyHour.dataTime",
        [{"member": "SsfbCountyHour.dataTime", "operator": "between", "values": ["2026-11-27", "2026-11-27"]}],
    )
    assert "date_range=['YYYY-MM-DD','YYYY-MM-DD']" in err
    assert "granularity='hour'" in err


def test_unknown_member_error_carries_cube_member_digest():
    """错误即目录：未知成员报错附带该 Cube 紧凑成员清单，下一轮即可修对。"""
    tool = XuchangCubeMetricsTool()
    _, err = tool._validate(["HenanPlatformAqAccumulate.nonsense"], [], None, [])
    assert "成员速查" in err
    assert "standard" in err and "periodType" in err
    _, err = tool._validate(["TotallyUnknownCube.x"], [], None, [])
    assert "成员速查" not in err


def test_related_member_hint_surfaces_official_yoy():
    """成功结果提示未查询的官方同比成员，避免手算同比。"""
    tool = XuchangCubeMetricsTool()
    hint = tool._related_member_hint("HenanPlatformAqAccumulate", ["HenanPlatformAqAccumulate.pm25"])
    assert "同比" in hint and "pm25YoY" in hint
    assert tool._related_member_hint(
        "HenanPlatformAqAccumulate", ["HenanPlatformAqAccumulate.pm25YoY"]
    ) == ""
    assert tool._related_member_hint("TownHour", ["TownHour.avgPm25"]) == ""


def test_tool_description_routes_function_zones_and_office_hour():
    description = XuchangCubeMetricsTool().function_schema["description"]
    assert "OfficeFiveMinute/OfficeHour" in description
    assert "示范区/开发区/东城区" in description
    assert "SsfbCountyHour/Day" in description


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


def test_henan_platform_requires_single_standard_and_accumulation_period():
    tool = XuchangCubeMetricsTool()
    _, err = tool._validate(["HenanPlatformAqMonth.pm25"], [], None, [])
    assert "standard" in err
    cube, err = tool._validate(
        ["HenanPlatformAqMonth.pm25", "HenanPlatformAqMonth.pm25YoY"],
        ["HenanPlatformAqMonth.region"], None,
        [{"member": "HenanPlatformAqMonth.standard", "operator": "equals", "values": ["new"]}],
    )
    assert cube == "HenanPlatformAqMonth" and err is None
    _, err = tool._validate(
        ["HenanPlatformAqAccumulate.pm25"], [], None,
        [{"member": "HenanPlatformAqAccumulate.standard", "operator": "equals", "values": ["new"]}],
    )
    assert "periodType" in err


def test_henan_platform_routing_excludes_unsupported_county_middle_platform():
    description = XuchangCubeMetricsTool().function_schema["description"]
    assert "许昌市及县市区当月MTD、当年截至某日YTD、完整月/年及官方报表缺期一律用" in description
    assert "中台airdata_calc_report_summary不支持区县市统计" in description
    assert "禁止调用或改查城市/站点结果替代" in description


@pytest.mark.asyncio
async def test_describe_with_query_params_serves_query_intent():
    """混合调用按查询执行：校验器给具体纠错，不再硬拒绝参数形态。"""
    result = await XuchangCubeMetricsTool().execute(
        describe_cube="SsfbCountyHour",
        measures=["SsfbCountyHour.pm25"],
    )
    assert result["success"] is False
    assert "未知度量" in result["summary"]
    assert "avgPm25" in result["summary"]


@pytest.mark.asyncio
async def test_describe_without_query_params_still_returns_catalog():
    result = await XuchangCubeMetricsTool().execute(describe_cube="SsfbCountyHour")
    assert result["success"] is True
    assert "成员目录" in result["summary"]


@pytest.mark.asyncio
async def test_henan_platform_describe_identifies_source_and_supplemental_role():
    result = await XuchangCubeMetricsTool().execute(describe_cube="HenanPlatformAqAccumulate")
    assert result["success"] is True
    context = result["semantic_context"]
    assert context["dataset"] == "DataCrawler.HenanPlatformAqAccumulateStat"
    assert "河南省城市空气质量大数据综合应用系统" in context["applicability"]
    assert any("standard" in item for item in context["limitations"])


def test_validate_requires_town_caliber_filter():
    tool = XuchangCubeMetricsTool()
    _, err = tool._validate(["TownHour.avgPm25"], [], None, [])
    assert "caliber" in err
    cube, err = tool._validate(
        ["TownHour.avgPm25"], [], None,
        [{"member": "TownHour.caliber", "operator": "equals", "values": ["app"]}],
    )
    assert cube == "TownHour"
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


@pytest.mark.asyncio
async def test_describe_cube_returns_semantic_definition_without_cube_call():
    result = await XuchangCubeMetricsTool().execute(describe_cube="SsfbCityRanking")
    assert result["success"] is True
    assert result["semantic_context"]["metric_definitions"]["rankPm25"]["name"]
    assert "daily" in result["semantic_context"]["applicability"]
    assert any("ProvinceMonth" in item for item in result["semantic_context"]["limitations"])
    # 瘦身后成员目录的唯一召回通道：members 清单带中文标题
    names = {m["name"] for m in result["members"]["measures"]}
    assert "SsfbCityRanking.rankPm25" in names
    assert result["members"]["dimensions"]


@pytest.mark.asyncio
async def test_describe_cube_index_lists_all_cubes():
    result = await XuchangCubeMetricsTool().execute(describe_cube="cubes")
    assert result["success"] is True
    assert len(result["cubes"]) == len(CATALOG)
    entry = next(c for c in result["cubes"] if c["cube"] == "SsfbCityRanking")
    assert entry["measures"] >= 1 and entry["applicability"]


@pytest.mark.asyncio
async def test_describe_unknown_cube_suggests_close_matches():
    result = await XuchangCubeMetricsTool().execute(describe_cube="SsfbCityRankin")
    assert result["success"] is False
    assert "SsfbCityRanking" in result["summary"]
    assert "describe_cube='cubes'" in result["summary"]
