# execute_echarts_python Schema Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move every `execute_echarts_python` calling constraint out of the chart-mode system prompt and expose the contract through the native tool schema plus a progressively read manual.

**Architecture:** Keep non-negotiable data-access and stdout rules in `ExecuteEChartsPythonTool.get_function_schema()` so they are always visible at tool-selection time. Put detailed workflows and examples in a dedicated Markdown manual referenced by the schema, while leaving only chart design workflow and tool selection in `build_chart_prompt()`.

**Tech Stack:** Python 3.11, pytest, Markdown tool documentation, conda environment `/root/miniconda3/envs/backend_py311`

---

### Task 1: Add red contract tests

**Files:**
- Create: `backend/app/tools/utility/execute_echarts_python_schema_spec.py`
- Create: `backend/app/agent/prompts/chart_prompt_contract_spec.py`

- [ ] **Step 1: Strengthen the tool schema test**

Add `test_execute_echarts_python_schema_owns_data_access_contract` with assertions against the combined tool and `code` descriptions:

```python
contract = " ".join([
    schema["description"],
    schema["parameters"]["properties"]["code"]["description"],
])
assert "backend/app/tools/utility/execute_echarts_python_manual.md" in contract
assert "read_file" in contract
assert "read_data_registry" in contract
assert "get_raw_data(data_id)" in contract
assert "open()" in contract
assert "pathlib" in contract
assert "物理文件路径" in contract
```

- [ ] **Step 2: Replace the obsolete chart-prompt example assertion**

Add a chart-prompt boundary test:

```python
def test_chart_prompt_selects_echarts_tool_without_embedding_its_call_contract():
    prompt = build_chart_prompt(["execute_echarts_python", "read_file"])

    assert "execute_echarts_python" in prompt
    assert "get_raw_data(" not in prompt
    assert "backend_data_registry/datasets" not in prompt
    assert "stdout 每行" not in prompt
    assert "execute_echarts_python 图表生成示例" not in prompt
    assert "series 在顶层" not in prompt
```

- [ ] **Step 3: Run the focused tests and verify RED**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q \
  backend/app/tools/utility/execute_echarts_python_schema_spec.py::test_execute_echarts_python_schema_owns_data_access_contract \
  backend/app/agent/prompts/chart_prompt_contract_spec.py::test_chart_prompt_selects_echarts_tool_without_embedding_its_call_contract
```

Expected: both tests fail because the schema lacks the data-access/manual contract and the chart prompt still embeds it.

### Task 2: Publish the tool-owned contract

**Files:**
- Create: `backend/app/tools/utility/execute_echarts_python_manual.md`
- Modify: `backend/app/tools/utility/execute_python_tool.py:2595-2627`
- Test: `backend/app/tools/utility/execute_echarts_python_schema_spec.py`

- [ ] **Step 1: Create the dedicated manual**

Write a focused manual with these concrete sections:

```markdown
# execute_echarts_python 工具指导手册
## 使用边界
## 标准数据访问流程
## 执行环境与跨调用复用
## ECharts stdout 协议
## 最小正确示例
## 常见错误
```

The data-flow section must show `read_data_registry(data_id=...)` before execution and `records = get_raw_data("...")` inside Python. The error section must reject `open()`, `pathlib.Path.read_text()` and guessed DataRegistry paths. The output section must cover pure JSON lines, top-level `series`, multiple charts, `expected_charts`, and JSON-serializable options.

- [ ] **Step 2: Add the core rules to the schema**

Update the schema description to include this contract, preserving existing rendering guidance:

```python
"首次使用或不熟悉完整契约时，必须先调用 read_file 阅读 "
"backend/app/tools/utility/execute_echarts_python_manual.md。"
"使用 DataRegistry 数据前必须先调用 read_data_registry(data_id=...) 读取可计算快照，"
"代码中再通过系统注入的 get_raw_data(data_id) 获取数据。"
"禁止使用 open()、pathlib 或猜测 DataRegistry 物理文件路径直接读取数据。"
```

Repeat the `get_raw_data(data_id)` requirement and physical-path prohibition in the `code` parameter description, while retaining the one-pure-JSON-option-per-line requirement.

- [ ] **Step 3: Run the schema test and verify GREEN**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q \
  backend/app/tools/utility/execute_echarts_python_schema_spec.py::test_execute_echarts_python_schema_owns_data_access_contract
```

Expected: `1 passed`.

### Task 3: Remove the contract from chart mode

**Files:**
- Modify: `backend/app/agent/prompts/chart_prompt.py`
- Test: `backend/app/agent/prompts/chart_prompt_contract_spec.py`

- [ ] **Step 1: Remove tool-call details from the initial workflow**

Keep the step that selects `execute_echarts_python`, but remove its nested `get_raw_data`, hard-coded path, stdout, and option-format instructions. The remaining step is:

```python
"5. **生成图表**：使用 `execute_echarts_python` 执行 Python 代码并返回前端 visuals\n\n",
```

- [ ] **Step 2: Remove the dedicated Python contract and examples**

Delete the complete prompt span beginning with `## Python 代码生成规范` and ending immediately before `## 工具使用方式`. This removes data access, stateless execution, stdout protocol, top-level `series`, serialization constraints, and all positive/negative invocation examples from the system prompt.

- [ ] **Step 3: Run the chart-prompt boundary test and verify GREEN**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q \
  backend/app/agent/prompts/chart_prompt_contract_spec.py::test_chart_prompt_selects_echarts_tool_without_embedding_its_call_contract
```

Expected: `1 passed`.

### Task 4: Verify the complete migration

**Files:**
- Verify: `backend/app/tools/utility/execute_echarts_python_schema_spec.py`
- Verify: `backend/app/agent/prompts/chart_prompt_contract_spec.py`
- Verify: `backend/app/tools/utility/execute_echarts_python_manual.md`

- [ ] **Step 1: Scan for stale prompt-owned contract text**

Run:

```bash
rg -n "get_raw_data\(|backend_data_registry/datasets|stdout 每行|series 在顶层|execute_echarts_python 图表生成示例" \
  backend/app/agent/prompts/chart_prompt.py
```

Expected: no matches.

- [ ] **Step 2: Run focused regression tests**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q \
  backend/app/tools/utility/execute_python_schema_spec.py \
  backend/app/tools/utility/execute_echarts_python_schema_spec.py \
  backend/app/agent/prompts/chart_prompt_contract_spec.py
```

Expected: all tests pass.

- [ ] **Step 3: Check formatting and inspect the diff**

Run:

```bash
git diff --check
git status --short
git diff -- backend/app/tools/utility/execute_python_tool.py \
  backend/app/tools/utility/execute_echarts_python_manual.md \
  backend/app/agent/prompts/chart_prompt.py \
  backend/app/tools/utility/execute_echarts_python_schema_spec.py \
  backend/app/agent/prompts/chart_prompt_contract_spec.py
```

Expected: no whitespace errors; only the planned files are changed, aside from pre-existing unrelated workspace content.

- [ ] **Step 4: Commit the implementation**

```bash
git add backend/app/tools/utility/execute_python_tool.py \
  backend/app/tools/utility/execute_echarts_python_manual.md \
  backend/app/agent/prompts/chart_prompt.py \
  backend/app/tools/utility/execute_echarts_python_schema_spec.py \
  backend/app/agent/prompts/chart_prompt_contract_spec.py
git commit -m "refactor: move echarts tool contract into schema"
```
