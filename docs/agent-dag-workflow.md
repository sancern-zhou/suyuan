# Agent DAG 动态工作流

本文介绍本项目的多 Agent 动态 DAG 工作流：报告主 Agent 如何自主编排子 Agent 任务图，运行时如何确定性调度执行，以及问数子 Agent 内部的固定工作流约束。

- 核心代码：`backend/app/agent/workflow/`（协调器与原语）、`backend/app/tools/agent_tools/run_agent_workflow.py`（编排入口）、`backend/app/agent/runtime/agent_runtime.py`（子 agent 执行循环）
- 适用范围：`report` 模式的报告生成是主要场景；`assistant`/`social` 等模式也可通过同一工具编排子任务

## 一、总体设计：两层分离

工作流采用"**编排动态化、执行确定化**"的两层设计：

```
┌─────────────────────────────────────────────────────────────┐
│ 第一层：报告主 Agent（模型）                                  │
│  通过 run_agent_workflow 工具自主规划 DAG：                    │
│  节点数量 / target_mode / goal / dependencies / 任务书         │
└──────────────────────────┬──────────────────────────────────┘
                           │ WorkflowDefinition（模型产出，运行时校验）
┌──────────────────────────▼──────────────────────────────────┐
│ 第二层：WorkflowCoordinator（代码）                           │
│  依赖就绪调度 / 并发上限 / 重试与预算扩容 / 会话续用 /           │
│  血缘校验 / 快照持久化 / 结果缓存 / journal 事件               │
└──────────────────────────┬──────────────────────────────────┘
                           │ 每个节点 = 一个隔离子 agent
┌──────────────────────────▼──────────────────────────────────┐
│ 第三层：子 Agent 运行时（代码约束 + 模型自由推理）              │
│  问数模式：固定三阶段（acquire → normalize → deliver），       │
│           阶段门控工具白名单与轮次；                           │
│  专家模式：自由推理，受 task_contract 粒度校验与预算约束         │
└─────────────────────────────────────────────────────────────┘
```

设计原则：**拓扑结构由模型决定**（按分析问题拆节点、按数据依赖连边），**调度与边界由代码决定**（模型不能决定"什么时候算完成""能用什么工具""失败怎么重试"）。这样既保留 LLM 编排的灵活性，又保证延迟、成本和行为可预期。

## 二、第一层：报告模型定义动态 DAG

### 2.1 编排入口 `run_agent_workflow`

报告主 Agent 通过 `run_agent_workflow` 工具（`backend/app/tools/agent_tools/run_agent_workflow.py`）提交完整 DAG 定义：

```json
{
  "workflow": {
    "workflow_id": "air-quality-report",
    "nodes": [
      {"task_id": "station-data", "target_mode": "query_monitoring_station",
       "goal": "查询指定站点和时间范围的站点小时监测数据"},
      {"task_id": "city-data", "target_mode": "query_monitoring_city",
       "goal": "查询同期城市口径数据与全国对比"},
      {"task_id": "cause-analysis", "target_mode": "expert_analysis",
       "goal": "基于上游数据完成污染成因研判",
       "dependencies": ["station-data", "city-data"],
       "task_contract": {"protocol_version": "workflow.v1", "question": "...", "deliverables": ["..."]}}
    ]
  },
  "max_concurrency": 4
}
```

节点字段：`task_id`（唯一）、`target_mode`（子 agent 模式）、`goal`（必填）、`context`（补充上下文）、`dependencies`（上游节点）、`task_contract` + `result_schema`（专家节点结构化任务书与结果协议）、`max_attempts`（默认 2，重试续用子会话）、`max_iterations`（推理轮次）、`timeout_seconds`（硬超时）、`phase`（用户可读的阶段名，面板按阶段分组展示故事线）。

### 2.2 编排硬约束（运行时校验，违规整单拒绝）

