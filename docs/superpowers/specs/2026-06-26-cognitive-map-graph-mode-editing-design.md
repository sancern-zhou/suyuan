# 认知地图 Graph 模式对话编辑设计

## 背景

当前认知地图已经支持文件上传、构建、实体/关系展示、审核状态、发布，以及后端实体/关系的增删改查和合并接口。缺口在于：地图生成后，用户无法通过多轮自然语言对话持续修正图谱内容。

本设计不新增独立图谱编辑聊天系统，也不新增专用图谱工具。第一阶段复用现有 ReAct Agent 架构和现有工具能力，新增一个 `graph` Agent 模式，并在认知地图面板右侧提供“对话编辑”入口。Graph 模式通过现有工具读取上下文、调用现有 REST API、生成修改摘要，并把最终变更落到当前认知地图。

## 目标

- 在认知地图面板右侧提供多轮对话编辑入口。
- 新增 `graph` Agent 模式，复用 `/api/agent/analyze` SSE 流程。
- 复用现有文件工具和执行工具，不新增专用图谱工具。
- 通过现有认知地图 REST API 修改实体和关系，保留校验、清洗、评估刷新和审核状态。
- 支持用户通过多轮表达逐步完成实体合并、实体修正、关系新增、关系修正和关系删除。
- 保持图谱编辑行为可解释：每次落盘前给出拟执行变更，落盘后返回结果摘要。

## 非目标

- 第一阶段不做独立权限管理系统。
- 第一阶段不新增 `cognitive_map_*_edit` 专用 LLM 工具。
- 第一阶段不自动从运维诊断结论沉淀图谱。
- 第一阶段不把 Graph 模式放到全局顶部模式栏。
- 第一阶段不要求 Agent 支持任意复杂批量重构图谱。
- 默认不允许 Agent 直接编辑 `extraction.json`、`map.json`、`evaluation.json` 等内部文件。

## 用户体验

认知地图面板右侧增加“对话编辑”区域。用户必须先选择或进入某张认知地图，系统才显示 Graph 对话入口。

典型流程：

```text
用户：把零漂和零点漂移合并。
Agent：找到两个候选实体，建议将“零漂”合并到“零点漂移”，保留“零漂”为别名。是否确认？
用户：确认，描述里补充这是分析仪零点漂移异常。
Agent：调用现有合并接口和实体更新接口，完成修改。已刷新图谱，新增别名 1 个，更新描述 1 条。
```

当目标不唯一时，Agent 必须先澄清：

```text
用户：删除这条关系。
Agent：当前上下文中有 2 条候选关系：A -> causes -> B、A -> related_to -> C。请指定删除哪一条。
```

## 前端设计

### 入口位置

在 `CognitiveMapPanel.vue` 的右侧管理抽屉中加入 `graph-chat` 区域，作为当前地图的内嵌 Agent 对话入口。它可以作为一个新 tab，也可以固定在右侧抽屉底部。第一阶段推荐新 tab，避免挤压实体、关系、证据详情。

入口只在存在 `currentMap` 时可用。没有当前地图时不允许发送消息。

### 请求方式

复用现有 `reactApi.analyze()`。发送时固定：

```json
{
  "mode": "graph",
  "map_context": {
    "active_map_id": "map_xxx",
    "active_map_name": "xxx",
    "selected_item": {
      "kind": "entity | relation | null",
      "id": "entity_xxx",
      "name": "零点漂移"
    },
    "visible_entity_ids": ["entity_a", "entity_b"],
    "visible_relation_ids": ["relation_a"],
    "entity_count": 20,
    "relation_count": 35
  }
}
```

`map_context` 不需要塞入完整图谱。完整实体、关系、证据由 Agent 通过现有 API 或文件读取方式按需获取。前端只传当前地图和当前 UI 选择状态，解决多轮指代中的“这个节点”“这条关系”问题。

### 前端状态

Graph 对话应使用独立的 `graph` mode session，不污染 `query`、`ops`、`assistant` 等模式消息。

需要扩展：

