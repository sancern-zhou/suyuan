# Assistant Candidate Skill Draft Design

## Context

The project already has a markdown-based skill library under `backend/docs/skills/`, a generated `SKILLS_INDEX.md`, a `list_skills` LLM tool, and skill management HTTP endpoints. The missing piece is a low-risk feedback loop for turning successful assistant-mode work into reusable candidate skills.

Hermes' useful pattern is not to inject full skills into the system prompt. It treats skills as runtime assets that can be listed, viewed, and managed through tools, with skill updates kept outside the main user response path. This design adopts the asset-management part first, but keeps generation user-confirmed and draft-only.

## Goals

- Let the assistant mode recommend candidate skill creation after a reusable workflow is completed.
- Require explicit user confirmation before writing any skill draft.
- Store generated drafts separately from official skills.
- Keep the first version small enough to validate timing, usefulness, and draft quality quickly.
- Avoid exposing write-capable skill tools to higher-risk or less relevant modes.

## Non-Goals

- No automatic promotion from draft to official skill.
- No background scheduled skill reviewer in the first version.
- No broad write access from `query`, `chart`, `social`, `ops`, `expert`, or `report` modes in the first version.
- No migration from the current flat `backend/docs/skills/*.md` format to Hermes-style nested `SKILL.md` directories.

## User Flow

1. The user asks the assistant to complete a task.
2. The assistant completes the task normally.
3. If the completed task looks reusable, the assistant adds a short suggestion in the final response:
   `这个流程后续可能复用，是否要保存为候选技能？`
4. If the user agrees, the assistant calls `create_skill_draft`.
5. The tool writes a markdown draft under `backend/docs/skills/.drafts/`.
6. The assistant reports the draft name, path, and summary.
7. A later review or API action can promote or reject the draft.

## Reusable Workflow Heuristics

The assistant should suggest a draft only when at least two of these are true:

- The task used a multi-step workflow rather than a single answer.
- Multiple tools, files, data sources, or transformations were involved.
- The workflow produced a repeatable artifact, report, analysis, or operating procedure.
- The task matches a domain pattern already common in this project, such as air-quality analysis, report generation, office document handling, ops audit, or data acquisition.
- The user used intent words like "以后", "下次", "固定流程", "保存", "复用", or "标准化".
- The assistant discovered a stable workaround or project-specific rule worth preserving.

The assistant should not suggest a draft for one-off factual answers, small code edits, transient debugging without a reusable procedure, or sensitive/private social conversations.

## Tool Scope

### `view_skill`

Read-only tool available to all normal agent modes that already have `list_skills`.

Responsibilities:

- Resolve a skill by file name, stem, or displayed title.
- Read official skills from `backend/docs/skills/`.
- Optionally read drafts from `backend/docs/skills/.drafts/` when requested.
- Enforce path traversal protection.
- Return title, description, file path, draft status, and content.

### `create_skill_draft`

Write-capable tool available only in `assistant` mode for the first version.

Responsibilities:

- Create a markdown skill draft from structured inputs.
- Write only under `backend/docs/skills/.drafts/`.
- Sanitize file names and reject path traversal.
- Avoid overwriting existing drafts unless an explicit `overwrite` flag is provided.
- Include source metadata such as created time, source mode, optional session id, and optional task summary.
- Return the created path, title, description, and next review action.

Inputs:

- `title`: human-readable skill title.
- `description`: one-sentence value statement.
- `applicable_scenarios`: list of concrete scenarios.
- `required_tools`: list of tool names and purposes.
- `workflow_steps`: ordered steps with purpose and operation.
- `notes`: pitfalls, constraints, or quality checks.
- `source_summary`: summary of the task that produced the draft.
- `overwrite`: default false.

The tool should not call an LLM. The assistant supplies the structured content, and the tool validates and renders it.

## Draft Format

Drafts use the existing skill template style with a metadata block:

```markdown
# <title>

<!--
status: draft
created_at: 2026-06-05T00:00:00+08:00
source_mode: assistant
source_session_id: <optional>
-->

## 概述
<description>

## 适用场景
- ...

## 所需工具
- `tool_name`：用途说明

## 详细流程

### 步骤1：...
- **目的**: ...
- **操作**: ...

## 注意事项
- ...

## 验证方式
- ...
```

## Prompt Changes

`assistant` mode prompt should gain a concise rule:

- When a completed task reveals a reusable workflow, suggest saving it as a candidate skill.
- Do not call `create_skill_draft` unless the user explicitly agrees.
- Draft only stable procedures, not one-off answers.
- Keep draft content operational: scenario, tools, steps, pitfalls, and verification.

No other prompt mode gets write-skill guidance in the first version.

## Registration

Update tool registration in two places:

- Register `view_skill` as a read-only utility tool wherever `list_skills` is already appropriate.
- Register `create_skill_draft` only in assistant mode via the mode tool registry.

The global tool registry can instantiate the tool, but mode filtering must keep it invisible outside assistant mode.

## API

Add HTTP endpoints only if they are needed by the frontend or admin review surface:

- `GET /api/skills/drafts` lists drafts.
- `GET /api/skills/drafts/{draft_name}` reads a draft.

Promotion and rejection can remain out of the first implementation unless the frontend already needs a review action. Official publication should not be implicit in `create_skill_draft`.

## Error Handling

- Missing title or empty workflow steps returns a validation error.
- Unsafe file names or paths are rejected.
- Duplicate draft names return a conflict unless `overwrite=true`.
- File write errors return a concise failure summary and leave existing files unchanged.
- Draft rendering should be deterministic and avoid embedding raw tool outputs unless they are short and useful.

## Testing

Focused tests should cover:

- `create_skill_draft` writes only under `.drafts`.
- Path traversal attempts are rejected.
- Duplicate names are not overwritten by default.
- Rendered markdown contains required sections.
- `view_skill` can read official skills and drafts.
- `assistant` mode includes `create_skill_draft`.
- Non-assistant modes do not include `create_skill_draft`.
- `list_skills` behavior remains unchanged for official skills.

## Rollout

1. Implement tools and tests.
2. Add assistant prompt guidance.
3. Manually test one reusable assistant task and one non-reusable task.
4. Review generated draft quality.
5. Decide whether to add background `skill_reviewer` or admin promote/reject endpoints after the foreground loop is validated.

