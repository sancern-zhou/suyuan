# Chart Mode Native Multimodal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make chart mode use the same native multimodal image input and fixed multimodal model profile as social mode.

**Architecture:** Add one shared runtime helper that declares which modes support native multimodal image input. Use it in `ReActAgent` model/profile selection, `ReActLoop` attachment passing, and `AgentRuntime` image content block construction. Update chart prompt text so uploaded images are understood as already visible to the model rather than requiring `analyze_image` or default `read_file` analysis.

**Tech Stack:** Python 3.11, pytest, existing Anthropic-compatible planner, existing `llm_service.use_auto_profile("multimodal")`, existing ReAct runtime.

---

## File Structure

- Create `backend/app/agent/runtime/mode_capabilities.py`
  - Owns the small mode capability predicate `supports_native_multimodal(mode)`.
- Create `backend/app/agent/runtime/mode_capabilities_test.py`
  - Tests the predicate for `social`, `chart`, and a normal text mode.
- Modify `backend/app/agent/react_agent.py`
  - Use the helper in `_select_auto_profile()`.
  - Pass `runtime_attachments` to `ReActLoop` for every native multimodal mode.
- Modify `backend/app/agent/session/social_session_storage_test.py`
  - Add chart-mode assertions for multimodal profile and attachment forwarding.
- Modify `backend/app/agent/runtime/agent_runtime.py`
  - Use the helper anywhere native multimodal blocks are built or tool-emitted image attachments are captured.
- Create `backend/app/agent/runtime/agent_runtime_multimodal_test.py`
  - Tests chart mode builds `text` + `image` blocks for planner input and non-native modes do not.
- Modify `backend/app/agent/runtime/multimodal.py`
  - Update comments/docstrings from social-only to native-multimodal modes.
- Modify `backend/app/agent/prompts/chart_prompt.py`
  - Update reference image and board snapshot instructions.
- Modify `backend/app/agent/prompts/task_tool_registry_test.py`
  - Update existing prompt expectations and add regression checks against default `analyze_image` / `read_file(path, analysis_type="chart")` guidance.

### Task 1: Add Mode Capability Helper

**Files:**
- Create: `backend/app/agent/runtime/mode_capabilities.py`
- Create: `backend/app/agent/runtime/mode_capabilities_test.py`

- [ ] **Step 1: Write the failing test**

Add `backend/app/agent/runtime/mode_capabilities_test.py`:

```python
from app.agent.runtime.mode_capabilities import supports_native_multimodal


def test_supports_native_multimodal_for_social_and_chart_modes():
    assert supports_native_multimodal("social") is True
    assert supports_native_multimodal("chart") is True


def test_supports_native_multimodal_rejects_text_only_modes():
    assert supports_native_multimodal("assistant") is False
    assert supports_native_multimodal("expert") is False
    assert supports_native_multimodal(None) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
conda run -n backend_py311 pytest backend/app/agent/runtime/mode_capabilities_test.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.agent.runtime.mode_capabilities'`.

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/agent/runtime/mode_capabilities.py`:

```python
"""Mode capability predicates for the ReAct runtime."""

from __future__ import annotations

from typing import Optional


NATIVE_MULTIMODAL_MODES = frozenset({"social", "chart"})


def supports_native_multimodal(mode: Optional[str]) -> bool:
    """Return whether a mode sends image attachments as native content blocks."""
    return (mode or "").strip().lower() in NATIVE_MULTIMODAL_MODES
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
conda run -n backend_py311 pytest backend/app/agent/runtime/mode_capabilities_test.py -q
```

Expected: PASS.

### Task 2: Route Chart Mode Through Multimodal Profile and Attachments

**Files:**
- Modify: `backend/app/agent/react_agent.py`
- Modify: `backend/app/agent/session/social_session_storage_test.py`

- [ ] **Step 1: Write the failing tests**

In `backend/app/agent/session/social_session_storage_test.py`, add tests beside the existing social-mode profile test. Reuse the existing fake `ReActLoop` pattern in the file.

```python
@pytest.mark.asyncio
async def test_chart_mode_uses_multimodal_auto_profile(monkeypatch):
    captured_kwargs = {}

    class FakeReActLoop:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)
            self.context_builder = type("ContextBuilder", (), {"memory_context": None, "board_context": None, "memory_file_path": None})()

        async def run(self, **kwargs):
            yield {"type": "complete", "data": {"answer": "ok"}}

    monkeypatch.setattr(react_agent_module, "ReActLoop", FakeReActLoop)
    agent = react_agent_module.ReActAgent()
    agent.enable_memory = False

    events = [
        event
        async for event in agent.analyze(
            user_query="按参考图生成图表",
            session_id="chart_session_profile",
            manual_mode="chart",
            attachments=[{"type": "image", "name": "ref.png", "url": "https://example.com/ref.png"}],
        )
    ]

    assert events[-1]["type"] == "complete"
    assert captured_kwargs["auto_profile"] == "multimodal"
    assert captured_kwargs["attachments"] == [
        {"type": "image", "name": "ref.png", "url": "https://example.com/ref.png"}
    ]


