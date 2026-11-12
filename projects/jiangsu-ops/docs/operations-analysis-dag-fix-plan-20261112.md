# 运维分析 DAG 修复方案（讨论稿 v3）

> 2026-11-12 · 基于 `js_ops_risk_202610` 失败复盘 · 供讨论，未实施
> **v3 修订说明**：按用户两点设计决策重构：
> ① **取消轮次预算，只保留时间预算**（轮次不是工作量单位：同样 10 轮实测 115-290s；
> 一轮可含多个并行工具调用或零调用纯文本）。
> ② **预算耗尽 ≠ 失败**：预算耗尽改为**原地续跑**（同子agent实例、上下文完整保留、
> 延长时间），只有真失败（异常/工具错误/schema 校验失败）才走重试。
> v2 的 expanded_budget 重试放宽、max_retries 竞争、重试防重取数、重试上下文重建等
> 补丁大半被此设计取代（它们都在修补"把预算耗尽当失败"的错误抽象）。
> v1 的"数据准备去 LLM 化"路线已撤回（v2），不再出现。

## 0. 复盘结论摘要

7 数据域 10 次执行仅 2 次成功：5 域 `max_iterations_reached` 被截断（alarm 出完图即被杀），
456 万 token（大头是每轮 48k 字符投影重复注入），5 分析节点 blocked，工作流 failed。
失败链：迭代预算不够 → 被当失败 → 重试不放宽（expanded_budget bug）且上下文丢失
（重试子会话只剩 3 条消息）→ 重取数再耗尽 → 全局 3 次重试预算耗尽 → 后 3 域无重试资格。

---

## 1. 核心设计：时间预算 + 原地续跑 + 空转熔断

### A. 时间预算是唯一硬预算

- react loop 取消迭代轮次上限，循环退出条件只剩：完成 / 时间预算 / 空转熔断。
- 分档时间预算：**数据准备节点 420s**（实测 10 轮取数+出图约 115-290s，留足收尾），
  分析节点沿用 900s 下限，查询节点维持轻预算。
- token 无需单独预算：LLM 每轮有物理耗时下限，时间上限即 token 上限；配合第 3 节
  投影瘦身控制单轮成本。

### B. 预算耗尽 → 原地续跑（不是重试）

在 `CallSubAgentTool` 内部处理，coordinator 上层无感：

```
时间预算到点
  ├─ 有进展（近期有工具产物/新交付）→ 原地续跑：同实例、上下文不动，+180s
  │    （可多次续跑，节点总上限 900s；日志 budget_extended_continue）
  ├─ 无进展 → 走 C 空转熔断
  └─ 临近节点总上限（剩 60s）→ 注入收尾提示：停止新取数，落盘已取得数据并交付清单
```

- 续跑不重建会话、不重新加载历史（26 条轨迹全程在）、不注入 retry_context。
- 续跑**不占用** attempt / max_retries（那是给真失败的）。
- 工作流总预算相应调整：当前 1200s 对"3 并发 × 节点可续跑至 900s"偏紧，
  建议提到 2400-3600s，或工作流级也采用"有进展即续"的同构逻辑。

### C. 空转熔断（时间预算之外的第二止损器）

不限轮次后，空转是主要浪费源（rates 域 8 轮纯文本零工具调用）：
- 连续 2 轮无工具调用 → 注入推进提示（"请立即执行下一步工具操作"）；
- 持续约 60s 无新产物 → 强制收尾：用已有产物交付（salvage 语义），标记
  `stalled_no_progress`，而不是继续空烧到超时。

### D. 真失败才重试

异常 / 工具错误 / schema 校验失败保留现有修复轮机制，重试时附带已有产物清单
（v2 P1-2 的清单逻辑保留给这条路径）。`expanded_budget` 的 min() bug 顺手修掉
（重试取 max(cap, scaled)），虽然触发场景已大幅减少。

