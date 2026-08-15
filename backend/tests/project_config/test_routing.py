from app.core.routing import RouterSpec, select_router_specs
from app.project_config.loader import load_project_context


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
    assert all(spec.owner in {"core", "legacy", "xuchang-air-quality"} for spec in ROUTER_REGISTRY)
    assert next(
        spec for spec in ROUTER_REGISTRY if spec.module == "app.api.project_config_routes"
    ).owner == "core"


def test_default_project_excludes_xuchang_router():
    from app.core.routing import ROUTER_REGISTRY

    context = load_project_context("default")
    selected = select_router_specs(ROUTER_REGISTRY, context.enabled_modules)

    assert "app.api.xuchang_air_quality_routes" not in {
        spec.module for spec in selected
    }


def test_xuchang_project_includes_xuchang_router():
    from app.core.routing import ROUTER_REGISTRY

    context = load_project_context("xuchang")
    selected = select_router_specs(ROUTER_REGISTRY, context.enabled_modules)

    assert "app.api.xuchang_air_quality_routes" in {
        spec.module for spec in selected
    }



