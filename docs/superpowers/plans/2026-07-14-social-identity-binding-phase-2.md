# Social Identity Binding Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind a Web-authenticated platform user directly to the WeChat identity returned by QR confirmation and expose only new bound social history as read-only Web history.

**Architecture:** Persist QR-task ownership and active platform-to-WeChat binding in PostgreSQL, while keeping the existing social file session as the runtime source of truth. The inbound bridge resolves every sender to an active platform binding before creating a session, registers that session in the phase-1 catalog, and rejects unbound senders. A social source adapter exposes cataloged social sessions to Web restoration without permitting Web writes.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, SQLAlchemy async, PostgreSQL, httpx, pytest, Vue 3, Axios, Node test runner

---

## Prerequisite

Complete and deploy `docs/superpowers/plans/2026-07-14-conversation-ownership-phase-1.md` first. This plan imports `ConversationCatalogService`, `ConversationSource`, and the unified session adapter registry created there.

## File Structure

- Create `backend/app/social/binding_service.py`: owned QR tasks and one-to-one platform/WeChat binding transactions.
- Create `backend/app/social/binding_repository.py`: transactional SQLAlchemy operations for scan tasks and bindings.
- Create `backend/app/social/binding_schemas.py`: QR task and binding DTOs.
- Create `backend/app/db/migrations/007_add_platform_social_bindings.sql`: new ownership fields, QR tasks, constraints, and indexes.
- Create `backend/tests/social/test_platform_social_binding.py`: binding and replacement rules.
- Create `backend/tests/api/test_owned_weixin_scan.py`: QR endpoint ownership tests.
- Create `backend/tests/social/test_bound_social_routing.py`: unbound rejection and catalog registration.
- Create `backend/tests/api/test_social_history_adapter.py`: read-only Web history tests.
- Modify `backend/app/social/models.py`: platform identity fields and QR task ORM model.
- Modify `backend/app/social/user_registry.py`: platform binding queries; retain legacy rows without migration.
- Modify `backend/app/channels/weixin.py`: persist QR-confirmed `ilink_user_id`.
- Modify `backend/app/api/social_account_routes.py`: authenticated, server-owned scan lifecycle.
- Modify `backend/app/social/agent_bridge.py`: remove new-flow code binding and require active platform identity.
- Modify `backend/app/social/session_mapper.py`: return mapping without creating it until binding/catalog registration succeeds.
- Modify `backend/app/conversations/adapters.py`: social read-only summary/detail adapter.
- Modify `backend/app/api/session_routes.py`: dispatch social read requests and reject writes through phase-1 policy.
- Modify `frontend/src/components/social/CreateAccountModal.vue`: reduce onboarding to QR scan and completion.
- Modify `frontend/src/components/social/createAccountFlow.js`: remove binding-code state.
- Modify `frontend/src/components/social/createAccountFlow.test.js`: new two-step flow tests.
- Modify `frontend/src/composables/reactAnalysis/useSessionManagement.js`: expose social read-only state.
- Modify `frontend/src/components/reactAnalysis/ChatArea.vue`: disable input for restored social history.

### Task 1: Persist QR Scanner Identity in the WeChat Channel

**Files:**
- Modify: `backend/app/channels/weixin.py`
- Create: `backend/tests/social/test_weixin_scanner_identity.py`

- [ ] **Step 1: Write failing scanner-state tests**

Create `test_weixin_scanner_identity.py`:

```python
import json

import pytest


@pytest.mark.asyncio
async def test_confirmed_qr_scan_persists_ilink_user_id(weixin_channel, monkeypatch):
    responses = iter([{
        "status": "confirmed",
        "bot_token": "secret-token",
        "ilink_bot_id": "bot-1",
        "ilink_user_id": "wx-user-1",
        "baseurl": "https://example.invalid",
    }])

    async def fake_get(*args, **kwargs):
        return next(responses)

    monkeypatch.setattr(weixin_channel, "_api_get", fake_get)
    weixin_channel._running = True

    assert await weixin_channel._wait_for_qr_scan("qr-1") is True
    assert weixin_channel.scanner_user_id == "wx-user-1"

    state = json.loads((weixin_channel._get_state_dir() / "account.json").read_text())
    assert state["scanner_user_id"] == "wx-user-1"
```

