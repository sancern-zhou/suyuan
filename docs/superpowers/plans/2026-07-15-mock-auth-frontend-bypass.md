# Mock Auth Frontend Bypass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `AUTH_MODE=mock` automatically open the frontend as the stable `local-developer` administrator without calling company authentication, while preserving company-mode behavior.

**Architecture:** The backend remains the only authority for the effective auth mode and exposes a public, no-store runtime-config endpoint. A shared backend factory constructs the same fixed Mock administrator for request authentication and the runtime response. Before Vue installs its router guard, the frontend loads that configuration and configures a mode-aware auth session; failures fall back to company mode.

**Tech Stack:** FastAPI, Pydantic Settings, pytest/httpx, Vue 3, Pinia, Vue Router, Vite, Node test runner

---

## File structure

- Modify `backend/app/auth/service.py`: own construction of the stable Mock administrator.
- Modify `backend/app/auth/routes.py`: expose the safe runtime auth configuration.
- Modify `backend/app/auth/middleware.py`: allow anonymous access only to the exact runtime-config path.
- Modify `backend/tests/auth/test_auth_service.py`: specify stable Mock administrator behavior.
- Create `backend/tests/auth/test_auth_routes.py`: specify runtime response shape and secrecy.
- Modify `backend/tests/auth/test_auth_middleware.py`: specify exact public-route behavior.
- Create `frontend/src/auth/runtimeConfig.js`: load, validate, and safely default runtime auth configuration.
- Create `frontend/src/auth/runtimeConfig.test.mjs`: specify loader and initialization behavior.
- Modify `frontend/src/auth/authStore.js`: support company and in-memory Mock sessions.
- Modify `frontend/src/auth/authStore.test.mjs`: specify Mock session behavior and company regression behavior.
- Modify `frontend/src/auth/routerGuard.test.mjs`: specify direct Mock navigation.
- Modify `frontend/src/main.js`: initialize auth mode before installing the router guard.

### Task 1: Stable Mock administrator identity

**Files:**
- Modify: `backend/tests/auth/test_auth_service.py`
- Modify: `backend/app/auth/service.py`

- [ ] **Step 1: Write the failing default-administrator test**

Append this test to `backend/tests/auth/test_auth_service.py`:

```python
@pytest.mark.asyncio
async def test_mock_mode_defaults_to_stable_local_administrator():
    service = AuthenticationService(
        settings=_settings(
            auth_mode="mock",
            auth_mock_enabled=True,
            auth_mock_user_id="local-developer",
            auth_mock_username="local-developer",
            auth_mock_display_name="本地开发用户",
            auth_mock_role_codes="",
            auth_admin_role_codes="",
        ),
        cache=IdentityCache(FakeRedis(), key_prefix="suyuan:auth:", max_ttl_seconds=60),
        platform_client=FakePlatformClient(error=AssertionError("must not call platform")),
    )

    user = await service.authenticate("ignored", "SUYUAN")

    assert user.id == "local-developer"
    assert user.username == "local-developer"
    assert user.auth_source == "mock"
    assert user.role_codes == ("SUYUAN_ADMIN",)
    assert user.is_admin is True
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
cd /home/xckj/suyuan/backend
/root/miniconda3/bin/conda run -p /root/miniconda3/envs/backend_py311 \
  pytest -q tests/auth/test_auth_service.py::test_mock_mode_defaults_to_stable_local_administrator
```

Expected: FAIL because the current Mock user has no roles and `is_admin` is false when both role settings are empty.

- [ ] **Step 3: Extract one shared Mock-user factory and use it in authentication**

In `backend/app/auth/service.py`, add the reserved role and factory above `AuthenticationService`:

```python
MOCK_ADMIN_ROLE_CODE = "SUYUAN_ADMIN"


def build_mock_user(settings: Settings, sys_code: str | None = None) -> CurrentUser:
    roles = [
        role.strip()
        for role in settings.auth_mock_role_codes.split(",")
        if role.strip()
    ]
    if MOCK_ADMIN_ROLE_CODE not in roles:
        roles.insert(0, MOCK_ADMIN_ROLE_CODE)
    return CurrentUser(
        id=settings.auth_mock_user_id,
        username=settings.auth_mock_username,
        display_name=settings.auth_mock_display_name,
        role_codes=tuple(roles),
        is_admin=True,
        sys_code=sys_code or settings.auth_sys_code,
        auth_source="mock",
    )
```

Replace the Mock branch inside `AuthenticationService.authenticate()` with:

```python
        if self._settings.auth_mode == "mock":
            if not self._settings.auth_mock_enabled:
                raise AuthenticationRejected("mock authentication is disabled")
            return build_mock_user(self._settings, sys_code)
```

Do not change company-mode role mapping.

- [ ] **Step 4: Run service tests and verify GREEN**

Run:

```bash
cd /home/xckj/suyuan/backend
/root/miniconda3/bin/conda run -p /root/miniconda3/envs/backend_py311 \
  pytest -q tests/auth/test_auth_service.py
```

Expected: all tests pass, including the existing explicitly configured Mock-role test.

- [ ] **Step 5: Commit the stable identity**

```bash
git add backend/app/auth/service.py backend/tests/auth/test_auth_service.py
git commit -m "feat: default mock auth to stable administrator"
```

### Task 2: Public backend runtime auth configuration

**Files:**
- Create: `backend/tests/auth/test_auth_routes.py`
- Modify: `backend/tests/auth/test_auth_middleware.py`
- Modify: `backend/app/auth/routes.py`
- Modify: `backend/app/auth/middleware.py`

- [ ] **Step 1: Write failing route-contract tests**

Create `backend/tests/auth/test_auth_routes.py`:

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.routes import get_auth_settings, router
from config.settings import Settings


def _client(settings: Settings) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_auth_settings] = lambda: settings
    return TestClient(app)


def test_company_runtime_config_exposes_only_safe_mode_fields():
    settings = Settings(
        _env_file=None,
        auth_mode="company",
        auth_service_url="http://secret-internal-auth/api",
    )

    response = _client(settings).get("/api/auth/runtime-config")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"authMode": "company", "sysCode": "SUYUAN"}
    assert "secret-internal-auth" not in response.text


def test_mock_runtime_config_returns_the_stable_administrator():
    settings = Settings(
        _env_file=None,
        auth_mode="mock",
        auth_mock_enabled=True,
        auth_mock_user_id="local-developer",
        auth_mock_username="local-developer",
        auth_mock_display_name="本地开发用户",
        auth_mock_role_codes="viewer",
    )

    response = _client(settings).get("/api/auth/runtime-config")

    assert response.status_code == 200
    assert response.json() == {
        "authMode": "mock",
        "sysCode": "SUYUAN",
        "mockUser": {
            "id": "local-developer",
            "userName": "local-developer",
            "name": "本地开发用户",
            "roleCodes": ["SUYUAN_ADMIN", "viewer"],
            "isAdmin": True,
            "sysCode": "SUYUAN",
            "authSource": "mock",
        },
    }


def test_disabled_mock_mode_falls_back_to_company_runtime_behavior():
    settings = Settings(
        _env_file=None,
        auth_mode="mock",
        auth_mock_enabled=False,
    )

    response = _client(settings).get("/api/auth/runtime-config")

    assert response.json() == {"authMode": "company", "sysCode": "SUYUAN"}
```

- [ ] **Step 2: Add the runtime path to the middleware public-route test**

In `_app()` in `backend/tests/auth/test_auth_middleware.py`, add:

```python
    @app.get("/api/auth/runtime-config")
    async def auth_runtime_config():
        return {"authMode": "company", "sysCode": "SUYUAN"}
