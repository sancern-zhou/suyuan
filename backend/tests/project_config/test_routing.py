from app.core.routing import RouterSpec, select_router_specs


def test_router_selection_keeps_core_and_enabled_modules():
    specs = [
        RouterSpec("app.core_route", owner="core"),
        RouterSpec("app.air_route", owner="atmosphere"),
        RouterSpec("app.noise_route", owner="noise"),
    ]

    selected = select_router_specs(specs, frozenset({"core", "noise"}))

    assert [spec.module for spec in selected] == ["app.core_route", "app.noise_route"]


def test_every_registered_router_has_a_migration_owner():
    from app.core.routing import ROUTER_REGISTRY

    assert ROUTER_REGISTRY
    assert all(spec.owner in {"core", "legacy"} for spec in ROUTER_REGISTRY)
    assert next(
        spec for spec in ROUTER_REGISTRY if spec.module == "app.api.project_config_routes"
    ).owner == "core"
