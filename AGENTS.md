# Repository Guidelines

## Project Structure & Module Organization
- `backend/` FastAPI app; `app/` hosts routers, services, database helpers, utilities, and `config/settings.py` holds runtime configuration.
- Migrate tests from legacy `backend/test_*.py` into `backend/tests/`; the Vue client lives in `frontend-vue/src` (components, stores, composables, services) and shared docs stay in `doc/`.

## Build, Test & Development Commands
- Backend: `cd backend && python -m venv .venv && .\.venv\Scripts\activate && pip install -r requirements.txt`; start with `uvicorn app.main:app --reload --port 8000` or `start.bat`.
- Validate backend via `pytest -vv` or `python test_api.py`; frontend uses `npm run dev`, `npm run build`, `npm run preview`, and `docker-compose up --build` starts both tiers.

## Coding Style & Naming Conventions
- Python: 4-space indent, type hints, `structlog` logging; keep orchestration in `app/services` and pure helpers in `app/utils`.
- Vue/TS: 2-space indent, `<script setup lang="ts">`, PascalCase components, camelCase composables, Vite aliases (`@/components/...`); store configs in `config/` or `data/`.

## Testing Guidelines
- Create `backend/tests/test_<feature>.py`, share fixtures via `conftest.py`, mock `httpx.AsyncClient`, mark slow cases so `pytest -m "not slow"` stays quick.
- Document seed data next to tests; future frontend suites should use `vitest` with `@vue/test-utils`.

## Commit & Pull Request Guidelines
- Use Conventional Commits with scoped prefixes, e.g. `feat(frontend): add chat overlay`, around 72 characters.
- PRs must describe intent, list checks (`pytest`, `npm run build`), highlight config changes, and attach UI evidence.

## Configuration & Security Tips
- Copy `backend/.env.example` to `.env`, fill LLM, AMap, Qdrant, Redis credentials, keep local only.
- Vite proxies `/api` to `http://localhost:8000`; adjust `VITE_API_BASE_URL` before `npm run build` and trim bulky `backend/data/` assets for releases.
- The current environment is WINDOWS and Powershell.

## Communication and Teaching Guidelines
- All communications with users must be conducted in Chinese. Avoid overusing English terminology; provide simple explanations for professional vocabulary when necessary.
- You are interacting with novice users, so use accessible expressions and avoid complex technical jargon.
- When teaching users to perform operations, break down the process into steps. Each step should include clear operation instructions and expected outcomes. Add notes or common problem prompts for critical steps.
- When responding to user questions, prioritize providing direct and actionable solutions first, then supplement with explanatory principles—balancing practicality and comprehensibility.

在询问、使用各类框架前，首先使用 context7的MCP，查看框架的最新版本。