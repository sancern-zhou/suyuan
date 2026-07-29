# Uvicorn Gateway Peer Auth Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent Uvicorn from rewriting the TCP gateway peer into the public user IP so legitimate Nginx traffic reaches Bearer authentication instead of failing with `untrusted_gateway_peer`.

**Architecture:** Preserve `scope.client` as the socket peer by disabling Uvicorn proxy-header parsing in every supported server entry point. Nginx continues carrying and logging public client addresses, while the application trust boundary checks only the immediate, non-header-derived peer.

**Tech Stack:** Uvicorn, FastAPI/ASGI, Bash startup scripts, Python AST contract tests, pytest, Nginx

---

### Task 1: Lock and fix the Uvicorn startup contract

**Files:**
- Create: `backend/tests/auth/test_uvicorn_startup_contract.py`
- Modify: `backend/start.sh`
- Modify: `backend/restart_server.sh`
- Modify: `backend/app/main.py`
- Modify: `backend/start_windows.py`

- [ ] **Step 1: Write the failing startup contract test**

Create `backend/tests/auth/test_uvicorn_startup_contract.py`:

```python
import ast
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _uvicorn_proxy_headers_value(relative_path: str) -> object:
    source = (BACKEND_ROOT / relative_path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if (
            isinstance(function, ast.Attribute)
            and isinstance(function.value, ast.Name)
            and function.value.id == "uvicorn"
            and function.attr == "run"
        ):
            for keyword in node.keywords:
                if keyword.arg == "proxy_headers":
                    return ast.literal_eval(keyword.value)
            return None
    raise AssertionError(f"uvicorn.run not found in {relative_path}")


def test_shell_entrypoints_disable_proxy_header_rewrite():
    for relative_path in ("start.sh", "restart_server.sh"):
        source = (BACKEND_ROOT / relative_path).read_text(encoding="utf-8")
        assert "--no-proxy-headers" in source, relative_path


def test_python_entrypoints_disable_proxy_header_rewrite():
    for relative_path in ("app/main.py", "start_windows.py"):
        assert _uvicorn_proxy_headers_value(relative_path) is False, relative_path
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
cd /home/xckj/suyuan/backend
/root/miniconda3/bin/conda run -p /root/miniconda3/envs/backend_py311 \
  pytest -q tests/auth/test_uvicorn_startup_contract.py
```

Expected: both tests fail because none of the four entry points explicitly disables proxy-header rewriting.

- [ ] **Step 3: Disable proxy-header parsing in shell entry points**

In `backend/start.sh`, extend the Uvicorn command:

```bash
"${PYTHON_BIN}" -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers "${WORKERS}" \
    --env-file .env \
    --no-proxy-headers
```

In `backend/restart_server.sh`, extend the background Uvicorn command:

```bash
nohup "${PYTHON_BIN}" -m uvicorn app.main:app \
    --reload \
    --host 0.0.0.0 \
    --port 8000 \
    --env-file .env \
    --no-proxy-headers \
    > /tmp/backend.log 2>&1 &
```

Add a comment immediately above each command explaining that the auth middleware must see the raw TCP peer and that Nginx owns public-IP logging.

- [ ] **Step 4: Disable proxy-header parsing in Python entry points**

In `backend/app/main.py`, add the keyword to `uvicorn.run()`:

```python
        proxy_headers=False,
```

In `backend/start_windows.py`, add the same keyword:

```python
        proxy_headers=False,
```

- [ ] **Step 5: Run the focused and existing auth tests and verify GREEN**

Run:

```bash
cd /home/xckj/suyuan/backend
/root/miniconda3/bin/conda run -p /root/miniconda3/envs/backend_py311 \
  pytest -q tests/auth/test_uvicorn_startup_contract.py tests/auth/test_auth_middleware.py
```

Expected: all tests pass, including exact gateway trust-boundary tests.

- [ ] **Step 6: Commit the startup fix**

```bash
git add backend/start.sh backend/restart_server.sh backend/app/main.py \
  backend/start_windows.py
git add -f backend/tests/auth/test_uvicorn_startup_contract.py
git commit -m "fix: preserve raw gateway peer for authentication"
```

### Task 2: Deploy and verify the company-auth conversation path

**Files:**
- Runtime deployment only; no additional source changes expected.

- [ ] **Step 1: Run the complete backend auth suite before deployment**

Run:

```bash
cd /home/xckj/suyuan/backend
/root/miniconda3/bin/conda run -p /root/miniconda3/envs/backend_py311 \
  pytest -q tests/auth tests/integration/test_gateway_auth_flow.py
```

Expected: all tests pass; existing dependency deprecation warnings may remain.

- [ ] **Step 2: Gracefully stop the current Uvicorn master**

Identify the master PID for `python -m uvicorn app.main:app --workers 4`, send `SIGTERM`, and wait until port 8000 is released. Do not terminate unrelated Python processes.

- [ ] **Step 3: Start the production backend with the fixed contract**

From `backend/`, start the same four-worker service with `.env` and the explicit flag:

```bash
nohup /root/miniconda3/envs/backend_py311/bin/python -m uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 4 \
  --env-file .env \
  --no-proxy-headers \
  > backend-uvicorn.log 2>&1 &
```

Wait until `/api/health` returns 200 before continuing.

- [ ] **Step 4: Verify the original 403 reproduction is fixed**

Run through Nginx:

```bash
curl -sS -D - \
  -H 'X-Forwarded-For: 120.85.100.12' \
  'http://127.0.0.1:5174/api/suyuan/sessions?limit=1'
```

Expected without a Token: `401 authentication_required`. A response of `403 untrusted_gateway_peer` is a failure.

- [ ] **Step 5: Verify company-auth dependencies and frontend regression tests**

Verify all of the following:

```text
GET /api/health                              -> 200
GET /api/suyuan/auth/runtime-config          -> {"authMode":"company","sysCode":"SUYUAN"}
GET /api/auth/token/captcha?...              -> 200 image/gif
```

Then run:

```bash
cd /home/xckj/suyuan/frontend
npm run test:auth
```

Expected: all frontend auth tests pass.

- [ ] **Step 6: Inspect final state**

Run `git status --short`, confirm the backend master command contains `--no-proxy-headers`, and report exact test counts and endpoint statuses. Preserve the pre-existing untracked `NormCraftAI/` directory.
