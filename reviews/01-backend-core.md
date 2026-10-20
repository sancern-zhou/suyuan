# 后端核心架构与应用安全评审

- 评审人：backend-core-reviewer（后端核心架构与应用安全）
- 评审方式：只读静态代码评审（未运行任何程序，所有结论基于代码阅读；不确定处标注「待验证」）
- 评审范围：`backend/app/main.py`、`worker.py`、`proxy_server.py`、`api_response_formats.py`、`kingbase_dialect.py`、`backend/app/api/` 全部路由、`services/` 非持久化服务、`config/`、`tools/`、`fetchers/` 结构性问题、`utils/` 核心工具；`db/`、frontend、deploy 仅在架构交互层面提及。

---

## 一、总体评价

这是一套成熟度中上、明显经过多轮安全加固的大型 FastAPI 单体（backend/app 共 1333 个 Python 文件）：入口装配已良好分层（main.py 仅 64 行，路由/中间件/生命周期/静态文件各自成模块），鉴权采用 default-deny ASGI 中间件 + 生产配置强校验，`execute_python` 沙箱 fail-closed，上传链路有完整的消毒与属主校验，整体架构方向正确。主要风险集中在三处：一是**部分管理面/工具面的权限与隔离不一致**（admin 配置写接口缺 admin 依赖、bash 沙箱未断网、`/tmp` 全目录文件管理）；二是**若干"自己定的规范自己破"**（`__file__`/cwd 相对路径仍遍布约 40 处生产代码、专家会商输出落在 cwd 相对目录）；三是**巨型文件仍在增长**（llm_service.py 3566 行、execute_python_tool.py 3540 行），且约 178 个测试/spec 文件混编在 app 生产包内。整体属于「骨架优秀、边角失守」的状态，无系统性架构级缺陷。

## 二、规模概览

- `backend/app` 共 **1333 个 .py 文件**；`backend/app/api/` 下 34 个生产路由文件 + 12 个 `*_test.py`/`*_spec.py`。
- 混入生产包的测试/规范文件共 **178 个**：`*_test.py` 103 个、`*_spec.py` 33 个、`test_*.py` 42 个（约占 app 包 13%）。
- 最大文件 Top10（按行数，抽样探测法统计，非全量排序；`__file__` 推断根目录违规点约 40 处见第五节）：

| # | 文件 | 行数 |
|---|------|------|
| 1 | backend/app/services/llm_service.py | 3566 |
| 2 | backend/app/tools/utility/execute_python_tool.py | 3540 |
| 3 | backend/app/services/ops_work_order_audit_engine.py | 2470 |
| 4 | backend/app/api/agent.py | 1955 |
| 5 | backend/app/agent/react_agent.py | 1679 |
| 6 | backend/app/tools/office/ppt_master_tool.py | 1673 |
| 7 | backend/app/agent/runtime/agent_runtime.py | 1601 |
| 8 | backend/app/api/scheduled_task_routes.py | 1485 |
| 9 | backend/app/knowledge_base/service.py | 1141 |
| 10 | backend/app/agent/context/context_builder.py | 1042 |

- 规模结论：`api/`、`services/` 单文件 800–2000 行常见；`llm_service.py`（多供应商客户端+路由+重试+预算）与 `execute_python_tool.py`（沙箱+AST 分析+产物归档+手册逻辑）是最应优先拆分的两处。

## 三、发现清单

### P0（必须修：安全漏洞 / 数据损坏 / 明显功能错误）

- [P0] **admin 配置写接口缺少管理员鉴权，任意登录用户可篡改运行时配置** — backend/app/api/admin.py:178-263 — `GET /api/admin/config/all`、`PUT /api/admin/config/{section}/{key}`、`POST /api/admin/config/reset`、`POST /api/admin/config/reload` 均无 `require_admin_user` 依赖（网关中间件只保证"已登录"，见 backend/app/auth/middleware.py:115-133），任何普通用户可改写查询模板、重置甚至删除配置文件（admin.py:242-248 直接 `os.remove`）；查询模板（backend/app/config/config_manager.py:103-145）会被 format 后发送到内部数据 API（backend/app/services/external_apis.py:231-243），构成越权数据查询/模板注入面。同项目的 monitoring 路由都做了 `_require_admin`（backend/app/api/monitoring.py:30-32），此处属于遗漏 → 给全部 `/api/admin/config*` 路由加 `Depends(require_admin_user)`（backend/app/auth/dependencies.py:33-41 现成），`reload` 这类删文件操作再单独收紧。

