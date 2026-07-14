import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.auth.models import CurrentUser
from app.auth.dependencies import require_current_user


class FakeTicketService:
    def __init__(self):
        self.valid = {"valid"}
        self.calls = []
        self.ttl_seconds = 30

    async def issue(self, user, *, purpose):
        self.calls.append((user.id, purpose))
        return "issued-ticket"

    async def consume(self, ticket, *, purpose):
        from app.auth.ws_tickets import InvalidWebSocketTicket

        self.calls.append((ticket, purpose))
        if ticket not in self.valid:
            raise InvalidWebSocketTicket("invalid ticket")
        self.valid.remove(ticket)
        return CurrentUser(id="u1", username="u", display_name="U")


class FakeEventBus:
    def __init__(self):
        self.connected = []
        self.disconnected = []

    async def connect(self, websocket):
        self.connected.append(websocket)
        await websocket.accept()

    def disconnect(self, websocket):
        self.disconnected.append(websocket)


@pytest.fixture
def websocket_api(monkeypatch):
    from app.api import scheduled_task_ws

    tickets = FakeTicketService()
    bus = FakeEventBus()
    monkeypatch.setattr(scheduled_task_ws, "get_event_bus", lambda: bus)
    app = FastAPI()
    app.state.ws_ticket_service = tickets
    app.include_router(scheduled_task_ws.router)
    return TestClient(app), tickets, bus


@pytest.mark.parametrize("url", ["/ws/scheduled-tasks", "/ws/scheduled-tasks?ticket=bad"])
def test_missing_or_invalid_ticket_closes_4401(websocket_api, url):
    client, tickets, bus = websocket_api

    with pytest.raises(WebSocketDisconnect) as raised:
        with client.websocket_connect(url):
            pass

    assert raised.value.code == 4401
    assert bus.connected == []


def test_valid_ticket_supports_ping_and_cannot_be_reused(websocket_api):
    client, tickets, bus = websocket_api

    with client.websocket_connect("/ws/scheduled-tasks?ticket=valid") as websocket:
        websocket.send_text("ping")
        assert websocket.receive_text() == "pong"

    with pytest.raises(WebSocketDisconnect) as raised:
        with client.websocket_connect("/ws/scheduled-tasks?ticket=valid"):
            pass
    assert raised.value.code == 4401
    assert tickets.calls == [
        ("valid", "scheduled-tasks"),
        ("valid", "scheduled-tasks"),
    ]


def test_authenticated_http_endpoint_issues_scheduled_task_ticket():
    from app.auth.routes import router

    app = FastAPI()
    tickets = FakeTicketService()
    app.state.ws_ticket_service = tickets
    app.include_router(router, prefix="/api")
    app.dependency_overrides[require_current_user] = lambda: CurrentUser(
        id="u1", username="u", display_name="U"
    )

    response = TestClient(app).post("/api/auth/ws-ticket")

    assert response.status_code == 200
    assert response.json() == {"ticket": "issued-ticket", "expires_in": 30}
    assert tickets.calls == [("u1", "scheduled-tasks")]
