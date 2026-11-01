# dsh-superagent-prototype 借鉴笔记与重构建议

来源：DeepSeek《Super-agent 设计探索：迈向更自主的 Agent 系统》（mp.weixin.qq.com/s/zoS7GlReWPhfCjENGxXCdg）
与其开源原型 github.com/deepseek-ai/dsh-superagent-prototype（TypeScript，单进程，SQLite；研究代码，非产品）。
本笔记对照本仓库现状，给出可借鉴设计与落地顺序。原文与原型的差异以仓库 docs/000–008 为准。

## 一、原型机制速览

数据流：Source（飞书/GitHub）→ Trigger（幂等事件）→ Eval（确定性 gate + LLM assessment，admission 表控制强度）→
Ticket（授权工作单元，携带不可变 Mandate）→ Assignment（派工，worker slot）→ Executor Session（一票一会话一目录）→
Report（progress/waiting/ready/blocked/failed/dropped）→ Channel（Outbox 回执投递）。

| 机制 | 实现 | 要点 |
| --- | --- | --- |
| Engine 单写者 | `src/core/engine.ts` | 五个 part（Intake/Evals/Tickets/Assignments/Replies）单向依赖；按调用角色暴露 `EngineForSources` 等 Pick 接口；每命令一个事务 |
| Effects 持久副作用队列 | `src/app/effects.ts` | kind+key 唯一、入队随事务提交后才执行、`Later` 不计失败、指数退避、连续 3 次失败报健康 |
| Outbox 回执 | `src/app/outbox.ts` | 同 Ticket 同会话消息按序投递；前一条连败 3 次才阻塞；dropped 记录原因码（channelGone/channelIgnored）；幂等 id 防重发 |
| Passes 泵 | `src/app/passes.ts` | 每 2 秒 + 到货即泵一次；并发调用合并为一次跟进 pass |
| Subscription 直通 | `src/core/tickets.ts` | 订阅 Thread 的消息绕过 gate 直接扇出到 Ticket；follow-up 由执行侧先裁决，超出范围才 handback 回 Eval |
| Policy/Mandate | `src/policy.ts` | 授权 = 规则版本 + 来源白名单 + admission 表；Mandate 记录 policy_version 与命中规则；恢复前再校验，收紧策略只影响恢复不撤销在途 |
| Ticket 阶段表 | `src/core/stage.ts` | person/*（delivery、answer、review、blocked、failed）与 working/*（queued、working）、idle 全部由存储事实推导（`waitsForPerson` 谓词），不另存状态字段 |
| Reasons 代码化 | `src/core/reasons.ts` | 一切"为什么"（决定、过滤、失败、跳过）= code+values 结构化记录，UI 层本地化 |
| HealthBoard | `src/infra/health.ts` | 每组件一个健康 entry，仅写入者可 claim；拒绝重复声明 |
| noWait 纪律 | `src/app/sessions.ts` | 主（路由）Session 拒绝 sleep、前台命令 >30s、job 等待 >5s；一切结果靠到货消息，阻塞步骤只会延迟新候选 |
| 评估上下文形状 | `prompts/admission.md` | Trigger ≤4000 字、相关 Ticket ≤8、Thread 窗口前后各 5 条（邻接两条 ≤1200 字、其余 ≤400 字、stub 可按 id 展开） |

文章补充结论（原型未全部实现）：事件拥塞时批处理评估摊薄成本（40 条/分钟时单决定 1.6s）；直通机制省 Router 决定量 30%、读缓存 token 37%。

## 二、现状对照：suyuan 已有的同构物

suyuan 不缺零件，缺的是语义收敛。三套 Trigger/Effect/Outbox 等价物并存、互不相通：

| 原型概念 | suyuan 现状 | 位置 | 差距 |
| --- | --- | --- | --- |
| Trigger | TaskEvent 事件目录；assistant_triggers | `scheduled_tasks/event_catalog.py`、`social/assistant_followup_models.py` | 无全局幂等去重与处置（disposition）审计；fetcher 重发/重启重放无防线 |
| Effects 队列 | WorkflowJobStore（Redis lease）；assistant_outbox；KnowledgeIndexOutbox | `agent/workflow/jobs.py`、`social/`、`knowledge_base/index_outbox.py` | 三套并存： lease 语义/退避/健康上报各写一遍 |
| Outbox 回执 | assistant_outbox；EventTaskDelivery | `social/`、`scheduled_tasks/event_delivery.py` | 无按会话顺序、无 dropped 原因码、无幂等回执 |
| Eval/gate | 无 | — | 告警事件直接触发执行，没有"该不该做"的评估层 |
| Mandate | 定时任务自定义工具集授权 | `scheduled_tasks/executor/task_executor.py` | 无版本化、无恢复前再校验 |
| Subscription | 无（事件按 project/type 定向投递） | `scheduled_tasks/service.py` | 事件不能路由到活跃会话/工作流，无直通 |
| 直通 | steer 已有跨进程通道 | `agent/runtime/steering.py`、RedisCancellationStateStore | 只服务"人打断模型"，未接事件源 |
| Ticket | TaskExecution、assistant_tasks、workflow 节点三套生命周期 | 各域 | 状态各自维护，无统一阶段表/谓词 |
| Router/Worker | 模式体系 + call_sub_agent/run_agent_workflow detached | `agent/`、`tools/agent_tools/` | 对话仍在 web 进程内联（detached 也只是进程内 task） |
| Watchdog | loop_watchdog、stall_watch、quota_resume、ErrorClassifier 重试、模型熔断 | `lifecycle/`、`agent/workflow/` | 已相当完整，缺的是结构化健康汇总出口 |
| 上下文预算 | test_agent_mode_context_budget.py 守门 | `backend/tests/` | 与原型 model-surface 测试同一思路，保持 |

## 三、可借鉴设计

### P0：小改动、立即收益（约 1–2 周）

1. **统一 Effects 领域层**。以 assistant_outbox 的表结构为种子，提升为通用 `domain_effects`
   （kind、key 唯一、payload、available_at、attempts、last_error），kind/key 相同的等待行合并（新 payload 立即到期不改队序）；
   `Later` 异常延迟不计失败；指数退避；同 kind 连续 3 次失败进健康汇总。
   改造点：`event_delivery.py`、`workflow/jobs.py` 入队侧、报告发布与 IM 推送统一走它。
   多进程适配：用 PG `SKIP LOCKED` 认领，或复用 WorkflowJobStore 的 Redis lease 模式（`session_advisory_lock.py` 已有 PG 锁先例）。
2. **Outbox 回执语义**。同会话按序（前一条连败 3 次才阻塞后一条）、发送幂等 id、dropped 带原因码
   （会话失效/渠道关闭/来源不再监听），撤回不重投。落点：`event_delivery.py`、`channels/` 发送侧。
3. **Reasons 代码化**。仿 `src/core/reasons.ts`：定时任务结果、事件处置、workflow node_errors 的错误信息
   统一为 code+values，展示层本地化。现在到处是自由文本 error，前端无法分类、监控无法聚合计数。
4. **HealthBoard 式健康汇总**。升级 `lifecycle/loop_watchdog.py`（log-only）为结构化 entry：
   effects 各 kind、workflow 队列、fetcher 轮询、嵌入服务各一个 entry，仅写入者可声明，`/internal/health` 汇总。
5. **一次写入者 + 角色化接口**。服务层按调用角色收窄接口（如 worker 侧只读事件、web 侧只入队），
   依赖单向化。工具层已有 mode 白名单，此条管服务层。

### P1：事件驱动语义层（约 2–4 周）

6. **Subscription 扇出 + 事件直通**。TaskEvent 增加 thread_key（如 `station:{code}`、`chat:{id}`、`workflow:{id}`），
   新增 thread_subscriptions；活跃会话/工作流订阅后，事件到达直接经 steer 通道投递（复用
   `agent/runtime/steering.py`，把触发方从"人"扩到"事件"），无活跃对象才落评估/通知。
   这是文章"订阅直通"的 suyuan 版，且省掉无活跃对象时的模型开销。
7. **Gate + admission 表 + observe 模式**。对告警类事件（如 `xuchang.station_deviation.alert_created`）加两级过滤：
   程序快路径（阈值、指纹去重、静默窗）→ LLM 慢路径评估（该不该分析、命中哪条规则）。
   accept_mode = off / observe / auto：observe 只记录"本会接受"的 Decision，观察两周质量后再开 auto。
   Mandate 记录 policy_version 与命中规则，任务恢复前按当前策略再校验（收紧不撤销在途）。
8. **Trigger 幂等 + Disposition 审计**。事件入库一次（source+external_id 唯一），处置去向
   （filtered/evaluated/fanned_out/acknowledged/attached）全量落表，评估超时重排两次后记 unavailable。
   现有 `storage/event_claim_storage.py` 只管执行认领，补齐接收侧审计。
9. **统一阶段表与 waitsForPerson 谓词**。TaskExecution/assistant_tasks/workflow 节点的"是否卡在人"统一由
   存储事实推导（最近 Report 类型 + 之后是否有人消息），不另存易漂移的状态字段；前端展示按阶段表归并。

### P2：结构性重构（按需立项）

10. **对话入 worker（存算分离）**。detached runs（`api/agent.py:1649` 起，RunEventStream + Last-Event-ID 回放）
    已把事件流和执行解耦，差最后一步：detached run 可选移交 worker 进程执行（复用 WorkflowJobStore lease），
    web 只做 SSE 回放。bge-m3 已独立成服务，worker 不再受内存约束，条件已具备。
    收益：web 滚动重启不断对话；跨机扩展成为可能。
11. **Intake 中间件（轻量 Router）**。把 `analyze_stream` 的模式/技能/工具解析、归属检查抽为同步、无模型的
    Intake 层；多事件并发时启用轻量 triage 模型做批处理评估（原型压测：40 条/分钟时单决定 1.6s）。
    不建议拆独立 Router 进程，web 3 worker 内做即可。
12. **运行工作区隔离**。对执行脚本/报告类节点增加 per-run 工作区（`DATA_REGISTRY_DIR/jobs/{run_id}/`），
    失败重试携带 recovery note 语义（检查已有产物、避免重复外部动作），衔接 resource_handoff/result_cache。
13. **IM 渠道 Source 化**。`channels/qq.py`、`weixin.py` 改造为 SourceKind 式插件接口
    （身份、配置 schema、读位点、健康、channel 发送），按群/按人 admission 表控制谁能交办，
    为"群里 @ 助手 → 触发任务"打底。顺带处理 `channels/manager.py:161` 懒导入不存在模块 `app.channels.dingtalk` 的隐患。

## 四、不建议照搬

- SQLite 单进程 + 目录锁：suyuan 是多进程（web×3 + worker）多机形态，PG/Redis 是正确选择；只继承"每类状态一个写入者"。
- noWait 极限纪律（5 秒切后台）：suyuan 交互用户在等 SSE，不适用；只约束后台/子 agent 路径。
- GitHub PR 结尾、auto-merge、目录即仓库等代码协作领域规则。
- 评估上下文具体形状：须按 `test_agent_mode_context_budget.py` 的 schema 预算重做，不能超 PER_TOOL_SCHEMA_CAPS。

## 五、落地顺序与守门

1. 第 1 周：Reasons 代码化 + HealthBoard + 每类状态"一次写入者"表格写进 backend/docs（零风险，纯规范）。
2. 第 2–3 周：统一 Effects/Outbox，迁移 assistant_outbox 与 event_delivery；测试仿 `tests/effects.spec.ts` 的
   合并/退避/健康三件套。
3. 第 4–5 周：Subscription + thread_key + 事件直通（steer 通道复用）；并发测试仿 `runtime-concurrency.spec.ts`。
4. 第 6 周起：Gate/observe 试点，选 station_deviation 告警一条链路，observe 两周评 Decision 质量。
5. 之后：对话入 worker、IM Source 化按业务需求立项。

与既有 assistant 五阶段计划（assistant-tasks → reminders → analysis → coaching → web）的关系：
unified-schedule 的 trigger/run/outbox 正是本提案 P0 的种子；五阶段完成后顺势进入事件驱动 super-agent 形态，
不需要另起炉灶。
