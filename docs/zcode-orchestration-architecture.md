# ZCode 的编排与调度架构（"DAG"考）

本文回答一个问题：**ZCode（本仓库开发所用的 AI 编码助手）内部有没有 DAG 工作流？** 结论先行：

> **ZCode 没有显式的依赖 DAG 工作流引擎**——代码中不存在 `WorkflowGraph`、`ready_tasks()`、拓扑排序这类结构（全量代码检索无一处字面 "DAG"）。它的多任务编排走的是另一条路：**中央调度器（任务队列 + cron 自动化 + 错峰调度）+ 主 agent 动态派生子 agent（后台运行、消息传递、扁平任务清单）**，依赖关系不建图，而是由模型在上下文中推理。
>
> ⚠️ **此结论已过时，仅对本文考察的 3.11.2 桌面版成立**。开源仓库（[zai-org/ZCode](https://github.com/zai-org/ZCode) main，v3.14.3）已包含一套完整的动态工作流引擎：模型编写 TypeScript 编排脚本，编译期从数据流**静态恢复依赖图**（术语是 site/causality/actor graph，不叫 DAG——这正是按 "DAG" 关键词检索漏掉它的原因）。详见 [zcode-dynamic-workflow.md](zcode-dynamic-workflow.md)。

- 考察对象：ZCode Desktop **3.11.2**（build `89817f5b`，2026-09-04），安装于 `D:\zcode`
- 考察方法：解析 Electron 应用包 `resources/app.asar`，提取 `out/host`、`out/scheduler`、`out/main` 三个 bundle 做静态分析；结合本机运行时目录（`~/.zcode/cli`）与 harness 外部契约交叉验证。bundle 为压缩产物，个别实现细节以行为为准。

## 一、进程与代码结构

ZCode Desktop 是 Electron 应用，`app.asar` 内的自有代码分四块：

| 模块 | 体积 | 职责 |
|---|---|---|
| `/out/main/index.js` | 1.4 MB | Electron 主进程：窗口、托盘、更新、原生服务编排 |
| `/out/host/index.js` | 2.2 MB | **Agent 宿主**：LLM 循环、工具执行、子 agent、权限代理 |
| `/out/scheduler/index.js` | 1.3 MB | **中央调度器**：任务队列、cron 自动化、错峰调度、agent 进程生命周期 |
| `/out/renderer` + `/out/preload` | — | 桌面 UI 与预加载桥 |

持久化落在 `~/.zcode/cli/`：`db/db.sqlite`（会话与状态）、`agents/`（子 agent 运行记录）、`rollout/`（会话回放）、`exec/`（命令执行产物）、`v2/tasks-index.sqlite`（任务索引）。

## 二、调度器：队列、自动化与错峰，而非依赖图

`/out/scheduler` 是全系统的任务入口，它管理的是**时间和队列**，不是**依赖关系**：

### 2.1 任务队列与生命周期

任务以 `enqueue_task_command` 入队、`cancel_task_command` 取消，事件沿 `agent-process-spawned → agent-process-ready → agent-running-task-count-changed → agent-process-exited / agent-process-error` 的进程生命周期流转。重试是时间维度的：`computeRetryAt` 计算下次重试时刻（`api_retry`、`model_retry_scheduled`），没有"重试预算随尝试次数扩容"这类策略。

### 2.2 cron 自动化

用户可见的定时自动化（CronCreate/CronUpdate/CronList/CronDelete）落在这里：`computeScheduleRuleNextRunAt` 计算标准 cron 的下一次触发，`computeAutomationNextRunAt` 统一相对延时（delayMinutes）与 cron 两种表达，`isOneShotAutomation` 区分一次性与周期任务。到点通过 `cron-scheduler-wake-request` 事件唤醒执行。

### 2.3 错峰调度（off-peak，最有特色的部分）

低峰时段批量执行任务的两阶段协议：

```
offpeak-dispatch-request（调度器派发）
  → handleOffPeakClaimed（任务认领，offPeakRunType requires offPeakTaskId）
  → offpeak-dispatch-result / settleOffPeakDispatchResult（结果结算）
  → reportOffPeakActiveCount（活跃数上报，控制并发水位）
```

错峰任务与 cron 自动化互斥（`automationId and offPeakTaskId are mutually exclusive`），且有一套错峰子 agent 的验收链（E2E 标记 `E2E_OFFPEAK_SUBAGENTS_PARENT / CHILD_EXPLORE / CHILD_GENERAL / CHILD_INHERIT`）——父任务可派生 Explore/general-purpose 子 agent 并继承配置，跑完由后台 reviewer 审查。

## 三、Agent 宿主：动态派生的子 agent，而非静态节点

`/out/host` 的编排模型是**每轮对话内动态派生**：

### 3.1 子 agent（Task 工具）

- 主 agent 按需 spawn 子 agent，内建类型 `general-purpose`（全工具）与 `Explore`（只读检索，"broad fan-out searches"）等；插件可注册更多（如评审用 judge）。
- **后台运行**：子 agent 可 `run_in_background`，"Runtime will wait for this background Agent"——完成时以 `background_notification` 通知主 agent，主 agent 用 TaskOutput 取结果、TaskStop 终止。
- **消息传递**：`SendMessage` 让主 agent 与已完成的子 agent 续聊；同一逻辑子 agent 的消息经 actor 串行化（`caller-serialized`），不同子 agent 并发。
- 子 agent 事件流独立上报（`subagent.lifecycle` / `subagent_child` / `subagent_message` / `subagent_notification`），UI 实时呈现。

### 3.2 任务清单（TodoWrite）——"穷人的 DAG"

跨轮次的工作分解用 `TodoWrite` 扁平清单：`pending / in_progress / completed` 三态，**约束至多一个 in_progress**。清单变更广播（`broadcastTaskListChange` / `workspace_task_list_changed`）到 UI 与计划审批流（`sessionTodosToPlanSteps` 把清单转为计划步骤）。依赖顺序不存在数据结构里——先做什么后做什么由模型自己按上下文推理，写清单只是让推理显式化、可观察。

### 3.3 计划模式与权限

复杂任务先 EnterPlanMode（探索 + 方案），ExitPlanMode 触发 `plan_approval` 审批；工具执行经 permission broker（权限代理）按会话权限模式放行，敏感操作（如计划外重启、删除）要求确认。

### 3.4 LLM 接入

host 经统一的 provider 层接多家模型（依赖树里有 `@anthropic-ai/*`、`@aws-sdk/*` 等），会话消息与工具轨迹全部落 `db.sqlite` / `rollout/`，可回放。

## 四、与显式 DAG 工作流的对比（以本仓库 suyan 为例）

| 维度 | suyan（显式 DAG） | ZCode（动态派生） |
|---|---|---|
| 拓扑 | 模型产出 `WorkflowDefinition`，代码建图、无环校验 | 无拓扑结构；依赖存在于模型上下文与提示词推理 |
| 节点 | 静态 `WorkflowNodeSpec`（target_mode/goal/依赖/预算） | 运行中动态 spawn 的子 agent，类型少而通用 |
| 就绪判定 | `ready_tasks()`：依赖全成功才启动 | 主 agent 顺序推进；后台子 agent 完成靠通知唤醒 |
| 重试 | 代码控制：会话续用 + 预算扩容 50% | 时间维度：`computeRetryAt` 定时重试 |
| 任务状态 | 图节点四态 + 血缘 + 快照恢复 | 扁平 todo 三态（单 in_progress）+ 会话落库 |
| 定时/批量 | scheduled_task 固定工作流（catalog 注册） | cron 自动化 + 错峰两阶段派发协议 |
| 并发 | 信号量（governor，默认 4） | 调度器水位（offpeak-active-count）+ 进程池 |
| 适用场景 | 结构稳定、可复用、可观测的多源分析流水线 | 开放式、探索性、人机协作的编码任务 |

**本质区别**：suyun 把"先做什么"编码成数据（图），执行引擎保证顺序与边界；ZCode 把"先做什么"留给模型实时决策，调度器只管"什么时候允许跑"（队列、时刻、水位）和"跑在哪个进程"。前者是工作流引擎，后者是**资源调度器 + 动态 agent 树**。两种范式各有取舍：显式 DAG 换来确定性与复用（缓存、断点恢复、血缘审计），动态派生换来对开放任务的适应性（无需预知任务形状）。

## 五、考察方法备注

```text
D:\zcode\resources\app.asar（307 MB，Electron 归档）
  ├─ 解析：8 字节长度头 → header JSON（[4]=header 大小，[12]=JSON 长度，[16..] 内容，文件数据基址 8+header_size）
  ├─ 提取：out/host/index.js、out/scheduler/index.js、out/main/index.js
  └─ 分析：字符串常量（日志/错误消息/E2E 标记在压缩后保留）+ 交叉验证 ~/.zcode/cli 运行时
```

压缩 bundle 无符号名，以上模块职责由字符串常量、事件名、E2E 验收标记与运行时行为综合推断；引用的标识符（如 `computeRetryAt`、`handleOffPeakClaimed`）为 bundle 中实际存在的字符串。