```

Add `"/api/auth/runtime-config"` to `test_exact_public_routes_do_not_authenticate`, and add
`"/api/auth/runtime-config/private"` to `test_similarly_named_routes_remain_private`.

- [ ] **Step 3: Run the new tests and verify RED**

Run:

```bash
cd /home/xckj/suyuan/backend
/root/miniconda3/bin/conda run -p /root/miniconda3/envs/backend_py311 \
  pytest -q tests/auth/test_auth_routes.py tests/auth/test_auth_middleware.py
```

Expected: collection fails because `get_auth_settings` does not exist, and the runtime path is not yet public.

- [ ] **Step 4: Implement the safe runtime-config endpoint**

Update imports in `backend/app/auth/routes.py`:

```python
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from config.settings import Settings, settings

from .dependencies import require_current_user
from .models import CurrentUser
from .service import build_mock_user
from .ws_tickets import WebSocketTicketService
```

Add these definitions before the WebSocket ticket route:

```python
def get_auth_settings() -> Settings:
    return settings


@router.get("/auth/runtime-config")
async def runtime_auth_config(
    auth_settings: Settings = Depends(get_auth_settings),
):
    payload = {
        "authMode": "company",
        "sysCode": auth_settings.auth_sys_code,
    }
    if auth_settings.auth_mode == "mock" and auth_settings.auth_mock_enabled:
        user = build_mock_user(auth_settings)
        payload = {
            "authMode": "mock",
            "sysCode": user.sys_code,
            "mockUser": {
                "id": user.id,
                "userName": user.username,
                "name": user.display_name,
                "roleCodes": list(user.role_codes),
                "isAdmin": user.is_admin,
                "sysCode": user.sys_code,
                "authSource": user.auth_source,
            },
        }
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})
```

Add `"/api/auth/runtime-config"` to `_PUBLIC_EXACT_PATHS` in
`backend/app/auth/middleware.py`. Do not add a prefix exemption.

- [ ] **Step 5: Run route and middleware tests and verify GREEN**

Run:

```bash
cd /home/xckj/suyuan/backend
/root/miniconda3/bin/conda run -p /root/miniconda3/envs/backend_py311 \
  pytest -q tests/auth/test_auth_routes.py tests/auth/test_auth_middleware.py
```

Expected: all tests pass; the exact path is public while its similarly named child path remains protected.

- [ ] **Step 6: Commit the backend runtime contract**

```bash
git add backend/app/auth/routes.py backend/app/auth/middleware.py \
  backend/tests/auth/test_auth_routes.py backend/tests/auth/test_auth_middleware.py
git commit -m "feat: expose safe auth runtime configuration"
```

### Task 3: Frontend runtime configuration loader

**Files:**
- Create: `frontend/src/auth/runtimeConfig.js`
- Create: `frontend/src/auth/runtimeConfig.test.mjs`

- [ ] **Step 1: Write failing loader and initialization tests**

Create `frontend/src/auth/runtimeConfig.test.mjs`:

```javascript
import assert from 'node:assert/strict'
import test from 'node:test'

import {
  companyRuntimeConfig,
  initializeAuthStore,
  loadAuthRuntimeConfig,
  normalizeAuthRuntimeConfig
} from './runtimeConfig.js'


const mockPayload = {
  authMode: 'mock',
  sysCode: 'SUYUAN',
  mockUser: {
    id: 'local-developer',
    userName: 'local-developer',
    name: '本地开发用户',
    roleCodes: ['SUYUAN_ADMIN'],
    isAdmin: true,
    sysCode: 'SUYUAN',
    authSource: 'mock'
  }
}


test('loads mock mode from the public business-gateway endpoint without credentials', async () => {
  const calls = []
  const config = await loadAuthRuntimeConfig({
    apiBaseUrl: '/api/suyuan',
    fetchImpl: async (url, options) => {
      calls.push({ url, options })
      return new Response(JSON.stringify(mockPayload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      })
    }
  })

  assert.deepEqual(config, mockPayload)
  assert.deepEqual(calls, [{
    url: '/api/suyuan/auth/runtime-config',
    options: { cache: 'no-store', credentials: 'same-origin' }
  }])
})


