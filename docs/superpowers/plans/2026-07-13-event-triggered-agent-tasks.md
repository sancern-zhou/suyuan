# Event-Triggered Agent Tasks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing task system with generic event triggers so code can run one Agent only when a matching event occurs, broadcast the result to administrator-selected WeChat users, and persist the broadcast in every recipient's social conversation.

**Architecture:** Add an event model/catalog and durable idempotency claims beside the current JSON task storage. `ScheduledTaskService.publish_event()` matches enabled event tasks, claims `task_id + event_id`, runs the existing executor once, then delegates targeted delivery and per-user conversation persistence to focused social services. The Yuncheng fetcher publishes the first registered event only after deterministic alert detection and context collection succeed.

**Tech Stack:** Python 3.11, Pydantic, asyncio, APScheduler, file-backed JSON/session storage, FastAPI, pytest/pytest-asyncio, Vue 3, Pinia, Node test runner, Vite.

---

## File Map

**Create:**

- `backend/app/scheduled_tasks/models/event.py`: validated event envelope and trigger matching.
- `backend/app/scheduled_tasks/event_catalog.py`: registered event definitions exposed to the Web UI.
- `backend/app/scheduled_tasks/storage/event_claim_storage.py`: cross-process idempotency claim files and status transitions.
- `backend/app/scheduled_tasks/event_output.py`: strict parser for Agent broadcast output.
- `backend/app/scheduled_tasks/event_delivery.py`: resolve configured backend users and deliver event output.
- `backend/app/social/broadcast_context.py`: append sent broadcasts and attachments to one user's main social session.
- `backend/tests/scheduled_tasks/test_event_models.py`: task/event validation, catalog, matching, and scheduler tests.
- `backend/tests/scheduled_tasks/test_event_claim_storage.py`: atomic claim and status tests.
- `backend/tests/scheduled_tasks/test_event_executor.py`: event context injection and output parsing tests.
- `backend/tests/scheduled_tasks/test_event_dispatch.py`: service matching, deduplication, execution, and delivery tests.
- `backend/tests/social/test_broadcast_context.py`: recipient delivery and conversation persistence tests.
- `backend/tests/scenarios/yuncheng_trial/test_event_trigger.py`: no-alert and alert event publication tests.
- `frontend/src/components/management/scheduledTaskForm.js`: pure task form/payload helpers.
- `frontend/src/components/management/scheduledTaskForm.test.js`: Node unit tests for event task payloads and user filtering.

**Modify:**

- `backend/app/scheduled_tasks/models/task.py`: trigger type and event/delivery configuration.
- `backend/app/scheduled_tasks/models/execution.py`: event metadata and per-recipient delivery results.
- `backend/app/scheduled_tasks/models/__init__.py`: event model exports.
- `backend/app/scheduled_tasks/storage/__init__.py`: claim storage export.
- `backend/app/scheduled_tasks/scheduler/simple_scheduler.py`: skip event tasks.
- `backend/app/scheduled_tasks/executor/task_executor.py`: accept event context and mark trigger metadata.
- `backend/app/scheduled_tasks/service.py`: publish, track, and stop event executions.
- `backend/app/scheduled_tasks/__init__.py`: public event API exports.
- `backend/app/api/scheduled_task_routes.py`: event task fields, validation, event catalog, and manual event execution.
- `backend/app/lifecycle/scheduled.py`: await tracked event executions during worker shutdown.
- `backend/app/social/broadcast_service.py`: detailed targeted results and optional context persistence.
- `backend/app/fetchers/yuncheng_trial/yuncheng_trial_fetcher.py`: publish `yuncheng.alert.created` after context readiness.
- `backend/app/scenarios/yuncheng_trial/evidence_store_spec.py`: update the existing fetcher behavior contract.
- `frontend/src/components/management/ScheduledTasksPanel.vue`: schedule/event form, multi-select recipients, and event task display.
- `frontend/src/stores/scheduledTasks.js`: load event catalog and social users; preserve response metadata.
- `frontend/package.json`: add the focused Node unit-test command.

**Operational data change after deployment:**

- Disable the legacy `运城市告警溯源报告推送` entry in the affected user's `HEARTBEAT.md` only after an enabled `yuncheng.alert.created` event task has been configured.

---

### Task 1: Add Backward-Compatible Event Task and Event Envelope Models

**Files:**

- Create: `backend/app/scheduled_tasks/models/event.py`
- Create: `backend/app/scheduled_tasks/event_catalog.py`
- Create: `backend/tests/scheduled_tasks/test_event_models.py`
- Modify: `backend/app/scheduled_tasks/models/task.py`
- Modify: `backend/app/scheduled_tasks/models/execution.py`
- Modify: `backend/app/scheduled_tasks/models/__init__.py`
- Modify: `backend/app/scheduled_tasks/__init__.py`

- [ ] **Step 1: Write failing model and matching tests**

```python
# backend/tests/scheduled_tasks/test_event_models.py
import pytest
from pydantic import ValidationError

from app.scheduled_tasks.event_catalog import get_event_definitions
from app.scheduled_tasks.models import ScheduledTask, TaskEvent, TaskStep


def _step() -> TaskStep:
    return TaskStep(step_id="report", description="生成报告", agent_prompt="处理事件")


def test_legacy_task_defaults_to_schedule_trigger():
    task = ScheduledTask(
        task_id="legacy",
        name="legacy",
        description="legacy task",
        schedule_type="daily_8am",
        steps=[_step()],
    )
    assert task.trigger_type == "schedule"
    assert task.event_type is None


def test_event_task_requires_event_type_and_recipient_when_broadcasting():
    with pytest.raises(ValidationError):
        ScheduledTask(
            task_id="event",
            name="event",
            description="event task",
            trigger_type="event",
            schedule_type=None,
            broadcast_enabled=True,
            target_user_ids=[],
            steps=[_step()],
        )


def test_event_matches_scalar_and_list_filters():
    event = TaskEvent(
        event_id="alert-1",
        event_type="yuncheng.alert.created",
        attributes={"city": "运城市", "alert_level": "medium"},
        payload={"evidence_dir": "/tmp/evidence"},
    )
    assert event.matches({"city": "运城市", "alert_level": ["medium", "high"]})
    assert not event.matches({"city": "太原市"})


def test_yuncheng_event_is_registered():
    definitions = {item.event_type: item for item in get_event_definitions()}
    assert "yuncheng.alert.created" in definitions
    assert "city" in definitions["yuncheng.alert.created"].filter_fields
```

- [ ] **Step 2: Run the tests and confirm the new types are missing**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/scheduled_tasks/test_event_models.py -q
```

Expected: collection fails because `TaskEvent` and `event_catalog` do not exist.

- [ ] **Step 3: Add trigger fields and validation to `ScheduledTask`**

Add `TriggerType` and make schedule configuration optional for event tasks:

```python
class TriggerType(str, Enum):
    SCHEDULE = "schedule"
    EVENT = "event"


