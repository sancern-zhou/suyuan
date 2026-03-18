# 智能 Agent 优化实施指南

> 目标：在保持既有 **ReAct / ReWOO 双策略**、**Reflexion 反思机制**、**规范化数据流** 与 **异步并发能力** 的基础上，进一步释放 LLM 的自主规划和工具泛化能力，同时保证数据一致性与可维护性。

---

## 1. 现状综述

| 能力 | 现有实现 | 价值 |
| ---- | -------- | ---- |
| ReAct & ReWOO | `backend/app/agent/react_agent.py` 通过 `plan_mode` 切换循环 / 规划执行；`backend/app/agent/core/rewoo_executor.py` 支持任务拆解与并行步骤 | 简单任务快速完成，复杂任务可整体规划 |
| Reflexion 反思 | `backend/app/agent/core/loop.py` 内置 `ReflexionHandler`，失败后可自我诊断并重试 | 提升失败恢复率，减少人工干预 |
| 数据规范链路 | `CLAUDE.md` 定义 “查询 → 统一 Schema → 分析 → 可视化”，`app/schemas/*` & `DataContextManager` 负责类型校验 | 确保跨工具数据语义一致 |
| 异步并发 | `asyncio.gather` + Semaphore 控制，详见 `backend/AGENT_ENHANCEMENTS_SUMMARY.md` | 对 IO 密集型调查可显著缩短耗时 |

**关键痛点**

1. LLM 在首次调用工具时必须一次性满足严格 schema，稍有偏差即报错，违背“宽进严出”原则；
2. 只有 PMF/OBM 具备“自动加载 data_ref”能力，其余数据密集工具需要 LLM 手动处理大数组；
3. 工具注册分散（`global_tool_registry`、`services.lifecycle_manager`、`tool_adapter` 各自维护），新增能力成本高；
4. 缺少模式自适应及数据驱动的指标，难以判断何时启用 ReAct / ReWOO、并发度多少、Reflexion 是否生效。

---

## 2. 优化原则

1. **宽进严出**：对 LLM 入口宽容（容错、补全、兜底），在流入统一数据层之前再做严格类型校验；
2. **数据句柄化**：所有大数据统一通过 `DataContextManager` 暴露句柄（handle），工具内部负责加载、抽样与验证；
3. **单一注册源**：任何工具只需在一个注册点声明，即自动同步到 LLM 描述、后端路由与测试；
4. **自适应策略**：让 Agent 根据任务规模、历史表现自动选择 ReAct / ReWOO、并决定并发策略；
5. **可观测性**：所有优化都需要配套指标（工具失败率、Reflexion 成功率、handle 命中率等）以持续迭代。

---

## 3. 优化蓝图

### 3.1 工具输入适配层（Input Adapter）

#### 3.1.1 设计目标

1. **强泛化**：以规则驱动为主，避免在单个工具上写硬编码；
2. **宽进严出**：允许 LLM 输出近似正确的自然语言/半结构化输入，由适配层完成标准化；
3. **可解释**：每次自动修正都要形成记录，便于日志与 Reflexion 回溯；
4. **可扩展**：新增字段类型（时间区间、地理坐标、污染物编码等）时，只需挂载新的 Normalizer。

#### 3.1.2 模块结构

```
ToolExecutor
 └─ InputAdapterEngine
     ├─ RuleLoader        # 从注册表读取规则
     ├─ Normalizers       # 字段别名、单位换算、时间解析、地理转换等
     ├─ Inferencers       # 缺省值、上下文/历史记忆推断
     ├─ Validators        # Pydantic + 自定义表达式
     └─ Reporter          # 输出修正日志 / 结构化错误
```

- `InputAdapterEngine` 在 `ToolExecutor.execute_tool` 入口执行，输入 `raw_args`、`tool_name`，输出 `normalized_args` 与 `adapter_report`；
- `Normalizers` 以插件形式注册，可复用在所有工具；
- `Inferencers` 可以获取 `ExecutionContext`、`HybridMemoryManager`（如最近一次城市、默认时间窗口）；
- `Reporter` 负责记录每个字段的修正原因，写入日志并返回给 Reflexion。

