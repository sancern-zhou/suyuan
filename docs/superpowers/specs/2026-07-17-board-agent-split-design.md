# 独立画板智能体拆分设计

## 背景

当前 `chart` 模式同时负责 ECharts、静态报告图和 draw.io 可编辑画板。三类任务共享同一份长提示词、同一组工具和同一套完成逻辑，导致画板任务的关键约束被无关上下文稀释，并出现截图未投递、工具失败后仍声称成功、跨轮丢失工具失败状态等问题。

本设计将可编辑画板能力从图表模式彻底剥离，新增独立的 `board` 模式和画板智能体实例。旧的 `chart_session_*` 画板会话不迁移、不识别、不兼容。

## 目标

1. 前端模式选择器提供独立的“图表”和“画板”入口。
2. `chart` 只负责 ECharts、静态报告图和相关数据查询。
3. `board` 只负责根据文本、文档或图片创建、检查和编辑 draw.io 画板。
4. 画板修改的成功、失败、重试、附件投递和最终结果尽可能由上下文组装、工具协议和运行时状态机保证，而不是依赖系统提示词约束模型。
5. 画板模式复用现有分析接口、SSE、会话数据库、取消机制和附件上传基础设施。

## 非目标

1. 不迁移或兼容历史 `chart_session_*` 画板会话。
2. 不为画板模式提供空气质量查询、SQL、ECharts、Python、bash、文件写入或子智能体工具。
3. 不新增独立的画板 HTTP/SSE 接口。
4. 不在本次拆分中重构通用 ReAct 框架或其他 Agent 模式。

## 模式与智能体边界

### 图表模式

`chart` 保留现有数据图表能力，但移除以下画板专属内容：

- `create_drawio_board` 工具；
- draw.io prompt 和设计指南；
- `board_context` 注入；
- 画板截图自动附件；
- draw.io 会话元数据的读取、写入和恢复；
- `DrawioBoardPanel` 展示逻辑。

### 画板模式

新增公开模式值 `board` 和独立的 `board_agent_instance`。该实例复用现有 ReAct 运行框架，但拥有独立配置：

- 独立的短提示词；
- 独立工具白名单；
- 独立上下文组装策略；
- 独立意图合同；
- 独立画板工具执行账本；
- 独立完成门禁和确定性 Finalizer；
- 独立会话前缀 `board_session_*`。

## 画板工具白名单

画板模式只暴露以下工具：

1. `create_drawio_board`：创建或编辑可交互 draw.io 画板。
2. `read_file`：读取 Markdown、XML 和本地参考文件，并按需挂载历史图片。
3. `read_docx`：提取 Word 文档内容。
4. `parse_pdf`：提取 PDF 内容。
5. `list_session_resources`：发现当前会话已有文档和资源。
6. `analyze_image`：分析历史文件图片；本轮用户上传图片优先使用原生多模态输入。

工具白名单不包含数据查询、SQL、ECharts、Python、bash、文件写入、记忆写入或子智能体工具。

## Board Run Contract

在进入画板智能体循环前，由 `BoardIntentResolver` 根据当前查询、最近对话状态和当前画板状态生成机器可读合同：

```json
{
  "request_kind": "inspect | create | edit",
  "action_required": true,
  "has_current_xml": true,
  "current_xml_sha256": "...",
  "board_version": 7,
  "attachment_count": 1,
  "selected_cell_ids": ["node-1"],
  "inherited_intent": false
}
```

分类规则如下：

- 明确要求“点评、分析截图、看看哪里不好”等只读行为时为 `inspect`。
- 明确要求“创建、绘制、修改、优化、重绘、连接、移动、删除”等行为时，根据是否存在当前 XML 选择 `create` 或 `edit`。
- “继续、按这个做、执行”等省略表达继承上一轮尚未执行的画板修改意图。
- 无法确定且不存在当前画板时默认 `create`；无法确定且存在当前画板时默认 `edit`，避免把操作请求错误降级成口头回答。

合同由上下文构建器以结构化区块注入当前轮次。系统提示词只描述画板设计角色和审美方法，不承担附件投递、工具成功判定或完成状态管理。

