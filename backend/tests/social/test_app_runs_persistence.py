import json
from types import SimpleNamespace

import pytest

from app.api import social_app_routes as routes
from app.social.app_identity import AppIdentity
from app.social.app_runs import AppRunStore


@pytest.mark.asyncio
async def test_detached_turn_persists_before_terminal_replay(tmp_path, monkeypatch, fake_lock_db):
    saved = []
    class Agent:
        async def analyze(self, **kwargs):
            yield {'type': 'start', 'data': {'session_id': kwargs['session_id']}}
            yield {'type': 'streaming_text', 'data': {'chunk': '完整回复'}}
            yield {'type': 'complete', 'data': {'answer': '完整回复'}}
    async def agent(): return Agent()
    async def memory(_identity): return object()
    async def persist(session, query, history): saved.extend(history)
    monkeypatch.setattr(routes, '_get_agent', agent)
    monkeypatch.setattr(routes, '_get_memory_store', memory)
    monkeypatch.setattr(routes, '_social_preferences', lambda _identity: {})
    monkeypatch.setattr(routes, '_persist_app_turn', persist)
    store = AppRunStore(tmp_path / 'runs.sqlite3')
    run, _ = await store.create('alice', 'request', 'session', 'fingerprint')
    identity = AppIdentity('alice', 'Alice', 'app:android:alice', 9999999999)
    store.start(run['run_id'], lambda: routes._stream_events(identity, 'session', '问题', [], 'query'))
    import asyncio
    await asyncio.gather(*store.tasks)
    assert [row['content'] for row in saved] == ['问题', '完整回复']
    assert (await store.get(run['run_id']))['status'] == 'completed'
    frames = [frame async for frame in store.stream(run['run_id'])]
    assert 'complete' in frames[-1]


@pytest.mark.asyncio
async def test_app_rejects_competing_run_before_loading_or_persisting_it(monkeypatch, fake_lock_db):
    import asyncio
    entered = []

    async def run(*args):
        entered.append(True)
        try:
            yield 'data: {"type":"start"}\n\n'
        finally:
            assert fake_lock_db.locked  # final transcript saved before release

    monkeypatch.setattr(routes, '_stream_events_unlocked', run)
    identity = AppIdentity('alice', 'Alice', 'app:android:alice', 9999999999)
    first = routes._stream_events(identity, 'session', 'question')
    await anext(first)
    async def other_request():
        return [frame async for frame in routes._stream_events(identity, 'session', 'duplicate')]
    rejected = await asyncio.create_task(other_request())
    assert len(entered) == 1
    payload = json.loads(rejected[0].removeprefix('data: '))
    assert payload['type'] == 'fatal_error'
    assert payload['data']['code'] == 'session_run_in_progress'
    await first.aclose()
    assert not fake_lock_db.locked