- [P0] **bash 工具沙箱未隔离网络，Agent 生成的命令可访问内网** — backend/app/tools/utility/bash_tool.py:243-269 — bwrap 参数只做了 `--unshare-pid/--unshare-ipc/--unshare-uts`，没有 `--unshare-net`；而同仓库 `execute_python` 沙箱的标准是"默认无网络"（backend/app/tools/utility/execute_python_tool.py:16-20）。经 bash 工具可对内网 Redis/PostgreSQL/Nacos/网关（settings 默认信任网段 10.10.204.0/24，backend/config/settings.py:225-228）做探测、横向访问与数据外传 → 补 `--unshare-net`（确有联网需求的白名单场景单独显式放行）。

### P1（应尽快修：健壮性 / 性能 / 架构隐患）

- [P1] **文件管理器把整个 /tmp 暴露给任意登录用户** — backend/app/api/file_manager_routes.py:23,101-253 — `ALLOWED_ROOT = Path("/tmp")`，`/file-manager/list|download|info` 可列出并下载 `/tmp` 下任意文件（含其他进程/会话写入的日志、临时数据；AGENTS.md 部署规范本身就往 /tmp 写 web/worker 日志与 PID）；路径穿越防护本身是完善的（resolve+is_relative_to），但边界过大 → 收敛到 `get_data_registry()` 下的专用子目录；另建议删除调试端点 `/file-manager/test`（:73-99）。
- [P1] **SQL 只读校验可被 `SELECT ... INTO` 绕过** — backend/app/utils/sql_validator.py:18-22,111-113 — 危险关键词黑名单没有 `INTO`，`SELECT * INTO xx FROM 白名单表`（SQL Server 语法）可通过校验并在库内建表/写数据；表名白名单只扫 `FROM/JOIN`（:311-345）扫不到 INTO 目标 → 黑名单补 `INTO`，并在数据库账号侧落实只读权限（账号权限「待验证」）。
- [P1] **http_client 在 INFO 日志记录完整请求头与响应体，可能泄露凭证** — backend/app/utils/http_client.py:67-74,90-97,228-236 — `http_request_detail` 记录 `headers`（调用方传入的 Authorization/Cookie 等会原样进日志）、`http_response_received` 记录响应前 200 字符；后端含大量携带 token 的出站调用（auth/jiangsu/qianlima 等）→ 头部做脱敏白名单（只记 Content-Type 等），响应预览降为 debug。
- [P1] **quarto 渲染子进程无超时** — backend/app/services/quarto_report_renderer.py:728-735 — `subprocess.run` 未传 `timeout`，quarto/pandoc 卡住（网络资源、jupyter 内核）将无限期占用调用线程；报告渲染在 web 请求链路内执行时会拖死一个 worker 线程 → 加 `timeout=` 并按进程组终止，参考 bash_tool 的 `_terminate_process_tree` 实现。
- [P1] **专家会商输出目录使用 cwd 相对路径，违反项目自身路径规范** — backend/app/services/expert_deliberation/deliberation_engine.py:31-32 — 默认 `output_root="data/expert_deliberations"` 依赖进程 cwd（startup.py:35-36 把 cwd 设为 backend/，产物实际落到 `backend/data/`，绕开了 `backend_data_registry` 统一管理与 DATA_REGISTRY_DIR 部署约定）；同文件 API 侧 `DEFAULT_INPUT_DIR` 默认 `/tmp/A会商文件`（backend/app/api/expert_deliberation.py:33）→ 默认值改为 `get_data_registry()/"expert_deliberations"`。
- [P1] **config_manager 浅拷贝导致“恢复默认值”失效** — backend/app/config/config_manager.py:197,200,266 — `DEFAULT_CONFIG.copy()` 是浅拷贝，`update_value`（:232-249）原位修改嵌套 dict 会同步污染 `DEFAULT_CONFIG`，之后 `reset_to_defaults()` 恢复的是被改过的值 → 用 `copy.deepcopy`；顺带修复多进程（许昌 3 worker）无锁并发写同一 system_config.json 的问题。
- [P1] **worker 入口以 import 副作用切换角色** — backend/app/worker.py:52-57 — 模块顶层执行 `os.environ["APP_ROLE"]="worker"` 且夹在 import 之间；任何先于该行 import settings 的路径都会读到错误角色；对测试/工具脚本 `import app.worker` 也会造成环境变量污染 → 把角色判定收敛到 `main()` 内显式传参。
- [P1] **web 进程内直跑长耗时数据抓取任务** — backend/app/api/routes.py:45-87,98-161 — `POST /api/fetchers/era5/historical`、`/api/fetchers/jining_era5/fetch` 在 web worker 内直接 `await` 全域 ERA5 抓取（分钟级）；`FetcherWorkerProxyMiddleware` 只代理 status/list/start/stop/trigger 等管理子路径（backend/app/core/fetcher_worker_proxy.py:11-36），这两个重任务不在代理名单，与"fetchers 跑在 worker"的部署模型相悖 → 移到 worker 或改为提交任务。

