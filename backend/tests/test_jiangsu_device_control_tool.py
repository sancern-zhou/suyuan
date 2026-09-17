import pytest

from app.tools.jiangsu.device_control import (
    _build_command,
    _decode_state_payload,
    _device_control_state_visual,
    _flatten_state_entries,
    _gateway_form_data,
    _normalise_station_token,
    _normalise_switch_state,
    _post_qc,
    _precondition_catalog,
    _request_succeeded,
    _resolve_station,
    _requires_frontend_confirmation,
    _workspace_command,
    JiangsuDeviceControlPrepareTool,
    JiangsuDeviceControlStateTool,
    JiangsuDeviceControlExecuteTool,
    _DeviceControlClient,
)


def test_air_conditioner_temperature_command_uses_reviewed_legacy_mapping():
    payload, summary = _build_command("320100001", "air_conditioner", "cool", 24)

    assert payload == {
        "stationId": "320100001",
        "userName": "suyuan-agent",
        "devName": "空调控制",
        "rType": 23,
        "cmdIndex": 1,
        "passageway": 1,
        "operationType": 0,
        "selectIndex": 9,
    }
    assert "制冷 24℃" in summary
    assert not _requires_frontend_confirmation("air_conditioner", "cool")


def test_switch_commands_are_held_for_frontend_confirmation():
    assert _requires_frontend_confirmation("zero_air_generator", "on")
    assert _requires_frontend_confirmation("air_conditioner", "off")


def test_air_conditioner_temperature_is_bounded():
    try:
        _build_command("320100001", "air_conditioner", "heat", 31)
    except ValueError as exc:
        assert "16–30℃" in str(exc)
    else:
        raise AssertionError("temperature above 30°C must be rejected")


def test_station_token_matching_tolerates_display_suffixes():
    assert _normalise_station_token(" 鼓楼站 ") == _normalise_station_token("鼓楼")
    assert _normalise_station_token("南京市鼓楼区站") == _normalise_station_token("南京市鼓楼区")


async def test_resolve_station_prefers_explicit_unique_code():
    station = await _resolve_station(" 320100001 ", None)

    assert station == {"station_id": "320100001", "station_name": None, "resolved_by": "unique_code"}


async def test_resolve_station_requires_identifier():
    with pytest.raises(ValueError, match="station_name"):
        await _resolve_station(None, None)


def test_state_visual_exposes_station_snapshot_and_preconditions():
    station = {"station_id": "320100001", "station_name": "鼓楼", "resolved_by": "unique_code"}
    visual = _device_control_state_visual(
        station,
        {"DevDtls": [{"DevPollCode": "a34013"}], "OtherAlarmDtls": []},
        "2026-09-17T08:00:00+00:00",
    )

    assert visual["type"] == "device_control_state"
    assert visual["id"] == "device_control_320100001"
    payload = visual["data"]["device_control"]
    assert payload["station"]["station_name"] == "鼓楼"
    assert {"label": "DevDtls[0].DevPollCode", "value": "a34013"} in payload["snapshot"]
    devices = {row["key"]: row for row in payload["devices"]}
    assert devices["o3_valve"]["allowed"] == []
    assert devices["air_conditioner"]["allowed"]


def test_flatten_state_entries_caps_and_skips_empty_values():
    rows = _flatten_state_entries({"a": "1", "b": None, "c": "", "d": ["x", "y"], "e": {"deep": 2}})

    labels = [row["label"] for row in rows]
    assert "b" not in labels and "c" not in labels
    assert {"label": "d", "value": "x、y"} in rows
    assert {"label": "e.deep", "value": "2"} in rows
def test_precondition_catalog_keeps_switches_blocked():
    rows = {row["key"]: row for row in _precondition_catalog()}

    assert rows["o3_valve"]["blocked"] == ["开启", "关闭"]
    assert rows["dynamic_calibrator"]["allowed"] == []
    assert rows["air_conditioner"]["allowed"] == ["制冷/制热/除湿/送风 16–30℃"]


def test_normalise_switch_state_handles_platform_values():
    assert _normalise_switch_state("开启") == "开启"
    assert _normalise_switch_state("关闭") == "关闭"
    assert _normalise_switch_state(True) == "开启"
    assert _normalise_switch_state(False) == "关闭"
    assert _normalise_switch_state("") is None
    assert _normalise_switch_state("未知") is None


def test_precondition_catalog_merges_live_switch_state():
    rows = {row["key"]: row for row in _precondition_catalog({"o3_valve": "开启"})}

    assert rows["o3_valve"]["status"] == "开启"
    assert rows["o3_valve"]["state_key"] == "O3质控阀"
    assert rows["o3_valve"]["icon"] == "o3"
    assert rows["so2_valve"]["status"] is None
    assert rows["air_conditioner"]["status"] is None