test('invalid, unknown, and unavailable runtime config fail closed to company mode', async () => {
  assert.deepEqual(normalizeAuthRuntimeConfig({ authMode: 'disabled' }), companyRuntimeConfig())
  assert.deepEqual(
    normalizeAuthRuntimeConfig({ authMode: 'mock', mockUser: { id: '' } }),
    companyRuntimeConfig()
  )
  assert.deepEqual(
    await loadAuthRuntimeConfig({ fetchImpl: async () => { throw new Error('offline') } }),
    companyRuntimeConfig()
  )
})


test('initializes the auth store with the loaded runtime config', async () => {
  const seen = []
  const authStore = { configure: config => seen.push(config) }

  const config = await initializeAuthStore(authStore, {
    load: async () => mockPayload
  })

  assert.deepEqual(config, mockPayload)
  assert.deepEqual(seen, [mockPayload])
})
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
cd /home/xckj/suyuan/frontend
node --test src/auth/runtimeConfig.test.mjs
```

Expected: FAIL with module-not-found for `runtimeConfig.js`.

- [ ] **Step 3: Implement the runtime configuration boundary**

Create `frontend/src/auth/runtimeConfig.js`:

```javascript
function configuredApiBase() {
  return import.meta.env?.VITE_API_BASE_URL || '/api/suyuan'
}


export function companyRuntimeConfig() {
  return { authMode: 'company', sysCode: 'SUYUAN', mockUser: null }
}


export function normalizeAuthRuntimeConfig(value) {
  if (!value || typeof value !== 'object') return companyRuntimeConfig()
  const sysCode = typeof value.sysCode === 'string' && value.sysCode
    ? value.sysCode
    : 'SUYUAN'
  if (value.authMode === 'company') {
    return { authMode: 'company', sysCode, mockUser: null }
  }
  const user = value.mockUser
  if (
    value.authMode !== 'mock' ||
    !user ||
    typeof user.id !== 'string' ||
    !user.id ||
    user.isAdmin !== true
  ) {
    return companyRuntimeConfig()
  }
  return { authMode: 'mock', sysCode, mockUser: { ...user } }
}


export async function loadAuthRuntimeConfig({
  fetchImpl = globalThis.fetch,
  apiBaseUrl = configuredApiBase()
} = {}) {
  try {
    const base = apiBaseUrl.replace(/\/$/, '')
    const response = await fetchImpl(`${base}/auth/runtime-config`, {
      cache: 'no-store',
      credentials: 'same-origin'
    })
    if (!response.ok) return companyRuntimeConfig()
    return normalizeAuthRuntimeConfig(await response.json())
  } catch {
    return companyRuntimeConfig()
  }
}


