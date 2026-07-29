# Scheduled Task Worker Proxy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Web task-management page read and operate on the single scheduled-task service hosted by `app.worker`.

**Architecture:** Register the existing scheduled-task router on the worker internal API and proxy the full `/api/scheduled-tasks` namespace from Web processes. Keep task execution out of multi-worker Web processes and repair the frontend action adapters to the current Store API.

**Tech Stack:** FastAPI, Starlette ASGI middleware, httpx, Vue 3, Pinia, pytest, Node test runner.

---

### Task 1: Scheduled-task worker proxy

**Files:**
- Create: `backend/app/core/scheduled_task_worker_proxy.py`
- Create: `backend/tests/scheduled_tasks/test_scheduled_task_worker_proxy.py`
- Modify: `backend/app/core/middleware.py`
- Modify: `backend/app/lifecycle/social_worker_api.py`

- [ ] Write tests proving Web requests match the full scheduled-task namespace, worker requests do not proxy, the worker internal API exposes the task list behind its token, and proxy transport errors return 503.
- [ ] Run the focused tests and confirm failures are caused by the missing proxy/router.
- [ ] Implement the minimal proxy by following `FetcherWorkerProxyMiddleware` and register `scheduled_task_routes.router` in the worker internal app.
- [ ] Run focused backend tests and confirm they pass.

### Task 2: Frontend task actions

**Files:**
- Create: `frontend/src/components/management/scheduledTaskActions.js`
- Create: `frontend/src/components/management/scheduledTaskActions.test.js`
- Modify: `frontend/src/views/ReactAnalysisView.vue`
- Modify: `frontend/src/views/ReactAnalysisViewRefactored.vue`
- Modify: `frontend/package.json`

- [ ] Write Node tests proving refresh loads tasks and statistics, toggle selects enable/disable using `task_id`, execute uses `executeTaskNow`, and delete uses `deleteTask`.
- [ ] Run the focused frontend test and confirm failure because the adapter does not exist.
- [ ] Add the adapter and use it in both views.
- [ ] Run frontend tests and production build.

### Task 3: Integrated verification

- [ ] Run scheduled-task backend tests and proxy tests in `/root/miniconda3/envs/backend_py311`.
- [ ] Restart only the Web and worker services using the project's existing service mechanism if required for runtime verification.
- [ ] Verify `GET http://127.0.0.1:8000/api/scheduled-tasks` returns 200 and includes `task_yuncheng_alert_tracing_event`.
- [ ] Verify the frontend build succeeds and preserve unrelated working-tree changes.