class ScheduledTask(BaseModel):
    # existing identity fields remain unchanged
    trigger_type: TriggerType = TriggerType.SCHEDULE
    schedule_type: Optional[ScheduleType] = None
    event_type: Optional[str] = None
    event_filters: Dict[str, Any] = Field(default_factory=dict)
    target_user_ids: List[str] = Field(default_factory=list)
    broadcast_enabled: bool = False

    @model_validator(mode="after")
    def validate_trigger(self):
        if self.trigger_type == TriggerType.SCHEDULE and self.schedule_type is None:
            raise ValueError("schedule_type is required for schedule tasks")
        if self.trigger_type == TriggerType.EVENT and not (self.event_type or "").strip():
            raise ValueError("event_type is required for event tasks")
        if self.broadcast_enabled and not self.target_user_ids:
            raise ValueError("target_user_ids is required when broadcast_enabled=true")
        return self
```

Keep old JSON compatible by defaulting `trigger_type` to `schedule`; old records already contain `schedule_type`.

- [ ] **Step 4: Implement the validated event envelope and matching**

```python
# backend/app/scheduled_tasks/models/event.py
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class TaskEvent(BaseModel):
    event_id: str
    event_type: str
    occurred_at: datetime = Field(default_factory=datetime.now)
    attributes: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_id", "event_type")
    @classmethod
    def non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    def matches(self, filters: dict[str, Any]) -> bool:
        for key, expected in filters.items():
            actual = self.attributes.get(key)
            if isinstance(expected, list):
                if actual not in expected:
                    return False
            elif actual != expected:
                return False
        return True
```

- [ ] **Step 5: Add a registered event catalog**

```python
# backend/app/scheduled_tasks/event_catalog.py
from pydantic import BaseModel, Field


class EventDefinition(BaseModel):
    event_type: str
    label: str
    description: str
    filter_fields: list[str] = Field(default_factory=list)


_EVENT_DEFINITIONS = {
    "yuncheng.alert.created": EventDefinition(
        event_type="yuncheng.alert.created",
        label="运城市空气质量告警",
        description="运城市小时盯守告警及溯源上下文已准备完成",
        filter_fields=["city", "alert_level", "target_pollutant"],
    )
}


def get_event_definitions() -> list[EventDefinition]:
    return list(_EVENT_DEFINITIONS.values())


def get_event_definition(event_type: str) -> EventDefinition | None:
    return _EVENT_DEFINITIONS.get(event_type)
```

- [ ] **Step 6: Extend execution metadata and exports**

Add to `TaskExecution`:

```python
event_id: Optional[str] = None
event_type: Optional[str] = None
event_attributes: Dict[str, Any] = Field(default_factory=dict)
delivery_results: List[Dict[str, Any]] = Field(default_factory=list)
```

Export `TriggerType`, `TaskEvent`, and `EventDefinition` through the existing model/package `__init__.py` files.

- [ ] **Step 7: Run model tests and existing task model regression tests**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  backend/tests/scheduled_tasks/test_event_models.py \
  backend/tests/test_scheduled_tasks.py -q
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit the model slice**

```bash
git add backend/app/scheduled_tasks/models backend/app/scheduled_tasks/event_catalog.py \
  backend/app/scheduled_tasks/__init__.py backend/tests/scheduled_tasks/test_event_models.py
git commit -m "feat: add event-triggered task models"
```

---

### Task 2: Keep Event Tasks Out of APScheduler

**Files:**

- Modify: `backend/app/scheduled_tasks/scheduler/simple_scheduler.py`
- Modify: `backend/tests/scheduled_tasks/test_event_models.py`

- [ ] **Step 1: Add failing scheduler tests**

```python
from app.scheduled_tasks.scheduler import SimpleScheduler
from app.scheduled_tasks.storage import TaskStorage


def test_event_task_is_not_registered_with_apscheduler(tmp_path):
    storage = TaskStorage(storage_dir=tmp_path)
    task = ScheduledTask(
        task_id="event",
        name="event",
        description="event task",
        trigger_type="event",
        event_type="yuncheng.alert.created",
        schedule_type=None,
        steps=[_step()],
    )
    storage.create(task)
    scheduler = SimpleScheduler(storage)
    scheduler.start()
    try:
        assert scheduler.scheduler.get_job(task.task_id) is None
    finally:
        scheduler.stop()
```

- [ ] **Step 2: Run the test and verify the event task reaches unknown schedule handling**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  backend/tests/scheduled_tasks/test_event_models.py::test_event_task_is_not_registered_with_apscheduler -q
```

Expected: FAIL before the scheduler explicitly skips event tasks.

- [ ] **Step 3: Guard all scheduler mutation entry points**

At the start of `_schedule_task`:

```python
if task.trigger_type == TriggerType.EVENT:
    logger.info("event_task_not_scheduled", task_id=task.task_id, event_type=task.event_type)
    return
```

Apply the same distinction in `add_task()` and `update_task()` so an event task never creates an APScheduler job and changing a schedule task into an event task removes its old job.

Fix `remove_task()` to log with `task_id` instead of the undefined `task` variable:

```python
logger.info(f"Removed task from scheduler: {task_id}")
```

- [ ] **Step 4: Run scheduler and legacy task tests**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  backend/tests/scheduled_tasks/test_event_models.py \
  backend/tests/test_scheduled_tasks.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit scheduler behavior**

```bash
git add backend/app/scheduled_tasks/scheduler/simple_scheduler.py \
  backend/tests/scheduled_tasks/test_event_models.py
git commit -m "feat: exclude event tasks from time scheduling"
```

---

### Task 3: Add Durable Cross-Process Event Claims

**Files:**

- Create: `backend/app/scheduled_tasks/storage/event_claim_storage.py`
- Create: `backend/tests/scheduled_tasks/test_event_claim_storage.py`
- Modify: `backend/app/scheduled_tasks/storage/__init__.py`

- [ ] **Step 1: Write failing claim tests**

