# Shared Agent Workflow Runtime

This package contains the domain-neutral coordination primitives used by all
Agent modes.  It does not encode report, expert, operations, or coding
workflows.

## Contracts

Use `build_agent_task()` for a task contract.  A contract identifies the task,
its parent, objective, inputs, constraints, dependencies, capabilities, and
the expected result schema.  Use `build_result_envelope()` for a stable result
shape containing outputs, evidence, uncertainties, artifacts, errors, and
metadata.  A mode may add a stricter schema inside `result_schema`.

## Runtime

`WorkflowRuntime` records task lifecycle transitions and append-only events:

```text
queued -> running -> waiting/repairing -> succeeded/failed/cancelled
```

Its snapshot is JSON serializable and can be persisted in a session, database,
or Redis.  Reconstructing a runtime from that snapshot preserves task state,
lineage, attempts, cancellation, and the event journal.

`WorkflowGraph` handles dependencies for multi-agent DAGs.  Tasks become ready
only after every dependency succeeds.  `WorkflowConcurrencyGovernor` provides
a domain-neutral concurrency bound.

`AgentActorRegistry` serializes turns for the same logical child runtime while
allowing different child runtimes to execute concurrently.  `call_sub_agent`
uses `session_id + target_mode` as its actor key.

## Mode adapters

Mode code supplies prompts, tool capabilities, task-specific contracts, and
result schemas.  The shared runtime owns scheduling, persistence, retries,
repair states, cancellation, capability filtering, and observability.  New
modes should call the runtime through the existing handoff tool rather than
implementing another parent/child execution path.

## Fixed workflow catalog

`catalog.py` is the shared registry for bounded Agent-mode workflows and
deterministic scheduled workflows. Both entry points publish a versioned
definition made of named phases; they differ only in their adapter:

- Agent-mode workflows let the model choose tool arguments while the runtime
  owns phase transitions, visible tools, retry bounds, and completion.
- Scheduled workflows bind a deterministic handler and continue to run without
  starting an Agent.

Latency-sensitive query modes are defined in `mode_workflows.py`. They use a
bounded acquire/normalize/deliver flow, so report DAG nodes and future scheduled
jobs can share the same execution policy instead of copying prompt conventions.

## 通用 Agent DAG

run_agent_workflow 用于具有独立子任务或明确依赖的任务；单一简单查询优先直接调用业务工具，
一次性委派可用 call_sub_agent。本轮优化参考 LangGraph 的状态恢复、任务隔离和重试策略，
沿用当前依赖就绪后立即调度的执行器，没有新增 LangGraph 运行依赖。

### 父模式与子节点

| 父模式 | 子节点类型 | 父 Agent 职责 |
| --- | --- | --- |
| query | query_monitoring_station、query_monitoring_city、query_forecast | 查询规划、跨源合并、核算、导出与展示 |
| expert | 上述取数节点，以及 expert_meteorology、expert_analysis | 证据判断、跨领域归因与结论整合 |
| report | 上述取数节点，以及 expert_meteorology、expert_analysis | 正式报告整合与交付 |

专家节点需给出任务契约和结果 schema，一个节点回答一个分析问题。
精简子节点保持原有工具白名单，并禁用 call_sub_agent 和 run_agent_workflow。
同一父会话的上游资源通过 dependencies 交接；已经获取的数据优先复用。
子节点的地域、时段、口径与职责须继承父任务边界。

项目专属白名单需要显式配置委派工具；公共默认白名单不覆盖项目配置。
项目提示词启用委派工具时会自动补充通用协作约定。

### 恢复与缓存

- 显式取消是终止操作；依赖失败使用 blocked 状态，避免与用户取消混淆。
- 恢复兼容旧快照中的 cancelled + dependency failed，成功后清除旧错误。
- 父执行协程中断时清理子任务，保留可恢复状态与已绑定的子会话。
- Redis 队列读取最新 snapshot；入队、领取和过期回收使用 Lua 原子状态检查。
- worker 独立发送心跳，保留父模式与并发配置；事件写入异常不会使队列等待永久挂起。
- 成果缓存按父会话和工作流隔离；任务上下文、契约和 schema 变化会使缓存失效。
- 缓存一小时内有效，文件原子替换；部分失败时已验证成功的节点也可复用。
- 参数、类型、权限和未实现错误不自动重试；连接与超时错误采用短暂退避和抖动。

### 当前边界

快照与资源保存仍属于尽力持久化，不能保证外部工具副作用恰好执行一次。
Redis 队列操作的原子性不替代数据库事务，也不提供跨系统副作用事务。
并发上限仍以工作流为单位；跨会话的服务配额需由部署层或服务层控制。
图在执行前确定，执行中补任务、持久人工暂停和循环重规划尚未加入。

通用实现先提交 main，再合并到项目分支；项目专属模式配置在项目分支维护。
