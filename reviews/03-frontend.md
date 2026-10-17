# 前端评审报告

- 评审对象：`frontend/`（Vue 3 + Vite + Pinia，FastAPI 后端的 SPA）
- 评审方式：只读静态代码评审（本会话无法运行 npm/构建/测试，所有结论基于静态阅读；不确定处标注「待验证」）
- 评审人：frontend-reviewer
- 证据格式：`文件路径:行号`

## 一、总体评价

前端整体工程质量中上：auth 层工厂化 + 依赖注入、run 归属/接流跟踪纯函数化、旧接口守卫测试、96 个单测 + 7 个 e2e，能看出有意识的架构治理。但存在 2 个必须立即处理的 P0：SM4 国密密钥硬编码入库且 IV=Key，技能文档渲染启用 `html:true` 且绕过统一 XSS 净化。其次是错误处理路径上的一个必现 ReferenceError、SSE 断线无自动重连、21 处重复且默认值不一致的 API base 解析，以及大量未接入任何 npm script 的「孤儿测试」。规模上 components 目录 178 个文件占 53%，reactStore.js（3253 行）、ChartPanel.vue（3222 行）等巨型文件亟待拆分。

## 二、规模概览

### 目录分布（src 共 336 个文件，其中测试文件 96 个 ≈ 28.6%）

| 目录 | 文件数 | 占比 | 说明 |
| --- | --- | --- | --- |
| src/components | 178 | 53% | 含 board/management/resources/reactAnalysis/queryDashboard/visualization 等子域 |
| src/services | 56 | 17% | API 封装与流/资源处理 |
| src/stores | 21 | 6% | Pinia store |
| src/auth | 20 | 6% | 认证/国密/HTTP/WS |
| src/api | 15 | 4% | 按域拆分的接口模块 |
| src/utils | 12 | 4% | |
| src/views | 11 | 3% | |
| src/config | 6 | 2% | agentModes/projectConfig 等 |
| src/composables | 6 | 2% | 仅 reactAnalysis 域 |
| src/router、styles、mock、根级 | 11 | 3% | mock 仅 1 个文件且为死代码 |

### 最大文件 Top10（行数为实测）

| # | 文件 | 行数 |
| --- | --- | --- |
| 1 | frontend/src/stores/reactStore.js | 3253 |
| 2 | frontend/src/components/visualization/ChartPanel.vue | 3222 |
| 3 | frontend/src/components/ReActMessageList.vue | 2943 |
| 4 | frontend/src/components/InputBox.vue | 2273 |
| 5 | frontend/src/components/management/ScheduledTasksPanel.vue | 1976 |
| 6 | frontend/src/views/KnowledgeBaseView.vue | 1743 |
| 7 | frontend/src/components/AssistantSidebar.vue | 1525 |
| 8 | frontend/src/components/visualization/TrajectoryMapPanel.vue | 984 |
| 9 | frontend/src/components/visualization/MapPanel.vue | 885 |
| 10 | frontend/src/components/reactAnalysis/MainLayout.vue | 882 |

紧随其后：ChatArea.vue 740、ReactAnalysisView.vue 736、MarkdownRenderer.vue 735、KnowledgeBasePanel.vue 731。App.vue 仅 63 行（「巨型 App.vue」疑点不成立，只有一段遗留 `.top-nav` 样式，见 P2-10）。

## 三、发现清单

### P0（安全 / 功能性错误）