#### 3.1.3 规则配置示例

规则采用 YAML/JSON，随工具注册生成：

```yaml
tool: get_air_quality
fields:
  city:
    aliases: ["城市", "location", "city_name"]
    required: true
    normalizers:
      - type: lookup
        dict: amap_city_aliases
  pollutant:
    aliases: ["污染物", "target"]
    type: enum
    enum: ["PM2.5","PM10","O3","NO2","SO2","CO"]
    fallback: last_success.pollutant
  start_time:
    type: datetime
    default:
      strategy: relative
      offset_hours: -24
  end_time:
    type: datetime
    default:
      strategy: now
constraints:
  - expression: "end_time > start_time"
    on_fail: adjust_end_time(+1h)
```

要点：
- `aliases`、`normalizers` 允许 LLM 用不同描述；
- `fallback` 可以引用长期记忆或最近一次成功调用；
- `constraints` 支持表达式，失败时可自动更正或返回提示；
- 规则可多层继承（全局 → 工具 → 版本），满足不同模型或环境。

#### 3.1.4 执行流程

1. **字段映射**：解析 `aliases`，统一字段名；
2. **类型/单位转换**：依次调用 Normalizers（时间解析、单位换算、地理坐标验证等）；
3. **缺省推断**：调用 Inferencers 填充缺失字段（如 query 中解析到的地点、默认时间）；
4. **业务校验**：Pydantic schema + `constraints` 双重校验，保证“严出”；
5. **生成报告**：Reporter 记录所有修正项与原因；
6. **返回结果**：成功则输出 `normalized_args` + `adapter_report`，失败则抛出结构化错误。

#### 3.1.5 失败与自愈

当无法满足校验时统一返回：

```json
{
  "success": false,
  "error_code": "INPUT_VALIDATION_FAILED",
  "expected_schema": {...},
  "detected_args": {...},
  "missing_fields": ["pollutant"],
  "suggested_call": "get_air_quality(city='广州', pollutant='O3', ...)"
}
```

- `ReflexionHandler` 根据 `missing_fields`、`suggested_call` 引导 LLM 自修正；
- 可自动修复的错误（例如时间范围顺序颠倒、单位混用）直接在适配层处理并写入 Reporter。

#### 3.1.6 泛化保障措施

1. **可插拔处理器**：Normalizers/Inferencers 通过注册表动态加载，新类型无需改动核心代码；
2. **规则版本化**：支持按模型或环境加载不同规则，便于灰度；
3. **统计反馈**：Reporter 输出修正率、失败率，驱动规则调整；
4. **测试基线**：每个工具新增“模糊输入→期望输出”的单测，确保适配层持续有效。

- **落地步骤**
  1. 在 `app/agent/core/executor.py` 中新增 `InputAdapterEngine`，所有工具调用前执行规范化；
  2. 通过工具注册自动生成规则（详见 3.3），字段别名/单位/默认值均在配置中声明；
  3. 当仍无法满足要求时，返回结构化错误（`expected_schema` + `suggested_call`），交由 `ReflexionHandler` 处理，并把 `adapter_report` 写入日志指标。

### 3.2 数据句柄治理

- **统一入口**：扩展 `DataContextManager`，工具返回数据时自动决定是否外置（依据大小、Schema），并生成 `handle_id`；
- **自动回填**：增强 `MemoryToolsHandler.register_memory_tools`，凡声明 `returns_big_data=True` 的工具会自动生成“加载+校验”包装，LLM 只需传入 `handle_id`；
- **抽样与裁剪**：保存摘要（字段统计、样本数据）供 Planner 使用，真正操作大数据前才加载完整内容；
- **收益**：LLM 不必处理大型 JSON；数据流仍保持 `CLAUDE.md` 要求的统一 Schema。

### 3.3 工具单一注册源

