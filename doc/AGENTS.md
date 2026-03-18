# Repository Guidelines

## Project Structure & Module Organization
- `backend/` contains the FastAPI API; `app/main.py` wires routers, services, utils, and structlog. Domain logic stays in `app/services/`, schemas in `app/models/`, config in `config/settings.py`. Transitional smoke scripts (`test_api.py`, `test_weather_simple.py`) live beside tooling—create real pytest modules in `backend/tests/`.
- `frontend/` holds the Vite + React client. Components live in `src/components/`, shared types in `src/types/`, data calls in `src/services/`. `vite.config.ts` defines aliases (`@components`, `@services`, etc.) and proxies `/api` to the backend.

## Build, Test, and Development Commands
- Backend: `python -m venv .venv && .venv\Scripts\activate`, then `pip install -r requirements.txt`. Launch with `python -m uvicorn app.main:app --reload` or the platform scripts `start.bat` / `start.sh`.
- Backend verification: prefer `pytest backend/tests -vv`; `pytest-asyncio` ships in `requirements.txt`. Keep the smoke scripts runnable via `python test_api.py` when debugging endpoints.
- Frontend: `npm install`, `npm run dev` for `http://localhost:5173`, `npm run build`, and `npm run preview` for production checks.

## Coding Style & Naming Conventions
- Python: follow PEP 8 with 4-space indents and type hints. Format with `black app/` + `isort app/`, then run `mypy app/`. Always read configuration via `config.settings` rather than hard-coding constants.
- TypeScript: use 2-space indents, single quotes, PascalCase component filenames, camelCase hooks (`useAMapLoader`). Store API helpers in `src/services/` and rely on the Vite aliases.

## Testing Guidelines
- Add async FastAPI coverage under `backend/tests/` using `pytest` + `pytest-asyncio`; name files `test_<module>.py`, define shared fixtures in `conftest.py`, and patch `httpx.AsyncClient` to isolate external APIs.
- Frontend tests are not scaffolded; if you add them, prefer `vitest` with React Testing Library, mirroring the component tree. Until then, record manual QA steps in each PR.

## Commit & Pull Request Guidelines
- No git history ships with the bundle; follow Conventional Commits (`feat: ...`, `fix: ...`) capped at ~72 characters and link tracker IDs when available.
- PRs should state intent, list verification (`pytest`, `npm run build`), flag configuration changes, and include UI captures for visible work. Update the relevant root docs when behaviour changes.

## Configuration & Secrets
- Copy `backend/.env.example` to `.env`, replace API keys (OpenAI, DeepSeek, AMap, Redis), and keep the populated file untracked. Ensure `CORS_ORIGINS` matches the front-end host you use locally.
- The Vite dev server proxies `/api` to `http://localhost:8000`; adjust `vite.config.ts` or introduce `VITE_API_BASE_URL` before building if the backend runs elsewhere.

## Agent 指令
- 处理自动化任务时优先复用现有脚本（`start.bat`、`start.sh`），避免执行破坏性 Git 命令；如需额外权限，请在评审说明中先行告知。
**我讨厌你每次修改完都生成一个总结文档，即使他没必要。**
**禁止生成带EMOJI图标的测试脚本。**