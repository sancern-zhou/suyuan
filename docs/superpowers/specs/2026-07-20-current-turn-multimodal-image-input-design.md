# 当前轮多模态图片输入修复设计

## 背景

系统已经使用 `SessionResourceManifest` 保存会话资源，并将最近、重要且当前工具可消费的资源引用有界地投影到 Agent 上下文。用户也可以通过 `@文件` 显式引用当前会话中的资源，Agent 可以通过 `list_session_resources` 和文件读取工具主动获取未进入当前投影预算的历史资源。

`chart`、`board` 和 `social` 三种模式支持原生多模态输入。它们还需要把本轮用户带入的图片作为原生图片内容块发送给模型，而不只是向提示词提供文件路径或资源元数据。

当前实现发生了两项相关回归：

1. Composer 在上传创建首个 session 时可能被尚未结束的异步草稿恢复覆盖，导致已经上传并登记到 Manifest 的图片没有进入本轮 `context_refs`。
2. 后端新增的 `selected_resource_projection()` 只保留显式选择资源，破坏了完整 Manifest 的自动有界投影语义。

故障会表现为图片已成功上传到同一会话，但持久化用户消息中的 `context_refs` 为空，运行时 `current_request_image_count=0`，首次模型请求不包含图片内容。

## 目标

1. 保证本轮刚上传图片和本轮通过 `@文件` 引用的历史图片稳定进入请求协议。
2. 在 `chart`、`board` 和 `social` 模式中，将本轮图片作为原生多模态附件发送给模型。
3. 恢复完整 Session Manifest 的自动有界资源投影；`@文件` 只提升优先级，不关闭自动投影。
4. 保持历史图片按需获取：未在本轮选择的历史图片不自动编码，Agent 可主动读取。
5. 对计划发送的本轮图片采用 fail-fast 校验，不静默跳过、不退化为纯文本请求。
6. 保持 base64 和图片字节不进入持久化会话历史。

## 非目标

- 不为 `assistant`、`expert`、`query`、`report`、`ops` 等非多模态模式增加原生图片输入。
- 不把 Manifest 中所有历史图片自动编码进模型请求。
- 不改变 `list_session_resources` 的历史资源发现职责。
- 不恢复已经废弃的 Web `attachments` 请求字段。
- 不重新设计通用资源生命周期、存储格式或跨会话资源授权。
- 不通过异常降级掩盖 Manifest、文件或图片构造错误。

## 语义边界

| 图片来源 | 非多模态模式 | `chart` / `board` / `social` |
|---|---|---|
| 本轮刚上传图片 | 资源引用元数据 | 原生图片附件 |
| 本轮 `@` 引用的历史图片 | 资源引用元数据 | 原生图片附件 |
| 自动投影但本轮未选择的历史图片 | 资源引用元数据 | 资源引用元数据 |
| Agent 主动读取历史图片 | 普通文件工具结果 | `read_file(as_multimodal_attachment=true)` 送入下一次模型调用 |

“本轮图片”是用户在当前请求中明确带入的图片，而不是 Manifest 中按时间推断出的任意历史图片：

- Web 请求以经过授权校验的 `context_refs` 为准；
- Social 请求以当前入站消息附件为准。

自动资源投影与原生图片附件是两条独立但共享资源身份的链路。自动投影负责资源可发现性，本轮附件负责当前模型调用的图片内容。

## 方案比较

### 方案 A：恢复完整资源投影，并单独严格解析本轮图片（采用）

完整 Manifest 继续进入现有有界投影器。本轮显式资源 ID 作为排序偏好，但不作为过滤条件。本轮选择资源另行经过严格图片解析，并只在支持原生多模态的模式进入运行时附件。

该方案保持已有架构边界，改动集中，能同时修复自动资源投影回归和当前轮图片缺失。

### 方案 B：从自动资源投影结果中提取所有图片

该方案会把自动命中的历史图片也作为原生内容发送，混淆资源可发现性和当前用户输入，增加请求体积并可能让模型误判用户指代，因此不采用。

