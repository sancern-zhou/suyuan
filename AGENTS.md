项目的运行环境是 conda 环境 `backend_py311`，本机路径为 `M:\suyuan-tools\envs\backend_py311`（Python 解释器 `M:\suyuan-tools\envs\backend_py311\Scripts\python.exe`）。

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
- 本机即广东项目的部署机（Windows，工作树 `M:\suyuan-guangdong`，分支 `project/guangdong`）。全部组件为 WinSW Windows 服务（配置在 `M:\suyuan-tools\winsvcs\`，开机自启、崩溃自动重启），用 `net start|stop <服务名>` 或 `deploy-local\start-web.bat`、`deploy-local\stop-all.bat` 等脚本操作，禁止在前台 shell 里长期挂进程：

  | 组件 | 端口 | 服务名 |
  |------|------|--------|
  | 统一入口网关（nginx，配置在 `deploy-local/nginx-8092/`） | 8092 | `suyuan-gateway-8092` |
  | 前端静态服务 + 反向代理 | 5176 | `suyuan-frontend` |
  | 后端 web（uvicorn 3 workers，`backend/.env.guangdong`） | 8000 | `suyuan-web` |
  | 后端 worker（`app.worker`，与 web 成对） | 内部 8011 | `suyuan-worker` |
  | 独立 bge-m3 嵌入服务（权重全机一份，web/worker 经 `EMBEDDING_SERVICE_URL` 调用） | 8020 | `suyuan-embedding` |
  | Redis | 6379 | `suyuan-redis` |
  | PostgreSQL | 5433 | `suyuan-pgsql` |
  | Qdrant | 6334 | `suyuan-qdrant` |

  修改 `.env.guangdong` 或 `winsvcs` 下服务 XML 后需重启对应服务生效；完整布局、公网入口与运维细节以 `deploy-local/README.md` 为准。
- Linux 部署环境（其他机器）的 web 与 worker 必须在独立于当前终端的会话中启动，禁止依赖前台 shell 或临时工具会话；否则终端会话结束后进程退出，网关将返回 502。启动时使用 `setsid` 脱离会话，并使用 `nohup`、独立日志和 PID 文件：

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
- 许昌（xuchang）分支的部署环境 web 进程使用 3 个 uvicorn worker 启动（`--workers 3`），用于支撑多并发对话任务；对话（agent SSE）请求由 web 进程处理，跨进程 cancel/steer 依赖环境文件中的 Redis 配置（`REDIS_HOST`/`REDIS_PORT`/`REDIS_DB`/`REDIS_PASSWORD`）。`app.worker` 后台进程仍为单实例，不随 web worker 数量扩展。bge-m3 嵌入权重已收敛到独立服务（`python -m app.services.embedding_server`，默认 `127.0.0.1:8020`）：web/worker 配置 `EMBEDDING_SERVICE_URL` 后走 HTTP 调用、不再各自加载约 1G 权重，多开 worker 不再受模型内存约束；未配置该变量的部署仍按进程本地加载，小内存机器的 worker 上限（如 6.5G 内存机器 ≤3 个 web worker）继续适用。
- 配置文件归属必须按工作树确认，不能把环境文件当作跨项目共享配置：`AGENTS.md`、`deploy/nginx/README.md` 和代码中的默认配置属于共享说明/代码层；`backend/.env.guangdong`（本机）、`backend/.env`、`backend/.env.jiangsu-ops` 是各自部署实例的运行环境文件，只能由对应工作树的 web 与 worker 成对使用。当前工作树若不存在某个环境文件，不得据文档假定它存在或用另一个项目的环境文件替代。
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