def test_state_visual_maps_platform_chinese_state_keys():
    station = {"station_id": "320118891", "station_name": "高淳淳溪"}
    visual = _device_control_state_visual(station, {"SO2质控阀": "开启", "零气机电源": "关闭"}, "2026-09-17T08:00:00+00:00")
    devices = {row["key"]: row for row in visual["data"]["device_control"]["devices"]}

    assert devices["so2_valve"]["status"] == "开启"
    assert devices["zero_air_generator"]["status"] == "关闭"
    assert devices["dynamic_calibrator"]["status"] is None


def test_decode_state_payload_unwraps_gateway_json_string():
    decoded = _decode_state_payload({"result": '+++http://host/QCAPI {"SO2质控阀": "开启"}'})

    assert decoded == {"SO2质控阀": "开启"}


def test_decode_state_payload_unwraps_nested_envelope():
    decoded = _decode_state_payload({"Result": True, "Data": {"Data": {"SO2质控阀": "开启"}}})

    assert decoded == {"SO2质控阀": "开启"}


def test_decode_state_payload_unwraps_gateway_envelope_json():
    payload = {"success": True, "result": '+++http://host/QCAPI {"Result": true, "Data": {"O3质控阀": "关闭"}}'}

    assert _decode_state_payload(payload) == {"O3质控阀": "关闭"}


def test_request_succeeded_handles_mixed_truth_values():
    assert _request_succeeded({"Result": True}) is True
    assert _request_succeeded({"success": True}) is True
    assert _request_succeeded({"Result": "1"}) is True
    assert _request_succeeded({"Result": False}) is False
    assert _request_succeeded({"Result": "false"}) is False
    assert _request_succeeded(None) is False


def test_workspace_command_carries_panel_step():
    command = _workspace_command("prepare", station={"station_id": "s"}, command="指令")

    assert command["type"] == "device_control_workspace"
    assert command["step"] == "prepare"


async def test_prepare_blocked_switch_emits_panel_command_without_token():
    tool = JiangsuDeviceControlPrepareTool()
    result = await tool.execute(station_id="320100001", device="o3_valve", action="on")

    assert result["status"] == "frontend_confirmation_required"
    command = result["data"]["ui_command"]
    assert command["type"] == "device_control_workspace"
    assert command["step"] == "blocked"
    assert "前端人工确认" in command["reason"]
    assert "confirmation_token" not in command


def test_gateway_form_data_appends_user_and_timestamp():
    data = _gateway_form_data({"StationId": "320100001", "userName": "x"}, user_name="admin")

    assert data.startswith("StationId=320100001&")
    assert "userName=admin" in data
    assert "timestamp=" in data


async def test_state_read_prefers_air_gateway_without_local_qc_key(monkeypatch):
    calls = {}

    class FakeGatewayApi:
        def __init__(self, *, source: str):
            assert source == "air"

        async def post(self, path: str, payload: dict):
            calls["path"] = path
            calls["payload"] = payload
            return {"Result": True, "Data": {"DevDtls": [{"DevPollCode": "a34013"}]}}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi", FakeGatewayApi)
    result = await JiangsuDeviceControlStateTool().execute(station_id="320100001")

    assert result["success"] is True
    assert result["metadata"]["channel"] == "air_gateway"
    assert calls["path"].endswith("QcSvcAgent")
    assert calls["payload"]["apiMethod"] == "GetQCStateInfo"
    assert "StationId=320100001" in calls["payload"]["data"]


async def test_state_read_falls_back_to_signed_endpoint_when_gateway_fails(monkeypatch):
    class FailingGatewayApi:
        def __init__(self, *, source: str):
            pass

        async def post(self, path: str, payload: dict):
            raise ValueError("gateway unavailable")

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi", FailingGatewayApi)
    monkeypatch.setattr(_DeviceControlClient, "_validate_config", lambda self: None)

    async def fake_post(self, method: str, payload: dict):
        return {"Result": True, "Data": {}}

    monkeypatch.setattr(_DeviceControlClient, "post", fake_post)
    result, channel = await _post_qc("GetQCStateInfo", {"stationId": "320100001"})

    assert channel == "direct_signed"
    assert result["success"] if isinstance(result.get("success"), bool) else result["Result"] is True