## 上下文组装

画板上下文包含：

- `board_run_contract`；
- 当前 `board_context.current_xml`；
- XML SHA-256、画板版本、dirty 状态和更新时间；
- 当前选中节点及其 geometry；
- viewport；
- 本轮附件的名称、来源、类型和上传时间；
- 当前运行内最近一次画板工具结果；
- 跨会话持久化的最近一次画板执行回执。

XML 表示结构权威状态，截图表示视觉权威状态。上下文同时提供两者，并要求模型在分析阶段指出可见差异。权威状态的投递由代码保证，不通过“你已经看到截图”等未经验证的提示词声明替代。

### 图片附件策略

`board` 模式本轮明确上传的图片始终作为原生多模态附件发送，即使请求同时包含 `current_xml`。现有“存在 XML 就抑制初始图片”的逻辑不适用于 `board`。

附件只在实际送模后标记为 consumed。同一轮工具迭代可通过结构化历史继续工作，不重复发送大图片；如果工具显式产生新的待分析图片，则作为 pending attachment 进入下一次模型调用。

## 工具协议和预校验

`create_drawio_board` 在执行前对完整操作列表做原子预校验：

- `add`、`update` 可以从 `new_xml` 的 mxCell `id` 自动推导 `cell_id`；显式 `cell_id` 与 XML id 不一致时拒绝执行。
- `delete`、`delete_with_edges`、`update_label`、`update_style`、`move_resize` 必须解析出有效目标。
- `connect` 必须包含唯一 edge id、有效 source 和有效 target。
- `target="selected"` 只有存在选中节点时才允许。
- 所有 XML 片段必须先完成解析、ID 唯一性和端点引用校验。
- 任一 operation 失败时整批操作不落盘，避免半成品画板。

失败结果采用结构化协议：

```json
{
  "success": false,
  "error_code": "operation_cell_id_required",
  "failed_operation_index": 2,
  "field": "cell_id",
  "retryable": true,
  "summary": "第 3 个 add 操作缺少可解析的 cell_id"
}
```

成功结果必须包含：

- `changed`；
- `changed_cells`；
- `applied_operations`；
- `current_xml` 或可读取的 XML 引用；
- `xml_sha256`；
- `version`；
- `operation`。

## 运行时执行账本和完成门禁

每个 board run 维护 `BoardToolLedger`，记录所有 `create_drawio_board` 调用的输入摘要、结果、错误码、前后 XML hash 和版本。

### Inspect

`request_kind=inspect` 时允许不调用画板工具。最终事件明确携带 `board_modified=false`，前端不刷新画板版本。

### Create/Edit

`action_required=true` 时：

1. 未调用画板工具的纯文本完成请求被运行时拒绝，并注入 `board_action_required` observation 继续循环。
2. 工具返回可重试失败时，将结构化错误回灌下一轮，要求模型只修正失败参数。
3. 工具成功后重新读取产物 XML，执行 XML 校验并核对返回 hash。
4. 只有工具成功、XML 校验通过且结果已进入执行账本，运行时才允许完成。
5. 连续失败达到配置的重试上限后停止循环，并由专用 Finalizer 返回失败结果。

工具失败事件及其错误码会以压缩形式持久化到下一轮 LLM 历史，不能只保存模型的自然语言最终答复。

## Board Finalizer

修改型请求不使用模型自由生成最终成功说明。`BoardFinalizer` 根据执行账本中最后一个已验证成功结果生成确定性响应，包含：

- 是否实际改变画板；
- 实际应用的操作数量；
- 实际变更的 cell id；
- 新版本和 XML hash；
- 画板标题。

如果结果为 no-op，明确说明目标内容已是期望状态。失败时输出最后错误码、失败步骤和画板未更新的事实。Finalizer 不根据模型文本推断成功。

## 前端设计

### 模式入口

模式选择器新增“画板”，内部值为 `board`。原“图表”入口保持，二者拥有独立的新会话状态。

- `chart` 新会话使用现有图表会话规则。
- `board` 新会话使用 `board_session_*`。
- 不根据旧会话元数据自动切换模式。