@pytest.mark.asyncio
async def test_non_multimodal_mode_does_not_forward_runtime_attachments(monkeypatch):
    captured_kwargs = {}

    class FakeReActLoop:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)
            self.context_builder = type("ContextBuilder", (), {"memory_context": None, "board_context": None, "memory_file_path": None})()

        async def run(self, **kwargs):
            yield {"type": "complete", "data": {"answer": "ok"}}

    monkeypatch.setattr(react_agent_module, "ReActLoop", FakeReActLoop)
    agent = react_agent_module.ReActAgent()
    agent.enable_memory = False

    events = [
        event
        async for event in agent.analyze(
            user_query="普通助手问题",
            session_id="assistant_session_profile",
            manual_mode="assistant",
            attachments=[{"type": "image", "name": "ref.png", "url": "https://example.com/ref.png"}],
        )
    ]

    assert events[-1]["type"] == "complete"
    assert captured_kwargs["auto_profile"] is None
    assert captured_kwargs["attachments"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
conda run -n backend_py311 pytest backend/app/agent/session/social_session_storage_test.py -q
```

Expected: the new chart test fails because `auto_profile` is `None` and `attachments` is not forwarded for chart mode.

- [ ] **Step 3: Implement minimal code**

In `backend/app/agent/react_agent.py`, import the helper near other runtime imports:

```python
from app.agent.runtime.mode_capabilities import supports_native_multimodal
```

Change `_select_auto_profile()`:

```python
        if supports_native_multimodal(manual_mode):
            return "multimodal"
        return None
```

Change the `ReActLoop(...)` constructor argument:

```python
                attachments=runtime_attachments if supports_native_multimodal(manual_mode) else None,
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
conda run -n backend_py311 pytest backend/app/agent/session/social_session_storage_test.py backend/app/agent/runtime/mode_capabilities_test.py -q
```

Expected: PASS.

### Task 3: Build Native Image Blocks in Chart Runtime

**Files:**
- Modify: `backend/app/agent/runtime/agent_runtime.py`
- Modify: `backend/app/agent/runtime/multimodal.py`
- Create: `backend/app/agent/runtime/agent_runtime_multimodal_test.py`

- [ ] **Step 1: Write failing tests**

Add `backend/app/agent/runtime/agent_runtime_multimodal_test.py`:

```python
import pytest

from app.agent.runtime.agent_runtime import AgentRuntime, AgentRuntimeConfig
from app.agent.runtime.types import RunState


class FakePlanner:
    def __init__(self):
        self.calls = []

    async def think_and_action_streaming(self, **kwargs):
        self.calls.append(kwargs)
        yield {"type": "action", "data": {"action": {"type": "PLAIN_TEXT_REPLY", "answer": "ok"}}}


class FakeExecutor:
    tool_registry = {}


class FakeContextDiagnostics:
    def log_report(self, **kwargs):
        return None


@pytest.mark.asyncio
async def test_chart_mode_sends_image_attachment_as_native_content_blocks(monkeypatch, tmp_path):
    image_path = tmp_path / "ref.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    planner = FakePlanner()
    runtime = AgentRuntime.__new__(AgentRuntime)
    runtime.config = AgentRuntimeConfig(
        memory_manager=None,
        planner=planner,
        tool_executor=FakeExecutor(),
        context_builder=None,
        task_completion_guard=None,
        attachments=[{"type": "image", "name": "ref.png", "local_path": str(image_path), "mime_type": "image/png"}],
        auto_profile="multimodal",
    )
    runtime.planner = planner
    runtime.executor = FakeExecutor()
    runtime.context_diagnostics = FakeContextDiagnostics()

    state = RunState(session_id="chart_session", user_query="照这个图生成", mode="chart")
    context_result = {"system_prompt": "system", "user_conversation": "user text"}
    events = [
        event
        async for event in runtime._run_planner_stream(
            state,
            context_result,
            conversation_history=[],
            tool_schemas=[],
        )
    ]

    assert events[-1]["type"] == "_planner_done"
    user_content = planner.calls[0]["user_content"]
    assert user_content[0] == {"type": "text", "text": "user text"}
    assert user_content[1]["type"] == "image"
    assert user_content[1]["source"]["type"] == "base64"
    assert user_content[1]["source"]["media_type"] == "image/png"


@pytest.mark.asyncio
async def test_assistant_mode_does_not_send_image_attachment_as_native_blocks(tmp_path):
    image_path = tmp_path / "ref.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    planner = FakePlanner()
    runtime = AgentRuntime.__new__(AgentRuntime)
    runtime.config = AgentRuntimeConfig(
        memory_manager=None,
        planner=planner,
        tool_executor=FakeExecutor(),
        context_builder=None,
        task_completion_guard=None,
        attachments=[{"type": "image", "name": "ref.png", "local_path": str(image_path), "mime_type": "image/png"}],
    )
    runtime.planner = planner
    runtime.executor = FakeExecutor()
    runtime.context_diagnostics = FakeContextDiagnostics()

    state = RunState(session_id="assistant_session", user_query="看图", mode="assistant")
    context_result = {"system_prompt": "system", "user_conversation": "user text"}
    events = [
        event
        async for event in runtime._run_planner_stream(
            state,
            context_result,
            conversation_history=[],
            tool_schemas=[],
        )
    ]

    assert events[-1]["type"] == "_planner_done"
    assert planner.calls[0]["user_content"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
conda run -n backend_py311 pytest backend/app/agent/runtime/agent_runtime_multimodal_test.py -q
```

Expected: first test fails because chart mode does not currently build image blocks.

- [ ] **Step 3: Implement runtime helper usage**

In `backend/app/agent/runtime/agent_runtime.py`, import:

```python
from .mode_capabilities import supports_native_multimodal
```

Replace every `state.mode == "social" and attachments` check with:

```python
supports_native_multimodal(state.mode) and attachments
```

Update `_effective_attachments()` docstring:

```python
        """Current-run image attachments available to native multimodal calls."""
```

Update `_capture_multimodal_attachments()` to no-op outside native multimodal modes:

```python
        if not supports_native_multimodal(state.mode):
            return
```

In `backend/app/agent/runtime/multimodal.py`, update the module and function docstrings so they refer to native multimodal modes instead of social mode only.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
conda run -n backend_py311 pytest backend/app/agent/runtime/agent_runtime_multimodal_test.py backend/app/agent/runtime/mode_capabilities_test.py -q
```

Expected: PASS.

### Task 4: Update Chart Prompt Away From Legacy Image Analysis Tools

**Files:**
- Modify: `backend/app/agent/prompts/chart_prompt.py`
- Modify: `backend/app/agent/prompts/task_tool_registry_test.py`

- [ ] **Step 1: Write failing prompt tests**

In `backend/app/agent/prompts/task_tool_registry_test.py`, add:

```python
def test_chart_prompt_treats_uploaded_images_as_native_multimodal_input():
    prompt = build_chart_prompt(["create_drawio_board", "read_file", "analyze_image"])

    assert "本轮上传图片和画板截图已经作为原生多模态输入提供" in prompt
    assert "直接基于可见图片理解图表类型、样式、配色和布局" in prompt
    assert "read_file(path, analysis_type=\"chart\")" not in prompt
    assert "可调用 `analyze_image` 对该截图做视觉质量检查" not in prompt
```

Update any existing test that expects `"analyze_image"` in the chart snapshot instructions to expect the native multimodal wording instead.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
conda run -n backend_py311 pytest backend/app/agent/prompts/task_tool_registry_test.py -q
```

Expected: FAIL because the current prompt still tells the model to call `analyze_image` and `read_file(path, analysis_type="chart")`.

- [ ] **Step 3: Implement prompt changes**

In `backend/app/agent/prompts/chart_prompt.py`, replace the Draw.io screenshot validation block with:

```python
    if "create_drawio_board" in available_tools:
        prompt_parts.extend([
            "## Draw.io 画板截图与原生多模态输入\n\n",
            "- 用户在前端点击“确认画板修改”后，下一轮图表模式请求可能会附带当前画板 PNG 截图。\n",
            "- 本轮上传图片和画板截图已经作为原生多模态输入提供；直接基于可见图片理解图表类型、样式、配色和布局。\n",
            "- 截图只用于视觉质量检查和参考复刻；XML 仍然是权威状态，继续编辑画板必须以 `board_context.current_xml` 为准。\n",
            "- 只有当需要读取历史文件路径或工具生成的本地图片时，才调用 `read_file(as_multimodal_attachment=true)` 将图片挂载到下一轮原生多模态输入。\n\n",
        ])
```

Replace scene 3 with:

```python
        "**场景3：用户提供参考图片**（⭐ 看图生成图表）\n",
        "1. **直接理解参考图片**：本轮图片已作为原生多模态输入提供，直接观察图表类型、结构、样式、配色和布局\n",
        "2. **查询数据**：根据参考图表需求使用数据查询工具获取数据\n",
        "3. **分析数据结构**：使用 `read_data_registry(data_id, list_fields=true)` 查看字段\n",
        "4. **展示设计方案**：向用户展示基于参考图片的设计方案并等待确认\n",
        "5. **生成图表**：使用 `execute_echarts_python` 生成与参考图片相同风格的 ECharts 图表\n\n",
```

Replace the later checklist item:

```python
        "7. **看图生成**：用户提供参考图片时，直接基于本轮原生多模态输入理解图表样式，再基于用户数据生成相同风格的图表\n",
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
conda run -n backend_py311 pytest backend/app/agent/prompts/task_tool_registry_test.py -q
```

Expected: PASS.

### Task 5: Integration Verification

**Files:**
- Verify all files touched above.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
conda run -n backend_py311 pytest \
  backend/app/agent/runtime/mode_capabilities_test.py \
  backend/app/agent/runtime/agent_runtime_multimodal_test.py \
  backend/app/agent/session/social_session_storage_test.py \
  backend/app/agent/prompts/task_tool_registry_test.py \
  backend/app/services/llm_auto_profile_test.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Inspect diff**

Run:

```bash
git diff -- backend/app/agent/runtime/mode_capabilities.py backend/app/agent/runtime/mode_capabilities_test.py backend/app/agent/react_agent.py backend/app/agent/session/social_session_storage_test.py backend/app/agent/runtime/agent_runtime.py backend/app/agent/runtime/agent_runtime_multimodal_test.py backend/app/agent/runtime/multimodal.py backend/app/agent/prompts/chart_prompt.py backend/app/agent/prompts/task_tool_registry_test.py
```

Expected: diff only contains chart/native multimodal changes and tests. Existing unrelated working tree changes remain untouched.

- [ ] **Step 3: Commit implementation**

Run:

```bash
git add \
  backend/app/agent/runtime/mode_capabilities.py \
  backend/app/agent/runtime/mode_capabilities_test.py \
  backend/app/agent/react_agent.py \
  backend/app/agent/session/social_session_storage_test.py \
  backend/app/agent/runtime/agent_runtime.py \
  backend/app/agent/runtime/agent_runtime_multimodal_test.py \
  backend/app/agent/runtime/multimodal.py \
  backend/app/agent/prompts/chart_prompt.py \
  backend/app/agent/prompts/task_tool_registry_test.py
git commit -m "feat: enable native multimodal chart mode"
```

Expected: commit succeeds. If unrelated user edits exist in the same files, review hunks with `git diff` before staging and stage only the intended hunks.

## Self-Review

- Spec coverage: plan covers chart image attachments, Draw.io PNG snapshots, tool-emitted multimodal attachments, model profile selection, prompt changes, and non-native mode preservation.
- Placeholder scan: no placeholder markers remain.
- Type consistency: helper name is consistently `supports_native_multimodal`; the profile string is consistently `"multimodal"`; content blocks use existing `build_anthropic_user_content()` shapes.