```python
# backend/tests/scheduled_tasks/test_event_claim_storage.py
from concurrent.futures import ThreadPoolExecutor

from app.scheduled_tasks.storage import EventClaimStorage


def _event(event_id="event-1"):
    return {
        "event_id": event_id,
        "event_type": "yuncheng.alert.created",
        "occurred_at": f"2026-07-13T16:{'01' if event_id == 'event-2' else '00'}:00+08:00",
        "attributes": {"city": "运城市"},
        "payload": {"evidence_dir": "/tmp/evidence"},
    }


def test_only_one_claim_wins_for_same_task_and_event(tmp_path):
    storage = EventClaimStorage(tmp_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: storage.try_claim("task-1", _event()), range(8)))
    assert sum(result is not None for result in results) == 1


def test_claim_status_survives_new_storage_instance(tmp_path):
    first = EventClaimStorage(tmp_path)
    claim = first.try_claim("task-1", _event())
    first.mark_status(claim.claim_id, "succeeded", execution_id="exec-1")

    second = EventClaimStorage(tmp_path)
    restored = second.get("task-1", "event-1")
    assert restored.status == "succeeded"
    assert restored.execution_id == "exec-1"


def test_failed_claim_can_be_retried_explicitly(tmp_path):
    storage = EventClaimStorage(tmp_path)
    claim = storage.try_claim("task-1", _event())
    storage.mark_status(claim.claim_id, "failed")
    assert storage.try_claim("task-1", _event()) is None
    retry = storage.retry_failed("task-1", "event-1")
    assert retry.status == "claimed"
    assert retry.attempt == 2


def test_latest_event_snapshot_can_drive_manual_execution(tmp_path):
    storage = EventClaimStorage(tmp_path)
    storage.try_claim("task-1", _event("event-1"))
    storage.try_claim("task-2", _event("event-2"))
    latest = storage.latest_event("yuncheng.alert.created")
    assert latest["event_id"] == "event-2"
```

- [ ] **Step 2: Run tests and verify the storage class is missing**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  backend/tests/scheduled_tasks/test_event_claim_storage.py -q
```

Expected: collection fails because `EventClaimStorage` does not exist.

- [ ] **Step 3: Implement file-backed claims under an exclusive lock**

Use one JSON file per SHA-256 idempotency key and a directory lock:

```python
@contextmanager
def _locked(self):
    self.lock_path.touch(exist_ok=True)
    with self.lock_path.open("r+") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def try_claim(self, task_id: str, event: dict[str, Any]) -> EventClaim | None:
    with self._locked():
        event_id = str(event["event_id"])
        path = self._claim_path(task_id, event_id)
        if path.exists():
            return None
        claim = EventClaim(
            claim_id=path.stem,
            task_id=task_id,
            event_id=event_id,
            event_type=str(event["event_type"]),
            event_snapshot=event,
            status="claimed",
            attempt=1,
        )
        self._atomic_write(path, claim.model_dump(mode="json"))
        return claim
```

`mark_status()` only accepts `running`, `succeeded`, or `failed`. `retry_failed()` only transitions `failed -> claimed` and increments `attempt`. `latest_event(event_type)` scans the immutable snapshots and returns the newest by `occurred_at`, supplying manual execution without invented payloads. Atomic writes use a temporary file in the same directory followed by `Path.replace()`.

- [ ] **Step 4: Run claim tests repeatedly to exercise contention**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  backend/tests/scheduled_tasks/test_event_claim_storage.py -q
```

Expected: all tests pass, including the eight-thread contention test with exactly one winning claim.

- [ ] **Step 5: Commit durable claims**

```bash
git add backend/app/scheduled_tasks/storage backend/tests/scheduled_tasks/test_event_claim_storage.py
git commit -m "feat: add durable event task claims"
```

---

### Task 4: Inject Event Context and Parse a Strict Agent Output Contract

**Files:**

- Create: `backend/app/scheduled_tasks/event_output.py`
- Create: `backend/tests/scheduled_tasks/test_event_executor.py`
- Modify: `backend/app/scheduled_tasks/executor/task_executor.py`

- [ ] **Step 1: Write failing executor and parser tests**