Add a restart test that constructs a new channel from the same state directory and asserts `scanner_user_id == "wx-user-1"`.

- [ ] **Step 2: Run the channel test and verify RED**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/social/test_weixin_scanner_identity.py -q
```

Expected: `scanner_user_id` is absent and `ilink_user_id` is discarded.

- [ ] **Step 3: Store scanner identity in both QR confirmation paths**

Initialize and expose the field in `WeixinChannel`:

```python
self._scanner_user_id: str = ""

@property
def scanner_user_id(self) -> str:
    return self._scanner_user_id
```

Load/save it with the existing account state:

```python
self._scanner_user_id = str(data.get("scanner_user_id") or "")
```

```python
data = {
    "token": self._token,
    "bot_id": self._bot_id,
    "scanner_user_id": self._scanner_user_id,
    "get_updates_buf": self._get_updates_buf,
    "context_tokens": self._context_tokens,
    "base_url": getattr(self.config, "base_url", "https://ilinkai.weixin.qq.com"),
}
```

In both `_wait_for_qr_scan` and `_qr_login`, assign before `_save_state()`:

```python
self._token = token
self._bot_id = bot_id
self._scanner_user_id = str(user_id or "")
```

Reset `_scanner_user_id` during forced login.

- [ ] **Step 4: Run channel tests and verify GREEN**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/social/test_weixin_scanner_identity.py backend/tests/social/test_weixin_channel.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit scanner persistence**

```bash
git add backend/app/channels/weixin.py backend/tests/social/test_weixin_scanner_identity.py
git commit -m "feat: persist WeChat scanner identity"
```

### Task 2: Add Owned QR Tasks and Platform Bindings

**Files:**
- Modify: `backend/app/social/models.py`
- Create: `backend/app/social/binding_schemas.py`
- Create: `backend/app/social/binding_service.py`
- Create: `backend/app/db/migrations/007_add_platform_social_bindings.sql`
- Create: `backend/tests/social/test_platform_social_binding.py`
- Create: `backend/tests/social/test_social_binding_migration.py`

- [ ] **Step 1: Write failing one-to-one binding tests**

Create `test_platform_social_binding.py` with a fake repository:

```python
import pytest

from app.auth.models import CurrentUser
from app.social.binding_service import SocialBindingConflict, SocialBindingService


@pytest.mark.asyncio
async def test_same_platform_user_replaces_previous_wechat_binding():
    repository = FakeBindingRepository()
    service = SocialBindingService(repository)
    user = CurrentUser(id="u1", username="alice", display_name="Alice")

    first = await service.activate(
        task_id="task-1", user=user, account_id="a1",
        ilink_user_id="wx-1", bot_account="bot-1",
    )
    second = await service.activate(
        task_id="task-2", user=user, account_id="a2",
        ilink_user_id="wx-2", bot_account="bot-2",
    )

    assert first.status == "replaced"
    assert second.status == "active"
    assert await repository.active_for_platform_user("u1") == second


@pytest.mark.asyncio
async def test_wechat_identity_cannot_be_taken_from_another_platform_user():
    repository = FakeBindingRepository()
    service = SocialBindingService(repository)
    await service.activate(
        task_id="task-1",
        user=CurrentUser(id="u1", username="alice", display_name="Alice"),
        account_id="a1", ilink_user_id="wx-shared", bot_account="bot-1",
    )

    with pytest.raises(SocialBindingConflict):
        await service.activate(
            task_id="task-2",
            user=CurrentUser(id="u2", username="bob", display_name="Bob"),
            account_id="a2", ilink_user_id="wx-shared", bot_account="bot-2",
        )
```

Also test that a QR task can be read/changed only by its owner or an administrator.

- [ ] **Step 2: Run binding tests and verify RED**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/social/test_platform_social_binding.py -q
```

Expected: module import fails because the binding service does not exist.

- [ ] **Step 3: Add binding DTOs and ORM fields**

Create `binding_schemas.py`:

```python
from datetime import datetime
from pydantic import BaseModel


class SocialBindingRecord(BaseModel):
    id: str
    platform_user_id: str
    platform_username: str
    platform_display_name: str
    account_id: str
    ilink_user_id: str
    bot_account: str
    status: str
    bound_at: datetime


class WeixinScanTaskRecord(BaseModel):
    id: str
    account_id: str
    owner_user_id: str
    owner_username: str
    owner_display_name: str
    status: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
```

Extend `SocialUser` with nullable `platform_user_id`, `platform_username`, `platform_display_name`, `account_id`, and `ilink_user_id`. Add `WeixinScanTask` with the fields in `WeixinScanTaskRecord`. Keep every new `SocialUser` column nullable so legacy rows remain untouched.

- [ ] **Step 4: Implement transactional binding service**

Create `binding_repository.py` with concrete database operations named `create_scan_task`, `get_scan_task`, `set_scan_status`, `replace_active_binding`, and `resolve_sender`. `replace_active_binding` owns a single `async_session.begin()` transaction: it locks the task, the active row for the platform user, and the active row for the incoming WeChat identity; rejects a foreign active owner; marks the caller's prior active binding `replaced`; inserts or updates the selected binding; and marks the task `confirmed`.

Expose these service methods with the following bodies:

```python
class SocialBindingConflict(RuntimeError):
    pass


class SocialBindingService:
    def __init__(self, repository):
        self.repository = repository

    async def create_scan_task(self, user: CurrentUser) -> WeixinScanTaskRecord:
        return await self.repository.create_scan_task(user)

    async def require_scan_task(
        self, task_id: str, user: CurrentUser
    ) -> WeixinScanTaskRecord:
        task = await self.repository.get_scan_task(task_id)
        if task is None or (not user.is_admin and task.owner_user_id != user.id):
            raise HTTPException(status_code=404, detail="weixin_scan_not_found")
        return task

    async def mark_scan_status(
        self, task_id: str, user: CurrentUser, status: str
    ) -> WeixinScanTaskRecord:
        await self.require_scan_task(task_id, user)
        return await self.repository.set_scan_status(task_id, status)

    async def activate(
        self, *, task_id: str, user: CurrentUser, account_id: str,
        ilink_user_id: str, bot_account: str,
    ) -> SocialBindingRecord:
        task = await self.require_scan_task(task_id, user)
        if task.account_id != account_id:
            raise HTTPException(status_code=404, detail="weixin_scan_not_found")
        try:
            return await self.repository.replace_active_binding(
                task=task,
                ilink_user_id=ilink_user_id,
                bot_account=bot_account,
            )
        except ForeignWeixinIdentityError as exc:
            raise SocialBindingConflict("weixin_identity_already_bound") from exc

    async def resolve_sender(
        self, *, channel: str, bot_account: str, sender_id: str
    ) -> SocialBindingRecord | None:
        if channel != "weixin" and not channel.startswith("weixin:"):
            return None
        return await self.repository.resolve_sender(
            bot_account=bot_account,
            ilink_user_id=sender_id,
        )
```

Import `HTTPException`, `CurrentUser`, the binding DTOs, and repository conflict type. Add a singleton `get_social_binding_service()` dependency built from `SocialBindingRepository`.

- [ ] **Step 5: Add migration contract and SQL**

Create `test_social_binding_migration.py`:

```python
from pathlib import Path


def test_social_binding_migration_preserves_legacy_rows_and_adds_unique_active_indexes():
    sql = Path("backend/app/db/migrations/007_add_platform_social_bindings.sql").read_text()
    assert "ADD COLUMN IF NOT EXISTS platform_user_id" in sql
    assert "CREATE TABLE IF NOT EXISTS weixin_scan_tasks" in sql
    assert "WHERE status = 'active'" in sql
    assert "UPDATE social_users SET platform_user_id" not in sql
```

Implement the SQL with nullable columns, the scan-task table, an index on task owner/status, and partial unique indexes for active `platform_user_id` and active `ilink_user_id`. Do not backfill legacy `social_users` or `social_session_mappings`.

