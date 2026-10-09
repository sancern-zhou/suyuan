import asyncio
import json
import sqlite3
import time

import pytest

from app.social.app_runs import AppRunStore


@pytest.mark.asyncio
async def test_concurrent_admission_is_idempotent_across_stores(tmp_path):
    stores = [AppRunStore(tmp_path / 'runs.sqlite3') for _ in range(6)]
    results = await asyncio.gather(*(s.create('alice', 'request', 'session', 'fingerprint') for s in stores))
    assert sum(created for _, created in results) == 1
    assert len({run['run_id'] for run, _ in results}) == 1
    with pytest.raises(ValueError, match='request_id_conflict'):
        await stores[0].create('alice', 'request', 'session', 'changed')
    with pytest.raises(ValueError, match='session_run_active'):
        await stores[0].create('alice', 'other-request', 'session', 'fingerprint')


@pytest.mark.asyncio
async def test_disconnect_does_not_cancel_execution_and_other_process_replays(tmp_path):
    store = AppRunStore(tmp_path / 'runs.sqlite3')
    reader = AppRunStore(store.path)
    run, _ = await store.create('alice', 'request', 'session', 'fingerprint')
    release = asyncio.Event()
    calls = []
    async def producer():
        calls.append('executed')
        await release.wait()
        yield 'data: ' + json.dumps({'type': 'complete', 'data': {'answer': '最终结果'}}) + '\n\n'
    store.start(run['run_id'], producer)
    subscription = store.stream(run['run_id'])
    first = await anext(subscription)
    assert 'start' in first
    cursor = int(first.splitlines()[0].split(': ')[1])
    await subscription.aclose()
    release.set()
    await asyncio.gather(*store.tasks)
    assert calls == ['executed']
    assert (await reader.get(run['run_id']))['status'] == 'completed'
    frames = [frame async for frame in reader.stream(run['run_id'], cursor)]
    assert len(frames) == 1
    assert '最终结果' in frames[0]


@pytest.mark.asyncio
async def test_explicit_cancel_from_another_process_stops_run(tmp_path):
    owner = AppRunStore(tmp_path / 'runs.sqlite3')
    caller = AppRunStore(owner.path)
    run, _ = await owner.create('alice', 'request', 'session', 'fingerprint')
    started = asyncio.Event()
    stopped = asyncio.Event()
    async def producer():
        try:
            started.set()
            await asyncio.Event().wait()
            yield ''
        finally:
            stopped.set()
    owner.start(run['run_id'], producer)
    await started.wait()
    assert await caller.cancel_session('session')
    await asyncio.wait_for(stopped.wait(), 3)
    await asyncio.gather(*owner.tasks, return_exceptions=True)
    assert (await caller.get(run['run_id']))['status'] == 'cancelled'
    assert (await caller.events(run['run_id']))[-1][1]['type'] == 'interrupted'


@pytest.mark.asyncio
async def test_dead_process_is_reported_without_reexecution(tmp_path):
    store = AppRunStore(tmp_path / 'runs.sqlite3')
    run, _ = await store.create('alice', 'request', 'session', 'fingerprint')
    with sqlite3.connect(store.path) as db:
        db.execute('UPDATE runs SET heartbeat=?', (time.time() - 100,))
    assert (await store.get(run['run_id']))['status'] == 'failed'
    same, created = await store.create('alice', 'request', 'session', 'fingerprint')
    assert not created
    assert same['status'] == 'failed'
    assert (await store.events(run['run_id']))[-1][1]['data']['code'] == 'app_run_lost'


@pytest.mark.asyncio
async def test_long_event_replay_is_not_truncated(tmp_path):
    store = AppRunStore(tmp_path / 'runs.sqlite3')
    run, _ = await store.create('alice', 'request', 'session', 'fingerprint')
    for _ in range(210):
        await store.append(run['run_id'], {'type': 'streaming_text', 'data': {'chunk': 'x'}})
    await store.append(run['run_id'], {'type': 'complete', 'data': {'answer': 'x' * 210}})
    frames = [frame async for frame in store.stream(run['run_id'])]
    assert len(frames) == 212
