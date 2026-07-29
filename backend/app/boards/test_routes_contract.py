from app.boards.routes import router


def test_board_restore_route_is_not_registered():
    assert not any(
        route.path == "/api/boards/{board_id}/restore" and "POST" in (route.methods or set())
        for route in router.routes
    )
