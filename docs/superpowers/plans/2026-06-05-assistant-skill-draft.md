# Assistant Skill Draft Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add assistant-mode, user-confirmed candidate skill draft creation with safe draft storage and read-only skill viewing.

**Architecture:** Add a focused skill-management utility module for path safety, metadata parsing, and deterministic draft rendering. Expose it through two LLM tools: `view_skill` for reading official/draft skills and `create_skill_draft` for assistant-only draft creation. Register both globally, then use mode filtering so only assistant sees `create_skill_draft` while existing skill discovery remains unchanged.

**Tech Stack:** Python 3.11, FastAPI, existing `LLMTool` interface, existing `ToolRegistry`, pytest, conda env `/root/miniconda3/envs/backend_py311`.

---

## File Structure

- Create `backend/app/tools/utility/skill_management/skill_paths.py`
  - Owns `SKILLS_DIR`, `DRAFTS_DIR`, filename sanitization, safe path resolution, title/description parsing, and markdown draft rendering.
- Create `backend/app/tools/utility/skill_management/view_skill_tool.py`
  - Read-only LLM tool for resolving and reading official skills or drafts.
- Create `backend/app/tools/utility/skill_management/create_skill_draft_tool.py`
  - Assistant-facing write tool that validates structured inputs and writes drafts only under `.drafts`.
- Modify `backend/app/tools/utility/skill_management/__init__.py`
  - Export the new tools.
- Modify `backend/app/tools/__init__.py`
  - Register both new tools in the global registry.
- Modify `backend/app/agent/prompts/tool_registry.py`
  - Add `view_skill` next to `list_skills` where relevant and add `create_skill_draft` only to assistant mode.
- Modify `backend/app/agent/prompts/assistant_prompt.py`
  - Add user-confirmed skill-draft guidance.
- Modify `backend/app/api/skills_routes.py`
  - Add draft list and draft detail endpoints using the same safe helpers.
- Create `backend/tests/tools/test_skill_draft_tools.py`
  - Tool-level tests for safety, rendering, duplicate handling, and read behavior.
- Create `backend/tests/test_assistant_skill_draft_tool_exposure.py`
  - Mode-filtering tests.
- Modify or add API tests only if an existing API test pattern is clear during implementation.

## Task 1: Shared Skill Path And Rendering Helpers

**Files:**
- Create: `backend/app/tools/utility/skill_management/skill_paths.py`
- Test: `backend/tests/tools/test_skill_draft_tools.py`

- [ ] **Step 1: Write failing helper tests**

Add `backend/tests/tools/test_skill_draft_tools.py` with these initial tests:

```python
from pathlib import Path

import pytest

from app.tools.utility.skill_management.skill_paths import (
    sanitize_skill_filename,
    render_skill_draft_markdown,
    resolve_skill_file,
)


def test_sanitize_skill_filename_blocks_path_traversal():
    assert sanitize_skill_filename("../bad") == "bad.md"
    assert sanitize_skill_filename("..\\bad") == "bad.md"
    assert sanitize_skill_filename("/tmp/bad.md") == "bad.md"


def test_sanitize_skill_filename_keeps_chinese_and_adds_md():
    assert sanitize_skill_filename("污染过程复盘") == "污染过程复盘.md"


def test_render_skill_draft_markdown_contains_required_sections():
    content = render_skill_draft_markdown(
        title="污染过程复盘",
        description="复用污染过程分析步骤。",
        applicable_scenarios=["城市出现连续污染过程"],
        required_tools=[{"name": "query_city_standard_report", "purpose": "查询城市报表"}],
        workflow_steps=[{"title": "查询数据", "purpose": "获取基础数据", "operation": "按城市和日期查询"}],
        notes=["核对时间范围"],
        source_summary="用户完成了一次污染过程复盘。",
        source_session_id="session-a",
    )

    assert content.startswith("# 污染过程复盘")
    assert "status: draft" in content
    assert "source_mode: assistant" in content
    assert "source_session_id: session-a" in content
    assert "## 概述" in content
    assert "## 适用场景" in content
    assert "## 所需工具" in content
    assert "## 详细流程" in content
    assert "## 验证方式" in content


def test_resolve_skill_file_rejects_unsafe_name(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    drafts_dir = skills_dir / ".drafts"
    skills_dir.mkdir()
    drafts_dir.mkdir()

    with pytest.raises(ValueError):
        resolve_skill_file("../secret", include_drafts=True, skills_dir=skills_dir, drafts_dir=drafts_dir)
```

- [ ] **Step 2: Run helper tests to verify failure**

Run:

```bash
cd backend
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/tools/test_skill_draft_tools.py -v
```

Expected: import failure for `skill_paths`.

- [ ] **Step 3: Implement helper module**

