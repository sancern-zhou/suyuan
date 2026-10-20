# 部署与工程质量评审报告

> 评审人：devops-quality-reviewer（只读静态评审）
> 基准：根目录 AGENTS.md 部署规范、CLAUDE.md、deploy/ 全部物料、backend 根部工程文件、CI、.gitignore 体系、backend/tests 布局
> 限制：Windows 检出环境，无法运行 docker/git/程序；所有「是否被 git 跟踪」的结论均按 .gitignore 规则推断，一律标注**（待验证）**。行号以当前工作树为准。

## 一、总体评价

部署主链路（restart_server.sh + nginx compose + deployment_preflight + 契约测试）设计成熟度明显高于平均水准：preflight 先行、进程组终止、cwd+cmdline 双重校验、ss+health 双验证，且 nginx 模板与启动脚本都有 pytest 契约测试守护。但仓库卫生是重灾区：backend 根目录堆积约 439 个杂物文件（约 300 个 noaa_response_*.html、12 个 zip、11 个日志、真实会话 cookie JSON），`.dockerignore` 不拦截它们，`COPY . .` 会全部打进镜像；`.env.production.template` 缺 AGENTS.md 强制的 `DATA_REGISTRY_DIR`；start.sh 与 restart_server.sh 双入口漂移且默认 4 worker 触碰 OOM 红线。docs/ 整目录被 gitignore，关键运维文档游离于版本控制之外。安全机制（gitleaks 全历史扫描、secrets 全局忽略、密码强制注入）在位，但历史泄露处置与入口一致性仍需收口。

## 二、部署拓扑现状

- **入口层**：`deploy/nginx/docker-compose.yml` 以 `network_mode: host` 运行 nginx:1.27-alpine（容器名 `suyuan-nginx`，默认端口 5174），只读挂载 `../../frontend/dist` 与 `./templates`；健康检查打 `/api/suyuan/health`（deploy/nginx/docker-compose.yml:5-20）。
- **路由**：`templates/default.conf.template` 将 `/api/auth/` 转发公司网关（默认 `http://10.10.204.80:8025`），`/api/suyuan/ws/`→`${BUSINESS_UPSTREAM}/ws/`（WebSocket），`/api/suyuan/`→`${BUSINESS_UPSTREAM}/api/`，`/api/social/app/**` 原样转发本机后端；auth 10r/s、api 50r/s 双层限流（default.conf.template:7-9,32-115）。
- **应用层**：每个项目 web（uvicorn，风清气智 8000 / 江苏运维 8001）与 worker（`python -m app.worker`，内部端口 8011/8012）成对运行于 systemd 单元或 nohup+setsid 会话；restart_server.sh 同时重启两者并自动探测 systemd 单元名（backend/restart_server.sh:93-103,208-218）。
- **数据层**：本机 PostgreSQL 16 容器（5433→5432，`SESSION_DATABASE_URL` 承载会话/任务表）+ 远端 weather_db（`DATABASE_URL`，代码按 URL 自动路由，deploy/postgres/README.md:3-15）；本机 Qdrant v1.13.4（6334→6333，`LOCAL_QDRANT_*`）+ 云端共享库（`SHARED_QDRANT_*`，deploy/qdrant/README.md:20）；Redis 仅在 env 中引用（`REDIS_HOST=localhost`），deploy/ 无对应 compose/README。
- **配置漂移面**：江苏运维的 compose（`deploy/nginx/docker-compose.jiangsu-ops.yml`）与本机实际生效的统一入口模板（`deploy/nginx/templates-local/default.conf`，deploy/nginx/README.md:82）都不在仓库内；另有 podman 版 systemd 单元 `deploy/postgres/suyuan-postgres.service` 与 docker 生态并存。

## 三、发现清单

### P0（安全/会造成事故）

