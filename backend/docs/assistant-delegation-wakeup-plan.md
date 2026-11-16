# 助手后台委派完成即唤醒（Delegation Wakeup）立项方案

> 状态：Phase 1–3 已实施（2026-11-06）。实现：`app/social/assistant_wakeup.py`（drain 门与唤醒回合）、
> `app/social/assistant_runs.py`（终态钩子 + 账本收口）、`config/settings.py`
> （`assistant_delegation_wakeup_enabled`，默认开）。测试：`tests/test_assistant_delegation_wakeup.py`
> （13 例，对齐 ZCode 语义清单）。对照实现：ZCode 上游 `zai-org/ZCode`（源码已克隆至 `M:/zcode-src`，Apache-2.0）。

## 一、问题

助手模式下 `call_sub_agent` / `run_agent_workflow` 默认转后台（`assistant_delegation_background_default=True`），受理后回合先答复"已开工"，结果依赖两条**拉取**通路：

1. **交付边界等待**（`agent_runtime.py` `_absorb_background_delegations`）：仅在回合以 `PLAIN_TEXT_REPLY` 收尾时同步等待，上限 `assistant_delegation_wait_seconds`（默认 1800s）。
2. **用户下条消息顺带吸收** 或模型主动 `manage_assistant_runs` 轮询。

回合结束（超时放行、被新消息顶掉、交付路径未走 PLAIN_TEXT_REPLY 分支）后，**委派完成不产生任何事件**，助手永远不会再被唤醒。实测（2026-11-05 夜，会话 `assistant_session_1793893090557_kra4kjnm8`）：expert_analysis 委派 00:38→00:48 跑完，期间用户两次追问（"进度"、"有啥就交付啥呗"）才促成最终整合回复；若无追问，用户只能干等。

单门方案文档已把这一定位写明（`assistant-single-door-plan.md`）：

- L27："不在本方案内做事件驱动订阅/扇出（属借鉴文档 P1，另行立项）"——本方案即该"另行立项"。
- L59（D5）："唤醒仅限追问路由 / partial·failed 决策 / 下条用户消息顺带处理"。
- L177：事件驱动按 P1 另行立项。

## 二、现状盘点：四套后台机制

| 机制 | 完成后的行为 | 有无回灌 | 底座 |
| --- | --- | --- | --- |
| `call_sub_agent`/`run_agent_workflow`（assistant 模式） | `AssistantRunService.launch` 起 asyncio 任务，进程内 `_PENDING_BY_SESSION` 登记 | **无主动回灌**；仅交付边界等待 + 用户消息顺带 | `app/social/assistant_runs.py` |
| `call_sub_agent`（其他模式，`run_in_background=true`） | `background_task_registry` 纯内存状态投影 + 事件列表 | **无**；模型须用 `background_task_id` 轮询 | `app/agent/workflow/background_tasks.py` |
| 定时执行计划（`manage_assistant_schedule`） | 执行终态入 durable 通知队列，worker APScheduler 每 10s 泵一次 | **有，完整回灌**：见第四节 | `app/social/assistant_notifications.py` |
| 事件定时任务 / 社交提醒·后台分析 | 执行器自带 agent run；结果经 broadcast / Outbox **推送给用户** | 推送≠唤醒：不触发对话回合续跑 | `app/scheduled_tasks/`、`app/social/assistant_followups.py` |

用户记忆中的"定时任务执行结果唤醒主循环"即第三行：执行计划的完成/失败/超时都会 enqueue 一条回复，**与执行状态无关、不依赖用户提问**（`assistant-result-replies.md` 已固化该语义）。

## 三、ZCode 参照机制（源码级）

ZCode 的每个 `AgentRuntime` 实例持有**常驻** runtime command queue；后台任务完成会把一条 `<task-notification>` 命令入队，队列 drain 门串行消费——空闲则主动启动一个 model-only 回合，忙碌则在当前回合后继续 drain。这就是"完成后主动触发对话"的实现。

### 3.1 数据流

