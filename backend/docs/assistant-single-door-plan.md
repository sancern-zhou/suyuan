# 助手单入口与两层路由实施方案

> 历史方案。2026-11-08 起，DAG 的机械 delivery checklist、固定 task_contract 和
> input/output resource contracts 已移除，改由可选 result_schema、真实文件路径
> 和父 Agent 业务验收承担。文中相关 C 阶段设计不再作为当前实现依据。

> 历史方案。2026-11-08 起，DAG 的机械 delivery checklist、固定 task_contract 和
> input/output resource contracts 已移除，改由可选 result_schema、真实文件路径
> 和父 Agent 业务验收承担。文中相关 C 阶段设计不再作为当前实现依据。
>
本文只覆盖"路由—交付—可控性—入口收敛"主线，不重复共享基础设施（统一 Effects/Outbox、事件订阅）那部分。

## 0. 问题与目标

**问题**：用户面对 8 个 Agent 入口（assistant/ppt/expert/query/knowledge/report/board/ops，
`frontend/src/config/agentModes.js`；后端另有 `mode` + 遗留 `assistant_mode` 双轨参数）不知道怎么选，
学习成本高；助手模式已具备委派能力，但对话效率、交付质量、过程可控性存在卡点。

**目标**：

1. 用户只面对一个对话入口，模式选择降级为实现细节；
2. 路由开销压到"每任务一次轻量首轮"，追问不再过路由；
3. 交付物有明确验收标准，缺口诚实声明；
4. 任务过程有统一阶段视图，"等人的事"排在最前。

**实施策略（两步走）**：先在**保留现有全部入口**的前提下，把助手模式作为并行入口跑通并用
试运行数据证明其效率、质量、可控性达标（阶段 A–E），**之后**才收敛入口（阶段 F）。
收敛前用户零感知、零迁移，随时可回退。

**明确不做**（已定决策，勿在实施中复活）：

- 不引入 L1 示例分类器/嵌入预分流（维护成本高、高速决策不可审计；重启条件见 §2 D2）；
- 不拆独立 Router 进程（web 3 worker 内完成，Intake 逻辑留在请求处理链）；
- 不在本方案内做事件驱动订阅/扇出（属借鉴文档 P1，另行立项）。

## 1. 总体架构

试运行期（阶段 A–E，入口不收敛）：

```
用户 ──现有任一入口（不变）──▶ 直达对应 agent instance
     └─（引导）经 assistant 入口──▶ assistant 首轮（理解+路由+一次结构化确认，一次调用）
                                       │
                                       ├─ 契约直通：活跃 run 的追问 ──steer──▶ 运行中任务（不过模型）
                                       └─ 委派：call_sub_agent / run_agent_workflow（默认后台）
                                                     │
                                       结果投递：complete 事件 + 资源附件直接落会话 ◀── 惰性吸收（一行摘要指针）
                                       任务卡片：阶段/待答问题/预算/steer/取消
```

收敛后（阶段 F 起）：assistant 成为默认且唯一对话入口，其余入口降级为场景快捷方式
（预填提示 + route_hint），不再直达独立 agent instance。

与原型（dsh-superagent）的对应：assistant ≈ 主 Session（只路由不做技术判断）、
子 Agent ≈ Executor Session、场景快捷方式 ≈ 显式引用 attach、追问直通 ≈ Subscription 直通、
惰性吸收 ≈ notice（注入不唤醒）、验收清单 ≈ Delivery Requirements、阶段视图 ≈ ticketStage。

## 2. 设计决策记录

