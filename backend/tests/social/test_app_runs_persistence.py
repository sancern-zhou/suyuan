import json
from unittest.mock import AsyncMock

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
async def test_app_chart_run_replays_canonical_answer_without_public_process_paths(tmp_path, monkeypatch, fake_lock_db):
    import asyncio

    chart_id = "a" * 32
    secret_path = "backend/backend_data_registry/趋势 图.png"
    raw_marker = f"[[chart:{secret_path}]]"
    answer = f"结论 [[chart:{chart_id}]]"
    chart = {
        "file_id": chart_id, "resource_id": chart_id, "run_id": "old-run",
        "mime_type": "image/png", "url": f"/api/social/app/sessions/session/resources/{chart_id}/content",
    }
    old_report = {"file_id": "old-report", "resource_id": "b" * 32, "run_id": "old-run"}
    lookup = AsyncMock(return_value=[chart, old_report])
    persist = AsyncMock()

    class Agent:
        async def analyze(self, **kwargs):
            yield {"type": "tool_result", "data": {"tool_name": "execute_python", "result": {
                "summary": f"生成结果 {raw_marker}",
                "chart_references": [{"path": secret_path, "marker": raw_marker}],
                "resources": [{
                    "resource_id": chart_id, "metadata": {"inline_chart": True},
                    "locator": {"path": secret_path}, "file_path": secret_path,
                }],
                "data": {
                    "description": f"草稿 {raw_marker[:-2]}",
                    "node_results": {"chart": {"published_charts": [{"path": secret_path, "marker": raw_marker}]}},
                },
            }}}
            yield {"type": "streaming_text", "data": {"chunk": "结论 【图表不可用】"}}
            yield {"type": "complete", "data": {"answer": answer, "response": answer}}

    monkeypatch.setattr(routes, "_get_agent", AsyncMock(return_value=Agent()))
    monkeypatch.setattr(routes, "_get_memory_store", AsyncMock(return_value=object()))
    monkeypatch.setattr(routes, "_social_preferences", lambda _identity: {})
    monkeypatch.setattr(routes, "_app_resource_descriptors", lookup)
    monkeypatch.setattr(routes, "_persist_app_turn", persist)
    store = AppRunStore(tmp_path / "runs.sqlite3")
    run, _ = await store.create("alice", "request", "session", "fingerprint")
    identity = AppIdentity("alice", "Alice", "app:android:alice", 9999999999)
    store.start(run["run_id"], lambda: routes._stream_events(identity, "session", "问题", [], "query"))
    await asyncio.gather(*store.tasks)

    events = [event for _, event in await store.events(run["run_id"])]
    assert [event["type"] for event in events] == ["start", "tool_result", "streaming_text", "complete"]
    assert secret_path not in json.dumps(events, ensure_ascii=False)
    assert events[1]["data"]["tool_name"] == "execute_python"
    assert "chart_references" not in events[1]["data"]["result"]
    assert events[-1]["data"] == {"answer": answer, "response": answer, "attachments": [chart]}
    lookup.assert_awaited_once_with("session", [chart_id])
    persisted = persist.await_args.args[2][-1]
    assert persisted["content"] == answer
    assert persisted["attachments"] == [chart]


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
