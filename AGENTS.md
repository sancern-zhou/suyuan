项目的运行环境是 conda 环境 `backend_py311`，本机路径为 `M:\suyuan-tools\envs\backend_py311`（Python 解释器 `M:\suyuan-tools\envs\backend_py311\Scripts\python.exe`）。

## 智能体架构与开发理念（提炼自《溯源智能体项目开发规范》2026-11-12，已按 main 代码实际校准）

### 核心架构理念

- **上下文管理是 Agent 项目的核心**：涵盖系统提示词、工具描述（Tools Schema）、对话历史、会话状态、工作记忆（最近 N 轮详细记录 + 压缩摘要）、长期记忆、会话资源目录；Skill 经 `list_skills`/`view_skill` 按需发现（无自动注入层，仅用户显式选中的技能按轮注入正文）；RAG 召回 + web search 的首轮预取证据包为知识问答模式专属（两个工具本身在 expert/ppt 等多模式可用）；知识图谱检索已在问数与运维故障诊断模式落地（`knowledge_graph_query`），问数入口的确定性图谱注入层按项目配置 `graph_entry_modes` 启用（当前各项目默认未开启）。大部分开发调试工作围绕这些内容展开（实现在 `backend/app/agent/context/context_builder.py`）。
- **任务编排三级**：循环编排是各智能体模式的基础编排；固定工作流编排（确定性有序阶段序列，定时任务直接走 workflow handler 绕过 Agent 循环）用于确定性高的定时任务（例行全网巡检日报、站点快速告警推送）；动态 DAG 编排由主 Agent 把大目标自动拆成子任务（数量、依赖每次不同），适合探索性的综合分析报告生成（引擎在 `backend/app/agent/workflow/`）。
- **工具（Tool/MCP）是业务场景的核心区分**，也是本项目区别于通用智能体的主要能力：每个工具仅开放必要资源、解决具体问题（取某一类数据、绘图、专项分析、报告生成）；工具与 Agent 不耦合、可插拔（全局 tool registry + 各模式工具白名单 + 管理端运行时启停）；工具 Schema 默认全量注入上下文，复杂工具说明走渐进式文档读取，工具数量多的模式可 opt-in deferred tools（tool_search 按需注入参数契约，默认关闭）（选型细则见下文"上下文注入选型策略"）。
- **业务知识注入五层分工**：系统提示词只写场景定位、工作流程和输出规范，禁止包含具体工具使用说明（存量模式提示词中的工具指引属待收敛项，新写/改写提示词时不得再添加）；工具描述只放路由（是什么/何时用/如何用/红线）；Skill 放灵活、偏业务流程、可跨 Agent 复用的知识（人编常调、改文件即生效）；知识库放非结构化业务知识，由 Agent 主动检索；知识图谱放关系型业务知识（如站点-城市-运维单位-运维人员图谱），自动检索注入与主动检索并用。
- **多 Agent 协作两种方式**：`call_sub_agent`（子代理）适合把单个轻量任务委派给特定 Agent；`run_agent_workflow`（DAG 编排）由主 Agent 以工具调用提交 DAG 定义动态发起工作流（节点数量与依赖由模型每次生成），适合探索性综合任务（如运维风险分析报告），子节点以委派精简子模式执行（不再二次委派或编排）以提高效率。
- **跨会话长期记忆两层**：常驻层为确认长期有效的规则与偏好，每次全量注入（一般手动维护，`MEMORY.md`）；事实层为一次性、时间敏感、待观察的事实，注入只读已整理事实索引（≤200 条 / 25K 字符），核实事实沿索引链接读原文（`backend/app/agent/memory/curated_facts.py`）。
- **安全护栏四件套**：文件系统沙箱（读根白名单 + 敏感文件拦截，`backend/app/utils/path_config.py`）、提示词层业务红线（不编造数据）、SQL 数据层护栏（数据只读、表白名单，`backend/app/utils/sql_validator.py`）、会话用户隔离（会话目录/数据文件/流式输出均按 owner 隔离）；鉴权复用公司基础架构，后续引入更完整的权限管理。
- **文件资源统一路径契约**：相对路径统一以仓库根解析（绝对路径输入亦接受并归一化，Agent 可见输出一律为相对路径；安全 + 多服务器多项目部署方便），持久化产物全部收敛在 data registry 目录下，会话内资源经资源目录统一登记与交付，跨会话与多 Agent 共享一律走共享文件路径（细则见"Agent 文件系统路径规范"）。
- **架构层归属 main 共享底座**，项目逻辑代码归 `project/*` 分支（细则见"分支与更新归属规范"）。