- `VALID_MODES` 增加 `graph`。
- `modeStates` 增加 `graph`。
- `activeSessionByMode` 支持 `graph`。
- `reactApi.analyze()` 已支持 `mode` 和 `map_context`，无需新协议。

Graph 模式不展示在顶部全局 `AgentModeSelector`，而是由认知地图面板内部启动。这样可以保证每次调用都有 `active_map_id`。

### 刷新机制

Agent 应用修改后，最终答案或工具结果中应包含稳定标记：

```json
{
  "cognitive_map_updated": true,
  "map_id": "map_xxx",
  "changed_entities": ["entity_a"],
  "changed_relations": ["relation_b"]
}
```

前端检测到该标记后刷新当前地图详情和图谱查询结果。第一阶段也可以在每次 Graph 对话完成后保守刷新当前图谱，减少事件协议改造。

## 后端设计

### Graph 模式

在工具注册中新增 `GRAPH_TOOL_NAMES` 和 `GRAPH_TOOL_ORDER`，但不新增新工具。

推荐第一阶段工具集：

```python
GRAPH_TOOL_NAMES = {
    "cognitive_map_guidance",
    "read_file",
    "grep",
    "list_directory",
    "search_files",
    "execute_python",
}
```

如实际部署中 `execute_python` 无法稳定调用本机 REST API，可临时加入 `bash` 用 `curl` 调用，但 prompt 必须限制其用途：只允许调用认知地图 API，不允许执行任意破坏性命令。

### Graph Prompt

新增 Graph 模式系统提示词，核心规则：

1. 你是认知地图编辑 Agent，只处理当前 `map_context.active_map_id` 对应地图。
2. 多轮对话中要利用历史消息和当前 `map_context.selected_item` 解析“它”“这个节点”“这条关系”等指代。
3. 修改前必须先输出拟执行变更；目标不唯一时必须追问。
4. 用户明确确认后，优先通过现有 REST API 修改图谱。
5. 禁止默认直接编辑 `extraction.json`、`evaluation.json`、`map.json`。
6. 只有当 REST API 不支持目标操作，且用户明确同意兜底风险时，才允许考虑文件级修改。
7. 修改后必须返回变更摘要、影响的实体/关系、是否需要重新发布。

Graph prompt 应内置现有 API 使用说明：

```text
GET    /api/cognitive-maps/{map_id}/entities
POST   /api/cognitive-maps/{map_id}/entities
PATCH  /api/cognitive-maps/{map_id}/entities/{entity_id}
POST   /api/cognitive-maps/{map_id}/entities/{entity_id}/merge
DELETE /api/cognitive-maps/{map_id}/entities/{entity_id}
GET    /api/cognitive-maps/{map_id}/relations
POST   /api/cognitive-maps/{map_id}/relations
PATCH  /api/cognitive-maps/{map_id}/relations/{relation_id}
DELETE /api/cognitive-maps/{map_id}/relations/{relation_id}
GET    /api/cognitive-maps/{map_id}/evidence
GET    /api/cognitive-maps/{map_id}/evaluation
```

### REST API 调用方式

不新增工具时，Graph Agent 可通过 `execute_python` 调用现有 REST API。推荐 prompt 中给出固定模式：

```python
import json
import os
import urllib.request

base_url = os.environ.get("INTERNAL_API_BASE_URL", "http://127.0.0.1:8000/api")
url = f"{base_url}/cognitive-maps/{map_id}/entities"
```

如果当前服务没有稳定的内部访问地址，需要在后端运行配置中提供 `INTERNAL_API_BASE_URL`。这属于环境配置，不属于新工具。

### 数据一致性

Graph Agent 不直接改 JSON 文件的原因：

- 现有 API 会调用 `_save_extraction()`。
- `_save_extraction()` 会清理无效关系和重复关系。
- 评估数据会通过 `_generate_evaluation()` 更新。
- 实体合并会重写相关关系端点。
- 删除实体会同步移除相关关系。

因此 Graph 模式必须把 REST API 作为默认写入通道。

## 多轮编辑策略