### E. 可观测性（原 P0-3）

返回 data 区分终态：`completed` / `extended_timeout`（续跑后仍未完成）/
`stalled_no_progress` / `failed`（真失败），附 delivered_files 与最后工具调用摘要。
父agent与前端可见子agent死在哪种状态——这是后续所有预算校准的反馈基础。

---

## 2. 被 v3 取代/删除的 v2 条目

| v2 条目 | v3 处置 |
| --- | --- |
| P0-1 expanded_budget min() bug | 降级为 D 的顺手修复（仅真失败重试路径使用） |
| P0-2 max_retries 与节点数脱钩 | 删除（续跑不占重试预算，竞争消失） |
| P1-1 数据域 16 轮/420s 下限 | 简化为 A 的 420s 时间预算（无轮次概念） |
| P1-2 重试防重取数 | 续跑场景不需要（上下文完整）；仅 D 真失败重试保留清单 |
| P1-3 剩 2 轮收尾 | 改为 B 的"剩 60s 收尾"（按时间触发） |
| P3 空转检测 | 升格为 C 空转熔断（核心止损器） |

---

## 3. 保留的配套修复（与 v2 相同）

- **投影瘦身**：`fresh_tool_result_projection` 预算 48000→16000 字符（settings 可配），
  最近 2 轮全文 + 更早轮次降级摘要+路径。预期单轮 input 47k→<25k token，提速并
  保上下文质量（47k/轮已逼近 50k 工作上限，会压缩轨迹）。
- **协议工具面对齐**：`build_escalation_tool` / finding 上报工具挂进工作流子agent
  工具面（机制已存在，装配缺口）；任务书注明 submit_result 在交付阶段注入。
- **工作流 JSON 生成稳健性**：节点数 >8 时先核心节点、extension 追加的指引（不强制）。

---

## 4. 实施顺序与验收

| 批次 | 内容 | 工作量 | 验收标准 |
| --- | --- | --- | --- |
| ①本周 | A+B+C+D+E（时间预算/续跑/熔断/重试语义/可观测性） | 2-3 天 | 单测绿；开发库重跑 11-12 同 query：7 域全 success、无重取数、总 token <200 万 |
| ②下周 | 投影瘦身 + 协议对齐 + JSON 指引 | 1-2 天 | 单轮 input <25k token；rates 无空转轮 |

单测重点：时间到点续跑（上下文不重建）、无进展熔断、续跑不占 max_retries、
真失败重试带产物清单、工作流总预算与节点续跑的协调。

回归基线：11-12 凌晨同 query（"完成上个月的运维风险监管分析"）开发库重跑，
对照域成功率 / 总 token / 端到端时长。

**观察约定**：止血回归后若仍有具体域持续失败，按域个案分析（工具面/任务书口径），
不预设架构级改动。

---

## 5. 待决策点

1. **续跑步长与上限**：每次 +180s、节点总上限 900s（与分析域对齐）是否合适？
   数据域 420s 起步值是否认同？
2. **工作流总预算**：1200s → 2400s 还是 3600s？或工作流级也做"有进展即续"？
3. **空转熔断阈值**：连续 2 轮无工具调用提示 + 60s 无产物强制收尾，是否过严/过松？
4. **投影预算**：48000→16000 一步到位（推荐），还是先 32000 观察？

---

## 附录 A：预算设定的收益/损失框架（v3 修订）

**定位**：预算是止损装置，不是成本约束。欠预算失败的损失是非线性的——死在半路意味着
前期投入全部沉没（alarm 10 轮 47 万 token 做完取数+图后被杀，产出零）+ 下游 blocked +
用户信任损耗。过宽预算的期望成本很低，因为完成即停（station 10 轮只用 9）。
**欠预算损失 >> 过宽损失，预算按 P80-P90 任务难度设定，不按最好情况。**