| # | 决策 | 理由 | 重启/回退条件 |
| --- | --- | --- | --- |
| D1 | assistant 为唯一对话入口；**但收敛后置**：先经试运行验证（阶段 E 关卡），通过后才收敛 | 把用户赶进还没跑通的门会透支信任；后端委派图已就绪（`delegation.py` PARENT_CHILD_MODES），先补能力再收口 | 收敛按 projectConfig 逐项目灰度，可整体回退到多入口 |
| D2 | 路由两层：契约直通（程序）+ assistant 模型裁决；**不设中间分类层** | L1 为自研扩展，维护成本与不可控性高；原型亦无此层 | 若试运行中"任务首轮延迟"成为可感知卡点（路由轮时长/token 指标），再评估轻量预分流 |
| D3 | 路由折叠进 assistant 首轮：一次调用输出路由决定 + 缺槽位结构化追问 + mandate 边界 | 两层设计下路由不是额外一跳，税来自"轮做贵了" | — |
| D4 | 子模式速查（一行一模式）内联进委派工具描述；describe_mode 仅兜底 | 高频速查进描述是既定注入策略；8 行约 240 token 在预算内 | — |
| D5 | 返回路径=投递不是代理：结果直接落会话，assistant 上下文只吸收一行摘要指针（≤600 字卡片）；唤醒仅限追问路由 / partial·failed 决策 / 下条用户消息顺带处理 | 返回多一次模型改写是最大隐性开销 | — |
| D6 | 交付验收清单 + mandate 范围字段；observe 模式先记录后强制；observe 期与试运行同跑 | 避免上线即卡死用户的返工循环；试运行决策数据即 observe 数据 | enforce 开关按清单灰度 |
| D7 | 阶段视图从存储事实推导（最近报告类型 + 之后有无用户消息），不另存状态字段 | 重启不丢、状态不漂移（原型 waitsForPerson 谓词） | — |

## 3. 分阶段实施

依赖关系：A、B 为试运行（阶段 E）的硬前置；C 随试运行以 observe 模式同跑；D 建议与试运行并行开发，
其基本可控性项纳入 E 关卡验收；**F 仅在 E 通过后启动**。

### 阶段 A：路由上下文与决策审计（后端）——已实施（2026-11-01）

| 项 | 内容 | 落点 | 状态 |
| --- | --- | --- | --- |
| A1 | 速查内联：一行一模式的定位+边界契约 + 路由规则 | 实施时确认 `build_target_mode_contract(compact=True)` 已内联进 call_sub_agent / run_agent_workflow 的 target_mode 描述，无需新增；预算测试通过（default 项目实测 call_sub_agent 5.1K / run_agent_workflow 8.7K，上限 7.5K / 11K） | 已存在 |
| A2 | describe_mode 按需披露 | 落地为**两个委派工具的参数**（非新工具，仿 describe_table 模式）：`describe_mode='modes'` 返回速查；`describe_mode=<mode>` 返回完整四段契约；未知名模糊纠错；主模式（query/expert/report）返回说明并标注不可作为子 Agent。核心函数 `describe_target_mode()`（target_mode_contract.py） | 已实施 |
| A3 | 路由决策落库：新表 `agent_route_decisions`（迁移 026 + init_db create_all 双通道）：id、session_id、user_identifier、parent_mode、target_modes、reason_code、reason_values、route_hint、created_at。reason_code：`assistant_judgment` / `scene_prefill`（runtime_metadata.route_hint 存在时）/ `continuity`（预留，阶段 B steer 用）/ `boundary_refused`。**只记顶层委派**：工作流节点带 `_workflow_node` 标记跳过、助手运行内部执行（managed_delegation 作用域）跳过 | `app/agent/workflow/route_decisions.py`（fail-soft 异步写入）、`app/db/models/agent_route_decision_db.py`、`app/db/migrations/026_create_agent_route_decisions.sql`、call_sub_agent / run_agent_workflow 的 execute() 入口 | 已实施 |
| A4 | 拒收审计：delegation_error 拒收时记 `boundary_refused` 行（含截断错误信息）；父模型据此重裁，重裁本身记为新的 `assistant_judgment` 行——两者构成"拒收→重裁"链路。原设想的 `handback_reroute` 语义由这一对行覆盖 | call_sub_agent._execute_foreground 边界校验处、run_agent_workflow._execute_untracked 边界校验处 | 已实施 |

测试：`app/agent/workflow/route_decisions_test.py`（10 项：模糊纠错、契约查询、决策行校验、fail-soft）；
`tests/test_agent_mode_context_budget.py` 通过。**部署注意**：存量库需手工应用迁移 026（干净库由 init_db 自动建表）。

