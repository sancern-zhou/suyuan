import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.api import social_app_routes as routes
from app.conversations.schemas import ConversationSource
from app.db.database import get_db
from app.social.app_identity import AppIdentity, require_app_identity
from app.social.app_runs import AppRunStore


QUESTIONS = [
    {'question': '请选择输出格式', 'header': '格式', 'options': [
        {'label': 'PDF', 'description': '固定版式'}, {'label': 'HTML', 'description': '手机浏览'},
    ], 'multiSelect': False},
    {'question': '需要哪些章节', 'header': '章节', 'options': [
        {'label': '摘要', 'description': '概览'}, {'label': '附录', 'description': '依据'},
    ], 'multiSelect': True},
]


@pytest.mark.asyncio
async def test_app_question_answer_resume_and_restore(tmp_path, monkeypatch):
    store = AppRunStore(tmp_path / 'runs.sqlite3')
    monkeypatch.setattr(routes, 'get_app_run_store', lambda: store)
    monkeypatch.setattr(routes, '_ensure_session', AsyncMock(return_value='social-session'))
    catalog = SimpleNamespace(require_read=AsyncMock(return_value=SimpleNamespace(source=ConversationSource.SOCIAL)))
    monkeypatch.setattr(routes, 'get_conversation_catalog', lambda: catalog)
    calls = []
    class Agent:
        async def analyze(self, **kwargs):
            calls.append(kwargs['user_query'])
            if kwargs['user_query'] == '生成报告':
                yield {'type': 'interaction_required', 'data': {'kind': 'structured_question', 'questions': QUESTIONS}}
                yield {'type': 'complete', 'data': {'answer': '等待选择'}}
            else:
                yield {'type': 'complete', 'data': {'answer': '根据回答生成报告'}}
    monkeypatch.setattr(routes, '_get_agent', AsyncMock(return_value=Agent()))
    monkeypatch.setattr(routes, '_get_memory_store', AsyncMock(return_value=object()))
    monkeypatch.setattr(routes, '_social_preferences', lambda _identity: {})
    monkeypatch.setattr(routes, '_persist_app_turn', AsyncMock())
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[require_app_identity] = lambda: AppIdentity('alice', 'Alice', 'app:android:alice', 9999999999)
    app.dependency_overrides[get_db] = lambda: None
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        first = await client.post('/api/social/app/chat/runs', json={'query': '生成报告', 'mode': 'query', 'request_id': 'first'})
        await asyncio.gather(*store.tasks)
        assert (await store.get(first.json()['run_id']))['status'] == 'awaiting_user'
        frames = await client.get(f"/api/social/app/chat/runs/{first.json()['run_id']}/events")
        assert 'interaction_required' in frames.text
        assert 'interaction_id' in frames.text
        pending = (await client.get('/api/social/app/sessions/social-session/interaction')).json()['interaction']
        assert pending['questions'][0]['question'] == QUESTIONS[0]['question']
        assert [option['label'] for option in pending['questions'][0]['options']] == [option['label'] for option in QUESTIONS[0]['options']]
        # A different process can restore the same question without replaying tools.
        reader = AppRunStore(store.path)
        assert (await reader.pending_interaction('social-session'))['interaction_id'] == pending['interaction_id']
        question_url = f"/api/social/app/sessions/social-session/interactions/{pending['interaction_id']}"
        assert (await client.post(question_url, json={'decision': 'answer', 'answers': [{'selected': [0, 1]}, {'selected': [0]}]})).status_code == 422
        assert (await client.post('/api/social/app/chat/runs', json={'query': '随便继续', 'mode': 'query'})).status_code == 409
        answers = {'decision': 'answer', 'answers': [{'selected': [1]}, {'selected': [0, 1], 'custom': '加入图表'}]}
        resolution = await client.post(question_url, json=answers)
        assert resolution.status_code == 200
        assert 'HTML' in resolution.json()['resume_query']
        assert '加入图表' in resolution.json()['resume_query']
        assert (await client.post(question_url, json=answers)).json() == resolution.json()
        assert (await client.post(question_url, json={'decision': 'reject'})).status_code == 409
        assert (await reader.pending_interaction('social-session')) is None
        continuation = {'query': resolution.json()['resume_query'], 'mode': resolution.json()['mode'],
                        'session_id': 'social-session', 'request_id': resolution.json()['request_id']}
        resumed = await client.post('/api/social/app/chat/runs', json=continuation)
        await asyncio.gather(*store.tasks)
        retry = await client.post('/api/social/app/chat/runs', json=continuation)
        assert resumed.json()['run_id'] == retry.json()['run_id']
        assert len(calls) == 2
        final = await client.get(f"/api/social/app/chat/runs/{resumed.json()['run_id']}/events")
        assert '根据回答生成报告' in final.text