```
producer（local_agent / bash / workflow 终态）
  → <task-notification> XML（task-id/tool-use-id/task-type/status/summary/output-file/result/error）
  → enqueueBackgroundTaskNotification：守卫（shutdown / branchGeneration 过期 / offPeakCancelled / sealed）
      ├─ runtimeCommandQueue.enqueue(mode="task-notification", priority="next")
      └─ sessionStore.saveSessionInput(kind="backgroundNotification", delivery="queue")   ← durable 账本（admitted）
  → drainRuntimeCommandQueue（单飞 drain gate；busy 即排队，idle 即开轮）
      ├─ 同优先级通知合批（dequeueNextBatch）→ 整批合并为一条 synthetic user 消息
      │    （inputSource="background_task"、inputVisibility="model-only"、skipUserPromptSubmitHooks）
      ├─ executeTurnCommand(...) → 模型读通知、继续工作、回复用户
      └─ markSessionInputPromoted(...)（账本 admitted→promoted）
```

### 3.2 关键源文件（`apps/zcode-cli/packages/core/`）

| 文件 | 职责 |
| --- | --- |
| `src/runtime/command-queue.ts` | `RuntimeCommandQueue`：`now/next/later` 优先级；`dequeueNextBatch` 把同优先级 task-notification 合批 |
| `src/runtime/methods/background-notifications.ts` | 入队守卫 + 账本 admission/promotion + 合批持久化（`persistBackgroundTaskNotificationBatch`）；子代理 runtime 的 sealed 抑制 |
| `src/runtime/methods/runtime-command-queue.ts` | `enqueueRuntimeCommand`（入队即触发 drain）、`drainRuntimeCommandQueue`（单飞 + 终态空闲沿）、`runTaskNotificationBatch`（合批跑一个 model-only 回合）、`hasActiveOrQueuedTurnWork` |
| `src/runtime-task/notification.ts` | `<task-notification>` XML 生成与合批连接 |
| `src/runtime/agent-runtime.ts` | runtime 实例级队列/drain 状态（每会话隔离，父子 runtime 队列隔离） |

### 3.3 持久化与崩溃语义

- 账本是队列唯一的 durable 痕迹：`saveSessionInput(admitted)` → 消费后 `markSessionInputPromoted(promotedMessageID)`。
- 崩溃重启后后台子进程已死、通知不可恢复：resume 把残留 admitted 收口为 `discarded(session_resumed)`——留痕不静默。
- 过期守卫：branchGeneration 不匹配（rewind 后的迟到通知）直接丢弃；`offPeakCancelled` 封住已取消执行的迟到通知。

### 3.4 上游设计文档

`apps/zcode-cli/docs/design/v2/loop/runtime-command-queue-plan.md`（Phase 0–7：纯队列 → prompt drain 门 → task-notification 命令 → local-agent producer → auto-background → bash/monitor producer → 回归清理）与测试语义（idle wake / waits behind active prompt / skip hook / 合批单轮 / 不双通知 / enqueue 失败不标记 notified）可直接作为我们测试清单的模板。

## 四、仓内同构物：定时执行计划的结果回灌（已验证，直接复用）

`app/social/assistant_notifications.py` 已实现与 ZCode 同构的回灌，且经过了生产验证：

| ZCode 概念 | 仓内对应 |
| --- | --- |
| producer（任务终态） | `enqueue_execution`（执行终态扫描） |
| durable 账本 + 泵 | SQL 通知表 + `tick`（APScheduler 10s 泵，租约清理、崩溃对账） |
| model-only 唤醒回合 | `_synthesize_reply`：在**源会话**上跑完整 assistant 回合（`create_react_agent().analyze(session_id=source_session_id, manual_mode="assistant")`），prompt 注入执行结果与事项上下文，要求助手核对、整理并向用户汇报 |
| 幂等入账 | `_append_transcript`：按 `notification_id` 去重，崩溃重放安全；transcript 先于 outbox ack 提交 |
| 用户可见性 | 回复追加进原对话，前端 5s 轮询 `assistant/conversations/{id}/sync` 即可见 |