### 方案 C：仅由前端恢复旧 `attachments` 字段

该方案绕过 Manifest 的资源授权与统一身份，也无法覆盖 `@` 历史文件和 Social 链路，会形成双协议，因此不采用。

## 架构

```text
SessionResourceManifest
        |
        +--> ResourceContextProjector
        |      输入：完整 active refs + 本轮 preferred ref IDs
        |      输出：有界资源引用文本
        |      用途：所有 Agent 模式
        |
当前轮资源
  Web: validated context_refs
  Social: inbound attachments
        |
        +--> StrictCurrentTurnImageResolver
                 |
                 +--> supports_native_multimodal(mode)
                          |
                          +--> chart / board / social
                                原生 image blocks
```

`supports_native_multimodal()` 继续作为唯一模式能力判断，模式列表保持：

```python
NATIVE_MULTIMODAL_MODES = frozenset({"social", "chart", "board"})
```

路由层、资源投影器和内容构造器不得各自复制模式列表。

## Web 数据流

### 上传

1. 输入框在需要时先创建 session ID。
2. 上传接口保存 `UploadedFile`。
3. 上传接口将文件登记为当前 session 的 `SessionResourceRef`。
4. 上传响应返回稳定的 `resource_ref.ref_id`。
5. Composer 把该引用加入本轮结构化文件选择。

上传成功意味着资源已经进入会话 Manifest，但当前轮原生图片输入仍以发送快照中的 `context_refs` 为准。

### Composer 发送

发送前形成不可变快照：

```json
{
  "query": "复刻这个架构图",
  "skill_ids": [],
  "context_refs": [
    {
      "type": "conversation_file",
      "resource_id": "stable-resource-ref-id",
      "display_name": "image.png"
    }
  ]
}
```

`display_name` 只用于展示和审计；服务端只使用 `resource_id` 定位与授权。

只有服务端接受流式请求后，Composer 才清空正文和本轮选择。请求失败时保持原状态。

### 路由解析

1. 加载当前 session Manifest。
2. 使用 `select_conversation_files()` 按提交顺序解析 `context_refs`。
3. 校验资源存在、属于当前 session、处于 `active` 状态且类型为文件或产物。
4. 将解析结果作为 `selected_resource_refs` 传给 `ReActAgent`。
5. 用户消息只把本轮显式 `context_refs` 持久化为消息元数据。

## Social 数据流

Social bridge 继续把当前入站消息媒体转换成 Agent 附件。Social 附件与 Web `selected_resource_refs` 在 `ReActAgent` 内汇合为当前轮运行时附件。

Social 不需要伪造 Web `context_refs`，但必须满足相同的严格图片校验，并且只能在 `supports_native_multimodal("social")` 为真时生成原生图片块。

## 自动资源投影

自动资源投影必须以完整 Manifest 为输入：

```python
project_session_resources(
    saved_manifest.refs,
    query=user_query,
    available_tools=available_tools,
    preferred_ref_ids=[ref.ref_id for ref in selected_resource_refs or []],
    max_chars=8000,
)
```

`preferred_ref_ids` 只改变排序。排序优先级为：

1. 本轮显式引用；
2. 当前 query 命中的资源；
3. pinned 资源；
4. high importance 资源；
5. 当前模式存在消费工具的资源；
6. 最近使用或最近登记的资源。

投影继续排除 `missing`、`invalid` 和 `superseded` 资源，并在预算截断时提示还有更多资源可通过 `list_session_resources` 查询。

必须删除或改写 `selected_resource_projection()` 的过滤语义，不能再用显式选择替代完整 Manifest。

## 当前轮图片解析

### 输入集合

严格图片解析器只接收当前轮资源：

- Web：`selected_resource_refs`；
- Social：当前入站附件；
- 工具产生的下一轮多模态附件继续走现有 `extract_multimodal_attachments()` 链路。

未在本轮选择的 Manifest 历史图片不进入该集合。