- [P0] **真实会话凭据明文落在 backend 根目录，且历史曾泄露** — backend/haikang_auth.json:3-5 — 文件含活体 CAS/JSESSIONID 票据（`CASTGC: TGT-260-…`、`JSESSIONID`、`EPORTAL_JSESSIONID`），同类还有 haikang_cookies.json、haikang_auth_info.json；.github/SECURITY_HISTORY_REMEDIATION.md:3-5 明确承认「仓库历史中曾含可到达的凭据」。当前 backend/.gitignore:46 `*.json` 已忽略它们**（待验证）**，但 backend/.dockerignore 未排除 `*.json`（仅 :11 排除 system_config.json），backend/Dockerfile:47 `COPY . .` 会把凭据打进镜像层 → 立即删除并轮换票据；在 .dockerignore 增加 `*.json`（带白名单反选）；确认 filter-repo 历史重写与强制轮换已执行（待验证）。

### P1（可靠性/规范）

- [P1] **nginx 对 /api/social/app/** 未剥离信任头，违背网关契约** — deploy/nginx/templates/default.conf.template:88-115 — `/api/social/app/voice/realtime` 与 `/api/social/app/` 两个 location 缺少 `proxy_set_header X-User-Id ""` / `X-Is-Admin ""`，而契约要求 stripClientHeaders（deploy/gateway/suyuan-route-contract.yaml:19-21），同模板其他 location 均已清除（:48-49,66-67,84-85）；后端 `TRUSTED_GATEWAY_NETWORKS` 含 127.0.0.1（backend/.env.example:78），nginx host 网络下后端看到的源恰是 127.0.0.1，客户端伪造这两个头可能被后端当作网关信任（后端消费逻辑待 backend-core-reviewer 确认）→ 两个 social location 补齐两行清除头，并让 tests/deploy/test_nginx_contract.py 按 location 断言。
- [P1] **江苏运维 compose 与生产 nginx 模板不在版本控制内** — deploy/nginx/README.md:236 引用 `deploy/nginx/docker-compose.jiangsu-ops.yml`（全仓 glob 不存在）；README.md:82 称本机 5174 实际使用 `deploy/nginx/templates-local/default.conf`，而根 .gitignore:303 有意忽略 `deploy/nginx/templates-local/` → 实际生产入口配置无版本记录、无法从仓库重建。至少应入库脱敏后的 templates-local 模板与 jiangsu compose（端口/容器名参数化）。
- [P1] **start.sh 与 AGENTS.md 规范冲突：前台启动 + 默认 4 worker** — backend/start.sh:55 `WORKERS="${WORKERS:-4}"`（6.5G 内存机器红线为 ≤3，AGENTS.md 明确 4 个即 OOM）、:64-69 uvicorn 前台运行，无 nohup/setsid/PID 文件（AGENTS.md 要求脱离终端会话+PID 文件）；且根 .gitignore:106 `backend/start*` 会忽略 start.sh**（待验证）**，restart_server.sh:177 默认 WORKERS=1 → 废弃或改造 start.sh（统一转 restart_server.sh 入口，或改为 setsid+PID 且 WORKERS 默认 1 并移出 gitignore）。
- [P1] **restart_server.sh worker 兜底路径未验证监听，PID 文件与文档不一致** — backend/restart_server.sh:272-292 无 systemd 时 worker 以 nohup 启动后不做 `ss` 端口归属检查（systemd 分支在 :253-262 有检查），不满足「web 与 worker 内部端口均在监听」的验收要求；worker PID 文件为 `/tmp/suyuan_backend_worker.pid`（:202）而 deploy/nginx/README.md:209 写 `/tmp/suyuan_worker.pid` → 兜底路径复用 `worker_unit_owns_port` 式校验；统一 PID 文件命名。
- [P1] **Qdrant 全网卡暴露且无认证；Redis 无部署物料** — deploy/qdrant/docker-compose.local.yml:5-6 端口映射 `6334:6333` 绑定 0.0.0.0，compose 未设置 `QDRANT__SERVICE__API_KEY`（Qdrant 默认无鉴权），backend 模板 `LOCAL_QDRANT_API_KEY=` 为空（backend/.env.example:296）；deploy/ 下没有 Redis 的 compose/README，而 AGENTS.md 规定多 web worker 的 cancel/steer 依赖 Redis → 端口改 `127.0.0.1:6334:6333` 并启用 API key；补 Redis 部署物料或明确复用说明。
- [P1] **关键运维文档整目录被 gitignore** — 根 .gitignore:56 与 :224 两次忽略 `docs/`，而 docs/knowledge-base-graph-operations.md（CLAUDE.md 指定的发布迁移步骤）与 docs/project-management-model.md 等仅存在于本地工作树**（待验证是否曾被 -f 加入）** → 运维/发布类文档应入库：`docs/` 改为忽略清单式（如仅忽略 `docs/*修复*.md` 类草稿），或显式 `!docs/knowledge-base-graph-operations.md` 等白名单。
- [P1] **生产环境模板缺 DATA_REGISTRY_DIR，与 AGENTS.md 强制项不一致** — 全 backend 仅 backend/.env.example:11 含 `DATA_REGISTRY_DIR`，backend/.env.production.template（195 行）完全没有该键（grep 证实）→ 按模板新建的生产环境会在 preflight 处被拦截（防线有效但体验为「报错而非配齐」），模板应补 `DATA_REGISTRY_DIR=/绝对路径` 占位与说明。
- [P1] **同目录双命名测试成对并存，pytest 重复收集** — backend/app/services/ops_audit/rules/ 下 `test_rf_range_rules.py`（283 行）与 `rf_range_rules_test.py`（283 行）、`test_rf_required_rules.py` 与 `rf_required_rules_test.py`、`attachment_rules*`、`rf_calibration_date_rules*`、`rf_pm_pressure_rules*`、`o3_value_pass_xls_rules*` 等多对并存；backend/pyproject.toml:59-60 `testpaths=["tests","app"]` 且 `python_files` 同时匹配两种后缀 → 同一规则模块两套测试全部执行、双维护。统一为一种命名并合并。
- [P1] **frontend/index.html 疑似被根 .gitignore 忽略，新 clone 无法构建** — 根 .gitignore:41 全局 `*.html`，frontend/.gitignore（1-33 行全文）无 `!index.html` 反选，全仓亦未检索到该反选 → 按规则推断 index.html 未被跟踪**（待验证；若 CI frontend-build 一直通过则可能曾被 `git add -f`）** → 规则上显式 `!frontend/index.html`，消除「构建入口文件依赖 gitignore 事故幸存」的状态。

### P2（卫生/建议）

- [P2] **backend 根目录约 439 个杂物文件** — backend/noaa_response_*.html 约 300 个（HTTP 调试转储）、app.zip / app (2).zip / app (3).zip / app3-8.zip / app 9.zip / config.zip / models.zip 共 12 个归档、install.log / test.log / test_output.log / server*.log / expert_deliberation_uvicorn.log / android_gateway.{stdout,stderr}.log 等 11 个日志、__tmp_test.py / __tmp_check.py、check_*/test_*/fix_*/analyze_*/search_* 等约 90 个一次性脚本、企业微信截图_*.png 等。gitignore 已基本覆盖（根 :32 `*.log`、:41 `*.html`、:136 `*.zip`；backend :95 `backend/test*.py`、:98-109 debug*/fix*/search* 等）**（待验证 tracked 状态）**，但 backend/.dockerignore 均未排除 → 物理删除；.dockerignore 增加 `noaa_response_*` `*.zip` `*.log` `__tmp_*` 等。
- [P2] **Windows 设备文件残留 nul/$null** — backend/nul、backend/app/nul、frontend/nul、backend/$null — 已被根 .gitignore:43 `nul` 与 backend/.gitignore:58,106 `$null` 覆盖**（待验证）** → 直接删除文件即可。
- [P2] **app 生产树内的 .bak 与镜像未过滤测试代码** — backend/app/tools/query/get_vocs_data/tool.py.bak（根 .gitignore:62 `*.bak` 已忽略，待验证）；backend/.dockerignore 不排除 `tests/`、`*_test.py`、`*.bak` → 镜像内混入非运行资产 → .dockerignore 补 `tests/`、`**/*_test.py`、`*.bak`。
- [P2] **backup.sh 脆弱点** — deploy/postgres/backup.sh:18 硬编码容器名 `suyuan-main-local-postgres-1`（与 compose 项目名 suyuan-main 强耦合，README:26 换项目名即失效）；:12/:31 `RETAIN_DAYS` 实际按「份数」而非「天数」清理；无校验和/异地副本（README:71 自认单盘）。凭据处理本身规范：:9 source .env、:18-20 pg_dump 在容器内执行、密码不落命令行 → 容器名参数化；变量改名 RETAIN_COUNT；追加 sha256 记录。
- [P2] **podman systemd 单元与 docker 生态不一致** — deploy/postgres/suyuan-postgres.service:8-9 使用 `/usr/bin/podman`，容器名 `suyuan-postgres` 与 compose 生成的 `suyuan-main-local-postgres-1` 对不上 → 确认是否遗留物，删除或注明适用环境。
- [P2] **nginx 安全头两处过宽** — CSP `frame-ancestors *`（default.conf.template:121,130,138）允许任意站点内嵌（clickjacking 面），`connect-src 'self' https: ws: wss:` 放行任意 https/ws → 在已知内嵌方固定后收紧为白名单。同文件 server_tokens off（:16）、限流（:7-9）为亮点。
- [P2] **nginx compose 无资源限制、默认上游写死内网 IP** — deploy/nginx/docker-compose.yml:9 `AUTH_UPSTREAM` 默认 `10.10.204.80:8025`、无 mem/cpu limits → 默认值移入 .env.example 类文件并补 limits。
- [P2] **后端 uvicorn 绑定 0.0.0.0** — backend/restart_server.sh:179、start.sh:65、Dockerfile:77 均绑全部网卡，8000/8001 可绕过 nginx 限流/头清洗直达 → AGENTS.md 本身如此规定，建议配合防火墙/安全组仅放行本机与网段，属部署环境动作（待验证）。
- [P2] **依赖锁定不彻底、无 hash** — backend/requirements.txt 核心已 pin（:2-7 fastapi==0.115.0 等），但仍有约 30 个范围依赖（:11-13 urllib3/chardet/charset-normalizer、:21-26 xarray/netCDF4/scipy/PyKrige/nimfa、:36-38 tiktoken/json-repair/llama-index-core、:83-84 jieba/rapidfuzz、:92-93 openpyxl/pypdf、:120-131 ipython/qq-botpy/pycryptodome 等）；无 lock 文件、无 --require-hashes；requirements-dev.txt 仅 3 包（pytest/pytest-asyncio/ruff）。python 约束良好：pyproject.toml:5 `>=3.11,<3.12`，environment.yml:7 python=3.11 → 引入 pip-tools/uv lock 或补齐 pin。
- [P2] **CI 缺口** — .github/workflows/ci.yml 未运行 ruff（pyproject.toml:22-55 已配置 lint 规则）；仅触发 main/master（:4-7），project/*、xuchang 分支无 CI；pytest 未按 marker 过滤（pyproject.toml:68-73 已定义 integration/browser/external_api/slow）；前端 test:session-resources（含 playwright e2e，frontend/package.json:18）未纳入 CI；gitleaks 全历史扫描（ci.yml:10-22）+ .gitleaks.toml 存在为亮点 → 补 lint job；分支触发放宽；CI 增加 `-m "not integration and not browser and not external_api"` 快速层 + 定时全量层。
- [P2] **测试组织双轨制** — backend/tests/ 根部平铺约 263 个文件，同时存在 12+ 个规整子目录（api/auth/knowledge_base/db/deploy/browser/conversations/integration/project_config/tools…），总数约 570 个 py；app/ 内另有约 105 个 `*_test.py`；conftest 仅 2 个（tests/conftest.py、tests/tools/gisctl/conftest.py），app 内测试无局部 conftest；tests 根混入 fixture JSON（tests/api_response_full.json、tests/test_particulate_api_responses.json），后者被 backend/.gitignore:46 `*.json` 忽略**（待验证）**而 backend/app/api_response_formats.py:360 会在运行时向 tests/ 写该文件（生产代码写测试目录，方向反了）→ 顶层文件按域归目录；fixture 移至 tests/fixtures/ 并加 gitignore 白名单；api_response_formats.py 的落盘行为参数化到数据目录。
- [P2] **.gitignore 补丁层过厚** — 根 .gitignore:254 `D:tmp/`（Windows 路径事故）；:56 与 :224 重复忽略 docs/；:58,148-153 针对个别 ops_audit `test_*.py` 的反选与现存 `*_test.py` 双命名互相纠缠；`*.png/*.html/*.txt` 全局粒度过粗导致 :40,65-66,82-91 一长串反选 → 做一次 gitignore 重构：全局规则收窄到生成物扩展名 + 目录清单，白名单改为目录级。
- [P2] **env 模板含真实基础设施信息** — backend/.env.example:45,82,97-104,253 与 .env.production.template:62,68-76,99,110-122 写明内网/公网 IP、OIDC issuer（idaut.cnemc.cn）等（内网项目常见做法，仍建议评估最小化）；API key 均为占位符 ✔。
- [P2] **deployment_preflight 覆盖缺口** — backend/app/utils/deployment_preflight.py 仅校验 DATA_REGISTRY_DIR（:16-38）与可选 cgroup（:41-75）：不检查目标目录是否存在/可写（路径打错也能过）；:22-25 os.environ 优先于 env 文件，shell 残留变量可掩盖 env 文件缺配；无 web/worker 双 env 文件同值比对模式；不校验 DATABASE_URL/SESSION_DATABASE_URL/Redis 等其他部署关键项 → 增加目录可写探测、`--compare-env a.env b.env` 模式与关键 URL 格式校验。
- [P2] **pytest 收集面含生产树** — pyproject.toml:59 `testpaths=["tests","app"]` 使 `pytest` 直接收集 app/ 内测试，配合双命名问题放大重复；工具脚本混入 tests 根（pmf_root_cause.py 等）→ 收敛 testpaths 到 tests/，app 内测试迁入或统一命名。

## 四、仓库卫生清单

以下文件按 .gitignore 规则推断**大概率未被跟踪（待验证）**，但均留在工作树与（除注明外）Docker 构建上下文中，建议物理清理：

| 类别 | 路径（示例全列） | gitignore 覆盖 | 建议 |
| --- | --- | --- | --- |
| 会话凭据 | backend/haikang_auth.json、backend/haikang_cookies.json、backend/haikang_auth_info.json | backend/.gitignore:46 `*.json` | **立即删除+轮换**，.dockerignore 补 `*.json` |
| HTTP 调试转储 | backend/noaa_response_*.html（约 300 个） | 根 :41 `*.html` | 删除 |
| 归档快照 | backend/app.zip、app (2).zip、app (3).zip、app3.zip…app8.zip、app 9.zip、config.zip、models.zip | 根 :136 `*.zip` | 删除（快照交 git 历史/制品库管） |
| 日志 | backend/install.log、test.log、test_output.log、server.log、server_new.log、server_final.log、server_debug.log、server_unified.log、expert_deliberation_uvicorn.log、android_gateway.stdout.log、android_gateway.stderr.log、frontend/frontend.log、frontend/vite-dev.log、frontend/vite-dev.err.log | 根 :32 `*.log`；frontend/.gitignore:29 | 删除 |
| 设备文件 | backend/nul、backend/app/nul、frontend/nul、backend/$null | 根 :43；backend/.gitignore:57-58,106-107 | 删除 |
| 一次性脚本 | backend/__tmp_test.py、__tmp_check.py、check_*.py（约 40 个）、test_*.py（约 40 个）、fix_*.py、analyze_*.py、search_*.py、find_*.py、debug_*.py、final_verification.py、run_batch_import.bat、run_sync_test.bat、test_sql_server_connection.py | 根 :95-109、:154-176 大部分覆盖；.bat 无规则 | 删除；.bat 若有价值移入 backend/scripts/ |
| 截图/调试图 | backend/error_screenshot.png、企业微信截图_17676192491931.png、auth_page.png、h5_error.png、before/after_*.png、ocx_status_check.png 等 | 根 :36 `*.png` | 删除 |
| 调试 JSON/HTML 数据 | backend/test_ekma_data.json、test_response_exact_web.json、carbon_test.json、test_create_task.json、haikang_js_files.json、js_analysis_result.json、deep_analysis_result.json、monitor_*.json、api_response_*.json、codex_zq_gz_no2_source_audit.json、tree_enhanced_*.json、chinese_test_results.txt、noaa_response_*.html | backend/.gitignore:46 `*.json`、根 :41 | 删除 |
| 运行时数据 | backend/data/station_info.json、backend/data/meteorology/gdas_*.json（约 30 个）、backend/data/jieba_env_dict.txt、backend/data/longterm_memory/task_solutions.jsonl | 根 :31,206 `data/`；backend :43 | jieba 词库若被代码依赖应移入 backend/config 并白名单，其余删除/迁移到 DATA_REGISTRY_DIR |
| .bak | backend/app/tools/query/get_vocs_data/tool.py.bak | 根 :62 `*.bak` | 删除 |
| 临时 HTML 测试页 | frontend/测试图表显示.html、frontend/chart.html、frontend/test_sse_parser.html | 根 :41 `*.html` | 删除或移入 frontend/tests/fixtures |
| 测试 fixture | backend/tests/api_response_full.json、backend/tests/test_particulate_api_responses.json | backend/.gitignore:46 `*.json`（**无反选，疑似未跟踪**） | 移入 tests/fixtures/ 并加 `!backend/tests/fixtures/**` 白名单 |
| 生成解析表 | backend/lextab.py、backend/yacctab.py | 无规则覆盖 | 确认用途；若为 PLY 生成物应忽略 |
| 已忽略大目录 | 参考/（根 :221）、Tesseract-OCR/（:201）、table-transformer-model/（:202）、obm-full-standalone/（:203）、backend/.venv6/（backend :32）、frontend/node_modules、frontend/dist（frontend/.gitignore:8）、suncere*/（:282）、deploy/nginx/templates-local/（:303）、迁移包/（:302） | 均已覆盖 | 无需动作（其被忽略状态本身合规） |
| 疑似漏网 | frontend/index.html（根 :41 `*.html` 无反选）、backend/restart_server.sh 之外的 backend/start.sh（根 :106 `backend/start*`）、backend/system_config.json（backend :46 `*.json`，被 .dockerignore:11 排除说明其为运行配置） | **规则上被忽略** | 前两者加白名单或停止使用；system_config.json 确认运行时生成则维持忽略 |

