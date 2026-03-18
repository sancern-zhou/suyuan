# 工具解析与输入适配修复方案

> 目标：纠正当前“智能响应处理器”偏离主线的实现，回归“LLM 输出 → 解析 → 校验 → 工具调用”的统一架构，确保解析器真正承担“宽进严出”的桥接职责。

---

## 1. 背景与问题

- `backend/app/agent/core/intelligent_response_handler.py` 额外实现了意图分析、工具选择等逻辑，与 `ReActLoop`/`LLMPlanner` 的职责重复，未真正融入执行链路。
- `react_prompts.py` 中虽提醒“必须输出 JSON”，但缺乏严谨示例与控制符，解析器仍无法稳定解析。
- `data_format_converter.py` 及 `ToolExecutor` 尚未集成“多策略解析 + schema 验证 + 结构化错误”机制，LLM 输出稍有偏差就掉链路。
- 解析失败缺乏自愈：没有自动提供 `expected_schema` 提示，也没有让 `ReflexionHandler` 发起重试。

---

## 2. 目标与需求

### 2.1 功能目标
1. **统一解析链路**：所有工具调用前必须经过 Input Adapter（解析 → 规范化 → 校验）。
2. **强约束输出**：Action Prompt 保证 LLM 始终以 ` ```json ... ``` ` 包裹的结构化 JSON 响应。
3. **自愈机制**：解析失败时返回结构化错误，并由 `ReflexionHandler` 发起 ReAsk。
4. **可观测性**：记录解析策略、修正字段、失败原因，支持指标分析。

### 2.2 约束与需求
- 不破坏 `ReActLoop` 与 `LLMPlanner` 的职责划分；
- 不在执行主路径中引入新的“人工规则工具选择器”；
- 所有输入适配逻辑应配置化，避免硬编码；
- 兼容 `DataContextManager`、`MemoryToolsHandler` 的 handle 流程；
- 保留原始 LLM 输出，方便调试与回放。

---

## 3. 实施方案

### Phase 1：解析器基础改造
1. **Prompt 加固**
   - 在 `backend/app/agent/prompts/react_prompts.py` 的 Action Prompt 中追加：  
     - 要求输出放在 ` ```json` 代码块；  
     - 给出完整字段示例；  
     - 说明“不得输出多余文本”。  
2. **多策略解析**
   - 重构 `backend/app/utils/data_format_converter.py`：  
     1. 规则 1：严格 JSON（带代码块剥离）  
     2. 规则 2：宽松 JSON（单引号、尾逗号、Text before/after）  
     3. 规则 3：调用 LLM 自证（可选，先留接口）  
   - 每步成功后通过 schema（Pydantic）验证，失败则继续下一策略。  
3. **结构化报错**
   - 解析失败时返回 `{error_code, raw_text, expected_schema, detected_args}`，供上层使用。  
4. **日志埋点**
   - `structlog` 增加 `parser_strategy`, `corrections`, `raw_length` 字段。

### Phase 2：Input Adapter 集成
1. 在 `backend/app/agent/core/executor.py` 的 `ToolExecutor.execute_tool` 中接入 `InputAdapterEngine`（参考 `doc/agent_optimization_plan.md` 3.1 小节）：  
   - 加载工具规则（先手工配置核心工具，后续自动生成）；  
   - 顺序执行 Field Mapping → Normalizers → Inferencers → Validators；  
   - 返回 `normalized_args` 和 `adapter_report`。  
2. 失败时抛出 `InputValidationError`，包含 `missing_fields`、`suggested_call`。

### Phase 3：ReAsk / Reflexion 对接
1. 在 `backend/app/agent/core/loop.py` 中捕获解析/校验失败的异常，将错误信息传给 `ReflexionHandler`：  
   - 生成提示：“你缺少字段 X，请以 JSON 重新输出”；  
   - 最多重试 2 次，仍失败则向用户报错。  
2. 在 SSE 调试模式下返回 `raw_response` 与 `normalized_args`，保障透明性。

### Phase 4：清理与收口
1. 评估 `intelligent_response_handler.py` 的必要性：  
   - 若其逻辑与规划/执行冲突，拆分或移除；  
   - 保留有效的统计/日志功能可迁移到工具层。  
2. 为每个核心工具编写“模糊输入 → 期望输出”的单测，确保 Input Adapter 行为稳定。  
3. 更新文档：  
   - `doc/agent_optimization_plan.md` 标记实施状态；  
   - 在 README/运维文档中说明解析器工作方式与调试方法。

---

## 4. 验收标准

1. Action Prompt 输出违反 JSON 时，解析器能自动修正或返回结构化错误；  
2. 工具调用失败日志中包含 `adapter_report`，可清晰定位字段修正；  
3. Reflexion ReAsk 触发后，LLM 能重新输出合规 JSON，并完成工具调用；  
4. 并发测试（≥3 并发）中解析成功率稳定 ≥ 95%；  
5. `intelligent_response_handler.py` 不再承担与 Planner 重复的职责，主链路清晰可控。

---

## 5. 时间与分工建议

| 阶段 | 负责人 | 预计耗时 |
| ---- | ------ | -------- |
| Phase 1 | Agent 架构组 + Prompt 负责人 | 2 天 |
| Phase 2 | Agent 架构组 | 3 天 |
| Phase 3 | Agent 架构组 + Reflexion 维护者 | 2 天 |
| Phase 4 | 架构组 + QA | 2 天 |

完成以上步骤后，即可恢复“解析器作为桥梁、LLM 专注推理、工具保持严格格式”的既定目标。***