export async function initializeAuthStore(authStore, { load = loadAuthRuntimeConfig } = {}) {
  const config = await load()
  authStore.configure(config)
  return config
}
```

- [ ] **Step 4: Run the loader tests and verify GREEN**

Run:

```bash
cd /home/xckj/suyuan/frontend
node --test src/auth/runtimeConfig.test.mjs
```

Expected: all runtime-config tests pass.

- [ ] **Step 5: Commit the frontend loader**

```bash
git add frontend/src/auth/runtimeConfig.js frontend/src/auth/runtimeConfig.test.mjs
git commit -m "feat: load auth mode from backend runtime config"
```

### Task 4: Mode-aware frontend session and application startup

**Files:**
- Modify: `frontend/src/auth/authStore.test.mjs`
- Modify: `frontend/src/auth/routerGuard.test.mjs`
- Modify: `frontend/src/auth/authStore.js`
- Modify: `frontend/src/main.js`

- [ ] **Step 1: Write failing Mock-session tests**

Append to `frontend/src/auth/authStore.test.mjs`:

```javascript
test('mock mode clears persisted company state and bootstraps the in-memory administrator', async () => {
  const raw = memoryStorage()
  const storage = createAuthStorage(raw)
  storage.writeSession({
    token: 'old-company-token',
    sysCode: 'SUYUAN',
    user: { id: 'old-user' }
  })
  const calls = []
  const mockUser = {
    id: 'local-developer',
    roleCodes: ['SUYUAN_ADMIN'],
    isAdmin: true
  }
  const api = {
    login: async () => calls.push('login'),
    currentUser: async () => calls.push('currentUser'),
    logout: async () => calls.push('logout')
  }
  const session = createAuthSession({
    api,
    storage,
    sysCode: 'SUYUAN',
    authMode: 'mock',
    mockUser
  })

  assert.deepEqual(raw.dump(), {})
  assert.equal(await session.bootstrap(), mockUser)
  assert.equal(session.token, '')
  assert.equal(session.user, mockUser)
  assert.deepEqual(await session.login({}), mockUser)
  await session.logout()
  assert.equal(session.user, mockUser)
  assert.deepEqual(calls, [])
  assert.deepEqual(raw.dump(), {})
})
```

Append to `frontend/src/auth/routerGuard.test.mjs`:

```javascript
test('mock administrator enters protected routes without a company token', async () => {
  let calls = 0
  const auth = store({
    authMode: 'mock',
    get isAuthenticated() { return this.authMode === 'mock' && Boolean(this.user) },
    async bootstrap() {
      calls += 1
      this.user = { id: 'local-developer', isAdmin: true }
      this.initialized = true
      return this.user
    }
  })

  assert.equal(
    await createAuthGuard(auth)({ path: '/knowledge-base', fullPath: '/knowledge-base' }),
    true
  )
  assert.equal(calls, 1)
})
```

- [ ] **Step 2: Run auth-store and guard tests and verify RED**

Run:

```bash
cd /home/xckj/suyuan/frontend
node --test src/auth/authStore.test.mjs src/auth/routerGuard.test.mjs
```

Expected: the new store test fails because `createAuthSession` ignores `authMode` and calls company APIs; existing company tests remain green.

- [ ] **Step 3: Implement the mode-aware session**

Change the signature and initialization in `frontend/src/auth/authStore.js`:

```javascript
export function createAuthSession({
  api,
  storage,
  sysCode = 'SUYUAN',
  authMode = 'company',
  mockUser = null
}) {
  const persisted = storage.readSession()
  const isMock = authMode === 'mock' && Boolean(mockUser?.id)
  if (isMock) storage.clear()
  const session = {
    authMode: isMock ? 'mock' : 'company',
    mockUser: isMock ? mockUser : null,
    token: !isMock && persisted.sysCode === sysCode ? persisted.token : '',
    user: !isMock && persisted.sysCode === sysCode ? persisted.user : null,
    sysCode,
    loading: false,
    initialized: false,
```

At the start of `bootstrap()` after the initialized guard, add:

```javascript
      if (this.authMode === 'mock') {
        this.initialized = true
        this.user = this.mockUser
        return this.user
      }
```

At the start of `login()` add:

```javascript
      if (this.authMode === 'mock') {
        this.initialized = true
        this.user = this.mockUser
        return this.user
      }
```

At the start of `logout()` add:

```javascript
      if (this.authMode === 'mock') {
        storage.clear()
        this.token = ''
        this.user = this.mockUser
        this.initialized = true
        return
      }
```

After `let browserSession`, add a default runtime value and make session creation configurable:

```javascript
let browserRuntimeConfig = {
  authMode: 'company',
  sysCode: 'SUYUAN',
  mockUser: null
}


function configureBrowserSession(runtimeConfig) {
  browserRuntimeConfig = runtimeConfig
  browserSession = undefined
}
```

Pass the runtime fields in `getBrowserSession()`:

```javascript
    browserSession = createAuthSession({
      storage,
      api: createAuthApi({ storage }),
      sysCode: browserRuntimeConfig.sysCode || 'SUYUAN',
      authMode: browserRuntimeConfig.authMode,
      mockUser: browserRuntimeConfig.mockUser
    })
```

Extend Pinia state and its getter:

```javascript
  state: () => ({
    authMode: 'company',
    token: '',
    user: null,
    loading: false,
    initialized: false
  }),
  getters: {
    isAuthenticated: state => Boolean(
      state.user && (state.authMode === 'mock' || state.token)
    )
  },
```

Replace `_sync(session)` and add the configure action before `bootstrap()`:

```javascript
    _sync(session) {
      this.authMode = session.authMode
      this.token = session.token
      this.user = session.user
      this.loading = session.loading
      this.initialized = session.initialized
    },
    configure(runtimeConfig) {
      configureBrowserSession(runtimeConfig)
      this._sync(getBrowserSession())
    },
```

- [ ] **Step 4: Wire runtime initialization before the router guard**

In `frontend/src/main.js`, import the initializer:

```javascript
import { initializeAuthStore } from './auth/runtimeConfig.js'
```

Replace the bottom-level setup with an async function so configuration is loaded before navigation:

```javascript
async function bootstrapApplication() {
  const app = createApp(App)
  const pinia = createPinia()

  app.use(pinia)
  const authStore = useAuthStore(pinia)
  await initializeAuthStore(authStore)
  installAuthGuard(router, authStore)
  app.use(router)
  app.mount('#app')
}


bootstrapApplication()
```

Remove the old duplicated top-level `app`, `pinia`, guard, router, and mount statements.

- [ ] **Step 5: Run focused frontend tests and verify GREEN**

Run:

```bash
cd /home/xckj/suyuan/frontend
node --test src/auth/authStore.test.mjs src/auth/routerGuard.test.mjs \
  src/auth/runtimeConfig.test.mjs
```

Expected: all focused tests pass; Mock mode makes no company API calls and company-mode regression tests still pass.

- [ ] **Step 6: Run the complete auth suite and production build**

Run:

```bash
cd /home/xckj/suyuan/frontend
npm run test:auth
npm run build:standalone
```

Expected: all auth tests pass and Vite finishes the standalone build successfully.

- [ ] **Step 7: Commit frontend Mock bypass behavior**

```bash
git add frontend/src/auth/authStore.js frontend/src/auth/authStore.test.mjs \
  frontend/src/auth/routerGuard.test.mjs frontend/src/main.js
git commit -m "feat: bypass company login in mock auth mode"
```

### Task 5: Cross-stack verification

**Files:**
- Verify only; no production files should change.

- [ ] **Step 1: Run the complete focused backend auth and gateway suite**

Run:

```bash
cd /home/xckj/suyuan/backend
/root/miniconda3/bin/conda run -p /root/miniconda3/envs/backend_py311 \
  pytest -q tests/auth tests/integration/test_gateway_auth_flow.py
```

Expected: all tests pass. Existing deprecation warnings may remain, but there must be no failures or errors.

- [ ] **Step 2: Run the complete frontend auth suite again**

Run:

```bash
cd /home/xckj/suyuan/frontend
npm run test:auth
```

Expected: all tests pass with zero failures.

- [ ] **Step 3: Inspect the final diff for scope and secrets**

Run:

```bash
cd /home/xckj/suyuan
git diff HEAD~4 --check
git diff HEAD~4 --stat
git status --short
```

Expected: no whitespace errors; only the auth files listed in this plan and the plan/design documents are involved; the pre-existing untracked `NormCraftAI/` directory remains untouched.

- [ ] **Step 4: Record verification evidence in the handoff**

Report the exact frontend test count, backend test count, build result, and any remaining warnings. Do not claim unrelated project suites pass.
