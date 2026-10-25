"""组分站审核取数分支（sup_rf_common 接入）的纯函数单测。"""

from app.services.ops_work_order_audit_local import (
    _SUP_FORM_UPPER_MAP,
    _uppercase_sup_form_row,
    is_sup_station_request,
)
from app.services.ops_work_order_audit_engine import (
    SUP_AUDIT_ORDER_TYPES,
    SUP_RF_COMMON_TABLE,
    effective_audit_order_types,
)


def test_sup_request_detection():
    assert is_sup_station_request(["SupCheck"]) is True
    assert is_sup_station_request(["SupCheck", "SupSECCheck"]) is True
    assert is_sup_station_request(["SupSECCheck"]) is True
    # 主网类型 / 混合 / 空：不走组分站分支
    assert is_sup_station_request(["Check"]) is False
    assert is_sup_station_request(["Check", "SupCheck"]) is False
    assert is_sup_station_request([]) is False
    assert is_sup_station_request(None) is False


def test_sup_types_still_excluded_on_main_network_path():
    # 主网请求里误传 SupCheck 仍被既有口径剔除；组分站请求不走该过滤（fetcher sup_mode）。
    assert effective_audit_order_types(["Check", "SupCheck"]) == ["Check"]
    assert {"SupCheck", "SupSECCheck"} == set(SUP_AUDIT_ORDER_TYPES)


def test_sup_form_row_uppercases_header_fields():
    row = {
        "id": 1,
        "workingordercode": "SUP2610200001",
        "stationid": "ST001",
        "stationcode": "4401A",
        "checkdate": "2026-10-20 09:30:00",
        "devicecode": "Y11448",
        "devicebrand": "THERMO",
        "devicemodel": "48i",
        "prepareuserid": "u1",
        "reviewuserid": None,
        "audituserid": None,
        "some_question_col": "值",
    }
    upper = _uppercase_sup_form_row(row)
    assert upper["WORKINGORDERCODE"] == "SUP2610200001"
    assert upper["STATIONID"] == "ST001"
    assert upper["STATIONCODE"] == "4401A"
    assert upper["CHECKDATE"] == "2026-10-20 09:30:00"
    assert upper["DEVICECODE"] == "Y11448"
    assert upper["DEVICEBRAND"] == "THERMO"
    assert upper["DEVICEMODEL"] == "48i"
    assert upper["PREPAREUSERID"] == "u1"
    # 空值不生成大写键（规则按"字段不存在/为空"口径统一处理）
    assert "REVIEWUSERID" not in upper
    # 题目项列保留小写原样
    assert upper["some_question_col"] == "值"
    # 原小写键保留，便于二期列语义普查对照
    assert upper["workingordercode"] == "SUP2610200001"


def test_sup_header_map_covers_audit_flow_fields():
    for low, upper in [
        ("prepareuserid", "PREPAREUSERID"),
        ("reviewuserid", "REVIEWUSERID"),
        ("audituserid", "AUDITUSERID"),
        ("checkdate", "CHECKDATE"),
        ("devicecode", "DEVICECODE"),
        ("stationcode", "STATIONCODE"),
    ]:
        assert _SUP_FORM_UPPER_MAP.get(low) == upper
    assert SUP_RF_COMMON_TABLE == "SUP_RF_COMMON"