### 上下文来源

多轮编辑上下文来自四处：

- 当前 Agent session 历史消息。
- 当前前端 `map_context`。
- 当前图谱实体、关系和证据列表。
- 上一轮 Agent 输出的拟执行变更。

不新增单独的 edit-session 存储。第一阶段依赖现有 session memory 即可。

### 指代解析

解析优先级：

1. 当前 `map_context.selected_item`。
2. 上一轮拟执行变更中的目标实体/关系。
3. 最近一轮用户和 Agent 明确提到的实体/关系名称。
4. 当前地图实体 `name`、`canonical_name`、`aliases` 精确匹配。
5. 关系三元组匹配：源实体、关系类型、目标实体。
6. 模糊匹配仅用于列候选，不可直接落盘。

### 支持的 MVP 意图

第一阶段只支持：

- `merge_entities`
- `update_entity`
- `create_relation`
- `update_relation`
- `delete_relation`

实体删除风险更高，第一阶段可以只允许删除关系；实体删除需二次确认，并提示会移除相关关系。

### 确认规则

以下场景必须等待用户确认：

- 合并实体。
- 删除实体或关系。
- 修改已发布实体/关系。
- 批量变更多于 1 条。
- 置信度不足或存在多个候选目标。

以下场景可以在用户明确命令中直接执行：

- “把实体 A 的别名加上 B”
- “把这条关系状态改为 rejected”
- “将描述改为……”

即使直接执行，也必须在最终答案中列出变更。

## 文件工具使用边界

Graph 模式可以使用文件工具读取：

- 上传语料文件。
- `files.json`。
- `extraction.json`，仅用于排查 API 查询不足或调试。
- 相关文档证据。

Graph 模式默认不使用文件工具写入：

- `extraction.json`
- `evaluation.json`
- `map.json`
- `build_runs.json`
- `agent_bindings.json`

如果未来要开放文件级修复，应放到权限管理之后，并要求显式管理员确认。

## 错误处理

- 当前没有 `active_map_id`：前端禁止发送；后端 prompt 也要求 Agent 返回需要选择地图。
- API 返回 404：Agent 应重新拉取实体/关系列表，提示目标可能已被修改或删除。
- 目标不唯一：返回候选列表，请用户选择。
- API 修改失败：返回错误原因，不尝试自动改 JSON 文件。
- 修改完成但刷新失败：提示用户修改已完成，可手动刷新。

## 测试计划

### 后端测试

- `get_tools_by_mode("graph")` 返回预期工具集。
- Graph prompt 能被 prompt builder 正确选择。
- `mode="graph"` 的 Agent 请求不会回退到其他模式工具。
- `map_context` 能进入 Agent 上下文。

### 前端测试

- 认知地图面板存在当前地图时显示 Graph 对话入口。
- 无当前地图时禁用入口。
- 发送消息时请求体包含 `mode: "graph"` 和当前 `map_context`。
- Graph 对话不污染其他模式 session。
- 对话完成后刷新当前图谱。

### 场景测试

- 多轮合并实体：提出合并、修改保留名称、确认应用。
- 修改关系类型：基于当前选中关系完成修改。
- 删除关系：要求确认后删除。
- 目标不唯一：返回候选，不落盘。
- API 失败：返回错误，不直接编辑 JSON。

## 实施顺序

1. 新增 Graph 模式枚举和前端状态。
2. 新增 Graph 模式工具集和工具排序。
3. 新增 Graph 模式 prompt。
4. 在 Agent 上下文构建中注入 `map_context`。
5. 在认知地图面板右侧添加 Graph 对话入口。
6. 对话完成后刷新当前地图。
7. 补充前后端测试。

## 后续演进

后续可以在权限管理稳定后再增加：

- 专用 `cognitive_map_propose_edit` 工具。
- 专用 `cognitive_map_apply_edit` 工具。
- 图谱变更审计表。
- proposal 列表和差异视图。
- 按用户角色限制批量编辑、删除、发布。
- 从 Agent 诊断结论自动生成图谱更新建议。