| 约束 | 规则 | 位置 |
|---|---|---|
| 节点模式白名单 | 报告 DAG 只允许 `query_monitoring_station` / `query_monitoring_city` / `query_forecast` / `expert_meteorology` / `expert_analysis`；综合 `query`、`query_monitoring` 兜底、成稿类模式一律拒绝 | `REPORT_NODE_ALLOWED_MODES` |
| 层级不明确 | 禁止用综合模式兜底，报告 Agent 必须先向用户确认口径 | 路由规则（`target_mode_contract.py`） |
| 专家节点粒度 | 必须携带 `task_contract.deliverables`（1~3 项），一个专家节点只回答一个分析问题，缺失/超限整单拒绝 | `_validate_expert_node_granularity` |
| 问数节点轮次 | 固定工作流由运行时约束为最多 4 轮，失败项最多补查一次 | `_DEFAULT_EXPERT_NODE_LIMITS` + 固定工作流 |
| 禁止越权 | DAG 禁止 report 子节点（报告父 Agent 是唯一成稿者），禁止子节点再次编排 | 模式白名单 + 工具边界 |
| 交付粒度 | 每节点 2~3 项强耦合必交物（最多 5 项）；同域多子分析拆并行节点，总耗时 ≈ 最慢节点 | 编排说明 |

同域多节点并行是默认模式：同一领域的独立子分析拆成多个同 mode 节点并行；只有必须共享同一份中间计算状态才允许合并。分析图表要求在子节点的 goal/task_contract 中声明、随节点并行产出，父 Agent 只复用排版，禁止 DAG 完成后串行补图。

## 三、第二层：执行引擎 WorkflowCoordinator

`backend/app/agent/workflow/coordinator.py`。DAG 定义经 `WorkflowDefinition.from_mapping` 校验（节点唯一、依赖存在、无环，`WorkflowGraph.validate`），由协调器确定性执行。

### 3.1 调度循环

- `WorkflowGraph.ready_tasks()`：依赖全部 succeeded 的 pending 节点进入就绪集；
- `WorkflowConcurrencyGovernor`（默认并发 4，可配 1~8）限制同时运行的节点数；
- 任一节点失败 → 整图 failed，未启动节点标记 cancelled；全部成功 → workflow succeeded；
- 每次状态变更通过 `persist` 回调写完整快照（存入父会话 metadata 的 `workflow_coordinators`），支持中断恢复。

### 3.2 重试：续用子会话 + 预算扩容

节点失败自动重试（`max_attempts` 默认 2），两个关键机制：

- **会话续用**：重试沿用上次的子 agent 会话，失败原因与已交付文件清单写入上下文（"在其基础上修正，不要从零重做"），保住已有工作；
- **预算扩容**：重试轮的 `max_iterations` 与 `timeout_seconds` 放大 50%（迭代封顶 120、超时封顶 1 小时）。首试保持紧凑预算，把余量留给重试，避免"同预算重试→再失败→累计更久"的浪费模式。

### 3.3 血缘与结果协议

节点结果必须通过血缘校验（`lineage.py`）：`task_id`、依赖列表与 `require_lineage` 信封校验，防止节点结果张冠李戴。专家节点的结果按 `result_envelope`（status/summary/evidence/uncertainties/artifacts/data_gaps）结构化返回，编排模型据此整合结论，不做重复全量复核。

### 3.4 结果缓存

同 workflow 重提时，`result_cache.py` 按输入指纹（payload + 依赖结果指纹）复用已成功节点——依赖闭包完整才复用，部分失败的结果不写缓存。配合快照恢复，长工作流的重试成本大幅降低。

### 3.5 可观测性与取消

- `journal.py`：事件（workflow.started / node.started / node.succeeded / node.failed / retry_budget_expanded 等）落 SQLite，fail-soft 不影响执行；
- `call_sub_agent` 持久化子会话执行事件（工具调用/结果，带 trace_id），供前端实时呈现；
- `registry.py`：进程内活动协调器注册表，支持协作式取消（API 可取消运行中的工作流）；
- 前端 `WorkflowPanel.vue` 按节点状态与业务阶段名展示故事线，子 agent 轨迹以会话形式呈现。