**差距**：该通路只覆盖"定时执行计划"，不覆盖实时后台委派；触发靠 10s 轮询而非完成即唤醒；唤醒与用户活跃回合无协调（`cancellation_registry.register` 的 `superseded_by_new_run` 会顶掉在跑回合，直接复用会打断用户）。

## 五、立项方案

**目标**：后台委派达到终态（succeeded/partial/failed/cancelled）后，主动唤醒源会话助手产出整合回复；用户零追问、零轮询。

### 5.1 设计原则（对齐 ZCode）

1. **完成即入账本，唤醒走统一入口**：模型不再负责轮询；`manage_assistant_runs` 保留为人工查询通道。
2. **活跃回合让路**：会话有在跑回合时只入队不唤醒；交付边界等待（既有快路径）优先吸收；回合以未吸收状态结束后，在结束沿触发唤醒。**绝不顶掉用户在跑的回合**。
3. **账本 durable、崩溃可对账**：唤醒状态挂在委派记录（已是持久化 JSON）上；泵兜底补投。
4. **合批**：多个委派同时完成合并为一个唤醒回合，避免每委派一个请求。
5. **通知结构化、返回即投递**（对齐 D5）：唤醒 prompt 只带摘要卡 + 缺口 + 产物指针，完整结果仍走 `manage_assistant_runs action=result` 按需读取。

### 5.2 Phase 1：唤醒通路（单进程内，核心）

- `AssistantRunService.run()` 终态收口处：`background` 且源会话非 scheduled_task 时，置 `record["wake_state"]="pending"` 并触发 `request_delegation_wakeup(source_session_id)`。
- **空闲判定**：基于 `cancellation_registry` 增加只读查询（会话无活跃 run handle 即空闲）。空闲 → 立即起唤醒回合；忙碌 → 仅登记，回合结束沿（`_complete_response` / 超时放行 / 顶替取消）后再判定。
- **唤醒回合**：复用 `_synthesize_reply` 形态，prompt 采用 `<task-notification>` 风格契约：

  ```
  <task-notification>
    <run-id>delegation_...</run-id>
    <target-mode>expert_analysis</target-mode>
    <status>succeeded | completed_with_gaps | failed | cancelled</status>
    <goal>…</goal>
    <summary>≤600 字摘要卡（build_delegation_result_card）</summary>
    <data-gaps>…</data-gaps>
    <artifacts>file/chart/resource 指针</artifacts>
    <full-result-pointer>manage_assistant_runs action=result run_id=…</full-result-pointer>
  </task-notification>
  ```

  要求助手：吸收结果、继续未竟步骤（可再委派）、向用户输出整合结论；不得把通知正文当作用户发言复述。
- **呈现**：唤醒 prompt 不进对话区（落库为隐藏/非 user 类型，或 `data.source="background_task"` 由前端过滤——实现时二选一，对齐 ZCode `model-only`）；对话区只见最终 assistant 回复与既有 `delegation_status` 卡。
- **多委派合批**：pending 集合一次性聚合为一个回合的多块 `<task-notification>`。

### 5.3 Phase 2：账本与对账

- 委派记录增加 `wake_state`（`pending / promoted / discarded`）与 `wake_message_id`；以 `run_id` 幂等。
- 补投泵：复用 worker APScheduler（10s）或 web 进程启动扫——扫描终态且 `wake_state=pending` 的记录补唤醒；与定时执行计划的对账语义一致。
- 进程重启丢失 asyncio 任务（记录仍 `running`）的情形**不唤醒**：沿用 `inspect` 的 `unknown` 语义（"没有可确认的活动执行器；不能据此判定完成"），留待用户显式处理。

### 5.4 Phase 3：抑制与边界

