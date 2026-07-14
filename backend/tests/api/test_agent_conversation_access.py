import pytest
from fastapi import HTTPException

from app.auth.models import CurrentUser
from app.conversations import ConversationSource
from app.routers.agent import (
    AgentAnalyzeRequest,
    AgentSteerRequest,
    analyze_stream,
    cancel_analysis,
    persist_new_web_session,
    steer_analysis,
)


class DenyingCatalog:
    def __init__(self):
        self.write_checks = []

    async def require_write(self, session_id, user):
        self.write_checks.append((session_id, user.id))
        raise HTTPException(status_code=404, detail="session_not_found")


class RecordingCatalog:
    def __init__(self, fail=False):
        self.fail = fail
        self.registrations = []

    async def register(self, **values):
        self.registrations.append(values)
        if self.fail:
            raise RuntimeError("catalog unavailable")


class RecordingSessionManager:
    def __init__(self, save_result=True):
        self.save_result = save_result
        self.deleted = []

    async def save_session_metadata(self, session):
        return self.save_result

    async def delete_session(self, session_id):
        self.deleted.append(session_id)


class UnusedRequest:
    async def json(self):
        raise AssertionError("denied sessions must be rejected before body processing")


ordinary_user = CurrentUser(id="u1", username="u1", display_name="U1")


@pytest.mark.asyncio
async def test_reusing_session_requires_write_access_before_body_processing():
    catalog = DenyingCatalog()

    with pytest.raises(HTTPException) as exc:
        await analyze_stream(
            AgentAnalyzeRequest(query="continue", session_id="other-session"),
            UnusedRequest(),
            user=ordinary_user,
            catalog=catalog,
        )

    assert exc.value.status_code == 404
    assert catalog.write_checks == [("other-session", "u1")]


@pytest.mark.asyncio
async def test_cancel_requires_write_access_before_runtime_lookup():
    catalog = DenyingCatalog()

    with pytest.raises(HTTPException) as exc:
        await cancel_analysis("other-session", user=ordinary_user, catalog=catalog)

    assert exc.value.status_code == 404
    assert catalog.write_checks == [("other-session", "u1")]


@pytest.mark.asyncio
async def test_steer_requires_write_access_before_runtime_lookup():
    catalog = DenyingCatalog()

    with pytest.raises(HTTPException) as exc:
        await steer_analysis(
            "other-session",
            AgentSteerRequest(message="next"),
            user=ordinary_user,
            catalog=catalog,
        )

    assert exc.value.status_code == 404
    assert catalog.write_checks == [("other-session", "u1")]


@pytest.mark.asyncio
async def test_new_web_session_is_persisted_then_registered_to_authenticated_user():
    from app.agent.session import Session

    manager = RecordingSessionManager()
    catalog = RecordingCatalog()
    session = Session(session_id="new-session", query="hello")

    await persist_new_web_session(
        manager=manager,
        session=session,
        catalog=catalog,
        user=ordinary_user,
        mode="expert",
    )

    assert catalog.registrations[0]["session_id"] == "new-session"
    assert catalog.registrations[0]["user"] == ordinary_user
    assert catalog.registrations[0]["source"] == ConversationSource.WEB


@pytest.mark.asyncio
async def test_catalog_failure_removes_new_source_session():
    from app.agent.session import Session

    manager = RecordingSessionManager()
    catalog = RecordingCatalog(fail=True)
    session = Session(session_id="new-session", query="hello")

    with pytest.raises(RuntimeError, match="catalog unavailable"):
        await persist_new_web_session(
            manager=manager,
            session=session,
            catalog=catalog,
            user=ordinary_user,
            mode="expert",
        )

    assert manager.deleted == ["new-session"]
