# Cognitive Map Graph Mode Editing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an embedded Graph Agent mode in the cognitive map panel so users can edit generated cognitive maps through multi-turn conversation while reusing existing tools and REST APIs.

**Architecture:** Add `graph` as a normal ReAct Agent mode with a dedicated prompt and a limited existing-tool whitelist. The cognitive map panel will host an embedded chat entry that sends requests through the existing `/api/agent/analyze` SSE path with `mode="graph"` and a compact `map_context`; graph changes are applied through existing cognitive map REST endpoints, not by direct JSON file edits.

**Tech Stack:** FastAPI/Python ReAct Agent, existing tool registry and prompt builder, Vue 3/Pinia frontend, existing `reactApi.analyze()` SSE client, current cognitive map REST API.

---

## File Structure

- Modify `backend/app/agent/prompts/tool_registry.py`
  - Add `GRAPH_TOOL_NAMES`, `GRAPH_TOOLS`, and graph ordering through existing insertion order.
  - Register `graph` in `get_tools_by_mode`.
- Create `backend/app/agent/prompts/graph_prompt.py`
  - Define Graph mode instructions, REST API usage rules, confirmation rules, and direct-file-edit restrictions.
- Modify `backend/app/agent/prompts/prompt_builder.py`
  - Add `graph` to `AgentMode`.
  - Import and route to `build_graph_prompt`.
- Modify `backend/app/agent/context/context_builder.py`
  - Preserve `map_context` for `graph` mode.
  - Add a compact graph map context summary to the user conversation.
  - Add system guidance that graph mode receives cognitive-map UI context.
- Modify `backend/app/agent/react_agent.py`
  - Pass `map_context` into `context_builder` for `graph` mode, not only query mode.
- Modify `backend/app/routers/agent.py`
  - Forward `request.map_context` when `request.mode == "graph"`.
- Test `backend/tests/test_graph_mode_prompt_and_context.py`
  - Assert graph tools, graph prompt routing, context policy, and router source contract.
- Modify `frontend/src/stores/reactStore.js`
  - Add `graph` to `VALID_MODES` and `modeStates`.
  - Allow `options.mapContext` to be sent for graph mode.
- Modify `frontend/src/components/InputBox.vue`
  - Add `graph` to local valid modes only if needed for store compatibility; do not expose graph in the global mode selector.
- Create `frontend/src/components/management/CognitiveMapGraphChat.vue`
  - Embedded chat panel for current cognitive map.
  - Builds compact `mapContext` from current map and selected graph item.
  - Calls `store.analyze(query, { agentMode: 'graph', mapContext, skipAutoFollowup: true })`.
- Modify `frontend/src/components/management/CognitiveMapPanel.vue`
  - Add a `对话编辑` drawer tab.
  - Render `CognitiveMapGraphChat` when a current map exists.
  - Refresh graph after Graph chat completion.
- Test `frontend/src/stores/react-store-graph-mode.test.mjs`
  - Static and light runtime checks for graph mode store behavior and request propagation.
- Test `frontend/src/components/management/cognitive-map-graph-chat-contract.test.mjs`
  - Static contract checks for Graph chat embedding, mode usage, and context shape.

## Task 1: Backend Graph Tool Registry

**Files:**
- Modify: `backend/app/agent/prompts/tool_registry.py`
- Test: `backend/tests/test_graph_mode_prompt_and_context.py`

- [ ] **Step 1: Write failing registry tests**

Create `backend/tests/test_graph_mode_prompt_and_context.py` with:

```python
from app.agent.prompts.tool_registry import get_tools_by_mode, get_tool_order_by_mode


def test_graph_mode_exposes_existing_safe_tools_only():
    tools = get_tools_by_mode("graph")

    assert list(tools.keys()) == [
        "cognitive_map_guidance",
        "read_file",
        "grep",
        "list_directory",
        "search_files",
        "execute_python",
    ]
    assert "edit_file" not in tools
    assert "write_file" not in tools
    assert "bash" not in tools


def test_graph_mode_tool_order_matches_registry_order():
    assert get_tool_order_by_mode("graph") == [
        "cognitive_map_guidance",
        "read_file",
        "grep",
        "list_directory",
        "search_files",
        "execute_python",
    ]
```

- [ ] **Step 2: Run registry tests to verify failure**

Run:

```bash
conda run -n backend_py311 pytest backend/tests/test_graph_mode_prompt_and_context.py -q
```

