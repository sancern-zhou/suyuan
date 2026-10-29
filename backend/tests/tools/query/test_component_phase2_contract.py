"""超站组分二期（物种/OFP/重构/微量元素）语义字典与客户端契约守卫。

- 语义字典：117 物种目录、42 元素编码、OFP 固定 GUID（component_semantics）；
- 客户端：物种接口固定 DetectionitemType、OFP 接口固定仪器 GUID 数组 +
  mirVerEmun=1 + factorUnit、重构接口 chartAnalysisType（超站接口约定值
  必须原样上送，不允许模型或调用方改写）；
- 接入：五个新工具进入全局注册表；geo_mappings 兜底副本可解析。
"""
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from app.utils.component_semantics import (
    METAL_ELEMENT_CODES,
    OFP_DETECTION_ITEM_TYPE_GUIDS,
    OFP_FACTOR_UNIT_GUIDS,
    OFP_MIR_VERSION,
    RECONSTRUCTION_COMPONENTS,
    TRACE_ELEMENTS,
    VOC_ALL_SPECIES,
    VOC_SPECIES_GROUPS,
    metal_element_catalog_text,
    resolve_element_codes,
    strip_mark_fields,
    voc_species_catalog_text,
    voc_species_group,
)


# ----------------------------------------
# 语义字典
# ----------------------------------------


def test_voc_species_catalog_has_117_unique_species_in_seven_groups():
    assert len(VOC_SPECIES_GROUPS) == 7
    assert len(VOC_ALL_SPECIES) == 117
    assert len(set(VOC_ALL_SPECIES)) == 117
    # 特征物种抽样：类别锚点 + OFP 高活性物种
    for species in ("乙炔", "乙烯", "异戊二烯", "苯", "甲苯", "甲醛", "氟利昂-11", "二硫化碳"):
        assert species in VOC_ALL_SPECIES
        assert voc_species_group(species)
    assert voc_species_group("不存在的物种") is None
    # 目录文本可直接注入提示词
    text = voc_species_catalog_text()
    assert "烷烃" in text and "OVOCs" in text and "乙烯" in text


def test_metal_element_catalog_resolves_symbols_and_chinese_names():
    assert len(METAL_ELEMENT_CODES) == 42
    # 微量元素默认十三项全部可解析
    codes, unresolved = resolve_element_codes(TRACE_ELEMENTS)
    assert len(codes) == len(TRACE_ELEMENTS)
    assert unresolved == []
    # 符号与中文名双入口
    assert resolve_element_codes(["Pb", "铅"])[0] == ["a20044"]
    # 地壳元素编码与既有一致（a20002 铝 等）
    assert resolve_element_codes(["Al", "Si", "Ca", "Fe", "Ti", "K"])[0] == [
        "a20002", "a20119", "a20029", "a20111", "a20095", "a20068",
    ]
    # 锰编码补齐（老地壳工具中缺失）
    assert resolve_element_codes(["Mn"])[0] == ["a20055"]
    unknown_codes, unknown = resolve_element_codes(["Xx"])
    assert unknown == ["Xx"] and unknown_codes == []
    assert "Pb=铅" in metal_element_catalog_text()


def test_reconstruction_contract_and_mark_stripping():
    assert len(RECONSTRUCTION_COMPONENTS) == 9
    assert "有机物" in RECONSTRUCTION_COMPONENTS and "微量元素" in RECONSTRUCTION_COMPONENTS
    assert strip_mark_fields({"苯": 1.2, "苯_Mark": "x", "TimePoint": "t"}) == {
        "苯": 1.2, "TimePoint": "t",
    }


# ----------------------------------------
# 客户端固定参数契约（GET 数组按重复键序列化）
# ----------------------------------------


def _client_stub(monkeypatch, response_body, capture):
    from app.utils import vocs_api_client as module

    class FakeResponse:
        status_code = 200

        def json(self):
            return response_body

        def raise_for_status(self):
            return None

    def fake_get(url, **kwargs):
        capture.update(url=url)
        return FakeResponse()

    monkeypatch.setattr(module.requests, "get", fake_get)
    return module.get_voc_api_client()


