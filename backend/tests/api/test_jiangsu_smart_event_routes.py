from app.core.routing import ROUTER_REGISTRY


def test_smart_event_router_is_registered():
    assert any(spec.module == "app.api.jiangsu_smart_event_routes" for spec in ROUTER_REGISTRY)


def test_smart_event_router_exposes_human_closure_routes():
    from app.api.jiangsu_smart_event_routes import router

    paths = {(route.path, tuple(sorted(route.methods or []))) for route in router.routes}
    assert ("/api/jiangsu/smart-events/{event_id}/ai-judgments", ("POST",)) in paths
    assert ("/api/jiangsu/smart-events/{event_id}/operations", ("POST",)) in paths
    assert ("/api/jiangsu/smart-events/{event_id}/archive", ("POST",)) in paths
