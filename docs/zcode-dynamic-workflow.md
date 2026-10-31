# ZCode 动态工作流（dynamic workflow）源码导读

> 考察对象：[zai-org/ZCode](https://github.com/zai-org/ZCode) `main` 分支（v3.14.3），Agent CLI 源码位于 `apps/zcode-cli/`。本文基于源码（非压缩产物），文件引用均可直接定位。
>
> **对前一篇文档的修正**：[zcode-orchestration-architecture.md](zcode-orchestration-architecture.md) 基于 3.11.2 桌面版压缩包得出"ZCode 没有显式 DAG 引擎"。经源码核实，**该结论只对旧版本成立**——本机已验证 3.11.2 包内无任何 `CreateWorkflow`/`dynamic-workflow` 痕迹（grep 零命中），而当前源码包含一套完整的动态工作流引擎（约 2.7 万行），其依赖图不叫 "DAG" 而叫 **site graph / causality graph / actor graph**，这正是之前按 "DAG" 关键词检索漏掉它的原因。

## 一、总览：ZCode 有两套工作流系统

| | Legacy Expert Workflow | Dynamic Workflow（本文重点） |
|---|---|---|
| 代码 | `apps/zcode-cli/packages/core/src/workflow/`（约 4.7k 行） | `apps/zcode-cli/packages/dynamic-workflow` + `dynamic-workflow-runtime`（约 2.7 万行） |
| 形态 | 固定 8 阶段管线的"长任务"工作流（NL→Code） | **模型编写的 TypeScript 脚本**，任意拓扑 |
| 触发 | `/expert` 命令 | 用户显式要求 workflow → `CreateWorkflow` 工具 |
| DAG 来源 | `arch_decompose` 阶段产出"实现+验证节点的依赖图"，`exec` 阶段按图执行（`scheduled_graph`） | **编译期静态分析脚本数据流恢复依赖图** |
| 状态 | 两系统并存；SKILL.md 明确"legacy `Workflow` 工具和 `/expert` 是共享同一个词的另一个旧功能" | 当前主推 |

## 二、Dynamic Workflow 是什么

一句话：**把工作流写成一段带类型标注的 TypeScript 编排脚本，ZCode 编译它、静态分析出依赖图给用户确认，然后在沙箱子进程里确定性执行，产物与中间结果全程可重放、可修订、可缓存复用。**

```ts
// 脚本示例（节选自官方 SKILL.md）：评审改动文件，每个发现独立确认
phase("逐个评审改动的文件并确认发现");
const confirmed = (
  await Promise.all(
    paths.map(async (p) => {
      const review = await agent(`reviewer-${p}`).ask<Review>(`Review ${p}`);
      return Promise.all(
        review.findings.map((f, i) =>
          agent(`confirmer-${p}-${i}`).ask<Confirmation>(`Reproduce: ${JSON.stringify(f)}`),
        ),
      );
    }),
  )
).flat();
```

四件套工具：`CreateWorkflow`（编译 + 用户确认 + 后台启动）、`AmendWorkflow`（修订运行中/已结束的 run，缓存导入）、`SaveWorkflow`（存为项目可复用工作流，带参数声明）、`EvalWorkflowSnippet`（同步试跑脚本片段，不落盘）。四个工具都拒绝在未加载 `dynamic-workflows` 技能的情况下执行——该技能（`bundled-skills/skills/dynamic-workflows/SKILL.md`，约 1500 行）是完整的编写契约。

## 三、DAG 从哪来：静态分析引擎

这是该设计最核心的决策：**拓扑不写成数据，而是从普通代码的数据流里恢复**。SKILL.md 原话："The harness recovers the dependency graph by reading your code before it runs."

`packages/dynamic-workflow/src/analysis/`（约 1.24 万行）实现了对脚本 TS AST 的抽象解释：

- **site graph**（规范图）：每个 `ask`/`world.run`/世界读是一个"站点"，journal、执行序号、运行期标记全部以站点为键；
- **causality graph**：因果图带三条车道（`WORKSPACE_LANE` 工作区写入、`UNKNOWN_LANE`、`SINK_ID`），节点带 `Certainty`，边是顺序边（order edges），并打上 `Phase/Region/Step` 三层坐标——phase 是用户看到的阶段（脚本里 `phase("...")` 标记声明），loop 回边让循环体聚成一个节点；
- **actor graph**：呈现级投影——**actor 为节点、ask 消息为边**（`actor-graph.ts`），附带 fan-out 基数（`fanout-cardinality.ts`）；`mermaid.ts` 把图渲染成确认对话框里的流程图（所以用户批准的是一个 phase 图，而不是三十张步骤卡）；
- **facade-misuse**：静态拒绝误用（循环内字面重名 actor、运行期拼装 artifact id 等）。

分析器与编译器共享一套诊断（`analyze.ts`：`ok` 表示可提交，任何 diagnostic 都会挡下提交）。可分析性是编写义务："Node 结果流经普通变量、模板插值、解构和小助手函数都会被精确追踪；把结果塞进容器再捞出来，换来的是可分析性诊断。"

## 四、执行模型：确定性状态机 + 沙箱子进程

### 4.1 编译与 lowering

`compiler/compile.ts` 把脚本包进 `async function __workflowScript__()` 后用 TypeScript 真编译检查（facade 的 `dts.ts` 提供环境声明）。一个有意思的工程决策：`strict` 开但 **`noUncheckedIndexedAccess` 刻意关掉**——注释写明"模型写的 TS 都默认这个标志是关的，开着它 TS2532/TS18048 占了本地运行 96% 的 undefined 类编译失败"。禁用 `Date.now`/`Math.random`/`fetch`/`fs` 也是编译期检查——可重放性的前提。`lowering/` 把通过编译的脚本降为可执行函数体。

### 4.2 沙箱与桥接

`dynamic-workflow-runtime/harness.ts`（文件头有完整的中文时序图）：降级后的脚本写进 `<cwd>/.zcode/workflow-runs/<runId>.mjs`，**spawn 一个 node 子进程**执行；子进程内的 `__host.*` 调用经 stdio 上的 **NDJSON 线协议**桥回父进程的引擎（`create-actor` 即发即忘、`request ask/world-read/publish-artifact` 需应答、`event log/report` 单向）。该包刻意只依赖 `@zcode/dynamic-workflow` 和 node 内建，"证明整条管线 app-free 可跑"。

### 4.3 引擎：journal 决定一切的确定性状态机

`engine/engine.ts`（文件头自述）：

- **核心不做任何 I/O、不读时钟、不用随机数**。随时间变化的决策要么进 journal，要么被"站点 id × 每站点执行序号"（`ask#3@n`）+ 每 actor FIFO 的 `actorSeq` 固定——**首次执行与 replay 逐字一致**；
- 每次 host 调用先查 journal 的 `(siteId, ordinal)`：命中即短路（不产生真实调用），并防御性校验 `inputHash`，不一致整个 run 大声失败（绝不静默偏移）；
- 并发由运行时决定（脚本里的 `max_concurrency` 只是用户主动设的上限），引擎暴露 `setMaxConcurrency` 活体控制面；
- 结算三态：`completed`（脚本 return）/ `errored`（脚本自身失败，不可恢复，改脚本走 Amend）/ `stopped`（可 `ResumeWorkflowRun` 原样恢复；stop reason：user/model/interrupted/provider/superseded）。模型侧错误（限流、过载、网络）在 run 内部无上限重试，脚本永远看不见。

### 4.4 修订与缓存导入（AmendWorkflow）

任何 run（哪怕运行中）都可被修订取代：编辑 run 的脚本文件 → `AmendWorkflow` → 停旧起新，**按命名 actor 沿其 ask 序列逐条匹配导入旧 run 的已完成工作，字节一致即命中缓存（零 token）**，直到修订后第一个"活写"（子 agent 写工作区或 `world.run` 真执行）为止——此后缓存全部失效，保证 gate 命令测的是新代码真正产出。旧 run 标记 `superseded`。配套的编写纪律：可调参数放脚本控制流（改它免费），别插值进 ask 文本（改它等于缓存清零）。

## 五、脚本面（facade）速览

| 设施 | 语义 |
|---|---|
| `agent(name?, persona?)` | 创建 actor：新上下文、名字即身份（run 内唯一，重复整个 run 失败）、persona 创建时冻结；同 actor 的并发 ask 排 FIFO（共享上下文 = 串行 = 标定一致） |
| `actor.ask<T>(instructions)` | 派任务；`T` 是脚本内定义的 TS 接口，**JSDoc 字段注释合成运行时 schema 给子 agent**（`schema/synthesize.ts`），控制流要分支就必须带类型 |
| `phase("...")` | 阶段标记（编译期字面量），同名聚为一个图节点；用户确认的是 phase 图 |
| `world.run(cmd, args)` | 确定性门：机器可判定的检查跑真命令、分支在退出码上；命令名必须编译期字面量——**用户批准的是脚本的命令集** |
| `files.glob/grep/read`、`git.changedFiles` | 世界读：超限**拒绝而非截断**（不给静默残缺视图）；可 catch 降级 |
| `report(item, tag?)` | 渐进交付：**run 失败也随完成通知带出**（salvage），条目去重、重放不重复 |
| `artifact.file/markdown/chart/dashboard` | 用户可打开的产物卡；`{ primary: true }` 标记主交付物；发布即版本化 |
| escalation | 子 agent 可升级阻塞性问题（全局唯一 `dwfq-*` id），只挂起该子 agent 的该次调用；`ResolveWorkflowQuestion` 应答；单 ask 限 3 次 |
| 禁止嵌套 | 子 agent 不能调 `CreateWorkflow`；更大的活建模为更多子 agent |

SKILL.md 的方法论部分（fresh eyes、每发现一确认者、确定性门优先、barrier 只留在真正需要全员的地方）本质是把"专家级交付"的评审文化编译进编写契约，并给出了完整的反模式清单。

## 六、与 suyan 显式 DAG 工作流的对比（修订版）

两套系统哲学高度同构——**模型负责编排，引擎负责确定性**——但在三个关键选择上不同：

| 维度 | suyan `run_agent_workflow` | ZCode dynamic workflow |
|---|---|---|
| 拓扑来源 | 模型产出 JSON 节点 + `dependencies` 字段 | 模型写 TypeScript，**编译期从数据流静态恢复**（含循环、分支、fan-out 基数） |
| 控制流 | 无（图固定，重试由引擎按预算自动做） | 脚本即控制流（循环/条件/typed 分支），重试写进脚本 |
| 重放/复用 | 节点结果指纹缓存（依赖闭包完整才复用） | journal 逐站点重放 + 修订按命名 actor 导入（字节级匹配） |
| 确定性保障 | 快照/血缘/结果信封 | 编译期禁随机与时钟 + journal inputHash 防御 |
| 子 agent 通信 | 上游产物清单 + 结论摘要（复用 file_path） | typed 结果跨 schema 边界插值进下游 prompt |
| 人工介入 | 层级不明确时主 agent 先问用户 | 子 agent 运行中升级问题（只挂起该调用） |

最值得借鉴的一点：ZCode 把"依赖图"从**模型要填对的字段**变成了**编译器保证的事实**——模型只写自然的编排代码，图是分析器送的；而 suyan 的模型必须自己正确声明 `dependencies`，靠运行时校验兜底。

## 七、代码地图

| 路径（`apps/zcode-cli/packages/`） | 行数 | 职责 |
|---|---|---|
| `dynamic-workflow/src/analysis/` | 12.4k | 静态分析：site/causality/actor 三图、fanout 基数、facade 误用诊断、mermaid 渲染 |
| `dynamic-workflow/src/engine/` | 5.4k | 确定性执行引擎：journal 重放、per-actor FIFO、结算、导入缓存 |
| `dynamic-workflow/src/compiler|facade|lowering|schema` | ~2.4k | TS 编译检查、facade dts、脚本降级、JSDoc→schema 合成 |
| `dynamic-workflow-runtime/src/` | ~1.1k | 沙箱 harness：子进程编排、NDJSON 线协议、child entry 渲染 |
| `bootstrap/src/app/dynamic-workflow-*.ts` | — | run 服务、提交、journal 持久化、进度回流 |
| `core/src/workflow/`（legacy expert） | 4.7k | 8 阶段管线、依赖图种子化调度器（collections/planner/frontier） |
| `bundled-skills/skills/dynamic-workflows/` | ~1.5k+ | SKILL.md 编写契约 + patterns.md 拓扑目录 + examples.md 完整示例 |

另：`packages/desktop/src/host/index.ts` 是桌面宿主与 CLI 的接驳点；`runtime/methods/background-stop-dynamic-workflow.ts` 等是 core 运行时的暴露方法。

## 八、v3.17.1 引擎演进与 suyan 移植对照（2026-10-31）

基线更新：引擎自本文考察的 v3.14.3 起又演进约 3.5k 行源码（至 10-30 sync 的 v3.17.1），并首次补齐两份官方规格文档：`packages/dynamic-workflow/docs/analysis.md`（1167 行，编译期分析）与 `docs/execution-engine.md`（917 行，执行引擎）。主要新机制与 suyan 的移植落点：

| ZCode 机制（出处） | 机制要点 | suyan 落点（本次移植） |
|---|---|---|
| Usage, not budget（`engine.ts` askStats→spentTokens→usage-updated） | 每次模型回合计量 `askStats {tokens, toolCalls, turns}`，引擎累计 `spent_tokens`，先写 journal 列再发事件；无预算无上限，纯遥测 | planner 每轮 `message_stop` 产出 `usage_delta`（跨协议合并 start/delta 两帧 usage）→ agent_runtime 累计 `state.tokens_spent` → call_sub_agent 聚合进信封 `metadata.usage` → coordinator 记 `node_usage` 并累计 `budget_state.spent_tokens`，journal 出 `workflow.usage` 事件，snapshot 透出 |
| Stall clock（`bootstrap/app/workflow-driver-concurrency.ts`，默认 20 分钟） | run 级停摆时钟：任一瞬态重试上膛时定闹钟，"距上次模型请求成功超阈值且本段排定过重试"→ `run-stalled` 事件，每静默段至多一次，纯观察不决策 | `workflow/stall_watch.py`：v1 用 journal 事件近似 ZCode 的模型请求信号（差异已注释），静默超 `budget.stall_notify_seconds`（默认 1200s）→ `workflow.stalled` journal 事件 + snapshot `stall` 字段 |
| 模型错误策略表 + transient redrive（`adapters/src/model/workflow-model-failure-policy.ts`） | 单一判定函数供多层共用：配额/鉴权/无效请求/模型不可用 → 立即停；上下文超限单独归类；表外一切（限流/过载/5xx/网络）→ run 内无限重试 + Retry-After 退避，逃生口是 stall clock | `workflow/model_failure_policy.py`：`resolve_model_failure_policy()` 唯一判定源 + `transient_backoff_seconds()`（Retry-After 优先，否则 2s→60s 指数退避+抖动）。coordinator `_run_node` 按策略决定重试/立即失败（journal 记 `node.retry_scheduled` 与 `failure_policy`）；agent_runtime 的 deterministic/quota 分类改为委托策略表（保留 2 次 deterministic 熔断安全网） |
| Salvage（`dynamic-workflow-run-observation.ts` reportsOf） | report 条目落持久行，终态通知无论成败都从 journal 捞回——失败也不丢已完成的工作量 | coordinator `delivery()` 新增 `salvage`：失败/被阻断节点在倒下前已交付的中间产物清单（来自 node_progress.delivered_files）；`run_agent_workflow` 最终报告未完全成功时优先呈现抢救产物 |

明确未移植：escalation（`dwfq-*` 阻塞应答，需 worker→主会话应答回路，留待下一轮）、hole 机制（suyan 拓扑是 JSON 定义而非模型脚本，无编译期站点概念）、前端用量展示。

移植验证：`backend/app/agent/workflow/model_failure_policy_test.py`（分类表 12 例）+ `coordinator_policy_test.py`（stop 类零重试、瞬态重试上膛记账、用量累计与事件顺序、salvage 内容、停摆单次通知）21 例全绿。

## 九、第二轮移植：AIMD 并发治理器与配额自动续跑（2026-10-31）

在第一轮四项的基础上，继续移植 ZCode 的两个模型资源治理机制：

| ZCode 机制（出处） | 机制要点 | suyan 落点（本轮移植） |
|---|---|---|
| AIMD 并发治理器（`dynamic-workflow/src/engine/concurrency.ts` + `bootstrap/app/workflow-concurrency-governor.ts`） | 闸门粒度是每次模型请求尝试：每 4 次连续成功 +1（需有等待者）、429/过载 ×0.75 收缩、空闲 5 分钟回初值、上限 2×D；epoch 防阻尼（同一批在飞请求只裁决一次）；lastGood 探测语义（已证明水位之上被拒回落不乘系数）；冷却仅由 Retry-After 驱动；**配额类停止走 ended-only**（额度窗口的 Retry-After 可达数小时，当并发信号会冻桶几小时） | `backend/app/services/llm_concurrency.py`：纯状态机 `ConcurrencyController`（全部收 now 参数）+ 进程级 per `provider:model` 桶 `LlmConcurrencyGovernor`。`llm_request_slot()` 异步上下文管理器在 `__aexit__` 自动按结果结算（正常/取消/限流/瞬态/永久），替换原固定信号量 `get_llm_pool_semaphore`（保留兼容）。作用域为 per 进程（与原信号量语义一致），跨进程 Redis 全局治理留待后续。配额信号补账进 `llm_failure_counter`（billing 原来不计数，运行监控看不到） |
| 配额重置自动续跑（`bootstrap/app/dynamic-workflow-quota-resume.ts` + 策略表 `resolveQuotaResetAt`） | 配额停止非终态：resetAt 解析（Retry-After 优先，否则原文重置时刻按北京时间，合理窗口 [now−24h, now+35d]）；唯一数据源是 run 行，定时器只是唤醒、到点复核 resetAt 未变才续；同一 resetAt 重复失败 10 分钟起 ×2 封顶 60 分钟拉开间隔 | 策略表 `FailurePolicy.reset_at`（`resolve_quota_reset_at`）；coordinator 记档 `quota_pause`（journal `workflow.quota_paused`）；`_prepare_snapshot_resume` 把 stop_quota 节点翻回可重试并抬高 run 的 attempt 上限（解除 resume 409 硬阻断）；`workflow/quota_resume.py`：Redis ZSET 唤醒器（`{prefix}:quota_resume`）+ worker 循环每 5s 扫描，统一覆盖 inline（web 进程）与 durable（worker 队列）两条路径，`store.enqueue` 与手动 resume 同路；防循环同 ZCode（10min ×2 封顶 60min、至多 3 次后留手动）；全程 fail-soft |

移植验证：`tests/services/test_llm_concurrency.py`（状态机 12 例 + 桶级 4 例）、`model_failure_policy_test.py` 补 reset_at 解析 6 例、`coordinator_policy_test.py` 补 quota_pause 记档与快照恢复 2 例、`quota_resume_test.py`（schedule/scan/防循环 8 例，全 fake Redis）。

明确未移植：跨进程 Redis 全局并发治理、run 间公平队列与 observer 模式（我们主 Agent 与工作流不同进程，无此争用）、LLM 层 Retry-After 头的 HTTP 读取（沿用错误文本解析，网关不透传时退化为指数退避）。

## 十、第三轮移植：escalation 阻塞应答（2026-10-31）

| ZCode 机制（出处） | 机制要点 | suyan 落点（本轮移植） |
|---|---|---|
| escalation 升级提问（`bootstrap/app/workflow-driver-escalation.ts`，MAX_ESCALATIONS_PER_ASK=3） | 子 Agent mid-turn 调 `escalate` → driver 停驻该 ask（deferred），双轨记 `escalation-raised`；主 Agent 经 run service 作答 → 解 deferred、`escalation-resolved`，turn 就地继续；第 4 次返回普通工具结果"自行以最佳判断推进"（抛错会被当可重试故障反复撞墙）；ask 结束三条异常路径撤下停驻 | `backend/app/tools/agent_tools/escalate_tool.py`：EscalateTool 照 submit_result 裸类模式，由 `build_escalation_tool` 在工作流节点上下文注入 child registry（agent_runtime 三处白名单与 submit_result 同待遇）。**真挂起**：execute 内轮询 Redis（0.5s）等答案，只挂起该节点、其余节点照常跑；问题/答案落 `{steering_prefix}:workflow:escalation:{eid}`（TTL 24h，跨 3 个 uvicorn worker 安全）；超时（`agent_escalation_timeout_seconds` 默认 600s）与预算（`agent_escalation_max_per_node` 默认 3）均返回**普通结果**按假设推进，不抛错。coordinator `record_escalation` 记档（journal `workflow.escalation_raised/resolved/timeout` + 快照 `pending_escalations` 推前端轮询）。API `POST /{workflow_id}/escalations/{eid}/resolve`（按 session_id/workflow_id 校验归属、幂等）；前端 WorkflowPanel 渲染澄清卡片（问题+输入框），复用快照轮询通道 |

与 ZCode 的语义差异：ZCode 的停驻在 driver 层、主 Agent 应答（run 后台化、主 Agent 空闲）；我们的主 Agent 在 inline 路径被工具调用阻塞，因此**应答方是用户**（WorkflowPanel 卡片），这也更贴合问数口径澄清的真实场景。挂起节点占住一个 governor 槽位（已知限制）。明确未做：durable 路径的持久化问答（用户离线→答案落库→续跑注入）、通知推送、主对话流渲染。

移植验证：`tests/tools/agent_tools/test_escalate_tool.py`（预算/超时/作答/注入条件 4 例）+ `coordinator_policy_test.py` 补记档与快照往返 1 例；workflow 包全量 134 通过无回归。

## 十一、第四轮移植：渐进交付 report_finding（2026-10-31）

| ZCode 机制（出处） | 机制要点 | suyan 落点（本轮移植） |
|---|---|---|
| report 渐进交付（`dw/src/engine/engine-report.ts` + `dynamic-workflow-run-observation.ts` reportsOf） | 子 Agent `report(item, tag)` 按条发布中间发现：落持久行（一次写入恒 completed）、事件扇出、去重、终态通知无论成败都从 journal 捞回（salvage 的本体）；有界（单条字节/条数/run 级字节，超限 failRun） | `backend/app/tools/agent_tools/report_finding_tool.py`：`report_finding(content, tag?)` 裸类，由 `build_finding_tool` 注入工作流节点子 Agent（agent_runtime 白名单三处与 submit_result/escalate 同组豁免）。coordinator `record_finding`：内容哈希去重、每节点 ≤20 条/单条 ≤1000 字符/总字节 ≤256KB（超限拒绝）、journal `node.finding` 即时落账（兼停摆观测进展信号）、**快照写 3s 防抖合并**（避免每条一次全量 metadata 持久化）。settle 兜底：未调用工具的节点从 result_envelope.findings 一次性补齐（成功与失败路径都做）。消费端：salvage 条目携带 findings（失败不丢）、重试上下文带最近 10 条（子 Agent 修正时站在已有发现上）、result_data 加 node_findings 摘要（失败节点优先）、`_node_history` 返回 findings 字段、WorkflowPanel 节点审查视图实时发现列表 + 节点行计数徽标 |

与 ZCode 的差异：ZCode 的 report 由编排脚本发布、供主 Agent 与看板消费；我们由节点子 Agent 显式发布，运行中受益方是前端（实时）与重试/失败抢救，父 Agent 本体在 settle 后经 compact 视图消费（工具阻塞语义决定运行中无法喂父 LLM 上下文）。

移植验证：`tests/tools/agent_tools/test_report_finding_tool.py`（上报/去重/上限/注入 5 例）+ `coordinator_policy_test.py` 补去重边界与 salvage、settle 兜底、快照往返 3 例；workflow 包全量 140 通过无回归。