Create `backend/app/tools/utility/skill_management/skill_paths.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
import re
from typing import Any, Iterable


BACKEND_DIR = Path(__file__).resolve().parents[5]
SKILLS_DIR = BACKEND_DIR / "docs" / "skills"
DRAFTS_DIR = SKILLS_DIR / ".drafts"


_UNSAFE_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')


def sanitize_skill_filename(name: str) -> str:
    raw = (name or "").strip().replace("\\", "/")
    raw = raw.split("/")[-1]
    raw = raw.replace("..", "")
    raw = _UNSAFE_CHARS.sub("_", raw).strip(" .")
    if not raw:
        raise ValueError("技能名称不能为空")
    if not raw.endswith(".md"):
        raw = f"{raw}.md"
    return raw


def ensure_within_directory(path: Path, directory: Path) -> Path:
    resolved_path = path.resolve()
    resolved_dir = directory.resolve()
    if resolved_path != resolved_dir and resolved_dir not in resolved_path.parents:
        raise ValueError(f"路径越界: {path}")
    return resolved_path


def resolve_skill_file(
    name: str,
    *,
    include_drafts: bool = False,
    skills_dir: Path = SKILLS_DIR,
    drafts_dir: Path = DRAFTS_DIR,
) -> Path:
    if any(part in (name or "") for part in ("../", "..\\", "/", "\\")):
        raise ValueError("技能名称不能包含路径分隔符")

    filename = sanitize_skill_filename(name)
    official_path = ensure_within_directory(skills_dir / filename, skills_dir)
    if official_path.exists() and official_path.is_file():
        return official_path

    if include_drafts:
        draft_path = ensure_within_directory(drafts_dir / filename, drafts_dir)
        if draft_path.exists() and draft_path.is_file():
            return draft_path

    raise FileNotFoundError(filename)


def parse_skill_metadata(content: str, fallback_name: str) -> dict[str, str]:
    title = Path(fallback_name).stem
    description = "暂无描述"
    lines = content.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped[2:].strip() or title
        if stripped.startswith("## 概述") and index + 1 < len(lines):
            candidate = lines[index + 1].strip()
            if candidate and not candidate.startswith("#"):
                description = candidate
                break
    return {"title": title, "description": description}


def _render_bullets(values: Iterable[str]) -> str:
    items = [str(value).strip() for value in values if str(value).strip()]
    return "\n".join(f"- {item}" for item in items) if items else "- 未提供"


def _render_required_tools(required_tools: list[Any]) -> str:
    lines: list[str] = []
    for item in required_tools:
        if isinstance(item, dict):
            name = str(item.get("name", "")).strip()
            purpose = str(item.get("purpose", "")).strip()
        else:
            name = str(item).strip()
            purpose = ""
        if not name:
            continue
        lines.append(f"- `{name}`：{purpose or '用途待审核确认'}")
    return "\n".join(lines) if lines else "- 未提供"


def _render_steps(workflow_steps: list[dict[str, Any]]) -> str:
    sections: list[str] = []
    for index, step in enumerate(workflow_steps, start=1):
        title = str(step.get("title") or f"步骤{index}").strip()
        purpose = str(step.get("purpose") or "说明该步骤的目的").strip()
        operation = str(step.get("operation") or "说明该步骤的具体操作").strip()
        sections.append(
            f"### 步骤{index}：{title}\n"
            f"- **目的**: {purpose}\n"
            f"- **操作**: {operation}"
        )
    return "\n\n".join(sections)


def render_skill_draft_markdown(
    *,
    title: str,
    description: str,
    applicable_scenarios: list[str],
    required_tools: list[Any],
    workflow_steps: list[dict[str, Any]],
    notes: list[str] | None = None,
    source_summary: str | None = None,
    source_session_id: str | None = None,
) -> str:
    created_at = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    notes = notes or []
    source_session_line = f"source_session_id: {source_session_id}" if source_session_id else "source_session_id: 未提供"
    source_summary_text = source_summary or "未提供"

    return (
        f"# {title.strip()}\n\n"
        "<!--\n"
        "status: draft\n"
        f"created_at: {created_at}\n"
        "source_mode: assistant\n"
        f"{source_session_line}\n"
        "-->\n\n"
        "## 概述\n"
        f"{description.strip()}\n\n"
        "## 适用场景\n"
        f"{_render_bullets(applicable_scenarios)}\n\n"
        "## 所需工具\n"
        f"{_render_required_tools(required_tools)}\n\n"
        "## 详细流程\n\n"
        f"{_render_steps(workflow_steps)}\n\n"
        "## 注意事项\n"
        f"{_render_bullets(notes)}\n\n"
        "## 验证方式\n"
        "- 核对输入条件、关键中间结果和最终产物是否符合用户目标。\n"
        "- 复用前确认城市、时间、文件路径、数据口径等上下文已经更新。\n\n"
        "## 来源摘要\n"
        f"{source_summary_text}\n"
    )
```