### 严格校验

对于当前轮集合中的图片，首次模型调用前必须验证：

- 资源状态为 `active`；
- MIME 类型属于支持的图片类型；
- locator 提供本地文件路径或受支持的远程 URL；
- 本地路径存在、是普通文件且可读取；
- 路径位于允许访问的存储边界内；
- 文件大小符合现有上传和模型限制；
- 同一个资源只出现一次。

非图片文件仍保留为资源上下文，但不生成 image block。

### 内容构造不变量

多模态内容构造必须满足：

```text
validated_current_turn_image_count == native_image_block_count
```

当前会静默跳过图片的路径必须改为显式失败：

- `resource_refs_to_runtime_attachments()` 不能忽略已识别为图片但缺少路径或 MIME 错误的资源；
- `_build_image_block()` 不能对已验证图片返回 `None`；
- `build_anthropic_user_content()` 不能在丢失图片块后退回纯文本。

本地图片按现有实现构造 base64 image block。base64 只存在于当前模型请求内，不进入会话消息、日志或资源 Manifest。

## Board 上下文

`board_context.current_request_images` 必须由最终已经验证并准备发送的当前轮图片生成，而不是从前端声明或 Manifest 历史推断。

其数量必须与首次模型请求中的原生图片块数量一致。这样 Board prompt 中的“当前请求图片”与模型实际视觉输入保持一致。

## Composer 竞态修复

当前 `restoreSelectionDraft()` 在异步资源加载开始时清空状态，并可能在 session 已创建、文件已上传后用旧结果覆盖新附件。

修复采用 generation guard 和原子应用：

1. 每次恢复任务获得递增 generation。
2. 恢复期间不提前清空当前 Composer 选择。
3. 异步结果只在 generation、session ID 和 mode 都仍匹配时应用。
4. 上传触发首次 session 创建时立即废止此前无 session 的恢复任务。
5. 上传中的临时附件和已完成上传的新附件不能被旧恢复结果覆盖。
6. 草稿恢复结果在校验完成后一次性替换目标 session 的选择。
7. 发送使用同步创建的不可变快照，后续响应只能决定是否清理，不能改变已发送内容。

草稿恢复失败必须显示错误并保留当前状态，不能用空选择覆盖现有内容。

## 错误策略

本设计不提供资源链路异常降级。

- Manifest 无法加载：终止请求并返回 `503 resource_manifest_unavailable`。
- 显式资源无效或跨会话：返回 `409 invalid_context_reference`。
- 当前轮图片底层文件缺失：返回 `409 current_turn_image_missing`。
- 当前轮图片 MIME、locator 或路径边界非法：返回 `409 current_turn_image_invalid`。
- 当前轮图片超过限制：返回 `413 current_turn_image_too_large`。
- 已验证图片无法构造原生内容块：返回 `500 native_image_build_failed`。
- Provider 拒绝已经构造的多模态请求：向上返回分类后的 Provider 错误，不重试为纯文本请求。

错误响应不得包含服务器绝对路径、base64 或敏感文件内容。所有错误必须发生在首次模型调用前，Provider 调用自身失败除外。

有界资源投影正常排除未入选历史资源不属于异常降级；这些资源仍可通过 `list_session_resources` 发现。

## 可观测性

每次请求在首次模型调用前记录一条结构化汇总：

```json
{
  "mode": "board",
  "manifest_version": 3,
  "manifest_active_count": 5,
  "explicit_ref_count": 1,
  "projected_ref_count": 5,
  "current_turn_image_count": 1,
  "native_image_block_count": 1,
  "projection_truncated_count": 0
}
```

日志只记录资源 ID、数量、MIME 类型和安全错误代码，不记录文件内容、base64 或绝对路径。

`agent_analyze_request` 应增加 `context_refs_count`，使请求边界丢失图片时无需查询数据库即可定位。

## 文件改动边界

### 后端