Expected: FAIL with `Unknown mode` behavior or graph tools missing.

- [ ] **Step 3: Add graph tool registry entries**

In `backend/app/agent/prompts/tool_registry.py`, add after `OPS_TOOL_NAMES`:

```python
# ===== 认知地图图谱编辑模式工具 =====
GRAPH_TOOL_NAMES = {
    "cognitive_map_guidance",
    "read_file",
    "grep",
    "list_directory",
    "search_files",
    "execute_python",
}
```

Add after `OPS_TOOLS = _build_tool_dict(OPS_TOOL_NAMES)`:

```python
GRAPH_TOOLS = _build_tool_dict(GRAPH_TOOL_NAMES)
```

Add `"graph": GRAPH_TOOLS,` to the `mode_tools_map` in `get_tools_by_mode`.

Because `get_tool_order_by_mode()` derives from `get_tools_by_mode(mode).keys()`, do not add a separate order constant.

- [ ] **Step 4: Run registry tests**

Run:

```bash
conda run -n backend_py311 pytest backend/tests/test_graph_mode_prompt_and_context.py::test_graph_mode_exposes_existing_safe_tools_only backend/tests/test_graph_mode_prompt_and_context.py::test_graph_mode_tool_order_matches_registry_order -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add backend/app/agent/prompts/tool_registry.py backend/tests/test_graph_mode_prompt_and_context.py
git commit -m "feat: add graph mode tool registry"
```

## Task 2: Backend Graph Prompt

**Files:**
- Create: `backend/app/agent/prompts/graph_prompt.py`
- Modify: `backend/app/agent/prompts/prompt_builder.py`
- Test: `backend/tests/test_graph_mode_prompt_and_context.py`

- [ ] **Step 1: Add failing prompt tests**

Append to `backend/tests/test_graph_mode_prompt_and_context.py`:

```python
from app.agent.prompts.prompt_builder import build_react_system_prompt


def test_graph_prompt_routes_from_prompt_builder():
    prompt = build_react_system_prompt("graph")

    assert "认知地图图谱编辑 Agent" in prompt
    assert "POST   /api/cognitive-maps/{map_id}/entities" in prompt
    assert "PATCH  /api/cognitive-maps/{map_id}/relations/{relation_id}" in prompt
    assert "禁止默认直接编辑 `extraction.json`" in prompt
    assert "execute_python" in prompt


def test_graph_prompt_rejects_unavailable_write_tools():
    prompt = build_react_system_prompt("graph", available_tools=["read_file", "write_file", "edit_file", "execute_python"])

    assert "execute_python" in prompt
    assert "read_file" in prompt
    assert "write_file" not in prompt
    assert "edit_file" not in prompt
```

- [ ] **Step 2: Run prompt tests to verify failure**

Run:

```bash
conda run -n backend_py311 pytest backend/tests/test_graph_mode_prompt_and_context.py::test_graph_prompt_routes_from_prompt_builder backend/tests/test_graph_mode_prompt_and_context.py::test_graph_prompt_rejects_unavailable_write_tools -q
```

Expected: FAIL because `graph` is not routed by the prompt builder.

- [ ] **Step 3: Create graph prompt builder**

Create `backend/app/agent/prompts/graph_prompt.py`:

```python
from __future__ import annotations

from typing import List, Optional


def build_graph_prompt(
    available_tools: List[str],
    memory_context: Optional[str] = None,
    memory_file_path: Optional[str] = None,
) -> str:
    prompt_parts: list[str] = []

    if memory_context:
        prompt_parts.append("## 历史记忆\n")
        prompt_parts.append(memory_context.strip())
        prompt_parts.append("\n\n")

    prompt_parts.append(
        "你是认知地图图谱编辑 Agent，负责通过多轮对话帮助用户修正当前认知地图。\n"
        "你只处理当前请求 map_context.active_map_id 指向的认知地图；如果没有当前地图，要求用户先选择地图。\n\n"
        "## 可用工具\n"
        f"{', '.join(available_tools)}\n\n"
        "## 工作原则\n"
        "1. 结合对话历史和 map_context.selected_item 解析“它”“这个节点”“这条关系”等指代。\n"
        "2. 修改前先说明拟执行变更；目标不唯一时先列候选并追问。\n"
        "3. 用户确认后，优先用 execute_python 调用现有认知地图 REST API。\n"
        "4. 禁止默认直接编辑 `extraction.json`、`evaluation.json`、`map.json`、`files.json`、`build_runs.json`。\n"
        "5. 只有 REST API 不支持目标操作且用户明确同意风险时，才允许讨论文件级兜底修复。\n"
        "6. 修改完成后返回变更摘要、影响的实体/关系，以及是否需要重新发布。\n\n"
        "## 支持的第一阶段编辑意图\n"
        "- merge_entities：合并实体。\n"
        "- update_entity：修改实体名称、别名、描述、属性或 review_status。\n"
        "- create_relation：新增关系。\n"
        "- update_relation：修改关系类型、描述、属性或 review_status。\n"
        "- delete_relation：删除关系。\n\n"
        "## 必须优先使用的现有 API\n"
        "GET    /api/cognitive-maps/{map_id}/entities\n"
        "POST   /api/cognitive-maps/{map_id}/entities\n"
        "PATCH  /api/cognitive-maps/{map_id}/entities/{entity_id}\n"
        "POST   /api/cognitive-maps/{map_id}/entities/{entity_id}/merge\n"
        "DELETE /api/cognitive-maps/{map_id}/entities/{entity_id}\n"
        "GET    /api/cognitive-maps/{map_id}/relations\n"
        "POST   /api/cognitive-maps/{map_id}/relations\n"
        "PATCH  /api/cognitive-maps/{map_id}/relations/{relation_id}\n"
        "DELETE /api/cognitive-maps/{map_id}/relations/{relation_id}\n"
        "GET    /api/cognitive-maps/{map_id}/evidence\n"
        "GET    /api/cognitive-maps/{map_id}/evaluation\n\n"
        "## execute_python 调用约束\n"
        "使用 Python 标准库 urllib.request 或项目内已有 HTTP 客户端调用上述 API。\n"
        "内部 API 地址优先读取环境变量 INTERNAL_API_BASE_URL；没有配置时使用 http://127.0.0.1:8000/api。\n"
        "处理 JSON 响应和 HTTP 错误码，不要吞掉错误。\n"
    )

    if memory_file_path:
        prompt_parts.append(f"\n## 记忆文件\n当前模式记忆文件路径：`{memory_file_path}`。\n")

    return "".join(prompt_parts)
```

- [ ] **Step 4: Route graph prompt**

In `backend/app/agent/prompts/prompt_builder.py`:

Add import:

```python
from .graph_prompt import build_graph_prompt
```

Add `"graph",` to `AgentMode`.

Add before `elif mode == "deliberation_meteorology":`

```python
    elif mode == "graph":
        return build_graph_prompt(filtered_tools, memory_context, memory_file_path)
```

- [ ] **Step 5: Run prompt tests**

Run:

```bash
conda run -n backend_py311 pytest backend/tests/test_graph_mode_prompt_and_context.py::test_graph_prompt_routes_from_prompt_builder backend/tests/test_graph_mode_prompt_and_context.py::test_graph_prompt_rejects_unavailable_write_tools -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add backend/app/agent/prompts/graph_prompt.py backend/app/agent/prompts/prompt_builder.py backend/tests/test_graph_mode_prompt_and_context.py
git commit -m "feat: add graph mode prompt"
```

## Task 3: Backend Graph Map Context Injection

**Files:**
- Modify: `backend/app/agent/context/context_builder.py`
- Modify: `backend/app/agent/react_agent.py`
- Modify: `backend/app/routers/agent.py`
- Test: `backend/tests/test_graph_mode_prompt_and_context.py`

- [ ] **Step 1: Add failing context tests**

Append to `backend/tests/test_graph_mode_prompt_and_context.py`:

```python
from pathlib import Path

from app.agent.context.context_builder import ContextBuilder


def test_graph_mode_preserves_map_context_and_builds_summary():
    builder = ContextBuilder()
    builder.set_mode("graph")
    builder.map_context = {
        "active_map_id": "map_123",
        "active_map_name": "站点故障图谱",
        "selected_item": {
            "kind": "relation",
            "id": "relation_abc",
            "name": "零点漂移 -> indicates -> 零漂异常",
        },
        "visible_entity_ids": ["entity_a", "entity_b", "entity_c"],
        "visible_relation_ids": ["relation_abc"],
        "entity_count": 3,
        "relation_count": 1,
    }

    builder._apply_mode_context_policy("graph")
    summary = builder._build_graph_map_context_user_summary()

    assert builder.map_context is not None
    assert "当前认知地图上下文" in summary
    assert "map_123" in summary
    assert "站点故障图谱" in summary
    assert "relation_abc" in summary
    assert "visible_entity_ids=3" in summary


def test_non_graph_non_query_modes_strip_map_context():
    builder = ContextBuilder()
    builder.set_mode("assistant")
    builder.map_context = {"active_map_id": "map_123"}

    builder._apply_mode_context_policy("assistant")

    assert builder.map_context is None


def test_router_forwards_map_context_for_graph_mode():
    source = Path("backend/app/routers/agent.py").read_text(encoding="utf-8")

    assert 'if request.mode in {"query", "graph"} and request.map_context:' in source
    assert 'analyze_kwargs["map_context"] = request.map_context' in source


def test_react_agent_sets_map_context_for_graph_mode():
    source = Path("backend/app/agent/react_agent.py").read_text(encoding="utf-8")

    assert 'if manual_mode in {"query", "graph"} and map_context:' in source
    assert "react_loop.context_builder.map_context = map_context" in source
```

- [ ] **Step 2: Run context tests to verify failure**

Run:

```bash
conda run -n backend_py311 pytest backend/tests/test_graph_mode_prompt_and_context.py::test_graph_mode_preserves_map_context_and_builds_summary backend/tests/test_graph_mode_prompt_and_context.py::test_router_forwards_map_context_for_graph_mode backend/tests/test_graph_mode_prompt_and_context.py::test_react_agent_sets_map_context_for_graph_mode -q
```

Expected: FAIL because graph map context is not preserved or forwarded.

- [ ] **Step 3: Preserve graph map context in context policy**

In `backend/app/agent/context/context_builder.py`, change:

```python
        if mode != "query" and self.map_context is not None:
```

to:

```python
        if mode not in {"query", "graph"} and self.map_context is not None:
```

Update the log event string from `"non_query_map_context_stripped"` to:

```python
                "mode_without_map_context_stripped",
```

- [ ] **Step 4: Add graph context summary method**

In `backend/app/agent/context/context_builder.py`, after `_build_map_context_user_summary`, add:

```python
    def _build_graph_map_context_user_summary(self) -> str:
        """Build a compact current-turn summary for cognitive-map graph editing."""
        if self.current_mode != "graph" or not isinstance(self.map_context, dict):
            return ""

        active_map_id = self.map_context.get("active_map_id") or self.map_context.get("map_id")
        if not active_map_id:
            return "## 当前认知地图上下文\n未收到 active_map_id；请先在认知地图面板选择地图。"

        lines = ["## 当前认知地图上下文", f"active_map_id={active_map_id}"]
        active_map_name = self.map_context.get("active_map_name") or self.map_context.get("map_name")
        if active_map_name:
            lines.append(f"active_map_name={active_map_name}")

        selected_item = self.map_context.get("selected_item")
        if isinstance(selected_item, dict):
            item_kind = selected_item.get("kind") or "unknown"
            item_id = selected_item.get("id") or selected_item.get("entity_id") or selected_item.get("relation_id") or ""
            item_name = selected_item.get("name") or selected_item.get("label") or ""
            lines.append(f"selected_item kind={item_kind} id={item_id} name={item_name}")

        visible_entity_ids = self.map_context.get("visible_entity_ids") or []
        visible_relation_ids = self.map_context.get("visible_relation_ids") or []
        if isinstance(visible_entity_ids, list):
            lines.append(f"visible_entity_ids={len(visible_entity_ids)}")
        if isinstance(visible_relation_ids, list):
            lines.append(f"visible_relation_ids={len(visible_relation_ids)}")

        entity_count = self.map_context.get("entity_count")
        relation_count = self.map_context.get("relation_count")
        if entity_count is not None:
            lines.append(f"entity_count={entity_count}")
        if relation_count is not None:
            lines.append(f"relation_count={relation_count}")

        return "\n".join(lines)
```

- [ ] **Step 5: Include graph summary in user conversation**

In `backend/app/agent/context/context_builder.py`, wherever `_build_map_context_user_summary()` is appended to user-facing sections, add graph context summary immediately after it:

```python
            graph_map_context_summary = self._build_graph_map_context_user_summary()
            if graph_map_context_summary:
                sections.append(graph_map_context_summary)
```

If there are two occurrences for regular and compressed conversation paths, update both occurrences.