**成本结构**：token 钱相对月报人工成本可忽略；token 大头是每轮 48k 字符投影重复注入，
控成本靠砍单轮固定开销（投影瘦身）而非砍迭代预算。投影瘦身同时提速、保上下文质量
（47k/轮逼近 50k 工作上限会压缩轨迹、降低决策质量）。

**轮次不是工作量单位**：同样 10 轮实测 115-290s（station 140s vs rates 288s），一轮可含
多个并行工具调用或零调用纯文本。时间才是统一的真实成本单位（用户等待、槽位占用、
token 均由时间约束）。因此 v3 取消轮次预算，只留时间预算。

**两类失败必须分开**：任务太重做不完（alarm：有产物进展）vs 模型不会做（rates：8 轮
零产物空转，预算拉满只会空转更久）。固定上限两头做错：错杀慢而有进展的 alarm，放过
空转的 rates。v3 对策 = 时间预算 + 空转熔断（连续 2 轮无工具调用提示；60s 无产物强制
收尾交付）；可观测性（E）区分终态，是预算校准摆脱"靠线上事故反馈"的前提。

**续跑 > 重试**：预算耗尽的本质是"还没做完"，不是"做错了"。原地续跑（同实例、上下文
完整、延长时间）零重建成本；任何形式的死后重试都有会话重建/上下文恢复/进度注入的
固定开销，且历史上重试上下文只剩 3 条消息导致重取数。重试只保留给真失败（异常/
校验失败），且必须带已有产物清单续作。


---

## 实施记录（2026-11-12 批次①，已落码未部署）

| 条目 | 文件 | 内容 |
| --- | --- | --- |
| 时间预算决策器（新） | `app/agent/runtime/time_budget.py` | TimeBudgetSpec/TimeBudget：软预算到点有进展续跑(+180s 至 hard 900 封顶)、空转提示(连续2轮无工具一次)/熔断(60s 无工具+软预算到点收尾)、收尾窗口(90s)后终止；终态 extended_timeout / stalled_no_progress |
| 主循环接入 | `app/agent/runtime/agent_runtime.py` | 预算模式(runtime_metadata.time_budget)取消轮次硬限；每轮开始 check()（stop→break 记 budget_termination；prompt→writer.add_user_message 注入）；轮末 on_turn_end(last_turn_tool_calls)；_run_iteration 各分支记录工具调用数 |
| RunState/finalizer | `app/agent/runtime/types.py` `finalizer.py` | state.budget_termination/last_turn_tool_calls 字段；finalizer.timeout 带 reason，complete 事件透出 |
| 节点预算下发 | `app/tools/agent_tools/run_agent_workflow.py` | normalize：自由 agent 节点(非专家默认/非固定问数) timeout 下限 420s + 写入 time_budget{soft,hard}（单一来源，随 WorkflowNodeSpec.payload）；execute 闭包经 `_time_budget` 传 call_sub_agent；schema 文案更新（时间预算说明） |
| 子agent透传/终态提取 | `app/tools/agent_tools/call_sub_agent.py` | execute 接受 `_time_budget` 注入 turn_runtime_metadata.time_budget（经 analyze→executor→AgentRuntimeConfig 既有链，零签名连锁）；_extract_final_result 识别 complete(incomplete) 的预算终态；structured_data.termination_reason 透出 |
| coordinator | `app/agent/workflow/coordinator.py` | ①expanded_budget 修复：cap 参与min截断→max(cap,scaled)（10→15→20 不再截回）②预算终态(node_termination 留档/快照)不安排重试，外层兜底 TimeoutError 同视为 extended_timeout ③外层墙钟对时间预算节点= hard+120s（避免续跑被外层提前取消） |

**单测**：`time_budget_test.py`（4 用例：续跑封顶/空转熔断/状态复位/配置回退）；`coordinator_test.py` 新增 3 用例（expanded_budget 放宽、预算耗尽不重试、真失败仍重试）+ 1 存量用例按新语义改写（超时不再重试）。
**回归**：runtime 64/65（1 失败=test_ppt_reference 为存量，HEAD 基线 worktree 对照复现，11-11 PPT 管线退役遗留，与本次无关）；workflow 工具层+江苏 DAG 契约 51/51 绿。