- [ ] **Step 4: Run helper tests to verify pass**

Run:

```bash
cd backend
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/tools/test_skill_draft_tools.py -v
```

Expected: the four helper tests pass.

- [ ] **Step 5: Commit helper module**

```bash
git add backend/app/tools/utility/skill_management/skill_paths.py backend/tests/tools/test_skill_draft_tools.py
git commit -m "feat: add skill draft path helpers"
```

## Task 2: Create `view_skill` Tool

**Files:**
- Create: `backend/app/tools/utility/skill_management/view_skill_tool.py`
- Modify: `backend/app/tools/utility/skill_management/__init__.py`
- Test: `backend/tests/tools/test_skill_draft_tools.py`

- [ ] **Step 1: Add failing `view_skill` tests**

Append these tests to `backend/tests/tools/test_skill_draft_tools.py`:

```python
from app.tools.utility.skill_management.view_skill_tool import ViewSkillTool


@pytest.mark.asyncio
async def test_view_skill_reads_official_skill(monkeypatch, tmp_path: Path):
    skills_dir = tmp_path / "skills"
    drafts_dir = skills_dir / ".drafts"
    skills_dir.mkdir()
    drafts_dir.mkdir()
    (skills_dir / "excel.md").write_text("# Excel 技能\n\n## 概述\n处理 Excel。", encoding="utf-8")

    import app.tools.utility.skill_management.view_skill_tool as module

    monkeypatch.setattr(module, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(module, "DRAFTS_DIR", drafts_dir)

    result = await ViewSkillTool().execute(name="excel")

    assert result["success"] is True
    assert result["data"]["name"] == "Excel 技能"
    assert result["data"]["is_draft"] is False
    assert "处理 Excel" in result["data"]["content"]


@pytest.mark.asyncio
async def test_view_skill_reads_draft_when_requested(monkeypatch, tmp_path: Path):
    skills_dir = tmp_path / "skills"
    drafts_dir = skills_dir / ".drafts"
    skills_dir.mkdir()
    drafts_dir.mkdir()
    (drafts_dir / "draft.md").write_text("# 草稿技能\n\n## 概述\n草稿内容。", encoding="utf-8")

    import app.tools.utility.skill_management.view_skill_tool as module

    monkeypatch.setattr(module, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(module, "DRAFTS_DIR", drafts_dir)

    result = await ViewSkillTool().execute(name="draft", include_drafts=True)

    assert result["success"] is True
    assert result["data"]["is_draft"] is True
    assert result["data"]["name"] == "草稿技能"


@pytest.mark.asyncio
async def test_view_skill_rejects_path_traversal():
    result = await ViewSkillTool().execute(name="../secret", include_drafts=True)

    assert result["success"] is False
    assert "路径" in result["summary"] or "名称" in result["summary"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd backend
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/tools/test_skill_draft_tools.py -v
```

Expected: import failure for `view_skill_tool`.

- [ ] **Step 3: Implement `ViewSkillTool`**

Create `backend/app/tools/utility/skill_management/view_skill_tool.py`:

```python
from __future__ import annotations

from typing import Any, Dict

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.utility.skill_management.skill_paths import (
    DRAFTS_DIR,
    SKILLS_DIR,
    parse_skill_metadata,
    resolve_skill_file,
)


class ViewSkillTool(LLMTool):
    def __init__(self):
        super().__init__(
            name="view_skill",
            description=(
                "读取技能文档完整内容。用于在 list_skills 找到相关技能后查看详细流程；"
                "默认只读正式技能，include_drafts=true 时也可读取候选草稿。"
            ),
            category=ToolCategory.QUERY,
            version="1.0.0",
            requires_context=False,
            function_schema={
                "name": "view_skill",
                "description": "读取指定技能文档的完整内容，支持按文件名或技能名查找。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "技能文件名或名称，例如 excel 或 excel.md。",
                        },
                        "include_drafts": {
                            "type": "boolean",
                            "description": "是否允许读取 .drafts 候选技能草稿。",
                            "default": False,
                        },
                    },
                    "required": ["name"],
                },
            },
        )

    async def execute(self, name: str, include_drafts: bool = False, **kwargs) -> Dict[str, Any]:
        try:
            skill_file = resolve_skill_file(
                name,
                include_drafts=include_drafts,
                skills_dir=SKILLS_DIR,
                drafts_dir=DRAFTS_DIR,
            )
            content = skill_file.read_text(encoding="utf-8")
            metadata = parse_skill_metadata(content, skill_file.name)
            is_draft = DRAFTS_DIR.resolve() in skill_file.resolve().parents

            return {
                "success": True,
                "data": {
                    "name": metadata["title"],
                    "description": metadata["description"],
                    "file": str(skill_file),
                    "is_draft": is_draft,
                    "content": content,
                },
                "summary": f"已读取技能文档：{metadata['title']}",
            }
        except FileNotFoundError:
            return {
                "success": False,
                "error": f"Skill not found: {name}",
                "summary": f"未找到技能文档：{name}",
            }
        except ValueError as exc:
            return {
                "success": False,
                "error": str(exc),
                "summary": f"技能名称或路径不安全：{exc}",
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "summary": f"读取技能失败：{str(exc)[:80]}",
            }
```