## 四、第三层：问数子 agent 的固定工作流

**问数节点（query 系）内部执行代码固化的三阶段流程**（`mode_workflows.py`），模型只能选择查询参数，阶段推进、工具可见性、重试边界、交付边界全部由运行时控制。

### 4.1 三个阶段

| 阶段 | 轮次 | 约束 |
|---|---|---|
| **acquire 批量取数** | 最多 2 次 | 一轮内发出全部独立查询；同库数据用一条合法 JOIN/UNION/CTE；禁止多语句 SQL、禁止取数前逐表探查或健康检查；0 行属于"无数据"，如实说明缺口，不怀疑表结构不重查；失败只补查失败项、不重查成功项 |
| **normalize 可选归一化** | 1 次 | 仅在确需合并/质量统计时用一次 `execute_python`；禁止新增数据源查询；读取类动作（`read_session_resource`）不推进阶段也不消耗轮次 |
| **deliver 交付** | 1 次 | 禁用一切工具，交付 file_path、字段说明、口径、记录数与缺口；不做机制分析 |

### 4.2 监测问数按层级拆分

| 模式 | 定位 | acquire 工具面 |
|---|---|---|
| `query_monitoring_station` | 站点层级：国控站小时/日历史、乡镇站与中台口径 | `execute_crawler_sql_query` + `xuchang_station_catalog` + `query_airdata_platform`（国控站直接 SQL 查采集库；乡镇站编码不可猜，先目录解析编码再查中台） |
| `query_monitoring_city` | 城市层级：城市小时/日/年均值、发布历史、全国对比 | `query_xcai_city_history`、`execute_sql_query`、`execute_crawler_sql_query`、`execute_postgres_sql_query`、`query_airdata_platform`、`airdata_calc_report_summary`、`query_national_city_air_quality` |
| `query_monitoring` | 层级混合兜底 | 原 9 个工具；**报告 DAG 已禁用**，仅限非报告父模式直接委托 |
| `query_forecast` | 气象实况/预报与空气质量预报 | `get_weather_data`、`get_current_weather`、`get_weather_forecast`、`query_airdata_platform`、`xuchang_station_catalog`、`resolve_station_geo`、`execute_postgres_sql_query` |

### 4.3 运行时如何强制（阶段门控）

子 agent 运行时（`agent_runtime.py`）对有固定工作流的模式施加四重约束：

1. **轮次封顶**：迭代上限压缩为三阶段轮次之和（4 轮）；
2. **工具白名单按阶段过滤**：每轮只暴露当前阶段允许的工具 schema，阶段外调用直接拦截（`fixed_workflow_tool_not_allowed`；`submit_result` 结构化交付工具全阶段放行）；
3. **阶段推进由代码判定**：`observe_tool_results` 按工具结果推进——成功批次立即推进，acquire 失败批次只给一轮修复；normalize 只认"动手"工具（`execute_python`/`write_file`/`publish_session_file`）为推进信号；
4. **禁止提前完结**：acquire 阶段的纯文本回复被拒（`fixed_workflow_phase_incomplete`），必须先完成取数。

同时每轮注入当前阶段提示（`render_phase_prompt`，含"第 X/Y 次机会"），采集库表字段契约（`data_table_contracts.yaml`，由 information_schema 生成）按层级注入 acquire 阶段说明，避免模型猜字段。

## 五、target_mode 契约与路由

`target_mode_contract.py` 是子 agent 能力/工具边界的单一事实来源，注入 `run_agent_workflow` 与 `call_sub_agent` 的工具说明，供编排模型按"问题 → 模式"路由：

- 机制/成因 → `expert`；气象研判 → `expert_meteorology`；六参数/AQI/时空对比 → `expert_analysis`；
- 站点/城市/预报取数 → 对应 query 系模式（见上表）；成稿 → `report`；图表/画板/PPT/知识/运维/助手/社交各有边界；
- 同一数据源已有上游节点产出的，必须通过 `dependencies` 复用其 file_path，禁止重复取数。

