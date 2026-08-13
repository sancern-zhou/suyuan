import pytest

from app.agent.runtime.agent_runtime import AgentRuntime, AgentRuntimeConfig
from app.agent.runtime.steering import InMemorySteeringStore, steering_registry
from app.agent.runtime.types import PlannerResult, RunState


class FakeSession:
    def __init__(self) -> None:
        self.messages = []

    def add_user_message(self, content):
        self.messages.append(content)

    def add_assistant_response(self, content):
        self.messages.append(content)

    def add_assistant_message(self, content, **_kwargs):
        self.messages.append(content)

    def get_messages_for_llm(self):
        return list(self.messages)


class FakeMemory:
    def __init__(self) -> None:
        self.session_id = "session-active-attachments"
        self.session = FakeSession()

    def add_iteration(self, **_kwargs):
        return None


@pytest.fixture(autouse=True)
def isolated_steering_store():
    previous = steering_registry.store
    steering_registry.store = InMemorySteeringStore()
    try:
        yield
    finally:
        steering_registry.store = previous


def make_runtime(memory: FakeMemory) -> AgentRuntime:
    return AgentRuntime(
        AgentRuntimeConfig(
            memory_manager=memory,
            planner=object(),
            tool_executor=object(),
            context_builder=object(),
        )
    )


@pytest.mark.asyncio
async def test_active_run_steering_preserves_document_and_image_attachments():
    session_id = "session-active-attachments"
    run_id = "run-active-attachments"
    attachments = [
        {
            "type": "file",
            "name": "磋商文件.pdf",
            "local_path": "/tmp/磋商文件.pdf",
            "mime_type": "application/pdf",
        },
        {
            "type": "image",
            "name": "现场照片.jpg",
            "local_path": "/tmp/现场照片.jpg",
            "url": "https://example.test/signed/现场照片.jpg",
            "mime_type": "image/jpeg",
        },
    ]

    await steering_registry.register(session_id, run_id, "social")
    try:
        accepted = await steering_registry.add_input(
            session_id,
            "请看这两个附件",
            attachments=attachments,
        )

        assert accepted is True
        [item] = await steering_registry.drain(session_id, run_id)
        assert item.content == "请看这两个附件"
        assert item.attachments == attachments
    finally:
        await steering_registry.unregister(session_id, run_id)


@pytest.mark.asyncio
async def test_runtime_applies_steered_attachments_to_next_iteration_context():
    memory = FakeMemory()
    runtime = make_runtime(memory)
    state = RunState(
        session_id=memory.session_id,
        user_query="介绍下这个项目",
        mode="social",
        run_id="run-runtime-attachments",
    )
    attachments = [
        {
            "type": "file",
            "name": "磋商文件.pdf",
            "local_path": "/tmp/磋商文件.pdf",
            "mime_type": "application/pdf",
            "resource_id": "resource-document-1",
        }
    ]

    await steering_registry.register(state.session_id, state.run_id, state.mode)
    try:
        await steering_registry.add_input(
            state.session_id,
            "[file: 磋商文件.pdf]",
            attachments=attachments,
        )

        events = [event async for event in runtime._apply_steering_inputs(state)]

        assert events and events[0]["type"] == "steering_applied"
        assert events[0]["data"]["inputs"] == [
            {
                "message": "[file: 磋商文件.pdf]",
                "input_id": events[0]["data"]["input_ids"][0],
                "attachments": [
                    {
                        "type": "file",
                        "name": "磋商文件.pdf",
                        "mime_type": "application/pdf",
                        "resource_id": "resource-document-1",
                        "ref_id": "resource-document-1",
                    }
                ],
            }
        ]
        assert state.pending_attachments == attachments
        assert "用户上传的附件" in memory.session.messages[-1]
        assert "磋商文件.pdf" in memory.session.messages[-1]
        assert "resource-document-1" in memory.session.messages[-1]
        assert "/tmp/磋商文件.pdf" not in memory.session.messages[-1]
    finally:
        await steering_registry.unregister(state.session_id, state.run_id)


@pytest.mark.asyncio
async def test_plain_text_completion_drains_late_steered_attachment_before_finishing():
    memory = FakeMemory()
    runtime = make_runtime(memory)
    state = RunState(
        session_id=memory.session_id,
        user_query="介绍下这个项目",
        mode="social",
        run_id="run-late-attachments",
    )
    attachments = [
        {
            "type": "file",
            "name": "磋商文件.pdf",
            "local_path": "/tmp/磋商文件.pdf",
            "mime_type": "application/pdf",
        }
    ]

    await steering_registry.register(state.session_id, state.run_id, state.mode)
    try:
        await steering_registry.add_input(
            state.session_id,
            "[file: 磋商文件.pdf]",
            attachments=attachments,
        )

        events = [
            event
            async for event in runtime._complete_response(
                state,
                PlannerResult(action={"type": "PLAIN_TEXT_REPLY", "answer": "项目介绍"}),
                "项目介绍",
            )
        ]

        assert [event["type"] for event in events] == ["steering_applied"]
        assert state.task_completed is False
        assert state.pending_attachments == attachments
    finally:
        await steering_registry.unregister(state.session_id, state.run_id)


@pytest.mark.asyncio
async def test_plain_text_completion_closes_steering_before_emitting_complete():
    memory = FakeMemory()
    runtime = make_runtime(memory)
    state = RunState(
        session_id=memory.session_id,
        user_query="介绍下这个项目",
        mode="social",
        run_id="run-closing",
    )

    await steering_registry.register(state.session_id, state.run_id, state.mode)
    try:
        events = [
            event
            async for event in runtime._complete_response(
                state,
                PlannerResult(action={"type": "PLAIN_TEXT_REPLY", "answer": "项目介绍"}),
                "项目介绍",
            )
        ]

        assert events[-1]["type"] == "complete"
        assert await steering_registry.add_input(state.session_id, "晚到的追加") is False
    finally:
        await steering_registry.unregister(state.session_id, state.run_id)


@pytest.mark.asyncio
async def test_runtime_close_helper_rejects_steering_for_other_terminal_paths():
    memory = FakeMemory()
    runtime = make_runtime(memory)
    state = RunState(
        session_id=memory.session_id,
        user_query="介绍下这个项目",
        mode="social",
        run_id="run-terminal",
    )

    await steering_registry.register(state.session_id, state.run_id, state.mode)
    try:
        await steering_registry.add_input(state.session_id, "终止前已接受")
        deferred = await runtime._close_steering(state)
        assert [item.content for item in deferred] == ["终止前已接受"]
        assert await steering_registry.add_input(state.session_id, "晚到的追加") is False
    finally:
        await steering_registry.unregister(state.session_id, state.run_id)
