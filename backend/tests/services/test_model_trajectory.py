import asyncio
import pytest
from app.services import model_trajectory as trajectory


@pytest.fixture
def store(tmp_path, monkeypatch):
    result = trajectory.ModelTrajectoryStore(tmp_path)
    monkeypatch.setattr(trajectory, "ModelTrajectoryStore", lambda: result)
    return result


class Service:
    provider = "fake"
    model = "fake-model"
    api_mode = "chat_completions"

    @trajectory.trace_model_call
    async def call(self, messages, system=None):
        return {"content": [{"type": "text", "text": "answer"}], "usage": {"input_tokens": 20, "output_tokens": 4}, "stop_reason": "end_turn"}

    @trajectory.trace_model_call
    async def stream(self, messages):
        events = [
            {"type": "message_start", "data": {"usage": {"input_tokens": 20}}},
            {"type": "content_block_start", "data": {"index": 0, "block": {"type": "thinking", "thinking": ""}}},
            {"type": "content_block_delta", "data": {"index": 0, "delta": {"type": "thinking_delta", "thinking": "consider"}}},
            {"type": "content_block_start", "data": {"index": 1, "block": {"type": "tool_use", "id": "a", "name": "query", "input": {}}}},
            {"type": "content_block_delta", "data": {"index": 1, "delta": {"type": "input_json_delta", "partial_json": '{"city":'}}},
            {"type": "content_block_delta", "data": {"index": 1, "delta": {"type": "input_json_delta", "partial_json": '"南昌"}'}}},
            {"type": "message_delta", "data": {"usage": {"output_tokens": 5, "cache_read_input_tokens": 3}, "stop_reason": "tool_use"}},
        ]
        for event in events:
            yield event


@pytest.mark.asyncio
async def test_full_request_and_response_are_saved_outside_transcript(store):
    with trajectory.trajectory_scope("session-1", run_id="run-1"):
        result = await Service().call([{"role": "user", "content": "query"}], system="system prompt")
    record = store.read("session-1")["records"][0]
    assert record["request"]["system"] == "system prompt"
    assert record["response"] == result
    assert record["status"] == "completed"
    assert record["duration_ms"] >= 0
    assert store.read("session-2")["records"] == []


@pytest.mark.asyncio
async def test_stream_assembles_thinking_tool_json_and_usage_without_changing_events(store):
    with trajectory.trajectory_scope("stream-session"):
        events = [event async for event in Service().stream([])]
    assert len(events) == 7
    record = store.read("stream-session")["records"][0]
    assert record["response"]["content"][0]["thinking"] == "consider"
    assert record["response"]["content"][1]["input"] == {"city": "南昌"}
    assert record["response"]["usage"]["input_tokens"] == 20
    assert record["response"]["usage"]["output_tokens"] == 5


@pytest.mark.asyncio
async def test_subagents_and_compaction_keep_root_and_child_session_ownership(store):
    with trajectory.trajectory_scope("parent"):
        with trajectory.trajectory_scope("child"):
            await Service().call([])
            with trajectory.trajectory_scope(source="compact"):
                await Service().call([])
    assert [record["source"] for record in store.read("parent")["records"]] == ["subagent", "compact"]
    assert len(store.read("child")["records"]) == 2
    await Service().call([])
    assert len(store.read("parent")["records"]) == 2


@pytest.mark.asyncio
async def test_concurrent_calls_do_not_share_scope(store):
    async def run(session):
        with trajectory.trajectory_scope(session):
            await asyncio.sleep(0)
            await Service().call([{"role": "user", "content": session}])
    await asyncio.gather(run("one"), run("two"))
    assert store.read("one")["records"][0]["request"]["messages"][0]["content"] == "one"
    assert store.read("two")["records"][0]["request"]["messages"][0]["content"] == "two"


@pytest.mark.asyncio
async def test_failures_and_cancellation_are_recorded(store):
    class Failing(Service):
        @trajectory.trace_model_call
        async def call(self, messages):
            raise ValueError("model failed")
    with trajectory.trajectory_scope("failed"):
        with pytest.raises(ValueError):
            await Failing().call([])
    assert store.read("failed")["records"][0]["status"] == "failed"
    with trajectory.trajectory_scope("cancelled"):
        stream = Service().stream([])
        await anext(stream)
        await stream.aclose()
    assert store.read("cancelled")["records"][0]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_persistence_failure_never_breaks_model_call(store, monkeypatch):
    def fail(record):
        raise OSError("disk full")
    monkeypatch.setattr(store, "write", fail)
    with trajectory.trajectory_scope("safe"):
        result = await Service().call([])
    assert result["content"][0]["text"] == "answer"


@pytest.mark.asyncio
async def test_cursor_pagination_and_hashed_paths(store):
    with trajectory.trajectory_scope("../../outside"):
        for _ in range(3):
            await Service().call([])
    first = store.read("../../outside", limit=2)
    assert first["has_more"] is True
    second = store.read("../../outside", before=first["oldest_request_id"], limit=2)
    assert len(second["records"]) == 1
    assert second["has_more"] is False
    assert store.session_directory("../../outside").parent == store.directory


@pytest.mark.asyncio
async def test_real_llm_service_entry_records_normalized_response_without_network(store, monkeypatch):
    from app.services.llm_service import LLMService
    service = LLMService()
    service.provider = "fake"
    service.model = "fixture-model"
    service.api_mode = "chat_completions"
    service.request_fallbacks = ""
    monkeypatch.setattr("app.services.llm_service.get_cooldown_failure", lambda provider: None)

    async def create(**kwargs):
        return {"content": [{"type": "text", "text": "actual normalized response"}], "model": "fixture-model", "usage": {"input_tokens": 3, "output_tokens": 2}}
    monkeypatch.setattr(service, "_chat_completions_create", create)
    with trajectory.trajectory_scope("integration"):
        await service.chat_anthropic(messages=[{"role": "user", "content": "hi"}], system="instructions")
    record = store.read("integration")["records"][0]
    assert record["request"]["system"] == "instructions"
    assert record["request"]["temperature"] == 0.3
    assert record["response"]["usage"]["input_tokens"] == 3


@pytest.mark.asyncio
async def test_stream_consumer_can_start_another_call_without_suppressing_it(store):
    with trajectory.trajectory_scope("parent"):
        stream = Service().stream([])
        await anext(stream)
        with trajectory.trajectory_scope("child"):
            await Service().call([])
        await stream.aclose()
    assert len(store.read("parent")["records"]) == 2
    assert store.read("child")["records"][0]["source"] == "subagent"