## 五、规范符合性核查表（AGENTS.md 部署条款）

| 条款 | 结论 | 证据 |
| --- | --- | --- |
| web/worker 必须成对启动 | **部分符合** | restart_server.sh 先 web 后 worker 一体重启（backend/restart_server.sh:157-196,198-292）；但江苏运维仅文档命令无脚本（deploy/nginx/README.md:211-220），start.sh 完全不启动 worker |
| setsid+nohup+独立日志+PID 文件 | **restart_server.sh 符合；start.sh 违反** | restart_server.sh:179-181（web：nohup setsid，/tmp/backend.log，PID /tmp/suyuan_backend.pid）、:288-290（worker 同规范）；start.sh:64-69 前台运行无任何脱离会话措施 |
| 启动后 ss -ltnp 验证监听（web+worker） | **部分符合** | web：ss+health 双验证（restart_server.sh:85-90,190）；worker systemd 路径有端口归属验证（:253-262）；worker nohup 兜底路径无验证（:272-292） |
| DATA_REGISTRY_DIR 显式绝对路径、web/worker 同值 | **部分符合** | preflight 强制显式+绝对（deployment_preflight.py:21-38）并接入 restart/start 脚本（restart_server.sh:19、start.sh:58）；但 .env.production.template 缺该键；「同值」仅靠共用 env 文件的纪律，preflight 无双文件比对 |
| 切换工作树前运行 deployment_preflight | **符合** | restart_server.sh:19、start.sh:58 自动执行；且有契约测试守护（backend/tests/auth/test_uvicorn_startup_contract.py:45 断言脚本内含 preflight 调用） |
| 禁止提交 backend/.env.*（模板除外）、frontend/dist-*、backend_data_registry*、suncere*/ | **符合（待验证）** | 根 .gitignore:272-277 `backend/.env.*`+三个模板反选、`frontend/dist-*/`、`backend/backend_data_registry*/`；:282 `suncere*/`；deploy/postgres/.env 与 backups/ 亦忽略（:278-279）。tracked 状态无法本机验证 |
| 前端构建产物含统一资源接口、无旧接口 | **符合** | CI frontend-build 执行三条 grep 并反向断言（.github/workflows/ci.yml:84-93）；deploy/nginx/README.md:19-21 同款命令 |
| 6.5G 机器 ≤3 web worker | **start.sh 违反** | start.sh:55 默认 `WORKERS=4`；restart_server.sh:177 默认 1；deploy/embedding/README.md:18 给出 6.5G 内存账 |

