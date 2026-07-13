# Yuncheng Event Task Assistant Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the Yuncheng alert tracing event task directly in assistant mode while leaving WeChat fan-out and per-user conversation persistence to the event delivery service.

**Architecture:** Keep the existing generic event execution and broadcast pipeline unchanged. Update only the operational task definition and the published Yuncheng Skill contract so the assistant Agent performs the workflow directly and returns the strict `EventTaskOutput` broadcast envelope.

**Tech Stack:** Python 3.11, pytest, JSON operational task storage, Markdown Agent skills, FastAPI scheduled-task API

---

### Task 1: Lock the assistant-mode Skill contract with tests

**Files:**
- Modify: `backend/tests/tools/test_yuncheng_skill_publication.py`
- Test: `backend/tests/tools/test_yuncheng_skill_publication.py`

- [ ] **Step 1: Replace the obsolete social-coordinator assertions**

Replace `test_yuncheng_skill_defines_social_assistant_expert_responsibilities` with assertions that require direct assistant execution, forbid social coordination wording, preserve expert delegation, and require the event broadcast envelope:

```python
@pytest.mark.asyncio
async def test_yuncheng_skill_defines_direct_assistant_event_contract():
    viewed = await ViewSkillTool().execute(name="yuncheng_alert_tracing_skill")
    content = viewed["data"]["content"]

    assert "事件任务使用助手模式直接执行本 skill" in content
    assert "调用专家子 Agent 分析" in content
    assert '"broadcast"' in content
    assert '"message"' in content
    assert '"media"' in content
    assert "事件任务服务负责广播" in content
    assert "不直接调用微信、广播或通知工具" in content
    assert "社交模式收到回复后推送" not in content
    assert "调用助手模式执行本 skill" not in content
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/tools/test_yuncheng_skill_publication.py::test_yuncheng_skill_defines_direct_assistant_event_contract
```

Expected: FAIL because the published Skill still describes the old social-to-assistant workflow and does not expose the event broadcast envelope.

### Task 2: Update the published Yuncheng Skill

**Files:**
- Modify: `backend/docs/skills/yuncheng_alert_tracing_skill.md`
- Test: `backend/tests/tools/test_yuncheng_skill_publication.py`

- [ ] **Step 1: Rewrite orchestration responsibilities**

Change the overview, usage flow and SOP so the event task invokes assistant mode directly. Preserve the two synchronous `expert` sub-Agent calls, report generation, report validation, evidence boundaries and 500-character WeChat summary requirements.

- [ ] **Step 2: Replace the final output contract**

Require the assistant to return only this success shape after confirming that `report.docx` exists:

```json
{
  "success": true,
  "broadcast": {
    "message": "500字以内微信摘要",
    "media": ["/absolute/path/to/report.docx"]
  }
}
```

Require failures to return only:

```json
{
  "success": false,
  "error": "具体失败原因"
}
```

State explicitly that the Agent must not call WeChat, broadcast or notification tools because `EventTaskDelivery` owns fan-out and social transcript persistence.

- [ ] **Step 3: Run the Skill test file and verify GREEN**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/tools/test_yuncheng_skill_publication.py
```

Expected: all tests pass.

- [ ] **Step 4: Commit the published contract**

```bash
git add backend/docs/skills/yuncheng_alert_tracing_skill.md backend/tests/tools/test_yuncheng_skill_publication.py
git commit -m "fix: run yuncheng event analysis in assistant mode"
```

### Task 3: Update the live event task definition

**Files:**
- Modify: `backend/backend_data_registry/scheduled_tasks/tasks.json`

- [ ] **Step 1: Change execution mode and prompt**

For `task_yuncheng_alert_tracing_event`, set `execution_mode` to `assistant`. Replace the step prompt so it instructs the assistant to read the three paths from trusted event payload, execute `backend/docs/skills/yuncheng_alert_tracing_skill.md` directly, avoid all notification tools, confirm the Word file exists, and return only the strict broadcast envelope.

- [ ] **Step 2: Preserve delivery configuration**

Verify these fields remain unchanged:

```json
{
  "trigger_type": "event",
  "event_type": "yuncheng.alert.created",
  "event_filters": {"city": "运城市"},
  "target_user_ids": ["c56158f3-faee-4bfe-9848-a70c7f513f9c"],
  "broadcast_enabled": true,
  "enabled": true
}
```

- [ ] **Step 3: Validate the operational JSON**

Run:

```bash
jq -e '.[] | select(.task_id == "task_yuncheng_alert_tracing_event") | .execution_mode == "assistant" and .trigger_type == "event" and .broadcast_enabled == true and .enabled == true' backend/backend_data_registry/scheduled_tasks/tasks.json
```

Expected: `true` and exit code 0.

### Task 4: Reload and verify the live task

**Files:**
- Runtime: worker process serving `127.0.0.1:8011`

- [ ] **Step 1: Restart only the scheduled-task Worker**

Stop the existing `python -m app.worker` process gracefully and start one detached Worker from `/home/xckj/suyuan/backend` with `APP_ROLE=worker` under the project Python 3.11 environment.

- [ ] **Step 2: Verify the public management API**

Run:

```bash
curl -sS http://127.0.0.1:8000/api/scheduled-tasks/task_yuncheng_alert_tracing_event | jq '.task | {task_id, execution_mode, trigger_type, event_type, target_user_ids, broadcast_enabled, enabled}'
```

Expected: `execution_mode` is `assistant`; the task remains enabled, event-triggered and broadcast-enabled with the configured recipient.

- [ ] **Step 3: Verify runtime health without executing the Agent**

Confirm exactly one Worker process exists and ports 8000 and 8011 listen. Do not manually execute or publish a test alert, avoiding model cost and accidental WeChat delivery.