- [ ] **Step 6: Run service and migration tests**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  backend/tests/social/test_platform_social_binding.py \
  backend/tests/social/test_social_binding_migration.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit binding persistence**

```bash
git add backend/app/social/models.py backend/app/social/binding_schemas.py backend/app/social/binding_repository.py backend/app/social/binding_service.py backend/app/db/migrations/007_add_platform_social_bindings.sql backend/tests/social/test_platform_social_binding.py backend/tests/social/test_social_binding_migration.py
git commit -m "feat: add platform WeChat identity bindings"
```

### Task 3: Make QR Account APIs Server-Owned and Authenticated

**Files:**
- Modify: `backend/app/api/social_account_routes.py`
- Modify: `backend/app/social/user_registry.py`
- Create: `backend/tests/api/test_owned_weixin_scan.py`

- [ ] **Step 1: Write failing QR ownership tests**

Create `test_owned_weixin_scan.py`:

```python
def test_auto_create_ignores_client_identity_and_uses_current_user(client_u1):
    response = client_u1.post("/api/social/accounts/weixin/auto-create", json={})
    assert response.status_code == 200
    assert response.json()["platform_user_id"] == "u1"
    assert response.json()["platform_username"] == "alice"
    assert response.json()["account_id"].startswith("auto_")


def test_other_user_cannot_read_refresh_finalize_or_delete_scan_task(client_u2, u1_task):
    for method, path in (
        ("GET", f"/api/social/accounts/weixin/{u1_task}/status"),
        ("GET", f"/api/social/accounts/weixin/{u1_task}/qrcode"),
        ("POST", f"/api/social/accounts/weixin/{u1_task}/refresh-qrcode"),
        ("POST", f"/api/social/accounts/weixin/{u1_task}/finalize"),
        ("DELETE", f"/api/social/accounts/weixin/{u1_task}"),
    ):
        assert client_u2.request(method, path, json={}).status_code == 404


def test_ordinary_account_list_is_owner_scoped_while_admin_sees_all(
    client_u1, client_admin, finalized_u1_account, finalized_u2_account
):
    assert ids(client_u1.get("/api/social/accounts")) == {finalized_u1_account}
    assert ids(client_admin.get("/api/social/accounts")) == {
        finalized_u1_account, finalized_u2_account
    }
```

Add success coverage for owner and administrator, scan timeout cleanup, and rejection when an ordinary user tries to start, stop, refresh, finalize, or delete another user's finalized account.

- [ ] **Step 2: Run QR API tests and verify RED**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/api/test_owned_weixin_scan.py -q
```

Expected: current API accepts a client-generated `temp_id` and has no owner checks.

- [ ] **Step 3: Replace client-generated temp IDs with scan tasks**

Change auto-create to accept no identity fields and use dependencies:

```python
@router.post("/weixin/auto-create")
async def auto_create_account(
    user: CurrentUser = Depends(require_current_user),
    bindings: SocialBindingService = Depends(get_social_binding_service),
):
    task = await bindings.create_scan_task(user)
    account_id = task.account_id
    # Existing channel/config creation continues with server-generated account_id.
    return {
        "task_id": task.id,
        "account_id": account_id,
        "platform_user_id": user.id,
        "platform_username": user.username,
        "platform_display_name": user.display_name,
        "status": "created",
        "qr_code_available": bool(getattr(channel, "_current_qr_code_path", None)),
    }
```

For qrcode/status/refresh/finalize/delete, load the scan task and call `require_scan_task` before resolving the channel or reading any QR file.

For finalized account list/start/stop/delete endpoints, resolve the active binding by `account_id`. Ordinary users may operate only records whose `platform_user_id == current_user.id`; administrators may operate all records. Filter the account list before serializing channel status so ordinary users never receive another user's account ID, bot account, login status, or QR availability.

- [ ] **Step 4: Finalize from channel scanner identity**

Remove `FinalizeRequest.name`. On finalize, take only server state:

```python
scanner_user_id = channel.scanner_user_id
bot_account = channel.bot_account
if not scanner_user_id or not bot_account:
    raise HTTPException(status_code=409, detail="weixin_scan_not_confirmed")