@pytest.mark.asyncio
async def test_reject_question_does_not_auto_run_or_leave_session_blocked(tmp_path):
    store = AppRunStore(tmp_path / 'runs.sqlite3')
    run, _ = await store.create('alice', 'request', 'session', 'fingerprint')
    await store.append(run['run_id'], {'type': 'interaction_required', 'data': {
        'interaction_id': 'question1', 'session_id': 'session', 'mode': 'query', 'kind': 'structured_question', 'questions': QUESTIONS,
    }})
    with pytest.raises(RuntimeError, match='interaction_turn_finishing'):
        await store.resolve_interaction('session', 'question1', 'reject', None)
    await store.append(run['run_id'], {'type': 'complete', 'data': {'answer': '等待选择'}})
    resolution = await store.resolve_interaction('session', 'question1', 'reject', None)
    assert resolution['resume_query'] is None
    assert await store.pending_interaction('session') is None
    assert (await store.get(run['run_id']))['status'] == 'cancelled'
    assert not store.tasks
    assert (await store.create('alice', 'new', 'session', 'new-fingerprint'))[1]


@pytest.mark.asyncio
async def test_parallel_question_decisions_have_one_winner(tmp_path):
    store = AppRunStore(tmp_path / 'runs.sqlite3')
    reader = AppRunStore(store.path)
    run, _ = await store.create('alice', 'request', 'session', 'fingerprint')
    await store.append(run['run_id'], {'type': 'interaction_required', 'data': {
        'interaction_id': 'question1', 'session_id': 'session', 'mode': 'query',
        'kind': 'structured_question', 'questions': QUESTIONS,
    }})
    await store.append(run['run_id'], {'type': 'complete', 'data': {'answer': '等待选择'}})
    with pytest.raises(ValueError, match='answer_pending_question_first'):
        await reader.create('alice', 'new', 'session', 'new-fingerprint')
    await store.cleanup()
    assert (await reader.pending_interaction('session'))['interaction_id'] == 'question1'
    decisions = await asyncio.gather(
        store.resolve_interaction('session', 'question1', 'answer', [{'selected': [0]}, {'selected': [1]}]),
        reader.resolve_interaction('session', 'question1', 'reject', None), return_exceptions=True,
    )
    assert sum(isinstance(item, dict) for item in decisions) == 1
    assert sum(isinstance(item, RuntimeError) for item in decisions) == 1
    assert await reader.pending_interaction('session') is None


@pytest.mark.asyncio
async def test_question_endpoints_require_app_conversation_permission(monkeypatch):
    from fastapi import HTTPException
    identity = AppIdentity('bob', 'Bob', 'app:android:bob', 9999999999)
    catalog = SimpleNamespace(require_read=AsyncMock(side_effect=HTTPException(status_code=404)))
    monkeypatch.setattr(routes, 'get_conversation_catalog', lambda: catalog)
    with pytest.raises(HTTPException) as exc:
        await routes.app_pending_interaction('other-session', identity)
    assert exc.value.status_code == 404
    catalog.require_read = AsyncMock(return_value=SimpleNamespace(source=ConversationSource.WEB))
    with pytest.raises(HTTPException) as exc:
        await routes.app_resolve_interaction('web-session', 'question', routes.AppQuestionResolution(decision='reject'), identity)
    assert exc.value.status_code == 404
