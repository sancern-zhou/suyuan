项目的运行环境是 conda 环境 `backend_py311`，具体 conda 路径按部署环境配置。

## Agent 文件系统路径规范

- 所有 Agent、子 Agent、工具和 Skill 接收的文件系统相对路径，统一以项目根目录（git 仓库根）为解析基准。
- 后端文件的项目相对路径必须显式包含 `backend/` 前缀，例如 `backend/app/main.py`。
- 工具返回项目内文件路径时，统一返回相对于项目根的路径；项目外临时文件可以返回规范化绝对路径。
- 禁止依赖进程当前工作目录推断项目根，统一使用 `backend/app/utils/path_config.py` 中的 `PROJECT_ROOT`、`resolve_agent_path()` 和 `format_agent_path()`。
- `/tmp/...` 以及报告包内部的 `assets/...` 等逻辑路径不属于项目相对文件系统路径。

## 构建与部署规范

- 前端源码唯一目录：仓库内的 `frontend/`。
- 前端构建必须在该目录执行：

  ```bash
  cd frontend
  npm run build:standalone
  ```

- 正式前端静态资源唯一来源：`frontend/dist`，由部署环境配置的静态资源服务提供。
- 构建完成后按部署环境的静态资源服务方式重新加载或发布前端资源。

- 禁止在项目根目录直接执行 `npm run build`，禁止维护第二套前端 bundle。
- 每个项目的 web 进程与 worker 进程必须成对启动（worker 缺失时 fetchers/scheduled-tasks 等接口会 503）。
- web 与 worker 必须在独立于当前终端的会话中启动，禁止依赖前台 shell 或临时工具会话；否则终端会话结束后进程退出，网关将返回 502。启动时使用 `setsid` 脱离会话，并使用 `nohup`、独立日志和 PID 文件：

  ```bash
  cd backend
  BACKEND_PYTHON=/path/to/conda/envs/backend_py311/bin/python
  nohup setsid "$BACKEND_PYTHON" -m uvicorn app.main:app \
    --host 0.0.0.0 --port 8000 --workers 1 --env-file .env --no-proxy-headers \
    > /tmp/suyuan-web.log 2>&1 < /dev/null &
  echo $! > /tmp/suyuan-web.pid

  nohup setsid "$BACKEND_PYTHON" -m app.worker \
    > /tmp/suyuan-worker.log 2>&1 < /dev/null &
  echo $! > /tmp/suyuan-worker.pid
  ```

  启动后必须检查 `ss -ltnp` 中 web 端口和 worker 内部端口均在监听；停止或重启时使用 PID 文件操作对应进程，不能只关闭当前终端。
- 许昌（xuchang）分支的部署环境 web 进程使用 3 个 uvicorn worker 启动（`--workers 3`），用于支撑多并发对话任务；对话（agent SSE）请求由 web 进程处理，跨进程 cancel/steer 依赖环境文件中的 Redis 配置（`REDIS_HOST`/`REDIS_PORT`/`REDIS_DB`/`REDIS_PASSWORD`）。`app.worker` 后台进程仍为单实例，不随 web worker 数量扩展。注意：每个 web worker 启动时会加载 bge-m3 嵌入模型（约 1G 内存），worker 数量受服务器内存约束——6.5G 内存的机器上限为 3 个 web worker，禁止在该规格机器上使用 4 个及以上（会触发 OOM 反复杀进程）。
- 本机当前仅部署两个项目，本条布局只适用于它们，其他项目（如 jiangxi、xuchang 等）部署时按实际环境单独规划，不受本条约束（详见 `deploy/nginx/README.md`）：
  - 风清气智（main 共享项目，工作树 `/home/xckj/suyuan-main`）：前端 5174（容器 `suyuan-nginx`，挂载该工作树 `frontend/dist`）→ 后端 8000（`backend/.env`，用 `backend/restart_server.sh` 重启）+ 配套 worker（内部端口 8011）。
  - 江苏运维（project/jiangsu-ops 分支，工作树 `/home/xckj/suyuan`）：前端 5175（容器 `suyuan-nginx-jiangsu`，挂载该工作树 `frontend/dist`）→ 后端 8001（`backend/.env.jiangsu-ops`）+ 配套 worker（`python -m app.worker --env-file .env.jiangsu-ops`，内部端口 8012）。
  - 两个 Nginx 容器禁止挂载同一个 `frontend/dist`；风清气智 web/worker 固定从 `/home/xckj/suyuan-main/backend` 启动并使用该目录下的 `backend_data_registry`，江苏运维 web/worker 从 `/home/xckj/suyuan/backend` 启动并使用项目专属 registry。
  - 每个项目的 web 进程与 worker 进程必须成对启动（worker 缺失时 fetchers/scheduled-tasks 等接口会 503）。
- 所有部署环境的 `DATA_REGISTRY_DIR` 必须在对应后端环境文件中显式配置为绝对路径；同一项目的 web 与 worker 必须使用同一个值。禁止依赖工作树位置推导持久化目录，切换工作树前须先运行 `python -m app.utils.deployment_preflight --env-file <env-file>` 校验。
- 前端部署后必须确认构建产物包含统一资源接口，并且不再包含旧接口：

  ```bash
  grep -R "resources?presentation_type=document" frontend/dist/assets
  ! grep -R "/office-documents" frontend/dist/assets
  ! grep -R "/visualizations" frontend/dist/assets
  ```

## 分支与更新归属规范

- 共享层改动一律提交到 `main`：`backend/app`（除 `tools/jiangsu/`、`fetchers/jiangsu_*`、`fetchers/weather/jiangsu_*`）、`backend/tests`（除 jiangsu 专用测试）、`backend/config`、`frontend/src` 公共组件与配置、CI、`.gitignore`、`AGENTS.md`。
- 项目改动提交到对应 `project/*` 分支：`backend/app/tools/jiangsu/**`、`fetchers/jiangsu_*`、`backend/app/db/repositories/jiangsu_*`、`backend/app/db/models` 中的项目模型、`projects/jiangsu-ops/**`、`backend/tests/test_jiangsu_*`、`backend/tests/project_config/test_jiangsu_*`、项目专属前端（如 StationhouseInspectionPanel）。
- 判定准则：路径含 jiangsu/项目名、或内容依赖 `projects/*/project.yaml`、`settings.project_id` 分支逻辑的，归项目分支；其余归 main。混合文件（如 `tools/__init__.py`、`tool_registry.py`）先在 main 提交共享部分，项目分支合并后再叠加项目部分。
- 工作流程：先在 main 提交共享改动 → 项目分支 `git merge main` → 再提交项目改动。禁止在项目分支直接修改共享文件而不回合 main。
- 项目分支每天开工先 `git merge main`；共享文件的改动永远以 main 为准。
- 禁止提交：`backend/.env.*`（模板除外）、`frontend/dist-*`、`backend/backend_data_registry*`、`suncere*/`（见 .gitignore）。