binding = await bindings.activate(
    task_id=task.id,
    user=user,
    account_id=task.account_id,
    ilink_user_id=scanner_user_id,
    bot_account=bot_account,
)
channel.config.name = user.display_name or user.username
```

If activation replaced an earlier binding for the same platform user, stop its old channel and set its account configuration `enabled=False`; retain the old binding row with `status="replaced"` for audit. Return only non-secret binding fields. Remove the existing `token_preview` log from finalize and never return or log the WeChat token.

- [ ] **Step 5: Run QR route and social-account regressions**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  backend/tests/api/test_owned_weixin_scan.py \
  backend/tests/api/test_social_account_routes.py -q
```

Expected: tests pass.

- [ ] **Step 6: Commit owned scan APIs**

```bash
git add backend/app/api/social_account_routes.py backend/app/social/user_registry.py backend/tests/api/test_owned_weixin_scan.py
git commit -m "feat: bind QR scans to authenticated users"
```

### Task 4: Simplify the Frontend to Login, Scan, Complete

**Files:**
- Modify: `frontend/src/components/social/CreateAccountModal.vue`
- Modify: `frontend/src/components/social/createAccountFlow.js`
- Modify: `frontend/src/components/social/createAccountFlow.test.js`

- [ ] **Step 1: Rewrite flow tests first**

Replace binding-code expectations with:

```javascript
import test from 'node:test'
import assert from 'node:assert/strict'

import { getOnboardingStep, scanOwnerLabel } from './createAccountFlow.js'

test('new flow goes directly from QR to completion', () => {
  assert.equal(getOnboardingStep({ scanCreated: false, scanConfirmed: false }), 'starting')
  assert.equal(getOnboardingStep({ scanCreated: true, scanConfirmed: false }), 'qrcode')
  assert.equal(getOnboardingStep({ scanCreated: true, scanConfirmed: true }), 'complete')
})

test('owner label comes from server-authenticated identity', () => {
  assert.equal(
    scanOwnerLabel({ platform_display_name: 'Alice', platform_username: 'alice' }),
    'Alice（alice）'
  )
})
```

- [ ] **Step 2: Run frontend flow tests and verify RED**

Run:

```bash
cd frontend && node --test src/components/social/createAccountFlow.test.js
```

Expected: current three-stage profile/QR/binding flow fails the new expectations.

- [ ] **Step 3: Implement the two-stage helper**

Use:

```javascript
export function getOnboardingStep({ scanCreated, scanConfirmed }) {
  if (!scanCreated) return 'starting'
  if (!scanConfirmed) return 'qrcode'
  return 'complete'
}

export function scanOwnerLabel(scan) {
  const username = scan?.platform_username || ''
  const displayName = scan?.platform_display_name || username
  return username && displayName !== username ? `${displayName}（${username}）` : displayName
}
```

Delete binding-instruction helpers from the new flow.

- [ ] **Step 4: Simplify the modal**

Remove the profile form, name/email state, pending social user creation, binding-code screen, bind polling, and related timers. On mount or the explicit start button, call `POST /api/social/accounts/weixin/auto-create` with `{}` and store `task_id`, `account_id`, and server-returned platform labels. Continue QR/status polling. When status becomes logged in, call finalize with `{}` and enter completion state.

The completion panel must show `scanOwnerLabel(scan)` and must not display a four-digit code or ask the user to send a message in WeChat.

- [ ] **Step 5: Run flow tests and frontend build**

Run:

```bash
cd frontend && node --test src/components/social/createAccountFlow.test.js && npm run build
```

Expected: tests pass and Vite build succeeds.

- [ ] **Step 6: Commit the simplified UI**

```bash
git add frontend/src/components/social/CreateAccountModal.vue frontend/src/components/social/createAccountFlow.js frontend/src/components/social/createAccountFlow.test.js
git commit -m "feat: simplify authenticated WeChat scanning"
```

### Task 5: Reject Unbound Senders and Register Bound Social Sessions

**Files:**
- Modify: `backend/app/social/agent_bridge.py`
- Modify: `backend/app/social/session_mapper.py`
- Create: `backend/tests/social/test_bound_social_routing.py`