### P2（建议：可维护性）

- [P2] **约 178 个测试/spec 文件混编在 backend/app 生产包内**（清单见第二节口径；例：backend/app/api/agent_attachment_history_test.py、backend/app/db/session_persistence_spec.py、backend/app/services/ops_audit/rules/test_rf_range_rules.py 等）→ 迁移到 backend/tests 或独立 tests 目录，避免被打进运行时镜像并被 import 扫描。
- [P2] **生产代码 `__file__` 推根违规约 40 处** — 代表：backend/app/config/config_manager.py:184（运行时配置写进源码树）、backend/app/core/static_files.py:14,23、backend/app/agent/selection_context.py:13、backend/app/agent/prompts/data_source_map.py:34、backend/app/knowledge_base/service.py:94、backend/app/services/ops_work_order_audit_engine.py:29、backend/app/tools/utility/grep_tool.py:156、backend/app/tools/query/compare_standard_reports/tool.py:480（还 `sys.path.append`）、backend/app/fetchers/quick_trace/quick_trace_fetcher.py:36；fetchers/city_statistics/ 下 12 个批处理脚本全部 `Path(__file__).parents[...]`。`Path.cwd()/os.getcwd()` 合规良好（生产代码仅 startup.py:39 一处，且是 chdir 后打印日志）→ 分批替换为 `path_config.PROJECT_ROOT/resolve_agent_path`，脚本类可用统一入口。
- [P2] **启动期 `os.chdir` 全局副作用** — backend/app/lifecycle/startup.py:35-41 — 用 `__file__` 推导 backend 目录并 chdir，是"cwd 推断根目录"禁令的变体；多 worker 下属进程全局状态变更 → 逐步让工具/数据路径全部走 path_config 后移除 chdir。
- [P2] **llm_response_parser 隐患两处** — backend/app/utils/llm_response_parser.py:614（`_error_result` 在 `can_retry=False` 时引用不存在的 `stats["fallback"]` 键，当前所有调用点恰好都传 True，属潜伏 KeyError）；:465-478（中文标点强制替换会把合法 JSON 字符串值里的 `“”`《》 改成 ASCII 引号/尖括号，轻则破坏本可解析的响应、重则污染最终答案文本）→ 补键、把替换限定在 JSON 结构层或仅做尝试性回退。
- [P2] **llm_response_parser 全局单例并发统计互踩** — backend/app/utils/llm_response_parser.py:97,132,735 — 模块级 `parser` 的 `_parse_cache`/`stats` 无锁，被并发请求共享；缓存本身无害，统计数会失真 → 每次解析新建实例或加锁。
- [P2] **api_response_formats.py 混入测试脚本与硬编码内网 IP** — backend/app/api_response_formats.py:236-390（`test_all_particulate_apis` 等可执行测试代码、`180.184.91.74` 多处）→ 测试移到 tests/，endpoint 改读 settings（settings 已有同值默认，backend/config/settings.py:304-317）。
- [P2] **system_status 泄露数据库主机信息** — backend/app/api/system.py:128-133 — `database_url.split("@")[1]` 在密码含 `@` 时会截出部分密码，且暴露内网 host:port → 用 SQLAlchemy `make_url` 渲染脱敏 DSN。
- [P2] **上传 Office 预览同步占用线程池** — backend/app/api/upload_routes.py:148-174,553 — `asyncio.to_thread(_office_pdf_preview)` 单次最长 90s，多个并发上传会占满默认线程池；`validate_file_type` 的 MIME 分支是死代码（:271-278 结果恒被忽略）→ 限制并发信号量，清理死分支。
- [P2] **monitoring 全局记录无上限** — backend/app/monitoring/llm_monitor.py:69,98-116 — `records` 列表无限增长并全量落盘 → 加 maxlen/滚动；另 monitoring.py:90-97 临时重定向 `sys.stdout` 在并发请求下不安全（当前同步执行风险低，属脆弱写法）。
- [P2] **config_crypto 失败静默降级** — backend/app/utils/config_crypto.py:84-90 — 解密失败时原样返回密文/原文，错误被吞 → 至少记录并抛出明确异常。
- [P2] **WebSocket 鉴权依赖各端点自律** — backend/app/auth/middleware.py:80-83 对非 http scope 直接放行，现有两个 WS 端点均自带票据/HMAC 校验（backend/app/api/scheduled_task_ws.py:19-26、backend/app/api/social_app_routes.py:206-217），但新增 WS 端点容易被遗漏 → 在中间件层为 websocket scope 增加统一票据门禁或注册表校验。
- [P2] **proxy_server.py 已退役仍保留** — backend/app/proxy_server.py:1-10 — 纯死代码 → 删除并清理部署脚本引用（如有，「待验证」deploy/ 侧）。
- [P2] **重复代码** — backend/app/utils/http_client.py:32-179 与 181-341 GET/POST 两段约 150 行重试逻辑几乎复制；`convert_svg_to_png`/`soffice`/`quarto` 等子进程调用散落多处、超时与终止策略不一致 → 抽公共 `run_subprocess_with_limits`。