## 六、亮点

1. **restart_server.sh 工程质量高**：preflight 失败即中止保留旧服务（:17-21）；按进程组终止避免 multiprocessing 孤儿（:37-64）；cwd+cmdline 双校验，只清理本工作树进程、不误伤江苏 8001/8012（:25-35,116-127,168-173）；systemd 单元自动探测并记录了历史命名漂移的教训注释（:206-218）。
2. **部署配置进入测试金字塔**：backend/tests/deploy/test_nginx_contract.py 对 nginx 路由、host 网络、只读挂载、信任头清除做断言；tests/auth/test_uvicorn_startup_contract.py 锁定启动脚本必须调用 preflight——配置漂移有自动化防线。
3. **安全机制体系化**：CI gitleaks 全历史扫描（ci.yml:10-22）+ .gitleaks.toml 在位；SECURITY_HISTORY_REMEDIATION.md 给出完整的 filter-repo 处置 SOP 并明确「不得靠 allowlist 放行历史发现」（:33-35）；secrets 全局忽略（*.pem/*.key/*credentials*.json 等，根 .gitignore:284-299）。
4. **postgres compose 的密码纪律**：`POSTGRES_PASSWORD: ${LOCAL_PG_PASSWORD:?required}` 强制注入（deploy/postgres/docker-compose.local.yml:10），.env.example 仅 change-me 占位并注明禁止提交（deploy/postgres/.env.example:1,5）；backup.sh 凭据不落命令行。
5. **nginx 模板有解释性注释**：CSP 为何不能放 server 级（与后端 HTML 预览 CSP 叠加取交集会拦内联脚本）写成注释（default.conf.template:23-28），限流参数附业务依据（:6-9）。
6. **依赖约束自洽**：pyproject `>=3.11,<3.12`（pyproject.toml:5）与 environment.yml python=3.11、Dockerfile python:3.11-slim 三方一致；numpy==1.26.3 的 pin 附 nimfa 兼容原因（requirements.txt:20）。

## 七、修复优先级路线建议

1. **本周（P0/P1 安全收口）**：删除并轮换 haikang_* 三份凭据文件；确认历史重写已执行（filter-repo SOP 落地）；.dockerignore 补 `*.json`/`noaa_response_*`/`*.zip`/`*.log`/`tests/`；nginx 两个 social location 补 X-User-Id/X-Is-Admin 清除并扩展契约测试；qdrant/postgres 端口改绑 127.0.0.1，qdrant 启用 API key。
2. **两周内（P1 规范收口）**：处置 start.sh（废弃或改造为合规入口）；restart_server.sh worker 兜底路径补 ss 验证、统一 PID 文件名并与 README 对齐；补齐/入库 docker-compose.jiangsu-ops.yml 与脱敏 templates-local 模板；.env.production.template 补 DATA_REGISTRY_DIR；docs/ 改白名单式忽略并入库两份运维文档；`!frontend/index.html` 白名单（待验证后）。
3. **一个月内（P2 工程质量）**：backend 根 439 个杂物物理清理；合并 ops_audit 双命名测试并收敛 pytest testpaths；CI 增加 ruff job、分支触发放宽、pytest marker 分层；gitignore 重构（去 `D:tmp/`、docs/ 去重、收窄全局扩展名规则）；依赖锁补全（pip-tools/uv）；deployment_preflight 增加目录可写探测与双 env 比对模式；为 Redis 补部署物料。
