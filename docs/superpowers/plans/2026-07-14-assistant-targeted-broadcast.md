# Assistant Targeted WeChat Broadcast Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow Web-process assistant Agents to call `broadcast_social_users` with required exact user names and have the Worker safely resolve unique bound WeChat users, send text/attachments, and persist recipient conversation context.

**Architecture:** Add a focused targeted-broadcast service in the social layer, expose it only through the authenticated Worker internal FastAPI app, and add a small HTTP client used by the assistant tool. The Worker performs exact-name grouping, rejects duplicate names, resolves unique records into bound WeChat social IDs, and reuses `SocialBroadcastService`; the Web process never touches the message bus.

**Tech Stack:** Python 3.11, FastAPI, httpx, Pydantic v2, pytest/pytest-asyncio

---

## File map

- Create `backend/app/social/targeted_broadcast_service.py`: resolve exact unique user names, invoke the existing broadcaster, merge valid and invalid per-name results.
- Create `backend/app/api/social_broadcast_worker_routes.py`: authenticated Worker-only request boundary.
- Create `backend/app/core/social_broadcast_worker_client.py`: HTTP client for the internal Worker endpoint.
- Modify `backend/app/lifecycle/social_worker_api.py`: register the Worker-only router.
- Modify `backend/app/tools/social/broadcast/tool.py`: require targets and call the Worker client.
- Create `backend/tests/social/test_targeted_broadcast_service.py`: service behavior tests.
- Create `backend/tests/api/test_social_broadcast_worker_routes.py`: Worker route and internal-token tests.
- Create `backend/tests/tools/social/test_broadcast_tool.py`: tool schema, validation, forwarding, and Worker failure tests.

### Task 1: Targeted broadcast domain service

**Files:**
- Create: `backend/app/social/targeted_broadcast_service.py`
- Test: `backend/tests/social/test_targeted_broadcast_service.py`

- [ ] **Step 1: Write failing tests for explicit user resolution and context persistence**

Create fakes for `SocialUserRegistry` and `SocialBroadcastService`. Verify that two explicitly requested exact user names are converted to their unique active bound WeChat `social_user_id` values, `persist_context=True` is used, and returned delivery rows include the input name and backend `user_id`.

```python
result = await service.broadcast(
    message="运城告警",
    target_user_names=["周三成", "李四"],
    media=[str(report)],
    context_metadata={"source": "assistant_tool"},
)
assert broadcaster.calls[0]["target_user_ids"] == [
    "weixin:bot:wx-1",
    "weixin:bot:wx-2",
]
assert broadcaster.calls[0]["persist_context"] is True
assert [row["user_name"] for row in result["delivery_results"]] == [
    "周三成",
    "李四",
]
```

- [ ] **Step 2: Write failing tests for invalid and mixed targets**

Verify empty targets fail without calling the broadcaster; missing, duplicate-name, disabled, unbound, and non-WeChat users get explicit per-name errors; and a mixed request sends only to unique valid explicitly requested users without broadcasting to any other user.

```python
result = await service.broadcast(
    message="运城告警",
    target_user_names=["唯一有效用户", "重名用户"],
)
assert broadcaster.calls[0]["target_user_ids"] == ["weixin:bot:valid"]
assert result["success"] is True
assert result["failed_user_names"] == ["重名用户"]
```

