from app.tools.jiangsu.device_control import _build_command, _requires_frontend_confirmation


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
