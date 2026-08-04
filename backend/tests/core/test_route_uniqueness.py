from collections import defaultdict

from fastapi.routing import APIRoute

from app.main import app


def test_final_http_method_and_path_pairs_are_unique():
    owners = defaultdict(list)
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        endpoint = route.endpoint
        owner = f"{endpoint.__module__}.{endpoint.__name__}"
        for method in route.methods:
            owners[(method, route.path)].append(owner)

    duplicates = {
        key: route_owners
        for key, route_owners in owners.items()
        if len(route_owners) > 1
    }
    assert duplicates == {}