### 阶段 B：异步节奏与追问直通——已实施（2026-11-01，含 B4 前端）

| 项 | 内容 | 落点 | 状态 |
| --- | --- | --- | --- |
| B1 | 后台委派默认化 | 实施发现 assistant 委派已由 `AssistantRunService.launch` 承载，旧默认是**同步 await**。现改为：`run_in_background` 缺省时按 `assistant_delegation_background_default`（默认 True）转后台，显式传 false 才同步等待。首轮文本先流式到用户；交付边界等待（`assistant_delegation_wait_seconds`，默认 1800s，试运行可调低）承担整合——吸收命中时中间"已开工"文本不投递，用户只见最终整合答案；超时放行则"已开工"交付、结果事后可达。两委派工具 schema 描述同步更新 | 已实施 |
| B2 | 惰性吸收内联/溢出 | `_absorb_background_delegations` 的旧 20000 字截断移除，改为 `apply_inline_or_spill`：结果 ≤`assistant_delegation_inline_result_chars`（默认 4000）整体内联；超出降为摘要卡（≤600 字摘要 + file/chart/resource 产物指针 + `manage_assistant_runs action=result` 读取方式）。**完成后的主动投递（合成消息/事件推送）未实施**：前端已经由 conversation snapshot 轮询 `background_runs` 状态卡看到状态流转，结果可查；合成消息投递与 B4 前端同轮实施（需要渲染入口） | 吸收已实施；主动投递待 B4 |
| B3 | 追问直通 | **实施与原方案有偏差（更安全）**：不改 analyze_stream 语义，新增独立端点 `POST /api/assistant/runs/{run_id}/steer`（`assistant_routes.py`），服务侧 `AssistantRunService.steer_run` 复用 command("steer") 同套校验（归属、终态、kind=child）+ `web_assistant_request` 权限域。"唯一活跃 run"判定由前端依据 snapshot 的 `background_runs` 长度==1 决定调用本端点还是常规对话；多 run 或新任务仍由 assistant 裁决 | 端点已实施；前端接线待 B4 |
| B4 | 前端提示与接线 | **已实施（2026-11-01）**：`InputBox` 新增 `backgroundRuns` prop 与直通提示条——非分析态、assistant 模式、唯一活跃 child 委派时显示"将追加给运行中的任务：\<goal\>"，附"作为新任务"按钮（按 `directThroughSuppressedRunId` 对该 run 抑制，新任务自动恢复）；发送按钮提示改为"转交给运行中的任务 (Enter)"。`useSessionManagement.handleSend` 前置拦截：命中直通则调用 `steerAssistantRun`（新 API，`assistantApi.js`），失败自动回落常规对话。后端 `steer_run` 受理后把消息落进父会话 transcript（fail-soft，`_persist_steer_message`），前端轮询快照即可见，无需本地回显。ChatArea 向 InputBox 透传 `backgroundDelegation.runs`。构建验证通过（build:standalone + dist 产物检查） | 已实施 |

测试：`tests/test_assistant_delegation_async.py`（9 项：默认后台/显式同步/开关回退、内联/溢出、steer 归属与守卫）；
既有 `tests/test_assistant_delegation_absorb.py`（6 项）与预算测试通过。

### 阶段 C：交付质量——已实施（2026-11-01，observe 默认）

实施切分按批准决策："机制现在开发、内容观察期定稿"。关键设计依据：B2 落地后父模型
经常只看摘要卡，验收必须代码化在交付路径上，不能依赖父模型通读全量结果。