- [ ] **Step 6: Add graph system context note**

In `_build_system_prompt`, after the query GIS section, add:

```python
        if self.current_mode == "graph" and self.map_context:
            sections.append(
                "## 认知地图图谱编辑上下文\n"
                "- 当前请求来自认知地图面板右侧的对话编辑入口。\n"
                "- 用户可能用“这个节点”“这条关系”“刚才那个实体”等表达指代，优先结合用户消息中的“当前认知地图上下文”。\n"
                "- 修改图谱时默认通过认知地图 REST API 完成，不要直接改内部 JSON 文件。"
            )
```

- [ ] **Step 7: Forward graph map context in ReActAgent**

In `backend/app/agent/react_agent.py`, change:

```python
            if manual_mode == "query" and map_context:
```

to:

```python
            if manual_mode in {"query", "graph"} and map_context:
```

Keep the existing `react_loop.context_builder.map_context = map_context`.

- [ ] **Step 8: Forward graph map context in router**

In `backend/app/routers/agent.py`, change:

```python
        if request.mode == "query" and request.map_context:
```

to:

```python
        if request.mode in {"query", "graph"} and request.map_context:
```

Do not change map scene metadata persistence; leave query-only map scene metadata behavior intact unless a test explicitly fails.

- [ ] **Step 9: Run context tests**

Run:

```bash
conda run -n backend_py311 pytest backend/tests/test_graph_mode_prompt_and_context.py -q
```

Expected: PASS.

- [ ] **Step 10: Commit**

Run:

```bash
git add backend/app/agent/context/context_builder.py backend/app/agent/react_agent.py backend/app/routers/agent.py backend/tests/test_graph_mode_prompt_and_context.py
git commit -m "feat: inject graph map context"
```

## Task 4: Frontend Store Graph Mode Support

**Files:**
- Modify: `frontend/src/stores/reactStore.js`
- Modify: `frontend/src/components/InputBox.vue`
- Test: `frontend/src/stores/react-store-graph-mode.test.mjs`

- [ ] **Step 1: Write failing frontend store contract tests**

Create `frontend/src/stores/react-store-graph-mode.test.mjs`:

```javascript
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const storeSource = readFileSync(new URL('./reactStore.js', import.meta.url), 'utf8')
const inputBoxSource = readFileSync(new URL('../components/InputBox.vue', import.meta.url), 'utf8')

test('react store declares graph as a valid mode with isolated state', () => {
  assert.match(storeSource, /const VALID_MODES = \[[^\]]*'graph'[^\]]*\]/)
  assert.match(storeSource, /modeStates:\s*\{[\s\S]*graph:\s*createEmptyModeState\(\)/)
})

test('react store sends explicit graph map context to agent api', () => {
  assert.match(storeSource, /mapContext\s*=\s*actualMode === 'graph'\s*\?\s*options\.mapContext/)
  assert.match(storeSource, /\.\.\.\(mapContext !== null \? \{ mapContext \} : \{\}\)/)
})

test('input box accepts graph as a valid internal mode without changing selector markup', () => {
  assert.match(inputBoxSource, /const validAgentModes = \[[^\]]*'graph'[^\]]*\]/)
})
```

- [ ] **Step 2: Run frontend store tests to verify failure**

Run:

```bash
node --test frontend/src/stores/react-store-graph-mode.test.mjs
```

Expected: FAIL because `graph` is not in frontend modes and explicit graph map context is not sent.

- [ ] **Step 3: Add graph to frontend modes**

In `frontend/src/stores/reactStore.js`, change:

```javascript
const VALID_MODES = ['assistant', 'expert', 'query', 'report', 'chart', 'ops']
```

to:

```javascript
const VALID_MODES = ['assistant', 'expert', 'query', 'report', 'chart', 'ops', 'graph']
```

Add to `modeStates`:

```javascript
        graph: createEmptyModeState()
```

- [ ] **Step 4: Allow explicit graph map context**

In `frontend/src/stores/reactStore.js`, inside `startAnalysis`, destructure `mapContext`:

```javascript
        mapContext: explicitMapContext = null,
```

from `options`.

Replace:

```javascript
        const mapContext = actualMode === 'query' ? buildMapContext(sessionState) : null
```

with:

```javascript
        const mapContext = actualMode === 'query'
          ? buildMapContext(sessionState)
          : actualMode === 'graph'
            ? explicitMapContext
            : null
```