- [ ] **Step 1: Write failing inbound-routing tests**

Create `test_bound_social_routing.py`:

```python
@pytest.mark.asyncio
async def test_unbound_sender_gets_instruction_without_session_or_agent_call(bridge):
    bridge.binding_service.resolve_sender.return_value = None

    await bridge._route_message(inbound(sender_id="wx-unbound", content="hello"))

    bridge.session_mapper.get_or_create_session.assert_not_awaited()
    bridge.agent.analyze.assert_not_called()
    outbound = await bridge.message_bus.consume_outbound()
    assert "先登录 Web" in outbound.content


@pytest.mark.asyncio
async def test_bound_sender_registers_social_catalog_before_processing(bridge):
    bridge.binding_service.resolve_sender.return_value = binding(platform_user_id="u1")

    await bridge._route_message(inbound(sender_id="wx-1", content="hello"))

    bridge.catalog.register_identity.assert_awaited_once_with(
        session_id=bridge.session_mapper.created_session_id,
        owner_user_id="u1",
        owner_username="alice",
        owner_display_name="Alice",
        source=ConversationSource.SOCIAL,
        mode="social",
        title="hello",
        read_only_on_web=True,
    )
```

Also assert that legacy binding-code messages are treated as ordinary unbound messages and do not bind anything.

- [ ] **Step 2: Run bridge tests and verify RED**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/social/test_bound_social_routing.py -q
```

Expected: current bridge creates sessions for unbound senders and intercepts four-digit codes.

- [ ] **Step 3: Resolve binding before SessionMapper**

Inject `SocialBindingService` and `ConversationCatalogService` into `AgentBridge`. At the top of social `_route_message`:

```python
binding = await self.binding_service.resolve_sender(
    channel=msg.channel,
    bot_account=bot_account,
    sender_id=msg.sender_id,
)
if binding is None:
    await self.message_bus.publish_outbound(OutboundMessage(
        channel=msg.channel,
        chat_id=msg.chat_id,
        content="请先登录 Web 端，在微信账号管理中完成扫码绑定。",
        reply_to=msg.sender_id,
    ))
    return
```

Remove the four-digit binding branch from the new message path.

- [ ] **Step 4: Register ownership before exposing a new mapping**

Split SessionMapper creation into `new_session_id(mode)` and `save_mapping(social_user_id, session_id)`. For a new sender mapping:

```python
session_id = self.session_mapper.new_session_id(self.mode)
await self.catalog.register_identity(
    session_id=session_id,
    owner_user_id=binding.platform_user_id,
    owner_username=binding.platform_username,
    owner_display_name=binding.platform_display_name,
    source=ConversationSource.SOCIAL,
    mode=self.mode,
    title=(msg.content or "微信会话")[:256],
    read_only_on_web=True,
)
await self.session_mapper.save_mapping(social_user_id, session_id)
```

If catalog registration fails, do not save the mapping or call Agent. Existing bound mappings must verify that their catalog owner still matches the active binding.

- [ ] **Step 5: Run bridge and existing social tests**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  backend/tests/social/test_bound_social_routing.py \
  backend/tests/test_social_user_registry.py \
  backend/tests/social/test_broadcast_context.py -q
```

Expected: new routing tests pass; update legacy binding tests to exercise the registry directly rather than AgentBridge because inbound four-digit binding is intentionally removed.

- [ ] **Step 6: Commit bound social routing**

```bash
git add backend/app/social/agent_bridge.py backend/app/social/session_mapper.py backend/tests/social/test_bound_social_routing.py backend/tests/test_social_user_registry.py
git commit -m "feat: require platform binding for social sessions"
```

### Task 6: Add Read-Only Social History to Unified Web Sessions

**Files:**
- Modify: `backend/app/conversations/adapters.py`
- Modify: `backend/app/api/session_routes.py`
- Create: `backend/tests/api/test_social_history_adapter.py`

- [ ] **Step 1: Write failing social history tests**

Create `test_social_history_adapter.py`:

```python
def test_bound_social_history_appears_only_for_owner_and_admin(owner_client, other_client, admin_client):
    assert "social-1" in ids(owner_client.get("/api/sessions"))
    assert "social-1" not in ids(other_client.get("/api/sessions"))
    assert "social-1" in ids(admin_client.get("/api/sessions"))


def test_owner_can_restore_social_history_but_cannot_mutate_it(owner_client):
    restored = owner_client.post("/api/sessions/social-1/restore")
    assert restored.status_code == 200
    assert restored.json()["session"]["read_only_on_web"] is True
    assert restored.json()["session"]["source"] == "social"

    for method, suffix in (("POST", "/save"), ("DELETE", ""), ("POST", "/case")):
        response = owner_client.request(method, f"/api/sessions/social-1{suffix}")
        assert response.status_code == 409
        assert response.json()["detail"] == "social_session_read_only"
```

- [ ] **Step 2: Run social history tests and verify RED**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/api/test_social_history_adapter.py -q
```

Expected: adapter registry has no social source.

- [ ] **Step 3: Implement the social read adapter**

Add to `adapters.py`:

```python
class SocialConversationAdapter:
    def __init__(self, file_manager):
        self.file_manager = file_manager

    async def summary(self, row):
        session = self.file_manager.load_session(row.session_id)
        if not session:
            return None
        return {
            **session.to_summary().model_dump(mode="json"),
            **row.model_dump(mode="json"),
        }

    async def detail(self, row, *, message_limit=100, **_options):
        session = self.file_manager.load_session(row.session_id)
        if not session:
            return None
        messages = session.conversation_history[-message_limit:]
        payload = session.model_dump(mode="json")
        payload["conversation_history"] = messages
        payload["source"] = "social"
        payload["read_only_on_web"] = True
        payload["has_more_messages"] = len(session.conversation_history) > len(messages)
        payload["total_message_count"] = len(session.conversation_history)
        return {"session": payload, "pagination": {
            "has_more": payload["has_more_messages"],
            "total_count": payload["total_message_count"],
            "oldest_sequence": None,
        }}
```

Register it for `ConversationSource.SOCIAL`. Do not add write methods.

- [ ] **Step 4: Dispatch social read endpoints and preserve fail-closed writes**

Make list/restore/detail/messages use the adapter selected by catalog `source`. Artifact endpoints may return empty collections for social sessions unless the file transcript already contains compatible artifacts. All mutation endpoints continue calling `catalog.require_write`, which returns `409` before any source access.

- [ ] **Step 5: Run social and unified session tests**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  backend/tests/api/test_social_history_adapter.py \
  backend/tests/api/test_session_catalog_routes.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit social history adapter**

```bash
git add backend/app/conversations/adapters.py backend/app/api/session_routes.py backend/tests/api/test_social_history_adapter.py
git commit -m "feat: expose read-only social conversation history"
```

### Task 7: Disable Web Input for Restored Social History

**Files:**
- Modify: `frontend/src/composables/reactAnalysis/useSessionManagement.js`
- Modify: `frontend/src/components/reactAnalysis/ChatArea.vue`
- Modify: `frontend/src/components/management/SessionHistoryPanel.vue`
- Create: `frontend/src/components/socialHistoryReadOnly.js`
- Create: `frontend/src/components/socialHistoryReadOnly.test.js`

- [ ] **Step 1: Write failing read-only policy tests**

Create `socialHistoryReadOnly.test.js`:

```javascript
import test from 'node:test'
import assert from 'node:assert/strict'

import { restoredConversationPolicy } from './socialHistoryReadOnly.js'

test('social history is read-only and starts a new Web session for new input', () => {
  assert.deepEqual(restoredConversationPolicy({ source: 'social', read_only_on_web: true }), {
    readOnly: true,
    notice: '微信会话历史仅支持查看',
    newConversationRequired: true
  })
})