- 抑制规则：会话已删除/关闭（sealed）、委派被 cancel（含 `assistant_user_cancelled`）→ 通知 discard 留痕；已 promoted 的通知不再重投。
- 与交付边界的关系：`assistant_delegation_wait_seconds` 等待**保留**为快路径（同回合吸收零额外请求）；唤醒只负责"回合已结束"的存量。超时放行的"已开工"回复照旧交付，其结果由唤醒补达——正好覆盖昨晚的体验缺口。
- 非 assistant 模式的 `background_task_registry` 维持现状（轮询），不在本范围。

### 5.5 Phase 4：配置与回归

- 新增 `assistant_delegation_wakeup_enabled`（默认开，可回退）。
- 测试清单（对齐 ZCode 测试语义）：
  - 空闲会话委派完成 → 单个唤醒回合，回复落 transcript；
  - 活跃回合期间完成 → 不打断在跑回合；回合未吸收结束后补唤醒；
  - 交付边界已吸收 → 不重复唤醒（promoted）；
  - 两委派先后完成 → 合批一个唤醒回合；
  - 唤醒回合进行中用户发消息 → 用户消息按既有语义顶掉唤醒回合；
  - 崩溃/重启 → 泵补投 pending；`running` 残留不误报；
  - cancelled 委派 → discard 不唤醒；
  - 重复触发 → `run_id` 幂等。

## 六、范围外（维持既有边界）

- 事件驱动订阅/扇出、TaskEvent thread、Gate+observe 告警评估（单门方案 P1，另行立项）。
- 子代理中途进展流式回灌（本方案只做终态唤醒）。
- 非 assistant 模式的进程内后台句柄改造。

## 七、实施归属与顺序

- 改动集中在 `app/social/`（assistant_runs、新 wake 模块、assistant_notifications 泵复用）与 `app/agent/runtime/`（回合结束沿钩子），均为共享层 → **提交 main**，项目分支合并获取。
- 顺序：Phase 1（唤醒通路 + 空闲判定 + 呈现）→ Phase 2（账本对账）→ Phase 3（抑制边界）→ Phase 4（配置回归）。
- 参考 ZCode 上游 `runtime-command-queue-plan.md` 的分阶段纪律：每阶段先补失败单测再实现，focused tests 通过才进下一阶段。

## 八、实施记录（2026-11-06）

与原方案的实现差异（均已在代码注释与测试中固化）：

| 原方案 | 实际实现 | 原因 |
| --- | --- | --- |
| cancellation_registry 增加空闲查询 + unregister 空闲沿钩子 | 不需要：唤醒 drain 直接经 `register()` 排队——会话有在跑回合时 `register` 阻塞等待，回合结束自然放行；交付边界吸收方在 `wait_for_session_runs` 就地置 `absorbed_in_turn`，唤醒侧即时可见跳过 | register 的等待语义本身就是"活跃回合让路"，省掉一套回调 |
| 仅进程内互斥 | 增加 `session_advisory_lock`（等待上限复用 `assistant_delegation_wait_seconds`，超时收口 `session_lock_timeout`） | 3 uvicorn worker 下用户回合可能落在其他进程，纯进程内 register 不够 |
| 账本对账泵（Phase 2） | 未做：进程崩溃后磁盘残留 `pending` 不自动补投（与 ZCode resume 收口 discarded 的"不静默重放"同语义）；`cancelled` 委派终态即收口 `discarded`，开关关闭时不挂账 | 留待后续按需补泵 |
| 唤醒 prompt 不落库（仅落最终回复） | 沿用定时回灌的既证形态：prompt 不进 transcript，最终回复按 `wake_id` 幂等追加 `assistant|final` 消息 | 与 `_synthesize_reply`/`_append_transcript` 同构，前端零改动 |
| 唤醒回合可续委派 | 不行：唤醒不带 assistant request 上下文，`call_sub_agent` 被授权层拒绝 | "后台事件不能代替用户授权"（assistant_request 契约），续做由用户下一条消息承载 |

wake_state 账本：`pending → promoted`（回复已落库）/ `absorbed_in_turn`（交付边界认领）/ `discarded`（delegation_cancelled、user 停止、wake_superseded_cap（顶掉重试 3 次上限）、owner_unresolved、session_missing、session_lock_timeout）。