async def test_state_read_reports_empty_qc_payload_honestly(monkeypatch):
    class EmptyGatewayApi:
        def __init__(self, *, source: str):
            pass

        async def post(self, path: str, payload: dict):
            return {"msg": None, "result": "", "state": 200, "success": True}

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi", EmptyGatewayApi)
    result = await JiangsuDeviceControlStateTool().execute(station_id="320118891")

    assert result["success"] is True
    assert result["data"]["state"] == {}
    assert result["metadata"]["has_snapshot"] is False
    assert "未返回设备状态数据" in result["summary"]


async def test_qc_call_surfaces_gateway_error_when_direct_unconfigured(monkeypatch):
    class FailingGatewayApi:
        def __init__(self, *, source: str):
            pass

        async def post(self, path: str, payload: dict):
            raise ValueError("gateway unavailable")

    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._JiangsuAuthenticatedApi", FailingGatewayApi)

    with pytest.raises(ValueError, match="gateway unavailable"):
        await _post_qc("GetQCStateInfo", {"stationId": "320100001"})


class _FakeContext:
    session_id = "session-simulation-1"


def _enable_simulation(monkeypatch, tmp_path):
    state_path = tmp_path / "device_control_simulation.json"
    monkeypatch.setenv("JIANGSU_DEVICE_CONTROL_SIMULATION", "1")
    monkeypatch.setenv("JIANGSU_DEVICE_CONTROL_SIMULATION_STATE", str(state_path))
    monkeypatch.setattr(
        _DeviceControlClient, "audit",
        staticmethod(lambda event: "backend/backend_data_registry_jiangsu_ops/device_control_audit.jsonl"),
    )
    return state_path


def test_simulation_disabled_blocks_switch(monkeypatch):
    monkeypatch.delenv("JIANGSU_DEVICE_CONTROL_SIMULATION", raising=False)

    assert _requires_frontend_confirmation("o3_valve", "on") is True


async def test_simulation_state_read_returns_seeded_states(monkeypatch, tmp_path):
    _enable_simulation(monkeypatch, tmp_path)
    result = await JiangsuDeviceControlStateTool().execute(station_id="320118891")

    assert result["success"] is True
    assert result["metadata"]["channel"] == "simulation"
    assert result["metadata"]["simulated"] is True
    assert result["data"]["state"]["O3质控阀"] == "开启"
    devices = {row["key"]: row for row in result["visuals"][0]["data"]["device_control"]["devices"]}
    assert devices["o3_valve"]["status"] == "开启"
    assert devices["dynamic_calibrator"]["status"] == "开启"
    assert result["visuals"][0]["meta"]["simulated"] is True


async def test_simulation_relaxes_switch_and_applies_command(monkeypatch, tmp_path):
    _enable_simulation(monkeypatch, tmp_path)
    context = _FakeContext()
    assert _requires_frontend_confirmation("o3_valve", "on") is False

    prepared = await JiangsuDeviceControlPrepareTool().execute(
        context=context, station_id="320115002", device="o3_valve", action="on",
    )
    assert prepared["status"] == "pending_confirmation"
    assert prepared["data"]["simulated"] is True
    assert prepared["data"]["ui_command"]["simulated"] is True

    executed = await JiangsuDeviceControlExecuteTool().execute(
        context=context, confirmation_token=prepared["confirmation_token"], confirmed=True,
    )
    assert executed["success"] is True
    assert executed["data"]["simulated"] is True
    assert executed["data"]["recheck"]["Data"]["O3质控阀"] == "开启"
    assert executed["data"]["ui_command"]["simulated"] is True

    read = await JiangsuDeviceControlStateTool().execute(station_id="320115002")
    assert read["data"]["state"]["O3质控阀"] == "开启"


async def test_simulation_records_ac_command(monkeypatch, tmp_path):
    _enable_simulation(monkeypatch, tmp_path)
    context = _FakeContext()

    prepared = await JiangsuDeviceControlPrepareTool().execute(
        context=context, station_id="320115002", device="air_conditioner", action="cool", temperature_celsius=24,
    )
    executed = await JiangsuDeviceControlExecuteTool().execute(
        context=context, confirmation_token=prepared["confirmation_token"], confirmed=True,
    )

    assert executed["success"] is True
    assert executed["data"]["recheck"]["Data"]["空调"] == "制冷 24℃"


def test_device_control_tools_declare_session_context_requirement():
    # The agent adapter only injects ExecutionContext when requires_context is
    # set; prepare/execute read context.session_id for the confirmation token.
    assert JiangsuDeviceControlStateTool().requires_context is False
    assert JiangsuDeviceControlPrepareTool().requires_context is True
    assert JiangsuDeviceControlExecuteTool().requires_context is True