- `backend/app/agent/selection_context.py`
  - 移除仅显式资源投影的过滤行为；
  - 严格转换当前轮图片资源。
- `backend/app/agent/resources/manifest.py`
  - 为完整 Manifest 投影增加 `preferred_ref_ids` 排序输入。
- `backend/app/agent/react_agent.py`
  - 使用完整 Manifest 构造资源上下文；
  - 仅使用本轮资源构造初始 `runtime_attachments`；
  - 记录投影和本轮图片诊断。
- `backend/app/agent/runtime/multimodal.py`
  - 对已经验证的图片严格构造原生内容块；
  - 保证输入图片数与输出块数量一致。
- `backend/app/routers/agent.py`
  - 记录 `context_refs_count`；
  - 保持结构化 Web 请求协议和资源授权边界。

### 前端

- `frontend/src/components/InputBox.vue`
  - 修复 session 创建、上传和草稿恢复之间的状态竞争；
  - 使用不可变发送快照。
- `frontend/src/components/inputBoxSelectionDraft.js`
  - 提供可单元测试的恢复 generation 与目标匹配逻辑。

## 测试策略

### 前端单元测试

- 上传图片创建首个 session 后，旧的无 session 恢复结果不能清除附件。
- session 或 mode 已变化时，过期恢复结果不能应用。
- 上传成功后发送 payload 包含对应 `context_refs`。
- 上传尚未形成 `resourceRefId` 时禁止发送。
- 请求失败保留正文和文件选择，请求被接受后才清空。
- 本轮发送快照创建后，异步选择状态变化不改变已发送 `context_refs`。

### 后端单元测试

- `context_refs=[]` 时完整 active Manifest 仍进入自动资源投影。
- 本轮显式资源排在自动资源之前，但不会过滤其他资源。
- 本轮选择图片可严格转换为一个运行时附件。
- 未选择的历史图片不会成为初始运行时附件。
- 当前轮图片缺失、不可读、MIME 非法或路径越界时显式失败。
- 非图片本轮资源不生成 image block，也不被误判为错误图片。
- 多模态内容构造的输入图片数与输出 image block 数一致。
- 持久化用户消息只保存文本和结构化引用，不保存 base64。

### 模式矩阵

- `board` + 本轮上传图片：首次模型请求包含原生 image block。
- `chart` + 本轮上传图片：首次模型请求包含原生 image block。
- `social` + 当前入站图片：首次模型请求包含原生 image block。
- `board` / `chart` + 本轮 `@` 历史图片：首次模型请求包含原生 image block。
- `board` / `chart` / `social` + 未选择历史图片：只投影引用元数据，不自动编码。
- 非多模态模式 + 本轮图片：不构造原生 image block，资源引用仍可见。
- 多模态模式调用 `read_file(as_multimodal_attachment=true)`：图片进入下一次模型调用。

### 回归集成测试

复现本次生产时序：

1. 新建 Board 会话。
2. 上传图片并触发 session ID 创建。
3. 等待或交错执行 Composer 草稿恢复请求。
4. 输入“复刻这个架构图”并发送。
5. 断言持久化用户消息 `context_refs` 包含图片资源。
6. 断言 `current_request_image_count == 1`。
7. 断言首次 Provider 请求包含一个原生图片块。
8. 断言 Agent 不会因缺少图片而要求用户重新上传。

## 验收标准

- 新会话上传图片后立即发送不会丢失 `context_refs`。
- `chart`、`board` 和 `social` 的本轮图片在首次模型调用中以原生图片内容提供。
- 其他模式不会因为本修复增加原生图片输入。
- 未在本轮选择的历史图片不会被自动编码。
- 完整 Manifest 的自动资源投影不再受 `context_refs` 是否为空影响。
- `@文件` 只提升本轮资源优先级，不关闭自动资源发现。
- 当前轮图片解析或构造失败会在模型调用前明确失败。
- 图片字节和 base64 不进入持久化历史或日志。
- Board 的 `current_request_images` 与实际原生图片块一致。
