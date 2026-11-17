"""上游截断工具参数的自愈：必须回灌失败往返，且不允许同指纹空转。"""

from types import SimpleNamespace

from app.agent.memory.session_memory import SessionMemory
from app.agent.runtime.agent_runtime import AgentRuntime
from app.agent.runtime.conversation_writer import ConversationWriter
from app.agent.runtime.event_bus import RuntimeEventBus
from app.agent.runtime.types import RunState
from app.services.chat_completions_adapter import ToolCallArgumentsError


def _runtime(tmp_path):
    runtime = object.__new__(AgentRuntime)
    memory = SimpleNamespace(session=SessionMemory("trunc", base_dir=tmp_path))
    runtime.memory = memory
    runtime.writer = ConversationWriter(memory)
    runtime.events = RuntimeEventBus()
    runtime.config = SimpleNamespace(agent_logger=None)
    return runtime


def test_memory_records_failed_exchange(tmp_path):
    session = SessionMemory("trunc-mem", base_dir=tmp_path)
    session.add_user_message("画图")
    session.add_truncated_tool_call_recovery(
        "call_1", "execute_echarts_python", "参数被截断", received_chars=120,
    )
    messages = session.get_messages_for_llm()
    assistant = [m for m in messages if m["role"] == "assistant"][-1]
    user = messages[-1]
    assert assistant["content"][0]["type"] == "tool_use"
    assert assistant["content"][0]["id"] == "call_1"
    assert user["role"] == "user"
    assert user["content"][0]["type"] == "tool_result"
    assert user["content"][0]["tool_use_id"] == "call_1"
    assert user["content"][0]["is_error"] is True


def test_signature_repeat_is_not_absorbed(tmp_path):
    runtime = _runtime(tmp_path)
    state = RunState(session_id="s", user_query="q", mode="expert")
    error = ToolCallArgumentsError('{"code": ', tool_name="execute_python", truncated=True)
    assert runtime._recover_truncated_tool_call(state, error) is not None
    assert runtime._recover_truncated_tool_call(state, error) is None
    assert state.truncated_tool_call_recoveries == 1


def test_non_truncated_arguments_error_is_not_absorbed(tmp_path):
    runtime = _runtime(tmp_path)
    state = RunState(session_id="s", user_query="q", mode="expert")
    error = ToolCallArgumentsError('{"code": ', tool_name="execute_python")
    assert runtime._recover_truncated_tool_call(state, error) is None