Modify `backend/app/tools/utility/skill_management/__init__.py`:

```python
"""
技能管理工具
"""

from app.tools.utility.skill_management.list_skills_tool import ListSkillsTool
from app.tools.utility.skill_management.view_skill_tool import ViewSkillTool

__all__ = ["ListSkillsTool", "ViewSkillTool"]
```

- [ ] **Step 4: Run tool tests to verify pass**

Run:

```bash
cd backend
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/tools/test_skill_draft_tools.py -v
```

Expected: helper and `view_skill` tests pass.

- [ ] **Step 5: Commit `view_skill`**

```bash
git add backend/app/tools/utility/skill_management/view_skill_tool.py backend/app/tools/utility/skill_management/__init__.py backend/tests/tools/test_skill_draft_tools.py
git commit -m "feat: add skill viewing tool"
```

## Task 3: Create `create_skill_draft` Tool

**Files:**
- Create: `backend/app/tools/utility/skill_management/create_skill_draft_tool.py`
- Modify: `backend/app/tools/utility/skill_management/__init__.py`
- Test: `backend/tests/tools/test_skill_draft_tools.py`

- [ ] **Step 1: Add failing draft tool tests**

Append these tests to `backend/tests/tools/test_skill_draft_tools.py`:

```python
from app.tools.utility.skill_management.create_skill_draft_tool import CreateSkillDraftTool


def _draft_payload():
    return {
        "title": "污染过程复盘",
        "description": "复用污染过程分析步骤。",
        "applicable_scenarios": ["城市出现连续污染过程"],
        "required_tools": [{"name": "query_city_standard_report", "purpose": "查询城市报表"}],
        "workflow_steps": [{"title": "查询数据", "purpose": "获取基础数据", "operation": "按城市和日期查询"}],
        "notes": ["核对时间范围"],
        "source_summary": "用户完成了一次污染过程复盘。",
        "source_session_id": "session-a",
    }


@pytest.mark.asyncio
async def test_create_skill_draft_writes_to_drafts(monkeypatch, tmp_path: Path):
    skills_dir = tmp_path / "skills"
    drafts_dir = skills_dir / ".drafts"
    skills_dir.mkdir()

    import app.tools.utility.skill_management.create_skill_draft_tool as module

    monkeypatch.setattr(module, "DRAFTS_DIR", drafts_dir)

    result = await CreateSkillDraftTool().execute(**_draft_payload())

    assert result["success"] is True
    created = Path(result["data"]["file"])
    assert created.parent == drafts_dir
    assert created.exists()
    assert "污染过程复盘" in created.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_create_skill_draft_rejects_duplicate_without_overwrite(monkeypatch, tmp_path: Path):
    drafts_dir = tmp_path / "skills" / ".drafts"
    drafts_dir.mkdir(parents=True)
    (drafts_dir / "污染过程复盘.md").write_text("# old", encoding="utf-8")

    import app.tools.utility.skill_management.create_skill_draft_tool as module

    monkeypatch.setattr(module, "DRAFTS_DIR", drafts_dir)

    result = await CreateSkillDraftTool().execute(**_draft_payload())

    assert result["success"] is False
    assert "已存在" in result["summary"]


@pytest.mark.asyncio
async def test_create_skill_draft_requires_workflow_steps(monkeypatch, tmp_path: Path):
    drafts_dir = tmp_path / "skills" / ".drafts"

    import app.tools.utility.skill_management.create_skill_draft_tool as module

    monkeypatch.setattr(module, "DRAFTS_DIR", drafts_dir)
    payload = _draft_payload()
    payload["workflow_steps"] = []

    result = await CreateSkillDraftTool().execute(**payload)

    assert result["success"] is False
    assert "workflow_steps" in result["error"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd backend
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/tools/test_skill_draft_tools.py -v
```

Expected: import failure for `create_skill_draft_tool`.

- [ ] **Step 3: Implement `CreateSkillDraftTool`**

Create `backend/app/tools/utility/skill_management/create_skill_draft_tool.py`:

```python
from __future__ import annotations

from typing import Any, Dict

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.utility.skill_management.skill_paths import (
    DRAFTS_DIR,
    ensure_within_directory,
    render_skill_draft_markdown,
    sanitize_skill_filename,
)


class CreateSkillDraftTool(LLMTool):
    def __init__(self):
        super().__init__(
            name="create_skill_draft",
            description=(
                "在用户明确同意后，将已完成任务中的可复用流程保存为候选技能草稿。"
                "只写入 backend/docs/skills/.drafts/，不会发布为正式技能。"
            ),
            category=ToolCategory.TASK_MANAGEMENT,
            version="1.0.0",
            requires_context=False,
            function_schema={
                "name": "create_skill_draft",
                "description": "创建候选技能草稿。必须在用户明确同意保存技能后调用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "候选技能标题。"},
                        "description": {"type": "string", "description": "一句话描述技能价值。"},
                        "applicable_scenarios": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "适用场景列表。",
                        },
                        "required_tools": {
                            "type": "array",
                            "description": "所需工具列表，可传字符串或 {name, purpose} 对象。",
                            "items": {
                                "oneOf": [
                                    {"type": "string"},
                                    {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "purpose": {"type": "string"},
                                        },
                                        "required": ["name"],
                                    },
                                ]
                            },
                        },
                        "workflow_steps": {
                            "type": "array",
                            "description": "有序流程步骤。",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "purpose": {"type": "string"},
                                    "operation": {"type": "string"},
                                },
                                "required": ["title", "operation"],
                            },
                        },
                        "notes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "注意事项、坑点或质量检查。",
                        },
                        "source_summary": {"type": "string", "description": "来源任务摘要。"},
                        "source_session_id": {"type": "string", "description": "来源会话ID。"},
                        "overwrite": {
                            "type": "boolean",
                            "description": "是否覆盖同名草稿，默认 false。",
                            "default": False,
                        },
                    },
                    "required": ["title", "description", "applicable_scenarios", "required_tools", "workflow_steps"],
                },
            },
        )

    async def execute(
        self,
        title: str,
        description: str,
        applicable_scenarios: list[str],
        required_tools: list[Any],
        workflow_steps: list[dict[str, Any]],
        notes: list[str] | None = None,
        source_summary: str | None = None,
        source_session_id: str | None = None,
        overwrite: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        try:
            if not title or not str(title).strip():
                raise ValueError("title 不能为空")
            if not description or not str(description).strip():
                raise ValueError("description 不能为空")
            if not workflow_steps:
                raise ValueError("workflow_steps 不能为空")

            filename = sanitize_skill_filename(title)
            DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
            draft_file = ensure_within_directory(DRAFTS_DIR / filename, DRAFTS_DIR)
            if draft_file.exists() and not overwrite:
                return {
                    "success": False,
                    "error": f"Draft already exists: {draft_file}",
                    "summary": f"候选技能草稿已存在：{draft_file.name}",
                }

            content = render_skill_draft_markdown(
                title=title,
                description=description,
                applicable_scenarios=applicable_scenarios,
                required_tools=required_tools,
                workflow_steps=workflow_steps,
                notes=notes or [],
                source_summary=source_summary,
                source_session_id=source_session_id,
            )
            draft_file.write_text(content, encoding="utf-8")

            return {
                "success": True,
                "data": {
                    "title": title,
                    "description": description,
                    "file": str(draft_file),
                    "is_draft": True,
                    "next_action": "请审核候选技能内容，确认后再发布为正式技能。",
                },
                "summary": f"已创建候选技能草稿：{draft_file.name}",
            }
        except ValueError as exc:
            return {
                "success": False,
                "error": str(exc),
                "summary": f"候选技能参数无效：{exc}",
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "summary": f"创建候选技能草稿失败：{str(exc)[:80]}",
            }
```

Update `backend/app/tools/utility/skill_management/__init__.py`:

```python
"""
技能管理工具
"""

from app.tools.utility.skill_management.create_skill_draft_tool import CreateSkillDraftTool
from app.tools.utility.skill_management.list_skills_tool import ListSkillsTool
from app.tools.utility.skill_management.view_skill_tool import ViewSkillTool

__all__ = ["CreateSkillDraftTool", "ListSkillsTool", "ViewSkillTool"]
```

- [ ] **Step 4: Run draft tool tests to verify pass**

Run:

```bash
cd backend
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/tools/test_skill_draft_tools.py -v
```

Expected: all skill draft tool tests pass.

- [ ] **Step 5: Commit draft tool**

```bash
git add backend/app/tools/utility/skill_management/create_skill_draft_tool.py backend/app/tools/utility/skill_management/__init__.py backend/tests/tools/test_skill_draft_tools.py
git commit -m "feat: add candidate skill draft tool"
```