- [P0] **SM4 密钥硬编码入库且 IV=Key** — frontend/src/auth/SM4.js:4-8 — `SECRET_KEY = 'GJwsXX_BzW=gJWJW'` 明文写死并打进 bundle，且 `iv: SECRET_KEY` 与密钥相同（密码学上明确禁止）；companyCrypto.js:34-39 的请求签名 `sign()` 直接用该密钥加密摘要，任何拿到 bundle 的人都能伪造合法 `Sign` 头，签名机制形同虚设 → 密钥改为部署时注入（后端下发会话密钥或至少环境变量注入，不入 git）；IV 必须独立；重新评估「前端 SM4 加密密码」的威胁模型（SM2 公钥加密已足够，见 companyCrypto.js:28-32 的 encryptType 分支）。
- [P0] **技能文档渲染存储型 XSS** — frontend/src/views/SkillsManagementView.vue:137-141 — markdown-it 实例配置 `html: true`，:321-328 `renderMarkdown()` 输出未过 `sanitizeRichHtml` 且渲染失败时 `'<pre>' + content + '</pre>'` 直接拼接原始内容，:111 `v-html` 渲染技能正文 → 违反 frontend/src/utils/sanitize.js:6「所有进 v-html 的 markdown/LLM 输出必须先过本函数」的约定；技能内容可经管理界面编辑（存储型注入面）。对照：MarkdownRenderer.vue:310 已正确净化，ScheduledTasksPanel.vue:743 与 ModeMemoryDialog.vue:83 的 md 实例为默认 `html:false`，均安全 → 该文件 md 实例改 `html:false`，或输出统一过 `sanitizeRichHtml`；fallback 改用纯文本转义。

### P1（健壮性 / 规范）