### 面板和请求

`DrawioBoardPanel` 只在 `board` 模式展示。每次请求发送：

- 用户文本；
- 本轮附件；
- `board_context.current_xml`；
- selected cells；
- viewport；
- version、dirty、updated_at；
- 上一轮前端执行回执。

### 结果处理

- `inspect` 结果只更新消息区。
- `create/edit` 成功结果只有在新 hash 或版本与当前状态不同时才刷新画板。
- 失败结果保留当前画板，不提升版本，并展示结构化错误摘要。
- `chart` 模式不构建或发送 `board_context`，也不加载 draw.io 面板。

## 会话持久化

`drawio_board` 元数据只在 `mode=board` 时读取、写入和恢复。持久化内容包括当前 XML 或 XML 引用、hash、版本、标题、更新时间和最近一次执行回执。

旧 `chart_session_*` 即使包含 `drawio_board` 元数据，也继续按普通图表会话处理，不迁移、不恢复画板。

## 错误处理

1. 缺少当前 XML 的 `edit` 请求转换为结构化不可执行结果，不使用历史 XML 猜测。
2. XML 非法、ID 冲突、端点缺失和 operation 参数错误在工具落盘前返回。
3. 可重试错误进入下一轮；不可重试错误直接由 Finalizer 返回。
4. 前端画板版本冲突时拒绝覆盖，并提示用户重新提交当前画板状态。
5. 附件无法读取时，`inspect` 明确说明无法完成视觉检查；`create/edit` 可在仅依赖 XML 时继续，否则失败退出。
6. 所有失败路径保持原 XML、hash 和版本不变。

## 测试策略

### 后端单元测试

- `board` 模式拥有独立工具白名单，`chart` 不再包含 `create_drawio_board`。
- board prompt 不包含 ECharts、SQL 和空气质量工作流。
- `BoardIntentResolver` 覆盖 inspect、create、edit 和继承意图。
- 存在 current XML 时，本轮上传图片仍进入原生多模态消息。
- `add/update` 从 `new_xml` 推导 id，显式 id 冲突时失败。
- operations 原子预校验和结构化错误字段正确。
- 修改合同下无成功工具结果不能完成。
- 工具失败可重试，达到上限后确定性失败。
- 成功 Finalizer 只使用账本中的已验证字段。
- 工具结果压缩后仍保留 success、error_code、hash 和 version。

### 后端集成测试

- `/api/agent/analyze` 接收 `mode=board` 并选择独立实例。
- board 会话正确保存和恢复 draw.io 元数据。
- chart 会话不读取、写入或恢复 draw.io 元数据。
- 成功工具结果更新版本；失败不改变持久化状态。

### 前端测试

- 模式选择器同时展示“图表”和“画板”。
- board 新会话使用 `board_session_*`。
- 只有 board 模式发送 `board_context` 和显示 `DrawioBoardPanel`。
- chart 模式不上传画板快照。
- inspect 不刷新画板；成功变更按 hash/version 刷新；失败保留原状态。
- 旧 chart 会话不会自动恢复成 board。

### 回归验证

- 现有 ECharts 和静态报告图流程在 chart 模式继续通过。
- 现有 query、report、assistant、expert、ops、graph 和 social 模式行为不变。
- draw.io XML 创建、编辑、选中元素操作和持久化测试继续通过，并迁移为 board 模式语义。

## 验收标准

1. 用户可从前端明确选择“画板”，并创建 `board_session_*` 会话。
2. board 模式上下文中不再出现大段 ECharts 或无关数据查询规则。
3. chart 模式不能调用 `create_drawio_board`，也不发送 `board_context`。
4. 用户上传截图并携带当前 XML 时，模型请求同时包含该截图和 XML 状态。
5. 修改型请求未成功执行画板工具时，系统不能返回成功完成。
6. 工具失败后能够根据结构化错误修正重试；最终失败时明确说明画板未变化。
7. 成功回复中的变更节点、操作数、版本和 hash 与真实工具结果一致。
8. 后端和前端相关测试在项目指定的 `backend_py311` 环境中通过。