## Task 4: Register Tools And Restrict Write Access To Assistant Mode

**Files:**
- Modify: `backend/app/tools/__init__.py`
- Modify: `backend/app/agent/prompts/tool_registry.py`
- Test: `backend/tests/test_assistant_skill_draft_tool_exposure.py`

- [ ] **Step 1: Write failing exposure tests**

Create `backend/tests/test_assistant_skill_draft_tool_exposure.py`:

```python
from app.agent.prompts.tool_registry import get_tool_order, get_tools_by_mode
from app.tools import create_global_tool_registry


def test_assistant_mode_exposes_create_skill_draft_and_view_skill():
    assistant_tools = get_tools_by_mode("assistant")
    assistant_order = get_tool_order("assistant")

    assert "view_skill" in assistant_tools
    assert "create_skill_draft" in assistant_tools
    assert "view_skill" in assistant_order
    assert "create_skill_draft" in assistant_order


def test_non_assistant_modes_do_not_expose_create_skill_draft():
    for mode in ("expert", "query", "report", "chart", "ops", "social"):
        assert "create_skill_draft" not in get_tools_by_mode(mode)
        assert "create_skill_draft" not in get_tool_order(mode)


def test_global_registry_registers_skill_tools():
    registry = create_global_tool_registry()
    tools = registry.list_tools()

    assert "view_skill" in tools
    assert "create_skill_draft" in tools
```

- [ ] **Step 2: Run exposure tests to verify failure**

Run:

```bash
cd backend
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/test_assistant_skill_draft_tool_exposure.py -v
```

Expected: missing tool names in mode registry or global registry.

- [ ] **Step 3: Register tools globally**

Modify `backend/app/tools/__init__.py` near the existing `ListSkillsTool` registration:

```python
    try:
        from app.tools.utility.skill_management.list_skills_tool import ListSkillsTool
        registry.register(ListSkillsTool(), priority=310)  # 修复: 508->310
        logger.info("tool_loaded", tool="list_skills")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="list_skills", error=str(e))

    try:
        from app.tools.utility.skill_management.view_skill_tool import ViewSkillTool
        registry.register(ViewSkillTool(), priority=311)
        logger.info("tool_loaded", tool="view_skill")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="view_skill", error=str(e))

    try:
        from app.tools.utility.skill_management.create_skill_draft_tool import CreateSkillDraftTool
        registry.register(CreateSkillDraftTool(), priority=312)
        logger.info("tool_loaded", tool="create_skill_draft")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="create_skill_draft", error=str(e))
```

If `parse_pdf` currently uses priority `311`, move it to `313` in the same local block to preserve deterministic order.

- [ ] **Step 4: Update mode registry**

Modify `backend/app/agent/prompts/tool_registry.py`:

```python
ASSISTANT_TOOL_NAMES = {
    # Shell命令
    "bash",

    # 文件操作
    "read_file", "edit_file", "grep", "write_file", "present_artifact", "list_directory",
    "search_files", "list_skills", "view_skill", "create_skill_draft",
```

Add read-only `view_skill` where `list_skills` already exists:

```python
OPS_TOOL_NAMES = {
    ...
    "read_file", "write_file", "present_artifact", "edit_file", "edit_word_document", "grep", "list_directory", "search_files", "list_skills", "view_skill",
}

SOCIAL_TOOL_NAMES = {
    ...
    "list_directory", "search_files", "list_skills", "view_skill",
```

Update assistant order:

```python
    # 任务管理
    "TodoWrite", "create_scheduled_task", "wait_task", "list_skills", "view_skill", "create_skill_draft",
```

Update `OPS_TOOL_ORDER` and `SOCIAL_TOOL_ORDER` by placing `view_skill` immediately after `list_skills`. Do not add `create_skill_draft` to any non-assistant mode.

- [ ] **Step 5: Run exposure and tool tests**

Run:

```bash
cd backend
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/test_assistant_skill_draft_tool_exposure.py tests/tools/test_skill_draft_tools.py -v
```

Expected: both test files pass.

- [ ] **Step 6: Commit registration**

```bash
git add backend/app/tools/__init__.py backend/app/agent/prompts/tool_registry.py backend/tests/test_assistant_skill_draft_tool_exposure.py
git commit -m "feat: expose skill draft tools by mode"
```

## Task 5: Assistant Prompt Guidance

**Files:**
- Modify: `backend/app/agent/prompts/assistant_prompt.py`
- Test: `backend/tests/test_assistant_skill_draft_tool_exposure.py`

- [ ] **Step 1: Add failing prompt test**

Append to `backend/tests/test_assistant_skill_draft_tool_exposure.py`:

```python
from app.agent.prompts.assistant_prompt import build_assistant_prompt


def test_assistant_prompt_requires_user_confirmation_before_skill_draft():
    prompt = build_assistant_prompt(["create_skill_draft", "view_skill", "list_skills"])

    assert "create_skill_draft" in prompt
    assert "候选技能" in prompt
    assert "用户明确同意" in prompt
    assert "不要调用" in prompt
```

- [ ] **Step 2: Run prompt test to verify failure**

Run:

```bash
cd backend
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/test_assistant_skill_draft_tool_exposure.py::test_assistant_prompt_requires_user_confirmation_before_skill_draft -v
```

Expected: assertion failure because prompt lacks the new guidance.

- [ ] **Step 3: Add prompt guidance**

Modify `backend/app/agent/prompts/assistant_prompt.py` inside the `"## 技能文档"` section:

```python
        "## 技能文档\n",
        "\n",
        "遇到复杂文件处理、Excel、可视化或文档生成任务时，可先查找并阅读相关技能文档，再按文档执行。\n",
        "- 任务完成后，如果本次工作形成了可复用流程，可在最终回复中简短询问用户是否保存为候选技能。\n",
        "- 只有在用户明确同意保存后，才可以调用 `create_skill_draft`；用户未确认时不要调用该工具。\n",
        "- 候选技能应记录适用场景、所需工具、详细流程、注意事项和验证方式，不保存一次性问答或敏感社交上下文。\n",
        "- `create_skill_draft` 只创建草稿，不代表正式发布；创建后告知用户草稿路径和后续审核动作。\n",
        "\n",
```

- [ ] **Step 4: Run prompt and exposure tests**

Run:

```bash
cd backend
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/test_assistant_skill_draft_tool_exposure.py -v
```

Expected: all tests in that file pass.

- [ ] **Step 5: Commit prompt guidance**

```bash
git add backend/app/agent/prompts/assistant_prompt.py backend/tests/test_assistant_skill_draft_tool_exposure.py
git commit -m "docs: guide assistant skill draft suggestions"
```

## Task 6: Draft Skill API Endpoints

**Files:**
- Modify: `backend/app/api/skills_routes.py`
- Test: `backend/tests/tools/test_skill_draft_tools.py` or new `backend/tests/test_skills_routes_drafts.py`

- [ ] **Step 1: Add route tests**

Create `backend/tests/test_skills_routes_drafts.py`:

```python
from pathlib import Path

import pytest

from app.api import skills_routes


@pytest.mark.asyncio
async def test_list_skill_drafts(monkeypatch, tmp_path: Path):
    skills_dir = tmp_path / "skills"
    drafts_dir = skills_dir / ".drafts"
    drafts_dir.mkdir(parents=True)
    (drafts_dir / "draft.md").write_text("# 草稿技能\n\n## 概述\n草稿内容。", encoding="utf-8")

    monkeypatch.setattr(skills_routes, "DRAFTS_DIR", drafts_dir)

    result = await skills_routes.list_skill_drafts()

    assert result["success"] is True
    assert result["data"]["count"] == 1
    assert result["data"]["drafts"][0]["name"] == "草稿技能"


@pytest.mark.asyncio
async def test_get_skill_draft_detail(monkeypatch, tmp_path: Path):
    skills_dir = tmp_path / "skills"
    drafts_dir = skills_dir / ".drafts"
    drafts_dir.mkdir(parents=True)
    (drafts_dir / "draft.md").write_text("# 草稿技能\n\n## 概述\n草稿内容。", encoding="utf-8")

    monkeypatch.setattr(skills_routes, "DRAFTS_DIR", drafts_dir)

    result = await skills_routes.get_skill_draft_detail("draft")

    assert result["success"] is True
    assert result["data"]["is_draft"] is True
    assert "草稿内容" in result["data"]["content"]
```

- [ ] **Step 2: Run route tests to verify failure**

Run:

```bash
cd backend
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/test_skills_routes_drafts.py -v
```

Expected: missing route functions.

- [ ] **Step 3: Implement route helpers**

Modify imports at the top of `backend/app/api/skills_routes.py`:

```python
from app.tools.utility.skill_management.skill_paths import (
    DRAFTS_DIR,
    parse_skill_metadata,
    resolve_skill_file,
)
```

Add routes before `@router.post("/refresh-index")`:

```python
@router.get("/drafts")
async def list_skill_drafts():
    """列出候选技能草稿。"""
    try:
        if not DRAFTS_DIR.exists():
            return {
                "success": True,
                "data": {"drafts": [], "count": 0, "drafts_dir": str(DRAFTS_DIR)},
                "summary": "当前没有候选技能草稿",
            }

        drafts = []
        for draft_file in sorted(DRAFTS_DIR.glob("*.md")):
            content = draft_file.read_text(encoding="utf-8")
            metadata = parse_skill_metadata(content, draft_file.name)
            drafts.append({
                "name": metadata["title"],
                "description": metadata["description"],
                "file": str(draft_file),
                "is_draft": True,
            })

        return {
            "success": True,
            "data": {"drafts": drafts, "count": len(drafts), "drafts_dir": str(DRAFTS_DIR)},
            "summary": f"找到 {len(drafts)} 个候选技能草稿",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list skill drafts: {str(e)}")


@router.get("/drafts/{draft_name}")
async def get_skill_draft_detail(draft_name: str):
    """读取候选技能草稿详情。"""
    try:
        draft_file = resolve_skill_file(
            draft_name,
            include_drafts=True,
            skills_dir=DRAFTS_DIR,
            drafts_dir=DRAFTS_DIR,
        )
        content = draft_file.read_text(encoding="utf-8")
        metadata = parse_skill_metadata(content, draft_file.name)
        return {
            "success": True,
            "data": {
                "name": metadata["title"],
                "description": metadata["description"],
                "file": str(draft_file),
                "is_draft": True,
                "content": content,
            },
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Draft not found: {draft_name}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get skill draft: {str(e)}")
```

- [ ] **Step 4: Run route tests**

Run:

```bash
cd backend
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/test_skills_routes_drafts.py -v
```

Expected: route tests pass.

- [ ] **Step 5: Commit API endpoints**

```bash
git add backend/app/api/skills_routes.py backend/tests/test_skills_routes_drafts.py
git commit -m "feat: add skill draft api endpoints"
```

## Task 7: Final Verification

**Files:**
- All files changed in Tasks 1-6.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
cd backend
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  tests/tools/test_skill_draft_tools.py \
  tests/test_assistant_skill_draft_tool_exposure.py \
  tests/test_skills_routes_drafts.py \
  tests/test_assistant_knowledge_tool_exposure.py \
  -v
```

Expected: all focused tests pass.

- [ ] **Step 2: Run import sanity check**

Run:

```bash
cd backend
conda run -p /root/miniconda3/envs/backend_py311 python - <<'PY'
from app.tools import create_global_tool_registry
from app.agent.prompts.tool_registry import get_tools_by_mode

registry = create_global_tool_registry()
assert registry.get_tool("view_skill") is not None
assert registry.get_tool("create_skill_draft") is not None
assert "create_skill_draft" in get_tools_by_mode("assistant")
assert "create_skill_draft" not in get_tools_by_mode("social")
print("skill draft registration sanity ok")
PY
```

Expected output includes:

```text
skill draft registration sanity ok
```

- [ ] **Step 3: Check git diff for unrelated changes**

Run:

```bash
git diff --stat
git diff -- backend/app/tools/utility/skill_management backend/app/tools/__init__.py backend/app/agent/prompts/tool_registry.py backend/app/agent/prompts/assistant_prompt.py backend/app/api/skills_routes.py backend/tests/tools/test_skill_draft_tools.py backend/tests/test_assistant_skill_draft_tool_exposure.py backend/tests/test_skills_routes_drafts.py
```

Expected: diff only covers the planned skill draft files and tests.

- [ ] **Step 4: Commit any final adjustments**

If Step 1 or Step 2 required small fixes, commit them:

```bash
git add backend/app/tools/utility/skill_management backend/app/tools/__init__.py backend/app/agent/prompts/tool_registry.py backend/app/agent/prompts/assistant_prompt.py backend/app/api/skills_routes.py backend/tests/tools/test_skill_draft_tools.py backend/tests/test_assistant_skill_draft_tool_exposure.py backend/tests/test_skills_routes_drafts.py
git commit -m "test: verify assistant skill draft flow"
```

If there are no final adjustments, skip this commit.

## Self-Review

- Spec coverage:
  - Assistant-only `create_skill_draft`: Task 4.
  - User-confirmed prompt behavior: Task 5.
  - Draft-only `.drafts` writes: Tasks 1 and 3.
  - `view_skill`: Task 2.
  - Optional draft API: Task 6.
  - No background reviewer: no task adds one.
  - No auto-promotion: no task adds promote/reject or official publication.
- Placeholder scan:
  - The plan intentionally avoids unresolved implementation placeholders; code snippets define concrete functions, tests, schemas, and commands.
- Type consistency:
  - Shared helper names are `sanitize_skill_filename`, `ensure_within_directory`, `resolve_skill_file`, `parse_skill_metadata`, and `render_skill_draft_markdown`.
  - Tool names are exactly `view_skill` and `create_skill_draft`.
  - Draft fields match the spec: `title`, `description`, `applicable_scenarios`, `required_tools`, `workflow_steps`, `notes`, `source_summary`, `source_session_id`, and `overwrite`.