**生效条件**：重启 backend（web）进程；改动均在共享层（backend/app），后续按 AGENTS.md 流程回合 main。
**验收（待做）**：开发库重跑 11-12 同 query「完成上个月的运维风险监管分析」：7 域全 success、无重取数、总 token <200 万；观察日志 time_budget_extended_continue / time_budget_finalize_entered / node_termination。


---

## 实施记录补充（2026-11-13 批次② + 重要结论更正）

### ⚠️ 结论更正：expanded_budget 的 min() 不是 bug，已撤回"修复"

批次①曾把 `expanded_budget()` 的 `min(120, iteration_cap, scaled)` 判为"重试放宽被短路"的 bug 并改为
`max(cap, scaled)`。回归中 `project_policy_test::test_project_budget_is_bounded_without_replacing_result_schema`
揭示该改动破坏政策语义后恢复原实现。事实链：

- `iteration_cap/timeout_cap` 由 `project_policy.prepare_node` 写入，来源是 **project.yaml 的
  agent_workflow_modes 政策治理硬顶**（凌晨数据域 iteration_cap=10/timeout_cap=300 正是江苏
  project.yaml 的 `max_iterations: 10 / timeout_seconds: 300`，非主agent声明）；
- project.yaml 数据域注释明确写着"重试扩容受 timeout_cap 封顶，须同步抬高策略值"——
  **政策封顶是设计意图，要放宽改 project.yaml，不是运行时越顶**；
- 因此凌晨"alarm#2 重试同预算再死"的真因是**政策值过时**（10 轮/300s 不够新契约下
  数据域任务重量），不是代码 bug；
- v3 已用正确方式解决：数据域运行时切换时间预算模式（轮次上限被忽略、超时抬到 420s
  软预算 + 900s 硬顶续跑），政策字段对自由节点事实退役；真失败重试仍受政策封顶（合理）。

### 批次②落地（2026-11-13，已重启生效）

| 条目 | 内容 |
| --- | --- |
| 投影瘦身 | `llm_fresh_tool_result_budget_chars` 48000→**16000**、`llm_fresh_tool_result_single_max_chars` 24000→**10000**（settings 默认 + session_memory 常量同步；single 校准为 10k 因序列化包装 +30%，8k 会把 6k 文本的中等结果整体挤出）。触发依据：11-12 回归实测 qc 域 16 轮 94 万 input（单轮 ~5.9 万 token、19-22s/轮），投影重复注入占大头 |
| JSON 分段指引 | WORKFLOW_SCHEMA_DESCRIPTION 增加指引：节点数 >8 或 JSON 超长被拒时先提交核心节点、extension 追加（已成功节点按结果缓存复用不重跑）——针对 11-12 实测 2 次 run_agent_workflow JSON 截断（浪费 ~4 分钟） |

测试：projection 测试按新预算尺度适配（"预算降级最旧"改直接断言注入计划——中等结果压缩
形态与 verbatim 在 payload 层不可区分）；coordinator_test 的 expanded_budget 用例改为政策
封顶语义。回归 284 passed / 2 failed（test_ppt_reference、test_history_projection 均经
HEAD worktree 基线对照确认为 11-11 合并存量，与本次无关）。

### 遗留

- 两个存量测试失败（PPT 多模态、历史投影截断标志）属 11-11 合并遗留，建议随批次②提交时一并修复或上游跟进；
- 江苏数据域政策的 max_iterations/timeout_seconds 字段对自由节点已无运行时效力，project.yaml 注释可择机更新（低优先）；
- 全部改动未提交；共享层文件按 AGENTS.md 流程先回 main 再合项目分支。