- [ ] **Step 5: Add graph to InputBox internal valid modes**

In `frontend/src/components/InputBox.vue`, change:

```javascript
const validAgentModes = ['assistant', 'expert', 'query', 'report', 'chart', 'ops']
```

to:

```javascript
const validAgentModes = ['assistant', 'expert', 'query', 'report', 'chart', 'ops', 'graph']
```

Do not add a Graph button to `AgentModeSelector.vue`.

- [ ] **Step 6: Run frontend store tests**

Run:

```bash
node --test frontend/src/stores/react-store-graph-mode.test.mjs
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add frontend/src/stores/reactStore.js frontend/src/components/InputBox.vue frontend/src/stores/react-store-graph-mode.test.mjs
git commit -m "feat: add frontend graph mode state"
```

## Task 5: Embedded Cognitive Map Graph Chat Component

**Files:**
- Create: `frontend/src/components/management/CognitiveMapGraphChat.vue`
- Test: `frontend/src/components/management/cognitive-map-graph-chat-contract.test.mjs`

- [ ] **Step 1: Write failing component contract tests**

Create `frontend/src/components/management/cognitive-map-graph-chat-contract.test.mjs`:

```javascript
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const source = readFileSync(new URL('./CognitiveMapGraphChat.vue', import.meta.url), 'utf8')

test('graph chat sends graph mode analysis with cognitive map context', () => {
  assert.match(source, /agentMode:\s*'graph'/)
  assert.match(source, /mapContext:\s*buildGraphMapContext\(\)/)
  assert.match(source, /active_map_id:\s*props\.currentMap\?\.id/)
  assert.match(source, /selected_item:/)
})

test('graph chat disables send without current map or input', () => {
  assert.match(source, /:disabled="!canSend"/)
  assert.match(source, /const canSend = computed/)
  assert.match(source, /props\.currentMap\?\.id/)
})
```

- [ ] **Step 2: Run component contract tests to verify failure**

Run:

```bash
node --test frontend/src/components/management/cognitive-map-graph-chat-contract.test.mjs
```

Expected: FAIL because the component does not exist.

- [ ] **Step 3: Create Graph chat component**

Create `frontend/src/components/management/CognitiveMapGraphChat.vue`:

```vue
<template>
  <section class="graph-chat-panel">
    <div class="graph-chat-header">
      <strong>对话编辑</strong>
      <span>{{ currentMap?.name || '未选择地图' }}</span>
    </div>

    <div class="graph-chat-messages">
      <div
        v-for="message in graphMessages"
        :key="message.id"
        class="graph-chat-message"
        :class="`message-${message.type}`"
      >
        <span class="message-role">{{ roleLabel(message.type) }}</span>
        <p>{{ message.content }}</p>
      </div>
      <div v-if="graphMessages.length === 0" class="graph-chat-empty">
        选择图中实体或关系后，可直接描述要合并、修正或删除的内容。
      </div>
    </div>

    <form class="graph-chat-input" @submit.prevent="sendGraphMessage">
      <textarea
        v-model="draft"
        :disabled="store.currentState?.isAnalyzing"
        rows="3"
        placeholder="例如：把零漂和零点漂移合并，保留零点漂移这个名称"
      ></textarea>
      <button type="submit" :disabled="!canSend">
        {{ store.currentState?.isAnalyzing ? '处理中' : '发送' }}
      </button>
    </form>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useReactStore } from '@/stores/reactStore'

const props = defineProps({
  currentMap: { type: Object, default: null },
  selectedGraphItem: { type: Object, default: null },
  entities: { type: Array, default: () => [] },
  relations: { type: Array, default: () => [] }
})

const emit = defineEmits(['graph-updated'])

const store = useReactStore()
const draft = ref('')

const graphMessages = computed(() => {
  const state = store.modeStates.graph
  return (state?.messages || []).filter(message => (
    message.type === 'user' || message.type === 'agent' || message.type === 'final'
  ))
})

const canSend = computed(() => (
  !!props.currentMap?.id &&
  draft.value.trim().length > 0 &&
  !store.modeStates.graph?.isAnalyzing
))

const selectedItemPayload = () => {
  const item = props.selectedGraphItem
  if (!item?.kind || !item?.raw) return null
  const raw = item.raw
  return {
    kind: item.kind,
    id: item.kind === 'relation'
      ? raw.relation_id || raw.id
      : raw.entity_id || raw.id,
    name: item.kind === 'relation'
      ? `${raw.source_name || raw.source_entity_id || ''} -> ${raw.relation_type || raw.type || ''} -> ${raw.target_name || raw.target_entity_id || ''}`.trim()
      : raw.name || raw.canonical_name || ''
  }
}

const buildGraphMapContext = () => ({
  active_map_id: props.currentMap?.id || null,
  active_map_name: props.currentMap?.name || '',
  selected_item: selectedItemPayload(),
  visible_entity_ids: props.entities
    .map(entity => entity.entity_id || entity.id)
    .filter(Boolean)
    .slice(0, 200),
  visible_relation_ids: props.relations
    .map(relation => relation.relation_id || relation.id)
    .filter(Boolean)
    .slice(0, 200),
  entity_count: props.entities.length,
  relation_count: props.relations.length
})

const roleLabel = (type) => {
  if (type === 'user') return '用户'
  if (type === 'final' || type === 'agent') return 'Graph'
  return type
}

const sendGraphMessage = async () => {
  if (!canSend.value) return
  const query = draft.value.trim()
  draft.value = ''
  await store.analyze(query, {
    agentMode: 'graph',
    mapContext: buildGraphMapContext(),
    skipAutoFollowup: true
  })
  emit('graph-updated')
}
</script>

<style scoped>
.graph-chat-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 320px;
}

.graph-chat-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
}

.graph-chat-header span {
  color: #64748b;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.graph-chat-messages {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 160px;
  max-height: 360px;
  overflow: auto;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 10px;
  background: #f8fafc;
}

.graph-chat-message {
  display: grid;
  gap: 4px;
  font-size: 13px;
}

.message-role {
  color: #475569;
  font-weight: 600;
}

.graph-chat-message p {
  margin: 0;
  white-space: pre-wrap;
  line-height: 1.5;
}

.graph-chat-empty {
  color: #64748b;
  font-size: 13px;
}

.graph-chat-input {
  display: grid;
  gap: 8px;
}

.graph-chat-input textarea {
  width: 100%;
  resize: vertical;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  padding: 8px;
  font-size: 13px;
}

.graph-chat-input button {
  justify-self: end;
  border: 1px solid #2563eb;
  border-radius: 6px;
  background: #2563eb;
  color: white;
  padding: 6px 14px;
  cursor: pointer;
}

.graph-chat-input button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}
</style>
```

- [ ] **Step 4: Run component contract tests**

Run:

```bash
node --test frontend/src/components/management/cognitive-map-graph-chat-contract.test.mjs
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add frontend/src/components/management/CognitiveMapGraphChat.vue frontend/src/components/management/cognitive-map-graph-chat-contract.test.mjs
git commit -m "feat: add cognitive map graph chat"
```

## Task 6: Embed Graph Chat in Cognitive Map Panel

**Files:**
- Modify: `frontend/src/components/management/CognitiveMapPanel.vue`
- Test: `frontend/src/components/management/cognitive-map-graph-chat-contract.test.mjs`

- [ ] **Step 1: Add failing embed contract test**

Append to `frontend/src/components/management/cognitive-map-graph-chat-contract.test.mjs`:

```javascript
const panelSource = readFileSync(new URL('./CognitiveMapPanel.vue', import.meta.url), 'utf8')

test('cognitive map panel embeds graph chat as a drawer tab', () => {
  assert.match(panelSource, /import CognitiveMapGraphChat from '\.\/CognitiveMapGraphChat\.vue'/)
  assert.match(panelSource, /inspectorTab === 'graph-chat'/)
  assert.match(panelSource, /<CognitiveMapGraphChat/)
  assert.match(panelSource, /@graph-updated="handleGraphChatUpdated"/)
})
```

- [ ] **Step 2: Run embed contract test to verify failure**

Run:

```bash
node --test frontend/src/components/management/cognitive-map-graph-chat-contract.test.mjs
```

Expected: FAIL because panel does not embed Graph chat.

- [ ] **Step 3: Import Graph chat component**

In `frontend/src/components/management/CognitiveMapPanel.vue`, add:

```javascript
import CognitiveMapGraphChat from './CognitiveMapGraphChat.vue'
```

near the existing imports.

- [ ] **Step 4: Add drawer tree tab**

In the drawer tree near the existing `构建与文件` and `Agent接入` buttons, add:

```vue
                  <button
                    class="tree-node"
                    type="button"
                    :class="{ active: inspectorTab === 'graph-chat' }"
                    @click="openManagementDrawer('graph-chat')"
                  >
                    对话编辑
                  </button>
```

- [ ] **Step 5: Render Graph chat section**

In the drawer body section switch where `inspectorTab` renders build, binding, entities, relations, and evidence sections, add:

```vue
                  <section v-else-if="inspectorTab === 'graph-chat'" class="inspector-section">
                    <CognitiveMapGraphChat
                      :current-map="currentMap"
                      :selected-graph-item="selectedGraphItem"
                      :entities="entities"
                      :relations="relations"
                      @graph-updated="handleGraphChatUpdated"
                    />
                  </section>
```

- [ ] **Step 6: Add refresh handler**

In the `<script setup>` area of `CognitiveMapPanel.vue`, add:

```javascript
const handleGraphChatUpdated = async () => {
  if (!currentMap.value?.id) return
  await refreshCurrentMapData()
  await refreshMaps()
}
```

- [ ] **Step 7: Run embed contract test**

Run:

```bash
node --test frontend/src/components/management/cognitive-map-graph-chat-contract.test.mjs
```

Expected: PASS.

- [ ] **Step 8: Commit**

Run:

```bash
git add frontend/src/components/management/CognitiveMapPanel.vue frontend/src/components/management/cognitive-map-graph-chat-contract.test.mjs
git commit -m "feat: embed graph chat in cognitive map panel"
```

## Task 7: Integration Verification

**Files:**
- Verify only; modify only if tests reveal a defect in files touched by prior tasks.

- [ ] **Step 1: Run backend graph tests**

Run:

```bash
conda run -n backend_py311 pytest backend/tests/test_graph_mode_prompt_and_context.py -q
```

Expected: PASS.

- [ ] **Step 2: Run related backend prompt tests**

Run:

```bash
conda run -n backend_py311 pytest backend/app/agent/prompts/task_tool_registry_test.py backend/tests/test_agent_map_context.py -q
```

Expected: PASS. If `backend/tests/test_agent_map_context.py` does not exist as a source file despite pycache entries, run only `backend/app/agent/prompts/task_tool_registry_test.py`.

- [ ] **Step 3: Run frontend graph tests**

Run:

```bash
node --test frontend/src/stores/react-store-graph-mode.test.mjs frontend/src/components/management/cognitive-map-graph-chat-contract.test.mjs
```

Expected: PASS.

- [ ] **Step 4: Build frontend**

Run:

```bash
cd frontend
npm run build
```

Expected: Vite build completes without Vue compile errors.

- [ ] **Step 5: Manual smoke test**

Start backend and frontend using the project’s normal development commands. Use the configured conda environment:

```bash
conda activate /root/miniconda3/envs/backend_py311
```

Then open the app, navigate to the cognitive map panel, select a map, open `对话编辑`, and send:

```text
请读取当前地图上下文，告诉我当前选中的实体或关系是什么。不要修改图谱。
```

Expected:

- The request uses `mode: "graph"`.
- The request body includes `map_context.active_map_id`.
- The Agent response references the current map context.
- No entity or relation is modified.

- [ ] **Step 6: Final commit if verification fixes were needed**

If verification required code fixes, commit them:

```bash
git add <changed-files>
git commit -m "fix: stabilize graph mode integration"
```

If no fixes were needed, do not create an empty commit.

## Self-Review

- Spec coverage:
  - Graph mode added through tool registry and prompt: Tasks 1 and 2.
  - Existing tools reused without new graph edit tools: Task 1.
  - REST API-first editing rules and no direct JSON editing: Task 2.
  - `map_context` for graph mode: Tasks 3 and 4.
  - Cognitive map panel right-side entry: Tasks 5 and 6.
  - Graph mode not shown in global mode selector: Task 4 explicitly avoids `AgentModeSelector.vue`.
  - Tests and verification: Task 7.
- Placeholder scan:
  - No placeholder markers or unspecified implementation steps remain.
- Type consistency:
  - Frontend uses `mapContext` option in store and sends `map_context` through existing `reactApi.analyze()`.
  - Backend uses existing `map_context` request field and `ContextBuilder.map_context`.
  - Component props use `currentMap`, `selectedGraphItem`, `entities`, and `relations`, matching current `CognitiveMapPanel.vue` state names.