### 开发理念

- **谨慎使用兜底代码逻辑**，避免真实问题被吞掉忽略。
- **避免字符匹配等硬编码路由策略**，智能体项目尽量由 LLM 推理路由。
- **新场景标准开发流程**：场景定义 → 新增 Agent 模式 → 系统提示词设计 → 工具白名单配置（需要哪些数据、做哪些分析、是否绘图、交互方式、是否生成报告）→ 前端新增入口 → 专属工具开发（已有工具无法满足时）→ 右侧面板调用轨迹核查（工具调用与上下文管理是否符合预期）→ 确认输出结果。
- 环境密钥等敏感信息不入跟踪提交范围；提交与推送是两步操作，先提交后推送。

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
- Linux 部署机（非本机）按项目分工作树部署，布局如下（其他项目如 jiangxi、xuchang 部署时按实际环境单独规划，不受本条约束，详见 `deploy/nginx/README.md`）：
  - 风清气智（main 共享项目，工作树 `/home/xckj/suyuan-main`）：前端 5174（容器 `suyuan-nginx`，挂载该工作树 `frontend/dist`）→ 后端 8000（`backend/.env`，用 `backend/restart_server.sh` 重启）+ 配套 worker（内部端口 8011）。
  - 江苏运维（project/jiangsu-ops 分支，工作树 `/home/xckj/suyuan`）：前端 5175（容器 `suyuan-nginx-jiangsu`，挂载该工作树 `frontend/dist`）→ 后端 8001（`backend/.env.jiangsu-ops`）+ 配套 worker（`python -m app.worker --env-file .env.jiangsu-ops`，内部端口 8012）。
  - 两个 Nginx 容器禁止挂载同一个 `frontend/dist`；风清气智 web/worker 固定从 `/home/xckj/suyuan-main/backend` 启动并使用该目录下的 `backend_data_registry`，江苏运维 web/worker 从 `/home/xckj/suyuan/backend` 启动并使用项目专属 registry。
- 配置文件归属必须按工作树确认，不能把环境文件当作跨项目共享配置：`AGENTS.md`、`deploy/nginx/README.md` 和代码中的默认配置属于共享说明/代码层；`backend/.env.guangdong`（本机）、`backend/.env`、`backend/.env.jiangsu-ops` 是各自部署实例的运行环境文件，只能由对应工作树的 web 与 worker 成对使用。当前工作树若不存在某个环境文件，不得据文档假定它存在或用另一个项目的环境文件替代。
  - 每个项目的 web 进程与 worker 进程必须成对启动（worker 缺失时 fetchers/scheduled-tasks 等接口会 503）。
- 所有部署环境的 `DATA_REGISTRY_DIR` 必须在对应后端环境文件中显式配置为绝对路径；同一项目的 web 与 worker 必须使用同一个值。禁止依赖工作树位置推导持久化目录，切换工作树前须先运行 `python -m app.utils.deployment_preflight --env-file <env-file>` 校验。
- 前端部署后必须确认构建产物包含统一资源接口，并且不再包含旧接口：

  ```bash
  grep -R "resources?presentation_type=document" frontend/dist/assets
  ! grep -R "/office-documents" frontend/dist/assets
  ! grep -R "/visualizations" frontend/dist/assets
  ```

## 后台任务与事件循环隔离规范（后台任务不得与前端竞争）

web/worker 进程的事件循环同时承载前端 API：worker 还承载 web 代理过来的全部 `/api/scheduled-tasks` 管理接口，AsyncIOScheduler 把所有 fetcher、scheduled-task 执行器把所有 agent 工具都跑在同一循环上。一次同步阻塞调用（哪怕只带 30~60 秒超时）会冻结整个循环，让同进程全部前端请求排队。生产实例：NMC 小时抓取任务用同步 requests 把 worker 卡住每小时约 70 秒，定时任务面板点击响应 2~4 秒。规则：