- [P1] **post() 错误路径必抛 ReferenceError** — frontend/src/services/api.js:54-60 — `errorJson` 在内层 try 块中用 `const` 声明，:60 `error.response = { data: errorJson }` 在块外引用；任何非 2xx 的 POST 都会抛 `errorJson is not defined`，后端 `detail/message` 错误详情全部丢失，调用方拿到误导性报错 → 把 `let errorJson = null` 提到内层 try 之外并判空。
- [P1] **API base URL 21 处重复解析且默认值分裂** — frontend/src/services/reactApi.js:8、frontend/src/api/session.js:6 等约 18 处为 `VITE_API_BASE_URL || '/api'`，而 frontend/src/auth/http.js:10、frontend/src/auth/runtimeConfig.js:2、frontend/src/auth/websocket.js:5 为 `|| '/api/suyuan'` — 环境变量缺失时 agent 主链路与认证链路会走不同前缀（vite 代理恰能兜住 `/api` 与 `/api/suyuan` 两种，但 standalone 模式下这是隐患）→ 抽出单一 `src/config/apiBase.js`，全量替换。
- [P1] **agent SSE 断线无自动重连** — frontend/src/services/reactApi.js:161-195 — `_readSseStream` 读到 done/异常即结束，无 retry/backoff；frontend/src/stores/reactStore.js:3117-3155 `reattachActiveRun` 为一次性接流，断流后仅设置 `sessionState.error = '未接收到运行中任务的进度…'` 要求用户手动重开会话（:3146-3152）→ 至少对流丢失场景实现指数退避自动重接（服务端已有 detached-run 镜像与 `stream_lost` 传输事件，基础设施齐备）。
- [P1] **WS 重连定时器无法被取消** — frontend/src/stores/scheduledTasks.js:339-348 — `onclose` 里 `setTimeout(() => this.connectWebSocket(), 5000)`，而 :298 `connectWebSocket()` 无条件 `wsReconnectEnabled = true`；`disconnectWebSocket()`（:352-360）后，挂起的 5 秒定时器仍会把重连开关重新打开并悄悄重连 → 定时器句柄入 store，disconnect 时 clearTimeout，且 connect 入口尊重 disabled 状态。
- [P1] **约 25 个测试文件未接入任何 npm script，无统一 test/lint 入口** — frontend/package.json:11-18 — 8 个 `test:*` 脚本仅覆盖部分文件；未覆盖示例：src/stores/react-store-graph-mode.test.mjs、src/stores/react-store-query-dashboard.test.mjs、src/components/management/knowledge-base/*.test.mjs（5 个）、src/components/board/*.test.js（4 个）、src/components/reactAnalysis/{messageProcessGrouping,executionTrajectory,modelTrajectory}.test.js、src/utils/{amapConfig,echartsOptionSanitizer,echartsBottomSpace}.test.mjs/js、src/api/knowledgeBaseGraph.test.mjs、src/components/queryDashboard/query-dashboard-input-message-contract.test.mjs、src/services/{workflowApi,inlineChartImages,inlineChartBlocks,markdownBracketMath,fileManagerDownload,resourceRendererRegistry,vitePreloadRecovery}.test.js；且无 `npm test` 聚合命令、无 eslint 配置（frontend/.eslintrc*、eslint.config.* 均不存在，devDependencies 亦无 eslint）→ 增加聚合 `test` script（node --test 全量 glob）并接入 CI；引入 eslint+plugin:vue。
- [P1] **SSE 数据清洗可能污染正文内容** — frontend/src/services/reactApi.js:17-23,183 — `sanitizeJSONString` 对整行 JSON 全局把 `NaN/Infinity/-Infinity` 替换为 `null`，若助手正文或工具结果字符串本身含这些词，展示内容会被改写为 "null" → 只在 `JSON.parse` 失败时降级尝试清洗，或改用支持 JSON5/宽松数值的解析策略，避免对成功路径做全文替换。

### P2（可维护性）

- [P2] **store 反向依赖组件层** — frontend/src/stores/reactStore.js:24-30,41-59 — store 直接 import `@/components/board/*`（drawioBoardBridge、boardSendPreparation、boardVersionHistory）与 `components/queryDashboard/mapProgramMerge`，分层倒置 → 把 board 协议逻辑下沉到 services/ 或 stores/board 域模块。
- [P2] **巨型文件需拆分** — frontend/src/stores/reactStore.js（3253 行，单 store 承载 10+ 模式状态机）、frontend/src/components/visualization/ChartPanel.vue（3222 行）、frontend/src/components/ReActMessageList.vue（2943 行）、frontend/src/components/InputBox.vue（2273 行）→ reactStore 已有 queue/steering/runReattach 等拆分先例，继续按「模式/事件处理/持久化」切分；ChartPanel 与 InputBox 按面板、上传、语音、草稿等子组件拆。
- [P2] **两套 HTTP 栈并存** — frontend/src/auth/http.js:79,82 — `authFetch`（fetch）为主，`authAxios`（axios）仅 3 个 social 组件使用（frontend/src/views/SocialAccountsView.vue:121、frontend/src/components/social/CreateAccountModal.vue:54、QRCodeModal.vue:39）→ social 组件迁 authFetch 后可移除 axios 依赖与响应拦截器。
- [P2] **两套国密库并存** — frontend/src/auth/SM2.js:1 用 `sm-crypto`，frontend/src/auth/SM4.js:1 用 `gm-crypt` → sm-crypto 自带 sm4，统一后删除 gm-crypt。
- [P2] **SSE 解析逻辑重复实现** — frontend/src/services/api.js:160-195 与 frontend/src/services/reactApi.js:161-195 几乎相同的 `data: ` 行解析循环（且两者结束时都未调 `decoder.decode()` 冲刷尾部多字节字符）→ 抽公共 readSseStream 工具；顺带补 flush。
- [P2] **API 调用散落在组件/composable，未收口到 api/ 层** — frontend/src/components/AssistantSidebar.vue:799（`/api/sessions?limit=`）、frontend/src/composables/reactAnalysis/useSessionManagement.js:486、frontend/src/composables/reactAnalysis/useDataFetcher.js:29-121、frontend/src/components/FileManagerPanel.vue:119、frontend/src/components/ReActMessageList.vue:1460 → 收口到 src/api/。
- [P2] **错误提取风格不统一** — frontend/src/services/api.js:30 只抛 status；frontend/src/api/session.js:29-32 抛原始 errorText；frontend/src/services/reactApi.js:214-215 抛 status；frontend/src/services/uploadApi.js:37-62 解析 detail — 建议统一 `extractApiError(response)`。
- [P2] **生产代码残留调试日志** — frontend/src/services/uploadApi.js:26-45（逐条 console.log 含 sessionId）、frontend/src/stores/scheduledTasks.js:316（打印整条 WS message）、frontend/src/services/api.js:199 等 → 接入按级别开关的 logger。
- [P2] **死代码/畸形文件** — frontend/src/mock/mapTestData.js 全仓无引用（grep `mock/|mapTestData` 零命中）；frontend/src/views/DemoShowcase.vue 未被 router/index.js 或任何组件引用；frontend/src/components/MarkdownRenderer.vue.test 是 3 行模板片段的畸形扩展名文件，node --test 不会执行 → 删除或改为正式 .test.mjs。
- [P2] **App.vue 遗留样式与路由不匹配** — frontend/src/App.vue:11-57 — `.top-nav` 系列样式对应的导航结构已不存在（模板仅 router-view）→ 删除遗留样式。
- [P2] **store 内使用阻塞式 confirm()** — frontend/src/stores/reactStore.js:3204 → 改为视图层确认弹窗，store 只暴露意图方法。
- [P2] **内网地址硬编码为 vite 代理默认值** — frontend/vite.config.js:43 — `target: env.VITE_AUTH_PROXY_TARGET || 'http://10.10.204.80:8025'`（dev-only，但内网拓扑随仓库扩散）→ 默认值改为 localhost 占位，真实地址走本地 .env.local。
- [P2] **高德 Key 入 .env.local** — frontend/.env.local:2 — `VITE_AMAP_KEY=337d…` 为浏览器端 key，本身会被打包公开，风险在于额度盗刷；frontend/.gitignore:13 已忽略 `.env.local`（是否曾被提交进历史待验证：`git log --all -- frontend/.env.local`）→ 确认在高德控制台配置域名白名单 + 配额告警；utils/amapConfig.js:3-28 已支持从 `/api/config` 下发 key，建议生产一律走后端下发。
- [P2] **package.json 构建入口与规范冲突** — frontend/package.json:7-9 — `build` 与 `build:standalone` 完全相同，另有 `build:gateway`（production 模式），与 AGENTS.md「唯一命令 build:standalone、禁止第二套 bundle」存在擦边 → 保留 build:standalone，删除或改名别名并注释说明；同时补 `engines` 字段。
- [P2] **websocket ticket 走 URL query** — frontend/src/auth/websocket.js:21 — `?ticket=` 会进 nginx/网关访问日志；票据为一次性（每次重连重新取票，scheduledTasks.js:345 有注释），风险可控 → 可改 `Sec-WebSocket-Protocol` 或首帧消息传票，并在网关对该路径关闭 query 日志。
- [P2] **token/用户信息存 localStorage** — frontend/src/auth/storage.js:25-32 — XSS 场景下可被窃取（当前 P0 XSS 修复后风险下降）；http.js:65-68 的 401 处理已做「延迟响应不误杀新会话」的令牌比对，属合理权衡 → 保持与 P0 XSS 修复联动，考虑 token 内存化 + refresh 机制（远期）。
- [P2] **markdown-it 实例 4 处重复配置** — frontend/src/components/MarkdownRenderer.vue:17-19、SkillsManagementView.vue:130-143、management/ScheduledTasksPanel.vue:534,743、reactAnalysis/dialogs/ModeMemoryDialog.vue:67,83 → 统一封装 createMarkdownRenderer()（P0 XSS 即此类不一致的产物）。
- [P2] **SVG 允许上传** — frontend/src/services/uploadApi.js:124 — `image/svg+xml` 在图片白名单内，SVG 可携带脚本；当前渲染若走 `<img>`/blob 通道是安全的（SharedConversationsPanel.vue:278-279 注释表明走 authFetch blob），但预览路径多样，待验证 → 明确禁止 SVG 或保证全部经 `<img>` 沙箱渲染。
- [P2] **任务面板事件风暴无去抖** — frontend/src/stores/scheduledTasks.js:313-331 — 每条 WS task_* 事件都 `fetchTasks()+fetchStats()` 全量刷新 → 加 300ms 合并去抖。

## 四、旧接口清理核查（/office-documents、/visualizations）

| 检查项 | 范围 | 结果 |
| --- | --- | --- |
| `/office-documents` | frontend/src | 仅 frontend/src/services/noLegacyResourceMechanisms.test.js:12 出现 — 该文件是**架构守卫测试**，断言这些旧路径不被任何模块引用，属预期存在 |
| `/visualizations` | frontend/src | 同上，仅守卫测试引用 |
| `/office-documents` | frontend/dist（含 assets） | **0 匹配** ✅ |
| `/visualizations` | frontend/dist（含 assets） | **0 匹配** ✅ |
| 统一资源接口 `resources?presentation_type=document` | frontend/dist/assets | 在 dist/assets/main-BXdc64wW.js 命中 ✅ |

结论：AGENTS.md 规定的三项构建产物验证全部通过；src 侧旧接口仅存于守卫测试，无业务残留。补充：dist/assets 下无 .map 文件（无源码泄漏），dist 同时含 index.html 与 chart.html，与 vite.config.js:18 的双入口一致；dist 与当前 src 的版本新旧一致性静态无法确认（待验证：重新构建比对 hash）。

## 五、亮点

1. **auth 层高度可测试**：createAuthFetch/createAuthApi/createCompanyCrypto/createAuthSession 全部工厂 + 依赖注入（frontend/src/auth/http.js:30、authApi.js:13、authStore.js:7），auth 目录 9 个 .test.mjs 全覆盖；http.js:49-51 禁止未声明的外部绝对 URL、:65-68 用令牌比对防止延迟 401 误登出新会话，都是成熟细节。
2. **开放重定向防护与 WS 票据**：routerGuard.js:1-7 `safeRedirect` 拦截 `//`、`/\` 开头的外站跳转；websocket.js:16-21 一次性 ticket 换取 WS 连接。
3. **运行归属/接流跟踪纯函数化**：reactStoreRunOwnership.js（16 行）与 reactStoreRunReattach.js（40 行）把「乱序/异 run 事件丢弃」「stream_lost 判定」抽成可单测纯函数，reactStore.js:1597 接入。
4. **架构守卫测试**：noLegacyResourceMechanisms.test.js 防旧资源接口复活；default-mode.check.mjs、session-history-behavior.check.mjs 用源码断言锁定关键行为（含跨栈核对 backend/app/api/session_routes.py 的 limit=200）。
5. **测试文化**：96 个 node:test 单测（≈28.6% 文件）+ 7 个 Playwright e2e（frontend/e2e/），覆盖流处理、队列、steering、资源渲染等核心链路。
6. **多项目构建配置严谨**：scripts/projectManifest.mjs:113-176 对 project.yaml 做 schema/枚举/去重/依赖闭合校验，vite.config.js:16 以 `VITE_BUILD_OUT_DIR` 隔离各项目产物目录。
7. **SVG 图标静态化**：v-html 仅用于本地常量 SVG（AssistantSidebar.vue:26 等），无外部输入进入这些点。

## 六、修复优先级路线建议

1. **立即（本周，安全）**：修复 SkillsManagementView XSS（html:false 或接 sanitizeRichHtml）；SM4 密钥治理（移出入库、IV 独立、评估去留）；确认 .env.local 从未被提交、高德 key 配置域名白名单。
2. **本迭代（正确性/规范）**：修 api.js:60 errorJson ReferenceError；修 scheduledTasks WS 重连竞态；新建 src/config/apiBase.js 统一 21 处 base URL；package.json 增加聚合 `test`/`lint` script 并把约 25 个孤儿测试接入。
3. **下一迭代（健壮性）**：reactApi 增加 stream_lost 自动重接（退避+上限）；合并 api.js/reactApi.js 两套 SSE 解析并补 decoder flush；收敛双 HTTP 栈（social 迁 authFetch）与双国密库（统一 sm-crypto）；统一 extractApiError。
4. **持续重构**：reactStore.js 按模式域继续拆分、ChartPanel/InputBox/ReActMessageList 组件化拆分；API 调用收口 api/ 层；清理 mock/mapTestData.js、DemoShowcase.vue、MarkdownRenderer.vue.test、frontend/nul、test_sse_parser.html、测试图表显示.html（.gitignore 增加 `nul` 与根级测试 HTML 规则）；vite.config.js 内网代理默认值改占位。