def test_voc_species_client_sends_fixed_detection_item_type(monkeypatch):
    from app.utils.component_semantics import VOC_SPECIES_DETECTION_ITEM_TYPE_GUID

    capture: dict = {}
    client = _client_stub(
        monkeypatch,
        {"success": True, "result": {"dataList": []}},
        capture,
    )

    result = client.get_voc_species("1042b", "2026-01-01 00:00:00", "2026-01-02 00:00:00")

    assert result["success"] is True
    query = parse_qs(urlparse(capture["url"]).query)
    assert query["DetectionitemType"] == [VOC_SPECIES_DETECTION_ITEM_TYPE_GUID]
    # tableType / TableType 双写同值
    assert query["tableType"] == ["2"] and query["TableType"] == ["2"]
    assert query["StationCodes"] == ["1042b"]


@pytest.mark.parametrize("method", ["get_ofp_timeseries", "get_ofp_top10"])
def test_ofp_clients_send_fixed_guids_mir_and_factor_unit(monkeypatch, method):
    capture: dict = {}
    client = _client_stub(
        monkeypatch,
        {"success": True, "result": [{"TimePoint": []}, {}]},
        capture,
    )

    result = getattr(client, method)("1042b", "2026-01-01 00:00:00", "2026-01-02 00:00:00")

    assert result["success"] is True
    query = parse_qs(urlparse(capture["url"]).query, keep_blank_values=True)
    # 7 个仪器 GUID 原样重复键上送、顺序保持
    assert query["DetectionitemType"] == OFP_DETECTION_ITEM_TYPE_GUIDS
    assert len(query["DetectionitemType"]) == 7
    # MIR 版本与因子单位为约定固定值（factorUnit 前两位为空串占位）
    assert query["mirVerEmun"] == [str(OFP_MIR_VERSION)]
    assert query["factorUnit"] == OFP_FACTOR_UNIT_GUIDS
    # tableType / TableType 双写同值
    assert query["tableType"] == ["1"] and query["TableType"] == ["1"]


def test_pm25_recovery_client_payload_contract(monkeypatch):
    from app.utils import particulate_api_client as module

    capture: dict = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"success": True, "result": {}}

        def raise_for_status(self):
            return None

    def fake_post(url, **kwargs):
        capture.update(url=url, payload=kwargs.get("json"))
        return FakeResponse()

    monkeypatch.setattr(module.requests, "post", fake_post)
    client = module.get_particulate_api_client()

    result = client.get_pm25_recovery(
        station="新兴",
        code="1042b",
        start_time="2026-01-01 00:00:00",
        end_time="2026-01-02 00:00:00",
        table_type=1,
        data_type=0,
    )

    assert result["success"] is True
    assert capture["url"].endswith("/api/supproduct/supoperation/ComponentPm25/GetComponentPm25RecoveryAnalysis")
    payload = capture["payload"]
    assert payload["StationCodes"] == ["1042b"]
    assert payload["tableType"] == 1
    assert payload["dataType"] == 0
    # 图表分析类型为接口必填约定值
    assert payload["chartAnalysisType"] == 0
    assert payload["IsMark"] is False
    assert payload["StartTime"] == "2026-01-01 00:00:00"


# ----------------------------------------
# 接入：注册表与站点映射兜底副本
# ----------------------------------------


def test_phase2_component_tools_registered_globally():
    from app.tools import create_global_tool_registry

    registry = create_global_tool_registry()
    names = set(registry.list_tools())
    for tool_name in (
        "get_vocs_species",
        "get_vocs_ofp",
        "get_ofp_top10",
        "get_pm25_recovery",
        "get_pm25_trace",
    ):
        assert tool_name in names, tool_name


def test_committed_geo_mappings_fallback_parses_to_38_stations():
    config_path = Path(__file__).resolve().parents[3] / "config" / "geo_mappings.json"
    data = json.loads(config_path.read_text(encoding="utf-8"))
    stations = data["stations"]
    assert len(stations) == 38
    assert stations["鹤山花果山"] == "1001b"
    assert stations["新兴"] == "1042b"
    assert all(code.endswith("b") for code in stations.values())