- async 代码内禁止直接调用同步阻塞 IO：`requests`/`urllib`、`httpx` 同步入口、`time.sleep`、`subprocess.run/call/check_*` 等；必须经 `asyncio.to_thread()`（或 `loop.run_in_executor()`）调度到线程。`subprocess.Popen` 仅构造进程不阻塞，可用；其 `wait()/communicate()` 必须走 to_thread。
- 同步客户端方法（如 `gd_suncere_api_client` 的 `query_*`/`_make_request`）在 async 中只能作为 to_thread 的参数出现，不得直接调用，也不得 `await`（await 同步方法会立刻 TypeError）。
- 新后台任务优先用异步客户端（`httpx.AsyncClient`、async SQLAlchemy）；确需同步库时，把同步逻辑收拢为一个同步函数，在 async 入口处一次性 to_thread，不要在循环上散落多次小段同步调用。
- 重 CPU 工作（pandas、openpyxl 大表、报表渲染、SVG 转码）与长批处理同样不得占用事件循环：小批量收拢 + to_thread；小时级批处理放独立进程，不与 web/worker 共循环。
- 守门测试 `backend/tests/core/test_async_no_blocking_calls.py` 静态扫描全部 async def（含同文件同步调用链的传递闭包与跨文件登记的同步客户端方法），违规即测试失败。新增同步客户端的网络方法必须在该测试的 `BLOCKING_METHOD_NAMES` 登记；一次性独立脚本可在 `ALLOWED_FILES` 说明豁免。
- 定位事件循环卡顿：web/worker 日志中的 `event_loop_lag`（loop_watchdog）与 web 的 `scheduled_task_proxy_slow` 告警即阻塞信号；采样用 `py-spy dump`。
- 同步存储层（`scheduled_task_*_storage`）经 `app/db/sync_bridge.py` 的 `run_db()` 落到常驻线程池：**每个池线程持有私有事件循环和池化引擎**（asyncpg 连接不能跨事件循环复用）。禁止退回"每次查询 `create_async_engine` + `NullPool`"——本机 asyncpg 单次握手约 200ms，会让每个定时任务管理接口固定多付 200~300ms，并在 fetcher 批量落库时（每小时 504 行）造成连接风暴和数秒级尖峰。
- `run_db()` 内部用 `loop.run_until_complete` 而非 `run_coroutine_threadsafe`（后者要求目标循环已在 `run_forever`）。池大小 6 容纳 1 层嵌套调用（协程内再同步调 `run_db`，见 `tests/scheduled_tasks/test_runtime_monitor_tool.py`）；加深嵌套层级必须同步调大 `_DB_POOL_SIZE`，否则会耗尽线程死锁。

## 上下文注入选型策略（工具描述 / skill / describe_table / deferred tools）

写入请求上下文的约束文本按"稳定性 × 内容类型"三选一，禁止把长文档整体内联进工具描述或系统提示词（单工具 schema 与单模式注入总量受 `backend/tests/test_agent_mode_context_budget.py` 预算上限守门）：

