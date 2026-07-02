# Tender Assistant SQL Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an assistant-mode SQL Server query tool limited to stored tender crawling data.

**Architecture:** Reuse the existing `BaseSQLQueryTool` implementation and add a tender-specific subclass with a three-table whitelist. Register the tool globally and expose only that tender-specific tool in assistant mode.

**Tech Stack:** Python 3.11, pytest, SQL Server via existing `pyodbc` SQL query infrastructure.

---

## File Structure

- Modify `backend/app/tools/query/execute_sql_query/tool.py`: add `TENDER_SQL_TABLES` and `ExecuteTenderSQLQueryTool`.
- Modify `backend/app/tools/query/execute_sql_query/__init__.py`: export the new tool class.
- Modify `backend/app/tools/__init__.py`: register the new tool in the global registry.
- Modify `backend/app/agent/prompts/tool_registry.py`: add `execute_tender_sql_query` to assistant mode.
- Create `backend/tests/test_tender_sql_query_tool.py`: verify schema, whitelist validation, registration, and assistant-mode exposure.

### Task 1: Tests

**Files:**
- Create: `backend/tests/test_tender_sql_query_tool.py`

- [ ] **Step 1: Write tests for the tender SQL tool**

```python
from app.agent.prompts.tool_registry import get_tool_order
from app.tools import create_global_tool_registry
from app.tools.query.execute_sql_query.tool import ExecuteTenderSQLQueryTool


def test_tender_sql_tool_schema_uses_tender_defaults():
    tool = ExecuteTenderSQLQueryTool()

    schema = tool.get_function_schema()

    assert tool.name == "execute_tender_sql_query"
    assert tool.default_database == "XcAiDb"
    assert schema["name"] == "execute_tender_sql_query"
    assert schema["parameters"]["properties"]["database"]["enum"] == ["XcAiDb", "AirPollutionAnalysis"]
    assert "tender_notices" in schema["description"]


def test_tender_sql_tool_allows_tender_tables():
    tool = ExecuteTenderSQLQueryTool()

    valid, error = tool.sql_validator.validate(
        "SELECT TOP 10 id, title FROM tender_notices ORDER BY publish_date DESC"
    )

    assert valid is True
    assert error == ""


def test_tender_sql_tool_rejects_non_tender_tables():
    tool = ExecuteTenderSQLQueryTool()

    valid, error = tool.sql_validator.validate("SELECT TOP 10 * FROM working_orders")

    assert valid is False
    assert "表名不在白名单中" in error
    assert "working_orders" in error


def test_tender_sql_tool_rejects_mutating_sql():
    tool = ExecuteTenderSQLQueryTool()

    valid, error = tool.sql_validator.validate("DELETE FROM tender_notices")

    assert valid is False
    assert "只允许SELECT查询" in error


def test_tender_sql_tool_is_registered_globally():
    registry = create_global_tool_registry()

    assert registry.get_tool("execute_tender_sql_query") is not None


def test_tender_sql_tool_is_available_in_assistant_mode():
    assert "execute_tender_sql_query" in get_tool_order("assistant")
```

- [ ] **Step 2: Run tests and verify they fail before implementation**

Run: `conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/test_tender_sql_query_tool.py -q`

Expected: FAIL because `ExecuteTenderSQLQueryTool` does not exist yet.

### Task 2: Tool Implementation

**Files:**
- Modify: `backend/app/tools/query/execute_sql_query/tool.py`
- Modify: `backend/app/tools/query/execute_sql_query/__init__.py`
- Modify: `backend/app/tools/__init__.py`
- Modify: `backend/app/agent/prompts/tool_registry.py`
- Test: `backend/tests/test_tender_sql_query_tool.py`

- [ ] **Step 1: Add tender SQL table whitelist and tool subclass**

Add this near the other SQL table whitelist constants:

```python
TENDER_SQL_TABLES = [
    "tender_notices",
    "tender_candidates",
    "tender_fetch_runs",
]
```

Add this class after `ExecuteOpsSQLQueryTool`:

```python
class ExecuteTenderSQLQueryTool(BaseSQLQueryTool):
    """助手模式招投标数据专用SQL查询工具。"""

    def __init__(self):
        schema_description = (
            "招投标数据SQL Server查询工具。支持二选一：describe_table查看表结构，或sql执行SELECT查询。"
            "用于助手模式查询已抓取、初筛、详情清洗并入库的招标公告和中标公告。"
            "只能查询下方列出的招投标白名单表；禁止查询其他业务库表。"
            "硬约束：只允许SELECT；禁止DROP/DELETE/INSERT/UPDATE；最大返回1000条。"
            "SQL Server语法：中文字符串必须加N前缀，如 N'生态环境局'；分页/限制用TOP，不支持LIMIT。"
            "database默认为XcAiDb。"
            "\n\n常用表说明："
            "\n- tender_notices：清洗后的目标公告详情表，包含title、notice_type、project_name、purchaser、agency、winning_bidder、budget_amount、winning_amount、province、city、publish_date、summary、raw_content等字段。"
            "\n- tender_candidates：列表页候选公告表，包含title、url、notice_type、keyword、publish_date、filter_status、filter_reason、filter_confidence、decision_source等字段。"
            "\n- tender_fetch_runs：每日抓取运行记录，包含target_date、keywords_json、notice_types_json、total_candidates、duplicate_candidates、filtered_out、detail_fetch_failures、saved_notices、status、started_at、finished_at等字段。"
            "\n\n常见查询："
            "\n- 昨天入库公告：SELECT TOP 50 title, notice_type, purchaser, publish_date FROM tender_notices WHERE publish_date = '2026-07-01' ORDER BY id DESC"
            "\n- 最近运行情况：SELECT TOP 10 * FROM tender_fetch_runs ORDER BY started_at DESC"
            "\n- 初筛统计：SELECT filter_status, COUNT(*) AS cnt FROM tender_candidates WHERE publish_date = '2026-07-01' GROUP BY filter_status"
            "\n\n提示：使用describe_table可查看白名单表的完整字段结构。"
        )
        super().__init__(
            tool_name="execute_tender_sql_query",
            tool_description="Execute tender information SQL queries on SQL Server database or get table structure",
            schema_description=schema_description,
            allowed_tables=TENDER_SQL_TABLES,
            default_database="XcAiDb",
            allow_information_schema_sql=False,
        )
```

- [ ] **Step 2: Export and register the tool**

Update `backend/app/tools/query/execute_sql_query/__init__.py` to import and export `ExecuteTenderSQLQueryTool`.

Update `backend/app/tools/__init__.py` in the SQL tool registration block to import and register `ExecuteTenderSQLQueryTool`.

- [ ] **Step 3: Add assistant-mode exposure**

Add `"execute_tender_sql_query"` to `ASSISTANT_TOOL_NAMES` near the existing data-capable assistant tools.

- [ ] **Step 4: Run focused tests**

Run: `conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/test_tender_sql_query_tool.py -q`

Expected: PASS.

### Task 3: Real Database Smoke Test

**Files:**
- No source changes expected.

- [ ] **Step 1: Run a real describe-table smoke check**

Run a small Python script in the backend conda env that instantiates `ExecuteTenderSQLQueryTool` and calls `execute(describe_table="tender_notices")`.

Expected: `success=True`.

- [ ] **Step 2: Run a real count query smoke check**

Run a small Python script in the backend conda env that calls:

```sql
SELECT TOP 10 publish_date, COUNT(*) AS cnt
FROM tender_notices
GROUP BY publish_date
ORDER BY publish_date DESC
```

Expected: `success=True` and at least the known recent tender rows are visible.

### Task 4: Commit

**Files:**
- All implementation and test files from Tasks 1-3.

- [ ] **Step 1: Review diff**

Run: `git diff`

Expected: Only tender assistant SQL tool, registration, mode exposure, and tests changed.

- [ ] **Step 2: Commit implementation**

Run:

```bash
git add backend/app/tools/query/execute_sql_query/tool.py backend/app/tools/query/execute_sql_query/__init__.py backend/app/tools/__init__.py backend/app/agent/prompts/tool_registry.py backend/tests/test_tender_sql_query_tool.py docs/superpowers/plans/2026-07-02-tender-assistant-sql-tool.md
git commit -m "feat: add tender sql query tool for assistant mode"
```

Expected: Commit succeeds.

## Self-Review

- Spec coverage: tool name, table whitelist, default database, assistant exposure, and testing are covered.
- Placeholder scan: no TODO/TBD placeholders.
- Type consistency: tool class and tool name are consistent across implementation, registration, and tests.