## 四、亮点

1. **default-deny 鉴权边界**：ASGI 中间件白名单放行 + 网关信任网段 + 剥离 `x-user-id/x-is-admin` 不可信头（backend/app/auth/middleware.py:25-57,124-133），配合 settings 生产强校验（禁 mock 认证、禁 `*` CORS、强制 share secret 与受限信任网段，backend/config/settings.py:269-301），鉴权设计在同类项目里属于高水准。
2. **统一路径能力层**：backend/app/utils/path_config.py 提供敏感路径黑名单（.env/密钥/.git）、保护写路径、单一读授权谓词与 Agent 路径格式化，是整个 Agent 文件工具面的安全基座。
3. **fail-closed 的 Python 沙箱**：execute_python 非 bubblewrap 引擎直接拒绝执行、不回退宿主机（backend/app/tools/utility/execute_python_tool.py:128-131,868-874），挂载白名单、资源限制、进程组终止齐全；bash 沙箱把 `backend/.env*` bind 为 /dev/null（bash_tool.py:290-292）。
4. **上传链路防御完整**：uuid 命名落盘、SVG 用 defusedxml 消毒并转 PNG（upload_routes.py:301-386）、会话属主校验（:50-61）、附件强制 Content-Disposition + nosniff。
5. **声明式装配与拆分**：ROUTER_REGISTRY 数据驱动注册、可选模块失败降级（core/routing.py:26-157），main.py 仅 64 行，lifecycle 按 database/social/kb/scheduled 分文件。
6. **SSE 基建统一**：core/sse.py 心跳与业务流分离、send 超时兜底；专家会商 SSE 在断连时正确 cancel 后台任务并回收（api/expert_deliberation.py:62-115）。
7. **SQL 工具白名单化**：表名白名单 + SELECT/CTE 限制 + TOP/Limit 消毒（sql_validator.py + tools/query/execute_sql_query/tool.py:688-709），方向正确（缺口见 P1）。
8. **合规自查工具化**：path_config_test.py 甚至内置了对生产代码 `Path.cwd()` 违规的静态扫描（backend/app/utils/path_config_test.py:144）。

## 五、修复优先级路线建议

1. **本周（P0，半天级工作量）**：admin 路由补 `require_admin_user`；bash 沙箱加 `--unshare-net`。两项都是几行改动，收益最大。
2. **两周内（P1）**：sql_validator 补 `INTO` 并核实 SQL Server 账号只读权限；http_client 日志脱敏；quarto/soffice 子进程统一加超时；专家会商 output_root 迁入 data registry；config_manager deepcopy；`/tmp` 文件管理器收敛目录。
3. **一个月内（P1 尾 + P2 结构性）**：web 内直跑的 ERA5 抓取任务移交 worker；启动 chdir 退场路径规划（先让全部工具走 path_config）。
4. **持续重构**：llm_service.py、execute_python_tool.py 按供应商/沙箱/产物归档拆包；178 个 app 内测试迁往 backend/tests；`__file__` 推根按目录分批清理（先 api/services，再 tools/fetchers 脚本）。
5. **防回归**：把「admin 路由必须带 admin 依赖」「沙箱网络隔离」「生产代码禁 __file__ 推根」三条加进 path_config_test 式的静态合同测试，现有测试文化（178 个内嵌测试）完全支撑这种做法。