| 项 | 内容 | 落点 | 状态 |
| --- | --- | --- | --- |
| C1 | 交付验收清单（两层） | 新模块 `app/agent/workflow/delivery_checklists.py`：①`checklist_text(mode)` 定性验收条目（通用缺口纪律 + 12 个模式的"什么算完成"）注入结构化交付的子 Agent 提示词；②`evaluate_delivery_checklist` 机械化核验（键存在性/类型），违规以 {"path","expected","got"} 形状并入 result_schema 校验同通道——enforce 模式下由**既有修复轮**喂回子会话修正，不新增打回机制。清单内容是数据文件，观察期按真实案例修订 | 已实施 |
| C2 | mandate 范围字段 | call_sub_agent 新增 `mandate` 参数（region/time_range/metrics/responsibility）：渲染为子提示词"授权边界"节（超范围产出无效、范围不足在 scope/data_gaps 声明）；随 envelope metadata 记录；提供 mandate 时机械核验要求结果带 `scope` 对象。**遗留**：run_agent_workflow 节点 v1 未加 mandate（节点已有 task_contract 承载范围，避免改 WorkflowNodeSpec） | 已实施（节点侧遗留） |
| C3 | observe 模式 | `delivery_checklist_mode` 设置（off/observe/enforce，默认 observe）。observe 记录两处：结构化日志事件 `delivery_checklist_evaluated` + result envelope metadata `delivery_checklist_violations`（随交付可经 manage_assistant_runs 审查，无需新表）。切 enforce 由 E 关卡按 would_reject 率决定 | 已实施 |
| C4 | 缺口纪律扩展 | `data_gaps` 机械核验覆盖所有结构化交付（含自定义 schema——EXPERT_ANALYSIS_RESULT_SCHEMA 本身已 required，此处补齐缺口）；通用清单文本（缺口声明+证据可追溯）进所有结构化交付提示词；B2 摘要卡新增 `data_gaps` 透出——父模型只看卡时也必须看到缺口 | 已实施 |

实施中发现（利好）：`EXPERT_ANALYSIS_RESULT_SCHEMA` 已 required
`status/findings/evidence/uncertainties/data_gaps` 且含 `scope` 字段——机械核验做薄即可，
qualitative 部分交由提示词条目。测试：`tests/test_delivery_checklists.py`（15 项）。

### 阶段 D：过程可控性（前端为主，约 2 周，可与试运行并行）

| 项 | 内容 | 落点 |
| --- | --- | --- |
| D1 | 统一阶段模型：working/queued、person/answer、person/review、idle、blocked/failed 六态，**由存储事实推导**（最近报告类型 + 之后有无用户消息），不新增状态字段 | 新共享推导模块；接入 TaskExecution / assistant_tasks / workflow 运行三类对象 |
| D2 | 任务卡片：每 run 一张卡（阶段 + 待答问题 + 预算消耗 + steer/暂停/取消按钮），"等人的"置顶，健康的不占版面；基于现有 run ownership / queue / steering store 组装 | `frontend/src/stores/reactStoreQueue.js`、`reactStoreRunOwnership.js`、`reactStoreSteering.js`、右侧面板组件 |
| D3 | interaction_required 结构化：问题带 schema（选项+默认值），前端渲染表单一次填完，替代自由文本追问 | SSE 事件（`backend/app/api/agent.py:682-690` 事件类型）+ 前端渲染 |

守门：阶段推导测试（各种报告/消息序列 → 阶段断言，含重启后推导一致性）。

### 阶段 E：助手模式跑通验证（试运行关卡，约 2–4 周，与 C/D 部分重叠）

入口不收敛，assistant 作为并行入口对白名单人群开放引导使用。此阶段同时产出 C3 observe 数据。

**前置条件**：A、B 完成上线；C 的 observe 记录就位；D 的最低可控性项（运行中可 steer/取消/看到待答问题，可暂用现有界面）可用。

**试运行设计**：

1. 人群与引导：内部团队 dogfood → 白名单用户；提供"经助手办理"引导文案，不隐藏旧入口。
2. 任务覆盖矩阵（每类至少 N=5 例，全部经 assistant 委派完成，直连入口做同样任务作对照）：
   问数 / 专家分析 / 知识问答 / PPT / 报告生成 / office 文档 / 混合多意图（一句话多件事）/
   中途改需求（运行中追加）/ 失败恢复（子 agent handback 后重裁）/ 长任务后台 + 回来看结果。
3. 采样与记录：全程路由决策（A3 表）、observe 决策、每任务 token 与时长、首响时间。

**关卡验收标准**（阈值在试运行启动前由团队定稿，以下为建议量级）：

