def test_smart_event_dispatch_proxy_matches_only_web_post_dispatch_route():
    from app.core.jiangsu_smart_event_worker_proxy import (
        build_worker_jiangsu_smart_event_dispatch_url,
        should_proxy_jiangsu_smart_event_dispatch,
    )

    path = "/api/jiangsu/smart-events/alarm:161345/ai-dispatch"
    assert should_proxy_jiangsu_smart_event_dispatch(path, "POST", "web")
    assert not should_proxy_jiangsu_smart_event_dispatch(path, "GET", "web")
    assert not should_proxy_jiangsu_smart_event_dispatch(path, "POST", "worker")
    assert not should_proxy_jiangsu_smart_event_dispatch(
        "/api/jiangsu/smart-events/alarm:161345", "POST", "web"
    )

    assert (
        build_worker_jiangsu_smart_event_dispatch_url(
            "http://127.0.0.1:8012/",
            path,
            "trace=1",
        )
        == "http://127.0.0.1:8012/internal/jiangsu/smart-events/alarm:161345/ai-dispatch?trace=1"
    )