- **Registry 设计**
  - 继续沿用 `app/tools/base/registry.py`，但新增元数据：`input_adapter_rules`、`return_schema`、`requires_handle`、`supports_batch` 等；
  - 注册时自动：
    1. 生成 LLM Function schema（供 `tool_adapter` 使用）；
    2. 输出测试样例（pytest fixture）；
    3. 更新输入适配器配置。
- **整合步骤**
  1. 清理 `services.lifecycle_manager.py` 的重复注册，只保留一个 registry；
  2. `tool_adapter` 改为直接读取 registry 导出的 schema；
  3. 提供 CLI（例如 `python scripts/register_tool.py --name ...`）辅助新增，降低学习成本。

### 3.4 策略自适应

- **Mode Selector**：新增模块，根据 `query_length`、`历史失败次数`、`工具数量`、`预估成本` 来自动选择 ReAct / ReWOO；默认策略：
  - 简单查询或历史已有成功策略 → ReAct；
  - 多数据源 + 历史失败率高 → ReWOO；
  - 失败后可切换模式并记录在长期记忆中。
- **并发控制**：引入基于任务特征的动态 semaphore（例如城市级查询使用 5，区域级使用 3），并记录调度指标。
- **Reflexion 触发条件**：引入冷却策略，避免在同一错误上无限反思，可借助失败类型标签（输入不合规、工具超时、数据缺失等）决定是否启用。

### 3.5 可观测与反馈

- **指标面板**
  - 工具调用成功率 / 自动修复占比；
  - Handle 命中率、平均加载体积；
  - 模式切换统计（ReAct vs ReWOO）；
  - Reflexion 成功率；
  - 并发任务平均耗时。
- **日志增强**
  - 在 `structlog` 事件中加入 `adapter_corrections`, `handle_id`, `mode_selected` 等字段；
  - 提供 `scripts/analyze_agent_logs.py`，用于快速汇总指标。

---

## 4. 实施路线图

| 阶段 | 目标 | 关键任务 | 交付物 |
| ---- | ---- | -------- | ------ |
| Phase 1 | 入口容错 | 实现 InputAdapter、结构化错误提示、Reflexion 对接 | `executor.py` 扩展、测试用例 |
| Phase 2 | 数据句柄化 | 扩展 `DataContextManager`、`MemoryToolsHandler`、handle 抽样策略 | Handle API、更新工具包装 |
| Phase 3 | 注册治理 | Registry 元数据扩展、CLI、自动 schema & 测试生成 | 新注册流程文档、示例工具 |
| Phase 4 | 策略自适应 | Mode Selector、动态并发、Reflexion 冷却 | 选择逻辑 + 指标输出 |
| Phase 5 | 可观测性 | 指标埋点、分析脚本、可视化面板 | Dashboard、报警阈值 |

每个阶段结束前需运行以下回归：
1. `pytest backend/tests -m "not slow"`；
2. `python test_unified_data_flow.py`；
3. 并发压测脚本（至少 3 并发请求，验证模式切换与句柄命中率）。

---

## 5. 协同与职责建议

- **Agent 架构组**：负责 InputAdapter、Mode Selector、Reflexion 策略调整；
- **数据与工具组**：维护 DataContextManager、统一 Schema、工具注册 CLI；
- **平台与 SRE**：建设指标面板、压测脚本、报警体系；
- **前端 / 体验组**：根据新指标展示 ReAct/ReWOO 选择、数据句柄状态、Reflexion 次数等，让用户理解 Agent 的决策过程。

---

## 6. 后续跟踪指标

1. 工具调用平均失败率 < 5%，其中输入不合规导致的失败需下降 50%；
2. 80% 以上的大数据调用走 handle 流程，LLM 本身不再传入超大 JSON；
3. ReAct/ReWOO 模式自动选择准确率 > 70%（以人工标注的最优方案为基准）；
4. Reflexion 成功修复率 ≥ 40%，且平均反思次数 ≤ 2；
5. 关键场景（城市级污染溯源）端到端耗时减少 30% 以上。

通过上述指南，可以在保持严谨数据规范的同时，最大化 LLM 与 Agent 的协同效率，为后续功能扩展提供可复制的落地路径。***
