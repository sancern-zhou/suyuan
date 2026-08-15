from app.tools.gisctl.place_resolver import resolve_place


def test_resolve_place_resolves_guangdong_city_name():
    place = resolve_place("佛山")

    assert place is not None
    assert place.name == "佛山"
    assert place.center == [113.1214, 23.0219]
    assert place.zoom == 10
    assert place.scope == "city"
    assert place.cities == ["佛山"]


def test_resolve_place_resolves_city_name_with_suffix():
    place = resolve_place("深圳市")

    assert place is not None
    assert place.name == "深圳"
    assert place.center == [114.0579, 22.5431]


def test_resolve_place_does_not_interpret_map_action_text():
    assert resolve_place("缩小地图") is None