test('ordinary Web history stays writable', () => {
  assert.equal(restoredConversationPolicy({ source: 'web' }).readOnly, false)
})
```

- [ ] **Step 2: Run the policy test and verify RED**

Run:

```bash
cd frontend && node --test src/components/socialHistoryReadOnly.test.js
```

Expected: module does not exist.

- [ ] **Step 3: Implement the policy helper**

Create `socialHistoryReadOnly.js`:

```javascript
export function restoredConversationPolicy(session = {}) {
  const readOnly = session.source === 'social' || session.read_only_on_web === true
  return {
    readOnly,
    notice: readOnly ? '微信会话历史仅支持查看' : '',
    newConversationRequired: readOnly
  }
}
```

- [ ] **Step 4: Apply policy after restore and in ChatArea**

When a session is restored, retain `source` and `read_only_on_web` in current state. Pass `readOnly` and `readOnlyNotice` into `ChatArea`. Disable the input, attachment controls, send button, save, case mark, and steering controls while read-only. Add a “新建 Web 对话” action that clears the current session ID before enabling input; it must not send text using the social session ID.

- [ ] **Step 5: Run frontend tests and build**

Run:

```bash
cd frontend && node --test \
  src/components/socialHistoryReadOnly.test.js \
  src/components/social/createAccountFlow.test.js \
  src/components/management/sessionHistoryAccess.test.js && npm run build
```

Expected: tests pass and build succeeds.

- [ ] **Step 6: Commit read-only UI**

```bash
git add frontend/src/composables/reactAnalysis/useSessionManagement.js frontend/src/components/reactAnalysis/ChatArea.vue frontend/src/components/management/SessionHistoryPanel.vue frontend/src/components/socialHistoryReadOnly.js frontend/src/components/socialHistoryReadOnly.test.js
git commit -m "feat: make social history read-only on Web"
```

### Task 8: Verify Phase 2 End to End

**Files:**
- Modify only if verification reveals a defect in files already listed above.

- [ ] **Step 1: Run focused backend tests**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  backend/tests/social/test_weixin_scanner_identity.py \
  backend/tests/social/test_platform_social_binding.py \
  backend/tests/social/test_bound_social_routing.py \
  backend/tests/api/test_owned_weixin_scan.py \
  backend/tests/api/test_social_history_adapter.py -q
```

Expected: all focused tests pass.

- [ ] **Step 2: Run social regressions**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  backend/tests/test_social_user_registry.py \
  backend/tests/social/test_weixin_channel.py \
  backend/tests/social/test_broadcast_context.py \
  backend/tests/api/test_social_account_routes.py -q
```

Expected: all retained social behavior passes; only four-digit inbound onboarding expectations are intentionally replaced.

- [ ] **Step 3: Run frontend tests and build**

```bash
cd frontend && node --test \
  src/components/social/createAccountFlow.test.js \
  src/components/socialHistoryReadOnly.test.js \
  src/components/management/sessionHistoryAccess.test.js && npm run build
```

Expected: tests pass and Vite build succeeds.

- [ ] **Step 4: Apply migration twice to a disposable database**

After inserting one legacy `social_users` row, apply `007_add_platform_social_bindings.sql` twice and query:

```sql
SELECT platform_user_id, ilink_user_id, status FROM social_users ORDER BY created_at;
```

Expected: the legacy row remains with null platform fields, and the second migration creates no duplicate structures or data.

- [ ] **Step 5: Perform a manual authenticated scan acceptance test**

Using a non-administrator platform user:

1. Log into Web.
2. Open “添加微信” and confirm no profile/binding-code step appears.
3. Scan and confirm in WeChat.
4. Send one WeChat message and wait for an Agent reply.
5. Open Web session history and verify the new 微信 row belongs to that user.
6. Restore it and verify messages render while input and mutation controls remain disabled.
7. Log in as another ordinary user and verify the row is absent.
8. Log in as `ScGuanLy` and verify the row is visible with owner labels and remains read-only.

- [ ] **Step 6: Verify unbound and replacement behavior manually**

Send a message from an unbound WeChat identity and verify only the Web-binding instruction is returned and no catalog row is created. Then rescan with the original platform user using a second WeChat identity, verify the old binding becomes `replaced`, and confirm messages from the new identity create/use the active social session.

- [ ] **Step 7: Commit any verification-only corrections**

If verification required changes:

```bash
git add backend/app backend/tests frontend/src
git commit -m "fix: close social binding regressions"
```

If no files changed, do not create an empty commit.
