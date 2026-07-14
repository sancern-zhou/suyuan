# Local Nginx Production Entry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add and rehearse a parameterized Docker Nginx production entry for Suyuan without interrupting the current Vite service on port 5174.

**Architecture:** The official Nginx image renders a versioned template with environment-provided listen and upstream values. Nginx serves `frontend/dist`, proxies company authentication to the existing company gateway, and proxies Suyuan HTTP/WebSocket traffic directly to the local backend.

**Tech Stack:** Nginx 1.27 Alpine, Docker Compose, Vue 3/Vite, pytest, Playwright

---

### Task 1: Lock the Nginx Routing Contract

**Files:**
- Create: `backend/tests/deploy/test_nginx_contract.py`
- Create: `deploy/nginx/templates/default.conf.template`

- [ ] **Step 1: Write the failing contract test**

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "deploy/nginx/templates/default.conf.template"


def test_nginx_routes_auth_business_websocket_and_spa():
    text = CONFIG.read_text(encoding="utf-8")
    assert "listen ${LISTEN_PORT}" in text
    assert "location ^~ /api/auth/" in text
    assert "proxy_pass ${AUTH_UPSTREAM};" in text
    assert "location ^~ /api/suyuan/ws/" in text
    assert "proxy_pass ${BUSINESS_UPSTREAM}/ws/;" in text
    assert "location ^~ /api/suyuan/" in text
    assert "proxy_pass ${BUSINESS_UPSTREAM}/api/;" in text
    assert 'proxy_set_header X-User-Id "";' in text
    assert 'proxy_set_header X-Is-Admin "";' in text
    assert "try_files $uri $uri/ /index.html;" in text
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/deploy/test_nginx_contract.py
```

Expected: FAIL because the Nginx template does not exist.

- [ ] **Step 3: Implement the Nginx template**

Create a server listening on `${LISTEN_PORT}` with:

- `/api/auth/` preserving its URI to `${AUTH_UPSTREAM}`.
- `/api/suyuan/ws/` replacing the prefix with `/ws/` and forwarding upgrade headers.
- `/api/suyuan/` replacing the prefix with `/api/`.
- Explicit forwarding of `Authorization`, `SysCode`, `Sign`, and `encryptType`.
- Empty `X-User-Id` and `X-Is-Admin` upstream headers.
- 100 MB body limit, 600 second proxy timeouts, SPA fallback, immutable asset caching, and no-store `index.html`.

- [ ] **Step 4: Run the contract test and verify GREEN**

Run the Step 2 command.

Expected: 1 test PASS.

- [ ] **Step 5: Commit the routing contract**

```bash
git add -f backend/tests/deploy/test_nginx_contract.py
git add deploy/nginx/templates/default.conf.template
git commit -m "feat: define local nginx routing contract"
```

### Task 2: Add Reproducible Container Deployment

**Files:**
- Create: `deploy/nginx/docker-compose.yml`
- Create: `deploy/nginx/README.md`

- [ ] **Step 1: Extend the failing contract test for Compose**

```python
COMPOSE = ROOT / "deploy/nginx/docker-compose.yml"


def test_compose_uses_host_network_read_only_mounts_and_restart_policy():
    text = COMPOSE.read_text(encoding="utf-8")
    assert "network_mode: host" in text
    assert "restart: unless-stopped" in text
    assert "../../frontend/dist:/usr/share/nginx/html:ro" in text
    assert "./templates:/etc/nginx/templates:ro" in text
    assert "${SUYUAN_NGINX_PORT:-5174}" in text
    assert "${AUTH_UPSTREAM:-http://10.10.204.80:8025}" in text
    assert "${BUSINESS_UPSTREAM:-http://127.0.0.1:8000}" in text
```

- [ ] **Step 2: Run the test and verify RED**

Run the Task 1 test command.

Expected: the Compose test FAILS because the file does not exist.

- [ ] **Step 3: Implement Compose and deployment documentation**

Use `nginx:1.27-alpine`, host networking, `restart: unless-stopped`, read-only mounts, a health check against `/api/suyuan/health`, and environment defaults. Document these exact flows:

```bash
cd frontend && npm run build
docker compose -f deploy/nginx/docker-compose.yml config
SUYUAN_NGINX_PORT=5175 docker compose -p suyuan-nginx-rehearsal -f deploy/nginx/docker-compose.yml up -d
SUYUAN_NGINX_PORT=5175 docker compose -p suyuan-nginx-rehearsal -f deploy/nginx/docker-compose.yml down
docker compose -p suyuan-nginx -f deploy/nginx/docker-compose.yml up -d
```

The README must state that production cutover requires stopping Vite on 5174 first and that rollback stops Nginx before restarting Vite.

- [ ] **Step 4: Validate Compose and Nginx syntax**

Run:

```bash
docker compose -f deploy/nginx/docker-compose.yml config
docker run --rm --network host \
  -e LISTEN_PORT=5175 \
  -e AUTH_UPSTREAM=http://10.10.204.80:8025 \
  -e BUSINESS_UPSTREAM=http://127.0.0.1:8000 \
  -v "$PWD/deploy/nginx/templates:/etc/nginx/templates:ro" \
  -v "$PWD/frontend/dist:/usr/share/nginx/html:ro" \
  nginx:1.27-alpine nginx -t
```

Expected: Compose renders successfully and Nginx reports configuration syntax is OK.

- [ ] **Step 5: Commit deployment assets**

```bash
git add deploy/nginx/docker-compose.yml deploy/nginx/README.md backend/tests/deploy/test_nginx_contract.py
git commit -m "feat: add local nginx production deployment"
```

### Task 3: Rehearse on Port 5175

**Files:**
- No source changes expected.

- [ ] **Step 1: Run frontend and contract verification**

```bash
cd frontend
npm run test:auth
npm run test:event-tasks
npm run build
cd ..
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/deploy/test_nginx_contract.py
```

Expected: all commands PASS.

- [ ] **Step 2: Start the rehearsal container**

```bash
SUYUAN_NGINX_PORT=5175 docker compose \
  -p suyuan-nginx-rehearsal \
  -f deploy/nginx/docker-compose.yml up -d
```

- [ ] **Step 3: Verify HTTP routing**

```bash
curl -fsS http://127.0.0.1:5175/login
curl -fsS http://127.0.0.1:5175/api/suyuan/health
curl -fsS http://127.0.0.1:5175/api/suyuan/ready
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5175/api/auth/token/captcha?key=nginx-smoke&type=1
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5175/api/suyuan/info
```

Expected: login HTML has no `/@vite/client`; health and ready return 200; captcha returns 200; anonymous business request returns 401.

- [ ] **Step 4: Run browser authentication acceptance**

Use Playwright against port 5175. Verify the captcha image loads, a login POST is emitted with `JCXT`, failed captcha refreshes the image, and no browser page error occurs. Do not print credentials, request bodies, or tokens.

- [ ] **Step 5: Verify current service remains unchanged**

Run:

```bash
curl -fsS http://127.0.0.1:5174/login
pgrep -af 'node .*/vite'
```

Expected: the original Vite service remains active on 5174.

- [ ] **Step 6: Stop the rehearsal container**

```bash
SUYUAN_NGINX_PORT=5175 docker compose \
  -p suyuan-nginx-rehearsal \
  -f deploy/nginx/docker-compose.yml down
```

- [ ] **Step 7: Final repository verification**

Run `git diff --check` and `git status --short --branch`.

Expected: no uncommitted task changes; the pre-existing untracked `NormCraftAI/` remains untouched.