```python
# backend/tests/scheduled_tasks/test_event_executor.py
import pytest

from app.scheduled_tasks.event_output import parse_event_task_output
from app.scheduled_tasks.models import TaskEvent


def test_parser_accepts_fenced_broadcast_json(tmp_path):
    report = tmp_path / "report.docx"
    report.write_bytes(b"docx")
    output = parse_event_task_output(
        '```json\n{"success":true,"broadcast":{"message":"告警摘要",'
        f'"media":["{report}"]}}\n```'
    )
    assert output.success is True
    assert output.broadcast.message == "告警摘要"
    assert output.broadcast.media == [str(report)]


def test_parser_rejects_missing_attachment(tmp_path):
    with pytest.raises(ValueError, match="attachment does not exist"):
        parse_event_task_output(
            '{"success":true,"broadcast":{"message":"告警摘要",'
            f'"media":["{tmp_path / "missing.docx"}"]}}'
        )


@pytest.mark.asyncio
async def test_executor_appends_event_context_to_agent_prompt(executor, event_task, fake_agent):
    event = TaskEvent(
        event_id="alert-1",
        event_type="yuncheng.alert.created",
        attributes={"city": "运城市"},
        payload={"evidence_dir": "/tmp/evidence"},
    )
    await executor.execute_task(event_task, event=event)
    prompt = fake_agent.prompts[0]
    assert "alert-1" in prompt
    assert "yuncheng.alert.created" in prompt
    assert "/tmp/evidence" in prompt
    assert "不要直接发送通知" in prompt
```

Define local fixtures in the test using temporary `TaskStorage`, `ExecutionStorage`, and a fake Agent whose `analyze()` yields a `final_response` with the strict JSON contract.

- [ ] **Step 2: Run focused tests and confirm failures**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  backend/tests/scheduled_tasks/test_event_executor.py -q
```

Expected: collection fails because `event_output` is missing and the executor has no `event` argument.

- [ ] **Step 3: Implement the event output contract**

```python
class BroadcastPayload(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
    media: list[str] = Field(default_factory=list)


class EventTaskOutput(BaseModel):
    success: bool
    broadcast: BroadcastPayload | None = None
    error: str | None = None

    @model_validator(mode="after")
    def validate_result(self):
        if self.success and self.broadcast is None:
            raise ValueError("broadcast is required for successful event output")
        return self
```

`parse_event_task_output()` strips one optional Markdown JSON fence, calls `json.loads()`, validates the model, and verifies every local media path exists before delivery.

- [ ] **Step 4: Extend the executor without changing scheduled-task behavior**

Change the signature:

```python
async def execute_task(
    self,
    task: ScheduledTask,
    event: TaskEvent | None = None,
) -> TaskExecution:
```

Set execution metadata from `event`, and build each event prompt with a deterministic suffix:

```python
def _build_event_prompt(self, prompt: str, event: TaskEvent) -> str:
    event_json = event.model_dump_json(indent=2)
    return f"""{prompt}

## 可信事件上下文
{event_json}

## 输出与投递约束
- 完成任务，但不要直接发送通知或调用广播工具。
- 最终只返回 JSON：
  {{"success":true,"broadcast":{{"message":"广播正文","media":["绝对附件路径"]}}}}
- 失败时只返回：{{"success":false,"error":"失败原因"}}
"""
```

Store `trigger_type="event"`, `event_id`, `event_type`, and `event_attributes` on `TaskExecution`. Scheduled calls continue passing no event and retain their current prompt.

- [ ] **Step 5: Run event executor and existing context tests**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  backend/tests/scheduled_tasks/test_event_executor.py \
  backend/tests/test_scheduled_task_context.py \
  backend/tests/test_scheduled_tasks.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit event execution support**

```bash
git add backend/app/scheduled_tasks/event_output.py \
  backend/app/scheduled_tasks/executor/task_executor.py \
  backend/tests/scheduled_tasks/test_event_executor.py
git commit -m "feat: execute tasks with trusted event context"
```

---

### Task 5: Persist Targeted Broadcasts in Every Recipient Conversation

**Files:**

- Create: `backend/app/social/broadcast_context.py`
- Create: `backend/tests/social/test_broadcast_context.py`
- Modify: `backend/app/social/broadcast_service.py`

- [ ] **Step 1: Write failing context persistence tests**

```python
# backend/tests/social/test_broadcast_context.py
import pytest

from app.agent.session.models import Session
from app.social.broadcast_context import persist_broadcast_context


class FakeSessionMapper:
    def __init__(self, session_id):
        self.session_id = session_id

    async def get_or_create_session(self, social_user_id, mode):
        assert mode == "social"
        return self.session_id


@pytest.mark.asyncio
async def test_broadcast_is_appended_as_assistant_message_with_attachment(monkeypatch, tmp_path):
    report = tmp_path / "report.docx"
    report.write_bytes(b"docx")
    session = Session(session_id="social-1", query="social")
    saved = []

    async def fake_load(session_id, *, mode):
        return session

    async def fake_append(value, *, mode):
        saved.append(value)
        return True

    monkeypatch.setattr("app.social.broadcast_context.load_session_for_mode", fake_load)
    monkeypatch.setattr("app.social.broadcast_context.append_session_transcript_for_mode", fake_append)

    ok = await persist_broadcast_context(
        session_mapper=FakeSessionMapper("social-1"),
        social_user_id="weixin:bot:user",
        message="运城告警摘要",
        media=[str(report)],
        metadata={"task_id": "task-1", "event_id": "alert-1", "execution_id": "exec-1"},
    )

    assert ok is True
    assert saved[0].conversation_history[-1]["role"] == "assistant"
    assert saved[0].conversation_history[-1]["data"]["attachments"][0]["path"] == str(report)
    assert saved[0].office_documents[-1]["file_path"] == str(report)


@pytest.mark.asyncio
async def test_same_broadcast_message_is_idempotent(monkeypatch, tmp_path):
    report = tmp_path / "report.docx"
    report.write_bytes(b"docx")
    session = Session(session_id="social-1", query="social")

    async def fake_load(session_id, *, mode):
        return session

    async def fake_append(value, *, mode):
        return True

    monkeypatch.setattr("app.social.broadcast_context.load_session_for_mode", fake_load)
    monkeypatch.setattr("app.social.broadcast_context.append_session_transcript_for_mode", fake_append)
    kwargs = {
        "session_mapper": FakeSessionMapper("social-1"),
        "social_user_id": "weixin:bot:user",
        "message": "运城告警摘要",
        "media": [str(report)],
        "metadata": {
            "task_id": "task-1",
            "event_id": "alert-1",
            "event_type": "yuncheng.alert.created",
            "execution_id": "exec-1",
        },
    }
    assert await persist_broadcast_context(**kwargs)
    assert await persist_broadcast_context(**kwargs)
    broadcasts = [item for item in session.conversation_history if item.get("type") == "broadcast"]
    documents = [item for item in session.office_documents if item.get("file_path") == str(report)]
    assert len(broadcasts) == 1
    assert len(documents) == 1
```

Add a broadcast service test with two target social user IDs: both outbound messages are published, and context persistence is called once for each successful target.

- [ ] **Step 2: Run focused tests and verify missing helper failures**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  backend/tests/social/test_broadcast_context.py -q
```

Expected: collection fails because `broadcast_context` does not exist.

- [ ] **Step 3: Implement idempotent per-user context persistence**

```python
async def persist_broadcast_context(
    *,
    session_mapper,
    social_user_id: str,
    message: str,
    media: list[str],
    metadata: dict[str, Any],
) -> bool:
    session_id = await session_mapper.get_or_create_session(social_user_id, mode="social")
    session = await load_session_for_mode(session_id, mode="social")
    if session is None:
        session = Session(session_id=session_id, query="社交广播上下文")

    message_id = (
        f"broadcast:{metadata['task_id']}:{metadata['event_id']}:"
        f"{social_user_id}"
    )
    attachments = [
        {"name": Path(path).name, "path": path, "type": "file"}
        for path in media
    ]
    if not any(item.get("id") == message_id for item in session.conversation_history):
        session.conversation_history.append({
            "id": message_id,
            "type": "broadcast",
            "role": "assistant",
            "content": message,
            "timestamp": datetime.now().astimezone().isoformat(),
            "data": {**metadata, "attachments": attachments},
        })

    documents = {item.get("file_path"): item for item in session.office_documents}
    for attachment in attachments:
        documents[attachment["path"]] = {
            "file_path": attachment["path"],
            "file_name": attachment["name"],
            "source": "broadcast",
            **metadata,
        }
    session.office_documents = list(documents.values())
    return await append_session_transcript_for_mode(session, mode="social")
```

- [ ] **Step 4: Extend `SocialBroadcastService.broadcast()` with delivery metadata**

Add optional arguments:

```python
context_metadata: Optional[Dict[str, Any]] = None,
persist_context: bool = False,
```

Preserve the distinction between an omitted target list and an explicitly empty target list:

```python
all_user_ids = (
    await session_mapper.get_all_social_user_ids()
    if target_user_ids is None
    else target_user_ids
)
```

This prevents `target_user_ids=[]` from falling through to a broadcast to every known user.

After each successful `publish_outbound`, persist context only for that recipient. Return a `delivery_results` row for every requested user:

```python
{
    "social_user_id": social_user_id,
    "sent": True,
    "context_persisted": True,
    "error": None,
}
```

A context persistence failure does not undo a successful send; set `context_persisted=False` and include the error. A send failure does not write conversation history.

- [ ] **Step 5: Run social persistence regressions**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  backend/tests/social/test_broadcast_context.py \
  backend/app/social/heartbeat_context_spec.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit targeted broadcast context**

```bash
git add backend/app/social/broadcast_context.py backend/app/social/broadcast_service.py \
  backend/tests/social/test_broadcast_context.py
git commit -m "feat: persist targeted broadcasts in social sessions"
```

---

### Task 6: Resolve Admin Users and Orchestrate Event Dispatch

**Files:**

- Create: `backend/app/scheduled_tasks/event_delivery.py`
- Create: `backend/tests/scheduled_tasks/test_event_dispatch.py`
- Modify: `backend/app/scheduled_tasks/service.py`
- Modify: `backend/app/scheduled_tasks/__init__.py`
- Modify: `backend/app/lifecycle/scheduled.py`

- [ ] **Step 1: Write failing dispatch tests**

```python
# backend/tests/scheduled_tasks/test_event_dispatch.py
from unittest.mock import Mock

import pytest

from app.scheduled_tasks.models import ScheduledTask, TaskEvent, TaskStep
from app.scheduled_tasks.service import ScheduledTaskService
from app.scheduled_tasks.storage import EventClaimStorage, ExecutionStorage, TaskStorage


class FakeDelivery:
    def __init__(self):
        self.resolved_social_user_ids = ["weixin:bot:one", "weixin:bot:two"]
        self.target_user_ids = []
        self.delivery_results = [
            {"user_id": "admin-1", "sent": True, "context_persisted": True},
            {"user_id": "admin-2", "sent": True, "context_persisted": True},
        ]

    async def resolve_social_user_ids(self, target_user_ids):
        self.target_user_ids = list(target_user_ids)
        return list(self.resolved_social_user_ids)

    async def deliver(self, **kwargs):
        requested = kwargs.get("target_user_ids")
        if requested is not None:
            self.target_user_ids = list(requested)
        return list(self.delivery_results)


@pytest.fixture
def agent_factory(tmp_path):
    report = tmp_path / "report.docx"
    report.write_bytes(b"docx")

    class FakeAgent:
        async def analyze(self, *args, **kwargs):
            yield {
                "type": "final_response",
                "content": (
                    '{"success":true,"broadcast":{"message":"告警摘要",'
                    f'"media":["{report}"]}}'
                ),
            }

    factory = Mock(side_effect=lambda: FakeAgent())
    return factory


@pytest.fixture
def event_task():
    return ScheduledTask(
        task_id="event-task",
        name="event task",
        description="event task",
        execution_mode="social",
        trigger_type="event",
        event_type="yuncheng.alert.created",
        event_filters={"city": "运城市"},
        broadcast_enabled=True,
        target_user_ids=["admin-1", "admin-2"],
        steps=[TaskStep(step_id="report", description="report", agent_prompt="report")],
    )


@pytest.fixture
def fake_delivery():
    return FakeDelivery()


@pytest.fixture
def service(tmp_path, agent_factory, fake_delivery):
    return ScheduledTaskService(
        agent_factory=agent_factory,
        task_storage=TaskStorage(tmp_path),
        execution_storage=ExecutionStorage(tmp_path),
        claim_storage=EventClaimStorage(tmp_path),
        event_delivery=fake_delivery,
    )


@pytest.mark.asyncio
async def test_unmatched_event_does_not_create_agent(monkeypatch, service, agent_factory):
    result = await service.publish_event(TaskEvent(
        event_id="event-1",
        event_type="other.event",
    ))
    assert result.matched_task_ids == []
    assert agent_factory.call_count == 0


@pytest.mark.asyncio
async def test_matching_event_runs_agent_once_and_broadcasts_to_two_users(
    monkeypatch, service, event_task, agent_factory, fake_delivery
):
    service.create_task(event_task)
    event = TaskEvent(
        event_id="alert-1",
        event_type="yuncheng.alert.created",
        attributes={"city": "运城市"},
        payload={"evidence_dir": "/tmp/evidence"},
    )
    first = await service.publish_event(event, wait=True)
    second = await service.publish_event(event, wait=True)

    assert first.accepted_task_ids == [event_task.task_id]
    assert second.duplicate_task_ids == [event_task.task_id]
    assert agent_factory.call_count == 1
    assert fake_delivery.target_user_ids == ["admin-1", "admin-2"]


@pytest.mark.asyncio
async def test_no_valid_recipients_fails_before_agent(
    service, event_task, agent_factory, fake_delivery
):
    fake_delivery.resolved_social_user_ids = []
    service.create_task(event_task)
    event = TaskEvent(
        event_id="alert-no-users",
        event_type="yuncheng.alert.created",
        attributes={"city": "运城市"},
    )
    result = await service.publish_event(event, wait=True)
    claim = service.claim_storage.get(event_task.task_id, event.event_id)
    execution = service.execution_storage.get(result.execution_ids[0])
    assert agent_factory.call_count == 0
    assert claim.status == "failed"
    assert execution.status.value == "failed"
    assert "no active bound WeChat recipients" in execution.error_message


@pytest.mark.asyncio
async def test_retry_delivery_does_not_rerun_agent(
    service, event_task, agent_factory, fake_delivery
):
    fake_delivery.delivery_results[1]["sent"] = False
    service.create_task(event_task)
    dispatched = await service.publish_event(TaskEvent(
        event_id="partial-delivery",
        event_type="yuncheng.alert.created",
        attributes={"city": "运城市"},
    ), wait=True)
    agent_factory.reset_mock()
    result = await service.retry_failed_delivery(dispatched.execution_ids[0])
    assert result.success is True
    assert fake_delivery.target_user_ids == ["admin-2"]
    assert agent_factory.call_count == 0
```

- [ ] **Step 2: Run tests and verify `publish_event` is absent**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  backend/tests/scheduled_tasks/test_event_dispatch.py -q
```

Expected: FAIL because event dispatch and delivery orchestration do not exist.

- [ ] **Step 3: Implement recipient resolution and delivery**

`EventTaskDelivery.resolve_social_user_ids()` loads every configured backend user ID and keeps only records satisfying:

```python
record.status == "active"
and bool(record.social_user_id)
and record.channel is not None
and record.channel.startswith("weixin")
```

`deliver()` calls:

```python
await SocialBroadcastService().broadcast(
    message=output.broadcast.message,
    media=output.broadcast.media,
    channels=["weixin"],
    target_user_ids=resolved_social_user_ids,
    persist_context=True,
    context_metadata={
        "task_id": task.task_id,
        "execution_id": execution.execution_id,
        "event_id": event.event_id,
        "event_type": event.event_type,
    },
)
```

- [ ] **Step 4: Add event task tracking to `ScheduledTaskService`**

Constructor dependencies become injectable for tests:

```python
def __init__(
    self,
    agent_factory=None,
    task_storage=None,
    execution_storage=None,
    claim_storage=None,
    event_delivery=None,
):
```

Track background executions:

```python
self._event_tasks: set[asyncio.Task] = set()

def _track_event_task(self, coroutine):
    task = asyncio.create_task(coroutine)
    self._event_tasks.add(task)
    task.add_done_callback(self._event_tasks.discard)
    return task
```

`stop()` awaits/cancels tracked work using an async `stop_async()` invoked by the lifecycle shutdown path; do not leave Agent sessions running after worker shutdown.

- [ ] **Step 5: Implement `publish_event()`**

Return a typed summary containing `matched_task_ids`, `accepted_task_ids`, `duplicate_task_ids`, and execution IDs. For each match:

1. Claim `task_id + event_id` together with the immutable event snapshot.
2. Resolve/validate recipients and create a failed execution record if none remain; do not create an Agent.
3. Run `executor.execute_task(task, event=event)` exactly once.
4. Parse the final successful step response through `parse_event_task_output()`.
5. Deliver and store `execution.delivery_results`.
6. Mark the claim `succeeded` after Agent success and delivery processing, including partial delivery; otherwise mark `failed`. Partial delivery remains retryable from the stored Agent response and never reopens the Agent claim.

Support `wait=True` for tests and administrator manual execution. Production publishers use the default `wait=False`, which registers tracked background tasks. Add `retry_failed_delivery(execution_id)` to parse the stored Agent response and call delivery only for backend user IDs whose prior result has `sent=false`; it must not call `agent_factory` or `executor.execute_task`.

Update `backend/app/lifecycle/scheduled.py` to await the service's async shutdown before returning, so worker termination does not abandon tracked event runs.

- [ ] **Step 6: Run dispatch, scheduler, and social tests**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  backend/tests/scheduled_tasks \
  backend/tests/social/test_broadcast_context.py \
  backend/tests/test_scheduled_tasks.py \
  backend/tests/test_scheduled_task_context.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit orchestration**

```bash
git add backend/app/scheduled_tasks/service.py backend/app/scheduled_tasks/event_delivery.py \
  backend/app/scheduled_tasks/__init__.py backend/tests/scheduled_tasks/test_event_dispatch.py
git commit -m "feat: dispatch idempotent event tasks"
```

---

### Task 7: Expose Event Tasks and Registered Events Through the API

**Files:**

- Modify: `backend/app/api/scheduled_task_routes.py`
- Create: `backend/tests/scheduled_tasks/test_event_task_routes.py`

- [ ] **Step 1: Write failing API tests**

```python
# backend/tests/scheduled_tasks/test_event_task_routes.py
def test_list_event_types(client):
    response = client.get("/api/scheduled-tasks/event-types")
    assert response.status_code == 200
    assert response.json()[0]["event_type"] == "yuncheng.alert.created"


def test_create_event_task_with_multiple_users(client):
    response = client.post("/api/scheduled-tasks", json={
        "name": "运城告警推送",
        "description": "有告警时生成报告并推送",
        "execution_mode": "social",
        "trigger_type": "event",
        "schedule_type": None,
        "event_type": "yuncheng.alert.created",
        "event_filters": {"city": "运城市"},
        "broadcast_enabled": True,
        "target_user_ids": ["admin-1", "admin-2"],
        "enabled": True,
        "steps": [{
            "step_id": "report",
            "description": "生成运城告警报告",
            "agent_prompt": "执行运城告警溯源报告任务",
            "timeout_seconds": 1800,
            "retry_on_failure": False,
        }],
        "tags": ["yuncheng", "event"],
    })
    assert response.status_code == 200
    task = response.json()["task"]
    assert task["trigger_type"] == "event"
    assert task["target_user_ids"] == ["admin-1", "admin-2"]


def test_retry_delivery_endpoint_does_not_create_new_execution(client, partial_execution):
    response = client.post(
        f"/api/scheduled-tasks/executions/{partial_execution.execution_id}/retry-delivery"
    )
    assert response.status_code == 200
    assert response.json()["retried_user_ids"] == ["admin-2"]
```

Also test that create/update rejects an unregistered `event_type`, an empty recipient list when broadcasting, and invalid/non-WeChat user IDs.

- [ ] **Step 2: Run route tests and confirm request fields are rejected or ignored**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  backend/tests/scheduled_tasks/test_event_task_routes.py -q
```

Expected: FAIL because the API has no event fields or event catalog endpoint.

- [ ] **Step 3: Expand create/update request models**

Add all timing fields already used by the frontend plus event fields:

```python
trigger_type: TriggerType = TriggerType.SCHEDULE
schedule_type: Optional[ScheduleType] = None
run_at: Optional[datetime] = None
interval_minutes: Optional[int] = None
hour: Optional[int] = None
minute: Optional[int] = None
event_type: Optional[str] = None
event_filters: Dict[str, Any] = Field(default_factory=dict)
broadcast_enabled: bool = False
target_user_ids: List[str] = Field(default_factory=list)
```

Pass these fields into `ScheduledTask` on create and copy them on update. Validate the event type through `get_event_definition()` and resolve every configured backend social user before saving.

- [ ] **Step 4: Add event catalog and manual event endpoints**

Add the static route before `/{task_id}` routes:

```python
@router.get("/event-types", response_model=list[EventDefinition])
async def list_event_types():
    return get_event_definitions()
```

For `POST /{task_id}/execute`, scheduled tasks retain current behavior. Event tasks load `claim_storage.latest_event(task.event_type)` and call `publish_event(event, wait=True, force_retry=True)`; `force_retry` may only reopen a `failed` claim, never a `succeeded` claim. If no event snapshot exists, return HTTP 409 with `No recorded event available for manual execution`.

Add `POST /executions/{execution_id}/retry-delivery`. It calls `service.retry_failed_delivery(execution_id)`, returns the retried backend user IDs and delivery results, and never creates a task execution or Agent run.

- [ ] **Step 5: Run API and scheduled task regressions**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  backend/tests/scheduled_tasks/test_event_task_routes.py \
  backend/tests/test_scheduled_tasks.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit API support**

```bash
git add backend/app/api/scheduled_task_routes.py \
  backend/tests/scheduled_tasks/test_event_task_routes.py
git commit -m "feat: expose event task configuration API"
```

---

### Task 8: Publish the Yuncheng Event Only After Alert Context Is Ready

**Files:**

- Create: `backend/tests/scenarios/yuncheng_trial/test_event_trigger.py`
- Modify: `backend/app/fetchers/yuncheng_trial/yuncheng_trial_fetcher.py`
- Modify: `backend/app/scenarios/yuncheng_trial/evidence_store_spec.py`

- [ ] **Step 1: Write failing no-alert and alert tests**

```python
# backend/tests/scenarios/yuncheng_trial/test_event_trigger.py
import pytest

from app.fetchers.yuncheng_trial import yuncheng_trial_fetcher as fetcher_module
from app.fetchers.yuncheng_trial.yuncheng_trial_fetcher import YunchengTrialFetcher


def _rows(*, alert: bool):
    latest_o3 = 135 if alert else 76
    return [
        {"time": "2026-07-13 13:00:00", "O3": 80, "PM2.5": 20, "PM10": 40, "CO": 0.8, "NO2": 20, "AQI": 40},
        {"time": "2026-07-13 14:00:00", "O3": 82, "PM2.5": 21, "PM10": 41, "CO": 0.8, "NO2": 19, "AQI": 41},
        {"time": "2026-07-13 15:00:00", "O3": 83, "PM2.5": 20, "PM10": 39, "CO": 0.7, "NO2": 18, "AQI": 39},
        {"time": "2026-07-13 16:00:00", "O3": latest_o3, "PM2.5": 19, "PM10": 38, "CO": 0.7, "NO2": 18, "AQI": 65},
    ]


@pytest.mark.asyncio
async def test_no_alert_does_not_publish_event(monkeypatch, tmp_path):
    published = []
    monkeypatch.setattr(fetcher_module, "fetch_target_city_hourly_rows", lambda **kwargs: _rows(alert=False))

    async def capture(event):
        published.append(event)

    monkeypatch.setattr(fetcher_module, "publish_task_event", capture)
    fetcher = YunchengTrialFetcher(registry_root=tmp_path)
    result = await fetcher.fetch_and_store()
    assert result["has_alert"] is False
    assert published == []


@pytest.mark.asyncio
async def test_ready_alert_publishes_one_event(monkeypatch, tmp_path):
    published = []
    manifest = tmp_path / "tracing_context_manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(fetcher_module, "fetch_target_city_hourly_rows", lambda **kwargs: _rows(alert=True))

    async def fake_collect(**kwargs):
        return manifest

    monkeypatch.setattr(fetcher_module, "collect_from_alert_file", fake_collect)

    async def capture(event):
        published.append(event)

    monkeypatch.setattr(fetcher_module, "publish_task_event", capture)
    await YunchengTrialFetcher(registry_root=tmp_path).fetch_and_store()
    assert len(published) == 1
    assert published[0].event_type == "yuncheng.alert.created"
    assert published[0].event_id.startswith("yuncheng-")
    assert published[0].payload["tracing_context_manifest_path"] == str(manifest)
```

The deterministic rows above keep this test offline and avoid contacting SQL Server.

- [ ] **Step 2: Run tests and verify no event is published yet**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  backend/tests/scenarios/yuncheng_trial/test_event_trigger.py -q
```

Expected: FAIL because the fetcher has no event publisher.

- [ ] **Step 3: Add a narrow task event publisher adapter**

In the fetcher module:

```python
async def publish_task_event(event: TaskEvent) -> None:
    from app.scheduled_tasks import get_scheduled_task_service

    service = get_scheduled_task_service()
    await service.publish_event(event)
```

After `collect_from_alert_file()` returns, publish only if the returned manifest path exists:

```python
if manifest_path and Path(manifest_path).is_file():
    await publish_task_event(TaskEvent(
        event_id=str(state["alert_id"]),
        event_type="yuncheng.alert.created",
        occurred_at=state["checked_at"],
        attributes={
            "city": state["city"],
            "alert_level": state.get("alert_level"),
            "target_pollutant": state.get("target_pollutant"),
        },
        payload={
            "alert_json_path": str(alert_path),
            "tracing_context_manifest_path": str(manifest_path),
            "evidence_dir": str(alert_path.parent),
        },
    ))
```

Do not call `get_scheduled_task_service()` on the silent path.

- [ ] **Step 4: Run Yuncheng scenario tests**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  backend/tests/scenarios/yuncheng_trial/test_event_trigger.py \
  backend/app/scenarios/yuncheng_trial/evidence_store_spec.py \
  backend/tests/scenarios/yuncheng_trial/test_context_manifest.py -q
```

Expected: all selected tests pass and the silent test records zero event publications.

- [ ] **Step 5: Commit the first event producer**

```bash
git add backend/app/fetchers/yuncheng_trial/yuncheng_trial_fetcher.py \
  backend/app/scenarios/yuncheng_trial/evidence_store_spec.py \
  backend/tests/scenarios/yuncheng_trial/test_event_trigger.py
git commit -m "feat: publish Yuncheng alert events from code"
```

---

### Task 9: Add Event Task and Multi-User Configuration to the Web UI

**Files:**

- Create: `frontend/src/components/management/scheduledTaskForm.js`
- Create: `frontend/src/components/management/scheduledTaskForm.test.js`
- Modify: `frontend/src/components/management/ScheduledTasksPanel.vue`
- Modify: `frontend/src/stores/scheduledTasks.js`
- Modify: `frontend/package.json`

- [ ] **Step 1: Write failing pure frontend tests**

```javascript
// frontend/src/components/management/scheduledTaskForm.test.js
import assert from 'node:assert/strict'
import test from 'node:test'

import { buildTaskPayload, selectableWeixinUsers } from './scheduledTaskForm.js'

test('filters active bound WeChat users', () => {
  const users = [
    { id: 'a', name: 'A', status: 'active', channel: 'weixin:auto', social_user_id: 'weixin:auto:bot:a' },
    { id: 'b', name: 'B', status: 'disabled', channel: 'weixin:auto', social_user_id: 'weixin:auto:bot:b' },
    { id: 'c', name: 'C', status: 'active', channel: 'qq', social_user_id: 'qq:bot:c' },
  ]
  assert.deepEqual(selectableWeixinUsers(users).map(user => user.id), ['a'])
})

test('builds an event task with multiple backend user ids', () => {
  const payload = buildTaskPayload({
    name: '运城告警推送',
    description: '生成并推送报告',
    execution_mode: 'social',
    trigger_type: 'event',
    event_type: 'yuncheng.alert.created',
    event_filters: { city: '运城市' },
    broadcast_enabled: true,
    target_user_ids: ['a', 'd'],
    enabled: true,
    tagsText: 'yuncheng,event',
  })
  assert.equal(payload.schedule_type, null)
  assert.deepEqual(payload.target_user_ids, ['a', 'd'])
  assert.equal(payload.steps[0].retry_on_failure, false)
})
```

- [ ] **Step 2: Add the test script and verify the helper is missing**

Add to `package.json`:

```json
"test:event-tasks": "node --test src/components/management/scheduledTaskForm.test.js"
```

Run:

```bash
npm --prefix frontend run test:event-tasks
```

Expected: FAIL because `scheduledTaskForm.js` does not exist.

- [ ] **Step 3: Implement pure form helpers**

```javascript
export const selectableWeixinUsers = (users = []) => users.filter(user =>
  user.status === 'active' &&
  Boolean(user.social_user_id) &&
  String(user.channel || '').startsWith('weixin')
)

export const buildTaskPayload = (form) => ({
  name: form.name.trim(),
  description: form.description.trim(),
  execution_mode: form.execution_mode,
  trigger_type: form.trigger_type,
  schedule_type: form.trigger_type === 'event' ? null : form.schedule_type,
  event_type: form.trigger_type === 'event' ? form.event_type : null,
  event_filters: form.trigger_type === 'event' ? form.event_filters : {},
  broadcast_enabled: Boolean(form.broadcast_enabled),
  target_user_ids: form.broadcast_enabled ? [...form.target_user_ids] : [],
  enabled: Boolean(form.enabled),
  steps: [{
    step_id: 'step_1',
    description: form.description.trim(),
    agent_prompt: form.description.trim(),
    timeout_seconds: 1800,
    retry_on_failure: false,
  }],
  tags: form.tagsText.split(',').map(tag => tag.trim()).filter(Boolean),
})
```

Include the existing timing fields only for schedule tasks.

- [ ] **Step 4: Load event definitions and social users in the store**

Add state and actions:

```javascript
eventTypes: [],
socialUsers: [],

async fetchEventTypes() {
  const response = await fetch(`${API_BASE}/event-types`)
  if (!response.ok) throw new Error('Failed to fetch event types')
  this.eventTypes = await response.json()
},

async fetchSocialUsers() {
  const response = await fetch('/api/social/users')
  if (!response.ok) throw new Error('Failed to fetch social users')
  this.socialUsers = await response.json()
},
```

Preserve each task response's `next_run_time` by merging it into the flattened task object instead of discarding it.

- [ ] **Step 5: Extend the task panel**

Change the panel title to `任务管理` and creation command to `新建任务`. Add a segmented trigger selector, registered event dropdown, structured city/alert-level filter controls, broadcast toggle, and checkbox multi-select of `selectableWeixinUsers(store.socialUsers)`.

Validation before submit:

```javascript
if (form.trigger_type === 'event' && !form.event_type) {
  formError.value = '请选择事件类型'
  return
}
if (form.broadcast_enabled && form.target_user_ids.length === 0) {
  formError.value = '请至少选择一名微信接收人'
  return
}
```

For task cards, show `事件触发 · <event label>` and omit next-run time for event tasks. Display selected recipient count. Reuse the same form for create and edit; submit `POST` for new tasks and `PUT` for existing tasks.

- [ ] **Step 6: Run frontend tests and build**

Run:

```bash
npm --prefix frontend run test:event-tasks
npm --prefix frontend run build
```

Expected: Node tests pass and Vite production build completes with no errors.

- [ ] **Step 7: Visually verify the management panel**

Start a development server on a free port and use Playwright at desktop and mobile widths. Verify:

- trigger controls do not shift when switching modes;
- long user names wrap without overlapping checkboxes;
- the selected-user list is scrollable;
- event tasks show no misleading next-run time;
- create/edit validation is visible without an alert dialog.

- [ ] **Step 8: Commit the Web configuration**

```bash
git add frontend/src/components/management/ScheduledTasksPanel.vue \
  frontend/src/components/management/scheduledTaskForm.js \
  frontend/src/components/management/scheduledTaskForm.test.js \
  frontend/src/stores/scheduledTasks.js frontend/package.json
git commit -m "feat: configure event tasks and WeChat recipients"
```

---

### Task 10: End-to-End Verification and Legacy Heartbeat Cutover

**Files:**

- Modify only if verification exposes defects in files already listed above.
- Operationally update the specific active `HEARTBEAT.md` after event-task configuration.

- [ ] **Step 1: Run the complete focused backend suite**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  backend/tests/scheduled_tasks \
  backend/tests/social/test_broadcast_context.py \
  backend/tests/scenarios/yuncheng_trial/test_event_trigger.py \
  backend/app/scenarios/yuncheng_trial/evidence_store_spec.py \
  backend/tests/scenarios/yuncheng_trial/test_context_manifest.py \
  backend/tests/test_scheduled_tasks.py \
  backend/tests/test_scheduled_task_context.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run frontend verification**

Run:

```bash
npm --prefix frontend run test:event-tasks
npm --prefix frontend run build
```

Expected: unit tests and build pass.

- [ ] **Step 3: Create the first event task through the Web UI**

In `任务管理 -> 新建任务`, configure these exact values:

- name: `运城市告警溯源报告推送`
- description: `读取事件中的运城告警和溯源上下文，调用助手模式生成报告，最终按严格 JSON 返回广播摘要和 report.docx 绝对路径。`
- execution mode: `social`
- trigger type: `事件触发`
- event type: `yuncheng.alert.created`
- city filter: `运城市`
- broadcast: enabled
- recipients: select the intended active bound WeChat administrators from the multi-select list
- enabled: true
- step description: `生成并交付运城市告警溯源报告`
- Agent prompt: `读取事件上下文中的 alert_json_path、tracing_context_manifest_path 和 evidence_dir；调用助手模式执行 backend/config/task_lists/yuncheng_alert_tracing_assistant_prompt.md 定义的报告流程。不要发送通知，按任务系统要求返回广播 JSON。`
- timeout: `1800`
- retry on Agent failure: disabled
- tags: `yuncheng`, `alert`, `event`

After saving, inspect the task response and verify `target_user_ids` contains the stable backend IDs of exactly the users selected in the UI.

- [ ] **Step 4: Verify the silent path has zero Agent calls**

Run the Yuncheng fetcher with a silent fixture or controlled no-alert hour. Confirm logs contain fetch completion but no `agent_runtime_run_started`, no `heartbeat_execute_callback`, and no MiMo request for this workflow.

- [ ] **Step 5: Verify one alert event with two test recipients**

Publish a fixture `TaskEvent` using a unique test `event_id` and valid fixture paths. Confirm:

- one task execution record with `trigger_type=event`;
- one Agent run regardless of two recipients;
- two delivery result rows;
- both recipient main social sessions contain the same `broadcast:<task>:<event>:<user>` assistant message;
- both sessions include `report.docx` in `office_documents`;
- publishing the same event again records a duplicate and starts no Agent.

- [ ] **Step 6: Cut over from the legacy heartbeat**

After the enabled event task and targeted recipients are verified, edit only the affected user's `HEARTBEAT.md` and set the legacy `运城市告警溯源报告推送` entry to `enabled: false`. Restart exactly one background worker so it loads the new code and heartbeat state. Confirm only one `python -m app.worker` process remains.

- [ ] **Step 7: Run diff and syntax checks**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 python -m py_compile \
  backend/app/scheduled_tasks/models/event.py \
  backend/app/scheduled_tasks/event_catalog.py \
  backend/app/scheduled_tasks/storage/event_claim_storage.py \
  backend/app/scheduled_tasks/event_output.py \
  backend/app/scheduled_tasks/event_delivery.py \
  backend/app/social/broadcast_context.py
git diff --check
git status --short
```

Expected: compilation succeeds, `git diff --check` is empty, and status contains no unintended files.

- [ ] **Step 8: Commit any verification-only corrections**

If verification required corrections, stage only the files involved and commit:

```bash
git commit -m "fix: complete event task delivery cutover"
```

If no corrections were needed, do not create an empty commit.
