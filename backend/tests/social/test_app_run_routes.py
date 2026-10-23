import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.api import social_app_routes as routes
from app.db.database import get_db
from app.social.app_identity import AppIdentity, require_app_identity
from app.social.app_runs import AppRunStore


@pytest.mark.asyncio
async def test_run_routes_retry_replay_and_user_isolation(tmp_path, monkeypatch):
    store = AppRunStore(tmp_path / 'runs.sqlite3')
    monkeypatch.setattr(routes, 'get_app_run_store', lambda: store)
    ensure = AsyncMock(return_value='social-session')
    monkeypatch.setattr(routes, '_ensure_session', ensure)
    catalog = SimpleNamespace(require_read=AsyncMock())
    monkeypatch.setattr(routes, 'get_conversation_catalog', lambda: catalog)
    release = asyncio.Event()
    calls = []
    async def producer(identity, session_id, query, attachments, mode, request_id=None, resource_refs=None):
        calls.append(query)
        await release.wait()
        yield 'data: ' + json.dumps({'type': 'complete', 'data': {'answer': '完成'}}) + '\n\n'
    monkeypatch.setattr(routes, '_stream_events', producer)
    app = FastAPI()
    app.include_router(routes.router)
    identity = AppIdentity('alice', 'Alice', 'app:android:alice', 9999999999)
    app.dependency_overrides[require_app_identity] = lambda: identity
    app.dependency_overrides[get_db] = lambda: None
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        payload = {'query': '测试', 'mode': 'query', 'request_id': 'client-request'}
        first = await client.post('/api/social/app/chat/runs', json=payload)
        assert first.status_code == 200
        run_id = first.json()['run_id']
        retry = await client.post('/api/social/app/chat/runs', json=payload)
        assert retry.json()['run_id'] == run_id
        ensure.assert_awaited_once()
        assert (await client.post('/api/social/app/chat/runs', json={**payload, 'query': 'different'})).status_code == 409
        assert json.loads((await store.get(run_id))['payload'])['query'] == '测试'
        # Submission returned before execution completed; the publisher is detached.
        assert (await client.get(f'/api/social/app/chat/runs/{run_id}')).json()['status'] == 'running'
        release.set()
        await asyncio.gather(*store.tasks)
        replay = await client.get(f'/api/social/app/chat/runs/{run_id}/events')
        assert replay.status_code == 200
        assert '完成' in replay.text
        assert replay.text.count('data: ') == 2
        assert calls == ['测试']
        identity = AppIdentity('bob', 'Bob', 'app:android:bob', 9999999999)
        assert (await client.get(f'/api/social/app/chat/runs/{run_id}')).status_code == 404
        assert (await client.get(f'/api/social/app/chat/runs/{run_id}/events')).status_code == 404


@pytest.mark.asyncio
async def test_legacy_stream_uses_detached_execution(tmp_path, monkeypatch):
    store = AppRunStore(tmp_path / 'runs.sqlite3')
    monkeypatch.setattr(routes, 'get_app_run_store', lambda: store)
    monkeypatch.setattr(routes, '_ensure_session', AsyncMock(return_value='social-session'))
    monkeypatch.setattr(routes, 'get_conversation_catalog', lambda: SimpleNamespace(find=AsyncMock(return_value=None)))
    release = asyncio.Event()
    async def producer(*args, **kwargs):
        await release.wait()
        yield 'data: {"type":"complete","data":{"answer":"done"}}\n\n'
    monkeypatch.setattr(routes, '_stream_events', producer)
    identity = AppIdentity('alice', 'Alice', 'app:android:alice', 9999999999)
    response = await routes.chat_stream(object(), routes.AppChatRequest(query='test'), None, identity)
    subscriber = response.body_iterator
    assert 'start' in await anext(subscriber)
    await subscriber.aclose()
    release.set()
    await asyncio.gather(*store.tasks)
    assert (await store.get(response.headers['x-run-id']))['status'] == 'completed'


@pytest.mark.asyncio
async def test_start_app_run_autotitles_placeholder_session(tmp_path, monkeypatch):
    store = AppRunStore(tmp_path / 'runs.sqlite3')
    monkeypatch.setattr(routes, 'get_app_run_store', lambda: store)
    monkeypatch.setattr(routes, '_ensure_session', AsyncMock(return_value='social-session'))
    catalog = SimpleNamespace(
        find=AsyncMock(return_value=SimpleNamespace(title='新对话')),
        rename=AsyncMock(return_value=True),
    )
    monkeypatch.setattr(routes, 'get_conversation_catalog', lambda: catalog)

    async def producer(*args, **kwargs):
        yield 'data: {"type":"complete","data":{"answer":"done"}}\n\n'

    monkeypatch.setattr(routes, '_stream_events', producer)
    await routes.start_app_run(
        object(),
        routes.AppChatRequest(query='  帮我  查一下空气质量  ', mode='query'),
        None,
        AppIdentity('alice', 'Alice', 'app:android:alice', 9999999999),
    )
    await asyncio.gather(*store.tasks)
    catalog.rename.assert_awaited_once_with('social-session', '帮我 查一下空气质量')


@pytest.mark.asyncio
async def test_autotitle_skips_named_sessions_and_broadcasts():
    catalog = SimpleNamespace(
        find=AsyncMock(return_value=SimpleNamespace(title='已有标题')),
        rename=AsyncMock(return_value=True),
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(routes, 'get_conversation_catalog', lambda: catalog)
        await routes._autotitle_session_from_query('social-session', '新问题')
        catalog.rename.assert_not_awaited()
        await routes._autotitle_session_from_query('broadcast_session_x', '新问题')
        assert catalog.find.await_count == 1
        await routes._autotitle_session_from_query('social-session', '   ')
        assert catalog.find.await_count == 1
        catalog.rename.assert_not_awaited()


@pytest.mark.parametrize('title,expected', [
    (None, True),
    ('', True),
    ('新对话', True),
    ('新会话', True),
    ('session_abc', True),
    ('session-ab real title', False),
    ('帮我查空气质量', False),
])
def test_placeholder_title_detection(title, expected):
    assert routes._is_placeholder_session_title(title, 'social-session') is expected