- **工具描述**：只放路由（是什么/何时用/红线）与高频速查，保持缓存稳定前缀精炼。少变的基础规范（SQL 方言、白名单红线、路径约定等）通过引用固定文档路径渐进读取（read_file 按需整读）；引用路径优先由工具结果或错误信息给出（确定性触发），描述内只留一行指引。硬约束优先做成运行时校验，错误信息即召回钩子，不依赖模型自觉读文档。
- **skill（list_skills/view_skill）**：灵活、偏业务流程的知识（编排方法、领域拆分、成稿风格等），人编常调、改文件即生效。工具描述在入口点名技能（如"编排前先 view_skill: xxx"），并配失败可见的确定性校验兜底。
- **describe_table（工具参数按需取数）**：具体表/字段信息等由数据管道生成的契约，单一来源零漂移、按表粒度取用；支持批量与表名索引（如 `describe_table='tables'`），错误信息带模糊纠错提示。
- **deferred tools（tool_search 按需注入 schema）**：解决"模式工具**数量**多"（与前三通道解决"单工具**内容**大"正交、可叠加）。模式 opt-in 后非 always_on 工具以薄存根常驻（name+路由描述，参数契约不注入；≤600 字符小工具豁免），运行时注入 `tool_search` 检索入口（算法移植自 ZCode：切词/`+`必含/`select:` 批量/打分，结果体积守门）；模型调用存根工具即升级回全 schema，发现状态经会话历史派生跨轮次持久（ZCode 派生思想：历史是唯一状态源），盲调失败时 observation 附完整契约兜底。配置三层：共享表 `DEFERRED_TOOL_MODES`（`app/agent/prompts/tool_registry.py`，默认空=零行为变化）、项目声明 `backend.agent_mode_deferred_tools`（project.yaml，优先于共享表）、全局缰绳 `AGENT_DEFERRED_TOOLS_ENABLED`。高频工具必须进 always_on（发现多一轮 LLM 往返）；机制实现 `app/tools/agent_tools/tool_search_tool.py` + `app/agent/tool_adapter.py:apply_deferred_tool_stubs`。
- 选型口诀：真相在管道 → 工具参数按需取；真相在人且常调 → skill；少变基础规范 → 引用文档渐进读取；真相在子模式 → 父侧只留一行定位；工具数量多 → 模式 opt-in deferred tools。参考实现：`execute_guangdong_mart_sql`（describe_table 契约）、技能 `agent-workflow-orchestration`（编排细则）、`tool_search` 三件套（deferred tools，江西 api_catalog 的运行时级推广）。

## 分支与更新归属规范

- 定位分工：`main` 承载平台架构与跨项目机制；`project/*` 分支承载具体项目的定时任务、业务场景与业务资产。需求只属于单个项目的代码，归该项目分支。
- 共享层改动一律提交到 `main`：`backend/app` 不带项目名的路径、`backend/tests` 共享测试、`backend/config`、`frontend/src` 公共组件与配置、CI、`.gitignore`、`AGENTS.md`。
- 项目改动提交到对应 `project/*` 分支：`backend/app` 下带项目名的路径（如 `tools/jiangsu/**`、`fetchers/jiangsu_*`、`fetchers/weather/jiangsu_*`、`scenarios/xuchang_*`）、`backend/app/db/repositories/jiangsu_*`、`backend/app/db/models` 中的项目模型、`projects/<project>/**`（project.yaml、scheduled_tasks、项目文档与技能）、`backend/tests/test_jiangsu_*`、`backend/tests/project_config/test_<project>_*`（如 test_guangdong_modes.py）、项目专属前端（如 StationhouseInspectionPanel）。
- 判定准则（需求归属优先于实现耦合）：为单一项目需求编写、或当前只有单个项目使用的代码，归该项目分支，并应放在带项目名的路径下，使归属可按路径识别；内容依赖 `projects/*/project.yaml`、`settings.project_id` 分支逻辑的一律归项目分支。反之，把代码放入共享路径即视为承诺跨项目复用，该文件此后在项目分支上的改动必须回合 main，不得长期单侧演化。
- 存量归属备注：`backend/app/services/station_operation_monitor/`（站点运行日报与小时采集引擎）为广东专属需求，历史上仅在 `project/guangdong` 演化，按项目层对待、无需回合 main；其他项目复用前，须先提炼为共享引擎提交 main（含把广东专属文案配置化），再由项目分支合并使用。
- 混合文件（如 `tools/__init__.py`、`tool_registry.py`）：先在 main 提交共享部分，项目分支合并后再叠加项目部分。项目专属注册块在一个文件内只允许出现一次；合并共享文件后必须重启对应服务验证启动（曾因 main 侧复制了广东工具注册块，合并后 guangdong 全部进程重复注册崩溃）。
- 工作流程：先在 main 提交共享改动 → 项目分支 `git merge main` → 再提交项目改动。禁止在项目分支直接修改共享层文件而不回合 main（带项目名的路径与上条存量备注所列文件除外）。
- 项目分支每天开工先 `git merge main`；共享层文件的改动永远以 main 为准。
- 禁止提交：`backend/.env.*`（模板除外）、`frontend/dist-*`、`backend/backend_data_registry*`、`suncere*/`（见 .gitignore）。