- [ ] **Step 3: Run the service tests and verify RED**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/social/test_targeted_broadcast_service.py
```

Expected: FAIL because `TargetedSocialBroadcastService` does not exist.

- [ ] **Step 4: Implement the minimal service**

Implement:

```python
class TargetedSocialBroadcastService:
    def __init__(self, user_registry=None, broadcast_service=None): ...

    async def broadcast(
        self,
        *,
        message: str,
        target_user_names: list[str],
        media: list[str] | None = None,
        context_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...
```

The method must trim and preserve requested-name order, deduplicate identical input names, load registry users once, group by exact `record.name`, reject groups whose size is not exactly one, validate the unique record using the same active/bound/WeChat rules as event delivery, call `SocialBroadcastService.broadcast` only when at least one valid target exists, force `channels=["weixin"]` and `persist_context=True`, map social IDs back to both input names and backend IDs, and calculate overall success from actual `sent` rows.

- [ ] **Step 5: Run service tests and verify GREEN**

Run the Task 1 pytest command. Expected: all tests PASS.

- [ ] **Step 6: Commit Task 1**

```bash
git add backend/app/social/targeted_broadcast_service.py backend/tests/social/test_targeted_broadcast_service.py
git commit -m "feat: add targeted social broadcast service"
```

### Task 2: Authenticated Worker broadcast endpoint

**Files:**
- Create: `backend/app/api/social_broadcast_worker_routes.py`
- Modify: `backend/app/lifecycle/social_worker_api.py`
- Test: `backend/tests/api/test_social_broadcast_worker_routes.py`

- [ ] **Step 1: Write failing route tests**

Build the internal app with `create_social_worker_api_app` and a non-empty internal token. Verify `POST /internal/social/broadcast` rejects a missing token with 403, accepts the correct token, validates non-empty `message` and `target_user_names`, and forwards all fields to a replaceable targeted-broadcast service dependency.

```python
response = client.post(
    "/internal/social/broadcast",
    headers={"x-social-worker-token": "secret"},
    json={
        "message": "运城告警",
        "target_user_names": ["周三成"],
        "media": ["/tmp/report.docx"],
        "context_metadata": {"source": "assistant_tool"},
    },
)
assert response.status_code == 200
assert fake_service.calls[0]["target_user_names"] == ["周三成"]
```

- [ ] **Step 2: Run the route tests and verify RED**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/api/test_social_broadcast_worker_routes.py
```

Expected: FAIL because the route module and endpoint do not exist.

- [ ] **Step 3: Implement the request model and route**

Create an `APIRouter(prefix="/internal/social")`, a Pydantic request with `message` length validation and `target_user_names` `min_length=1`, and `POST /broadcast`. Provide a small module-level override setter for tests, matching the existing channel-manager override pattern.

- [ ] **Step 4: Register the router in the Worker internal app**

Import and include the new router in `create_social_worker_api_app`. Do not add it to the public Web FastAPI router set; the existing internal-token middleware remains the authorization boundary.

- [ ] **Step 5: Run route and service tests and verify GREEN**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/api/test_social_broadcast_worker_routes.py backend/tests/social/test_targeted_broadcast_service.py
```

Expected: all tests PASS.

- [ ] **Step 6: Commit Task 2**

```bash
git add backend/app/api/social_broadcast_worker_routes.py backend/app/lifecycle/social_worker_api.py backend/tests/api/test_social_broadcast_worker_routes.py
git commit -m "feat: expose targeted broadcast on social worker"
```

### Task 3: Worker HTTP client and assistant tool

**Files:**
- Create: `backend/app/core/social_broadcast_worker_client.py`
- Modify: `backend/app/tools/social/broadcast/tool.py`
- Test: `backend/tests/tools/social/test_broadcast_tool.py`

- [ ] **Step 1: Write failing tool tests**

Verify the tool schema includes `target_user_names` in `required`, empty targets fail locally without invoking HTTP, and a valid call forwards message, exact names, media, and assistant source metadata to a fake Worker client.

```python
result = await tool.execute(
    message="运城告警",
    target_user_names=["周三成"],
    media=["/tmp/report.docx"],
)
assert fake_client.calls[0]["target_user_names"] == ["周三成"]
assert fake_client.calls[0]["context_metadata"]["source"] == "assistant_tool"
```

Also verify Worker connection errors become a structured failed tool result and never fall back to local broadcast-all behavior.

- [ ] **Step 2: Run tool tests and verify RED**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/tools/social/test_broadcast_tool.py
```

Expected: FAIL because the tool does not require targets or use a Worker client.

- [ ] **Step 3: Implement the Worker client**

Create `SocialBroadcastWorkerClient` using `httpx.AsyncClient`, `settings.social_worker_internal_url`, and `settings.social_worker_internal_token`. POST to `/internal/social/broadcast`, set `x-social-worker-token` when configured, use a bounded timeout, return decoded JSON, and raise a focused `SocialBroadcastWorkerUnavailable` exception for request failures and non-2xx responses.

- [ ] **Step 4: Update the tool schema and execution path**

Add:

```python
"target_user_names": {
    "type": "array",
    "items": {"type": "string"},
    "minItems": 1,
    "description": "后台微信用户名称列表，精确匹配且重名时拒绝",
}
```

Set `required` to `['message', 'target_user_names']`. Inject or lazily create the Worker client, reject empty targets, and remove the direct `get_message_bus`/`SocialBroadcastService` path.

- [ ] **Step 5: Run tool tests and verify GREEN**

Run the Task 3 pytest command. Expected: all tests PASS.

- [ ] **Step 6: Commit Task 3**

```bash
git add backend/app/core/social_broadcast_worker_client.py backend/app/tools/social/broadcast/tool.py backend/tests/tools/social/test_broadcast_tool.py
git commit -m "fix: proxy assistant broadcasts to social worker"
```

### Task 4: Regression and live verification

**Files:**
- Verify all files from Tasks 1–3.

- [ ] **Step 1: Run focused regression tests**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q \
  backend/tests/tools/social/test_broadcast_tool.py \
  backend/tests/api/test_social_broadcast_worker_routes.py \
  backend/tests/social/test_targeted_broadcast_service.py \
  backend/tests/social/test_broadcast_context.py \
  backend/tests/scheduled_tasks
```

Expected: all tests PASS.

- [ ] **Step 2: Run static diff checks**

```bash
git diff --check
```

Expected: no output and exit code 0.

- [ ] **Step 3: Restart Web and Worker with the configured environment**

Restart only after tests pass. Keep the Worker model configuration at `LLM_PROVIDER=deepseek` and `DEEPSEEK_MODEL=deepseek-v4-flash`. Verify exactly one Worker listens on 8011 and Web listens on 8000.

- [ ] **Step 4: Perform one authorized targeted live test**

Use the assistant tool with `target_user_names=["周三成"]` only. Send a clearly labeled test message without report regeneration. Verify the tool result has exactly one row with `user_name="周三成"`, `sent=true`, and `context_persisted=true`, and verify the target social session contains the broadcast metadata. Do not send to any other user.

- [ ] **Step 5: Request code review and address findings**

Review the complete diff for authentication, accidental broadcast-all behavior, exact-name and duplicate-name handling, ID mapping, partial-failure semantics, and context persistence. Fix Critical and Important findings and rerun Task 4 Steps 1–2.

- [ ] **Step 6: Final verification record**

Record the passing test count, live delivery result, target user name and resolved backend user ID, social session ID, active Worker model, and service listener PIDs in the handoff response.
