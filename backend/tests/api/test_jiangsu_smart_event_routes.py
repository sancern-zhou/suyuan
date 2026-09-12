from app.core.routing import ROUTER_REGISTRY


def test_smart_event_router_is_registered():
    assert any(spec.module == "app.api.jiangsu_smart_event_routes" for spec in ROUTER_REGISTRY)


def test_smart_event_router_exposes_human_closure_routes():
    from app.api.jiangsu_smart_event_routes import router

    paths = {(route.path, tuple(sorted(route.methods or []))) for route in router.routes}
    assert ("/api/jiangsu/smart-events/{event_id}/ai-judgments", ("POST",)) not in paths
    assert ("/api/jiangsu/smart-events/{event_id}/operations", ("POST",)) in paths
    assert ("/api/jiangsu/smart-events/{event_id}/archive", ("POST",)) not in paths
    from app.api.task_review_routes import router as review_router
    review_paths = {(route.path, tuple(sorted(route.methods or []))) for route in review_router.routes}
    assert ("/api/task-reviews/{review_id}/decision", ("POST",)) in review_paths


def test_smart_event_router_exposes_manual_ai_dispatch_route():
    from app.api.jiangsu_smart_event_routes import router

    paths = {(route.path, tuple(sorted(route.methods or []))) for route in router.routes}
    assert ("/api/jiangsu/smart-events/{event_id}/ai-dispatch", ("POST",)) in paths


def test_smart_event_router_exposes_disposal_closure_routes():
    from app.api.jiangsu_smart_event_routes import router

    paths = {(route.path, tuple(sorted(route.methods or []))) for route in router.routes}
    assert ("/api/jiangsu/smart-events/{event_id}/dispatch-order", ("POST",)) in paths
    assert ("/api/jiangsu/smart-events/{event_id}/feedback", ("POST",)) in paths


def test_smart_event_worker_router_exposes_feedback_internal_route():
    from app.api.jiangsu_smart_event_worker_routes import router

    paths = {(route.path, tuple(sorted(route.methods or []))) for route in router.routes}
    assert ("/internal/jiangsu/smart-events/{event_id}/feedback", ("POST",)) in paths
    assert ("/internal/jiangsu/smart-events/{event_id}/ai-dispatch", ("POST",)) in paths


def test_worker_proxy_covers_dispatch_and_feedback_suffixes():
    from app.core.jiangsu_smart_event_worker_proxy import (
        build_worker_jiangsu_smart_event_dispatch_url,
        should_proxy_jiangsu_smart_event_dispatch,
    )

    assert should_proxy_jiangsu_smart_event_dispatch(
        "/api/jiangsu/smart-events/alarm:1/ai-dispatch", "POST", "web"
    )
    assert should_proxy_jiangsu_smart_event_dispatch(
        "/api/jiangsu/smart-events/alarm:1/feedback", "POST", "web"
    )
    assert not should_proxy_jiangsu_smart_event_dispatch(
        "/api/jiangsu/smart-events/alarm:1/feedback", "GET", "web"
    )
    assert not should_proxy_jiangsu_smart_event_dispatch(
        "/api/jiangsu/smart-events/alarm:1/feedback", "POST", "worker"
    )
    assert build_worker_jiangsu_smart_event_dispatch_url(
        "http://worker:8012", "/api/jiangsu/smart-events/alarm:1/feedback"
    ) == "http://worker:8012/internal/jiangsu/smart-events/alarm:1/feedback"