| 维度 | 标准 |
| --- | --- |
| 功能覆盖 | 任务矩阵全绿：每类任务经 assistant 完成率 ≥ 对照直连方式的 90% |
| 效率 | 任务首轮时长不劣于直连；describe_mode 常态 0 次；每任务路由 token 在预算内 |
| 质量 | observe 期 would_reject 率收敛到阈值以下并呈下降趋势；缺口声明覆盖所有交付 |
| 可控性 | 直通零误投（或降级开关及时生效）；handback 率低于阈值；运行中断可恢复 |
| 稳定性 | 试运行期无 P1/P2 事故；A3 决策记录完整可审计 |

**关卡结论**：通过 → 启动 F；未通过 → 按维度归因（路由/委派/交付/可控），修复后复测，入口维持现状。

### 阶段 F：入口收敛（前端为主，约 1 周，前置：E 通过）

| 项 | 内容 | 落点 |
| --- | --- | --- |
| F1 | `AGENT_MODES` 收敛：默认仅暴露 assistant；expert/query/ppt/knowledge 等改为场景（scene）定义——welcome 文案、预填提示、route_hint、示例，不再是独立智能体入口 | `frontend/src/config/agentModes.js`、`frontend/src/config/projectConfig.js` |
| F2 | 场景快捷方式交互：点击场景 = 新建 assistant 会话 + 预填输入框 + route_hint 随请求携带 | `frontend/src/services/reactRequestBody.js`、`frontend/src/stores/reactStore.js`（currentMode 收敛为"会话属性"） |
| F3 | 后端双轨收敛：请求参数合并为 `mode` + 可选 `route_hint`；`assistant_mode`（meteorology-expert 等）标记 deprecated，保留读取兼容一个版本周期；`select_agent_instance`（`backend/app/api/agent.py:627`）仅服务兼容路径 | `backend/app/api/agent.py`（:455/:519/:627/:775-800） |
| F4 | 历史会话兼容：按旧 mode 创建的会话原样打开，不强制迁移 | 会话目录 `backend/app/conversations/` |

灰度顺序：本机广东项目 → 其他项目，按 projectConfig 逐项目生效；四个独立开关（入口收敛、后台化默认值、直通、enforce）任一可单独回退。

## 4. 指标与基线

阶段 A 上线前先采基线（当前多入口直连模式的任务完成时长、返工率、每任务 token），试运行对照组即基线来源。

| 指标 | 口径 | 目标 |
| --- | --- | --- |
| 任务首轮时长 | 首条用户消息→assistant 首轮响应 | 不劣于直连对照 |
| 每任务路由开销 | 首轮 token + describe_mode 调用次数 | describe_mode 常态为 0 |
| 直通率 | steer 直达消息 / 任务存续期消息 | 只增不减，且 handback 率不升 |
| handback 率 | 超范围 handback / 委派总数 | 低于阈值；试运行期重点观察 |
| 验收打回率 | observe 期 would_reject 比例 | 收敛并决定清单是否转 enforce |
| 任务完成率（按类） | 任务矩阵分类统计 | 经助手 ≥ 对照直连的 90% |

## 5. 分支与提交归属

- 前端 `frontend/src/config|services|stores`、后端 `backend/app/api|agent|tools`、`backend/docs` 均为共享层：按仓库规范先提交 `main`，项目分支合并后叠加项目差异（场景文案、工具集按项目裁剪属项目分支内容）。
- 迁移文件接 `backend/app/db/migrations/` 现有编号顺序，走各部署既有迁移流程。

## 6. 遗留与后续

- 试运行期间旧入口与 assistant 并存产生的数据口径差异（任务从哪个入口发起）需在指标统计中区分标注；
- `mode`/`assistant_mode` 双轨的 deprecated 周期（F3 起）结束后删除兼容分支；
- 事件驱动（TaskEvent thread_key、订阅扇出、Gate+observe 告警评估）按借鉴文档 P1 另行立项，届时任务卡片直接复用 D1 阶段模型；
- 对话运行移交 worker 进程（借鉴文档 P2-10）与本方案解耦，若立项则 B1/B2 的投递通道不变，仅执行位置迁移。