## 六、资源交接与 data_shape

### 6.1 上游产物复用

依赖节点启动时（`resource_handoff.py`），上游产出的文件与会话资源被登记进子会话的资源目录并授权访问（`set_authorized_input_paths`），上下文注入两块内容：

- **上游产物清单**（可直接复用的 file_path / session resource，附 `data_shape` 形状行）；
- **上游结论摘要**（result_envelope 的 summary/evidence/uncertainties/data_gaps，不带原始工具轨迹）。

### 6.2 data_shape 元数据

`data_shape.py` 为外置数据文件生成"列名/类型/行数"形状元数据：SQL 工具库侧精确类型优先（采集库走表契约 YAML，PG/KingbaseES 走 information_schema 缓存，SQL Server 走线程池查询），派生列样本推断兜底。形状随工具结果进 LLM 上下文（经 `compact_shape` 截断为前 12 列 + `columns_total` 总列数）、落 `.data_shape.json` sidecar、随 DAG 资源交接流转，下游模型不再凭记忆猜列名。

## 七、子 agent 运行时的其他约束

- **思考策略**（`llm_thinking_policy.py`）：按模型档位（flash 关 / pro 开）与调用方类型（子 agent 一律关）决定 scnet/go 网关是否关闭慢思考——轮间慢思考会击穿节点墙钟预算；
- **工具面按模式白名单**（`tool_registry.py`）：问数模式不配 `read_file`，读上游结果用 `read_session_resource`；`describe_table` 参数对问数模式隐藏（形状已随结果注入）；`execute_python` 的手册引用对问数模式剥离（问数直接写脚本）；
- **专家节点结构化交付**：带 `result_schema` 的节点自动注入 `submit_result` 工具，另有独立的结构化修复轮（同会话内修正，不占节点重试预算）。

## 八、关键文件索引

| 文件 | 职责 |
|---|---|
| `backend/app/tools/agent_tools/run_agent_workflow.py` | 编排入口：DAG 校验、粒度校验、节点执行器、缓存、持久化 |
| `backend/app/tools/agent_tools/call_sub_agent.py` | 子 agent 调用：会话隔离/续用、事件持久化、subagent 思考档位 |
| `backend/app/agent/workflow/coordinator.py` | DAG 协调器：调度、重试、预算扩容、血缘、快照 |
| `backend/app/agent/workflow/graph.py` | 依赖图（无环校验、就绪集）与并发信号量 |
| `backend/app/agent/workflow/mode_workflows.py` | 问数固定工作流定义与阶段推进状态机 |
| `backend/app/agent/workflow/catalog.py` | 固定工作流注册表（agent_mode / scheduled_task 两个入口） |
| `backend/app/agent/workflow/target_mode_contract.py` | 子 agent 能力契约与路由规则 |
| `backend/app/agent/workflow/resource_handoff.py` | 跨节点资源交接（目录登记 + 授权） |
| `backend/app/agent/workflow/result_cache.py` | 节点结果指纹与缓存复用 |
| `backend/app/agent/workflow/journal.py` | 工作流事件 SQLite 流水账 |
| `backend/app/agent/workflow/runtime.py` | 任务生命周期状态机（queued→running→…→终态） |
| `backend/app/agent/runtime/agent_runtime.py` | 子 agent 执行循环：阶段门控、工具过滤、推进判定 |
| `backend/app/agent/context/data_shape.py` | 数据形状元数据（生成、压缩、sidecar、缓存） |
| `backend/app/agent/prompts/tool_registry.py` | 按模式工具白名单（含问数分模式清单） |
| `backend/config/data_table_contracts.yaml` | 采集库表字段契约（scripts/generate_data_table_contracts.py 再生成） |
| `frontend/src/components/workflow/WorkflowPanel.vue` | 工作流面板：阶段分组、节点状态、子 agent 轨迹 |
