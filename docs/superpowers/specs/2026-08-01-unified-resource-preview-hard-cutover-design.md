# 统一资源预览与文件产物硬切设计

日期：2026-08-01  
状态：已确认，待实施计划

## 1. 目标

将工具产出文件、前端文件列表、实时预览、下载、图表、画板和新会话恢复统一到 `session_resources`。硬切后，资源目录是唯一权威状态，不再从消息、会话快照、工具事件或服务器文件路径重建预览。

本次改造一次性覆盖资源生产、持久化、访问接口、实时通知、前端状态、预览渲染和旧机制删除，不保留双读、双写、兼容开关或长期适配层。

## 2. 范围与非目标

### 2.1 范围

- 所有会产生文件、图表、画板或可预览 artifact 的工具显式声明资源。
- 主产物及其预览、转换格式、源文件和附件使用资源关系表达。
- 新增“文件产物”标签页，作为工具交付物的统一入口。
- 文档、图表、画板标签页改为统一资源集合的筛选和渲染视图。
- 实时预览和新会话恢复使用相同的资源加载流程。
- 预览和下载只通过会话资源内容接口访问。
- 编辑、渲染和分享等业务命令成功后必须回写资源目录。
- 删除旧前端状态、消息恢复、路径推断、旧下载依赖和旧后端推导代码。

### 2.2 明确不做

- 不迁移硬切前的历史会话资源。
- 不从旧 `session_resource_manifests`、`sessions.data_ids`、`sessions.visual_ids`、`sessions.office_documents` 或历史消息回填资源。
- 不保留数据库或旧资源索引备份。
- 不保证硬切前会话的文件、预览和资源关系可恢复。
- 不将编辑、转换、分享的业务语义强行合并成一个巨型资源 CRUD 接口。

验收范围从硬切发布后创建的新会话开始。

## 3. 核心原则

1. `session_resources` 是资源展示和恢复的唯一事实来源。
2. 消息只保存对话；消息载荷不承担资源恢复职责。
3. 工具事件只触发资源目录刷新；事件不携带前端可直接消费的预览对象。
4. 每个可访问内容都有不透明的 `resource_id`；前端不可见服务器路径。
5. 主文件、预览文件和转换格式都是资源，不把路径集合塞进非结构化预览 JSON。
6. 实时显示之前必须先持久化资源；允许为此增加几十到几百毫秒延迟。
7. 前端只维护一套按会话隔离的资源状态。

## 4. 资源模型

### 4.1 资源组与资源关系

同一个逻辑产物及其全部格式、预览和版本组成一个资源组。

资源记录至少包含：

- `resource_id`：具体内容的不透明标识。
- `session_id`：所属会话。
- `group_id`：逻辑产物组标识。
- `parent_resource_id`：派生资源关联的直接父资源，可为空。
- `relation`：`primary`、`preview`、`rendition`、`source` 或 `attachment`。
- `kind`：`file`、`artifact`、`visual`、`data` 或 `url`。
- `role`：沿用业务角色，用于区分 `output`、`report`、`source`、`attachment` 等用途。
- `label`：用户可见名称。
- `format`：例如 `docx`、`pdf`、`html`、`xlsx`、`pptx`、`vega-lite`、`drawio`。
- `media_type`：内容响应的 MIME 类型。
- `renderer`：前端建议渲染器。
- `version`：资源组内的交付版本。
- `status`：统一生命周期状态。
- `capabilities`：资源支持的预览、下载、编辑、渲染和分享能力。
- `locator`：仅服务端保存的物理定位信息。
- `tool_name`、`run_id`、`turn_sequence`、创建和更新时间等追踪字段。

数据库必须约束父资源和子资源属于同一会话及同一资源组。预览子资源绑定具体主资源版本，不能跨版本复用。

### 4.2 关系示例

一个报告资源组可以包含：

- QMD：`relation=source`
- DOCX：`relation=primary`
- HTML：`relation=preview`
- PDF：`relation=rendition`
- 报告图表：`relation=attachment`

一个 PPT 资源组可以包含 PPTX 主资源、PDF 预览、逐页 PNG 预览和 montage 图片。逐页图片不作为文件产物列表中的独立交付物。

### 4.3 生命周期

资源状态统一为：

- `processing`：正在生成或转换。
- `active`：可正常访问。
- `superseded`：已被同组新版本替代。
- `missing`：记录存在但实际内容丢失。
- `invalid`：契约、关系或安全校验失败。
- `failed`：生成或转换失败。

同组新版本成为当前交付版本后，旧 primary 标记为 `superseded`。目录默认返回当前版本，版本历史显式请求 superseded 记录。

## 5. 后端资源生产与持久化

### 5.1 工具契约

所有产出工具必须返回显式 `resources[]` 声明。执行器不再从 `file_path`、`pdf_preview`、`html_preview`、`visuals` 或任意工具私有字段推断资源，也不扫描工具结果中的路径。

资源构建器负责统一生成主资源、子资源、关系、格式、MIME 和 renderer。工具可以调用共享构建器，但最终结果必须满足同一个严格契约。

产出实际文件但未声明资源视为工具契约缺陷：文件不会出现在前端，测试必须阻止此类工具通过验收。

### 5.2 持久化顺序

1. 工具生成内容。
2. 执行器验证声明、文件存在性、允许目录、关系和格式。
3. 在一个数据库事务中写入资源组、资源记录和新的 `resource_version`。
4. 事务提交成功后发送 `resources_changed`。
5. 前端根据版本刷新统一目录。

工具完成后立即执行上述流程，不等整个 Agent 回合结束。Agent 最终消息不负责资源耐久化。

工具结果中的 `resources[]` 是后端提交契约，不是前端预览载荷。

### 5.3 业务动作

编辑、渲染、转换和分享可以保留各自的领域服务。资源目录通过 `capabilities` 和 `actions` 描述前端允许调用的动作，前端不按文件类型硬编码服务器路径。

业务动作成功后必须创建或更新资源，提交新的资源版本并发送 `resources_changed`。前端不得使用动作响应中的临时 URL 或预览对象直接修改预览状态。

预览尚未生成时，主资源声明 `preview` capability。预览动作产生 `preview` 子资源后，前端通过资源刷新看到结果。

## 6. 统一 API

### 6.1 资源目录

```text
GET /api/sessions/{session_id}/resources
```

支持按状态、种类、角色、renderer、资源组和分页游标筛选。响应返回前端安全 DTO，不返回 `locator`、本地路径或可反推服务器路径的字段。

DTO 包含资源 ID、关系、显示信息、格式、媒体类型、renderer、版本、状态、能力和服务端生成的 action 描述。

### 6.2 内容访问

```text
GET /api/sessions/{session_id}/resources/{resource_id}/content
GET /api/sessions/{session_id}/resources/{resource_id}/content/{asset_path}
```

普通文件只使用第一个接口。第二个接口仅服务 HTML、报告等目录型 artifact 的相对资源。

接口规则：

- 始终先校验当前用户对会话的读取权限。
- 服务端根据资源记录定位内容，前端不提交文件路径。
- 预览响应使用安全的 `Content-Disposition: inline`。
- 下载响应使用 `Content-Disposition: attachment`。
- 使用资源记录中的 MIME，并发送 `X-Content-Type-Options: nosniff`。
- HTML artifact 的 `asset_path` 必须限制在资源根目录，拒绝绝对路径、`..` 和符号链接越界。
- HTML 预览使用隔离 iframe 和 CSP，不能继承主应用权限。

图表以 JSON/spec 资源返回，画板以 XML/JSON 资源返回，文件类预览以相应媒体流返回。所有 renderer 只依赖资源 DTO 和内容接口。

### 6.3 实时通知

实时通道只发送目录失效通知：

```json
{
  "type": "resources_changed",
  "session_id": "session-id",
  "resource_version": 12,
  "changed_resource_ids": ["resource-id"]
}
```

事件只能在资源事务提交后发送。相同或较低版本不会触发重复刷新。事件丢失不影响耐久性，页面恢复或版本比较能够重新发现资源。

## 7. 前端架构

### 7.1 唯一资源 Store

新增按 `session_id` 隔离的 `sessionResourceStore`，核心状态为：

- `resourcesById`
- `groupsById`
- `catalogVersion`
- `loading` 和 `error`
- `selectedResourceId`
- `selectedGroupId`
- `activePreviewTab`
- 当前加载 request token

删除 `officeDocumentHistory`、`lastOfficeDocument`、`visualizationHistory` 作为独立资源状态，也删除从消息或事件拼装的资源副本。

版本历史由 `group_id + version` 派生。选择旧版本只改变选中资源，不复制或改写目录。

### 7.2 标签页

- 文件产物：显示工具生成且 `role=output/report` 的顶层文件和 artifact。
- 文档：显示适用于 PDF、HTML、Markdown、表格、PPT、图片等文档 renderer 的资源组。
- 图表：显示 chart/visualization renderer 的资源组。
- 画板：显示 board renderer 的资源组。

文件产物列表不显示用户上传附件、输入数据、缩略图、PPT 页面 PNG 和其他派生预览资源。派生格式位于主产物的预览、下载和版本区域。

点击文件产物时，Store 选中资源组和首选资源，根据首选预览子资源切换到文档、图表或画板标签。没有专用 renderer 时留在文件产物页显示通用详情和下载操作。

### 7.3 Renderer Registry

`ResourcePreviewHost` 根据 `renderer` 选择独立渲染器：

- `pdf` → `PdfRenderer`
- `html` → `HtmlRenderer`
- `markdown` → `MarkdownRenderer`
- `spreadsheet` → `SpreadsheetRenderer`
- `presentation` → `PresentationRenderer`
- `image` → `ImageRenderer`
- `chart` → `ChartRenderer`
- `board` → `BoardRenderer`
- 其他 → `FileDetailRenderer`

Renderer 不查询会话、不维护资源历史、不猜测路径、不识别工具私有字段。Renderer 加载失败只影响当前预览，不删除资源，也不影响下载。

## 8. 新会话存储与恢复

### 8.1 新会话运行

创建新会话时初始化空资源目录和 `resource_version=0`。每次工具完成后先持久化资源，再通知前端刷新。因此长任务中已完成的工具产物可以提前出现，刷新页面后也不会丢失。

资源提交失败时不能发送成功预览通知。Agent 终态需要明确暴露资源持久化失败，不能把未落库的文件描述为可恢复产物。

### 8.2 会话恢复

恢复时并行加载：

- 消息接口：只恢复聊天记录。
- 资源接口：只恢复文件、文档、图表、画板和预览。

恢复流程：

1. 激活 `session_id` 并生成新的 request token。
2. 获取会话信息中的 `resource_version` 和分类计数。
3. 并行加载消息和资源目录。
4. Store 按 `group_id` 建立资源组。
5. 默认选择最近更新且可预览的顶层产物。
6. 根据 renderer 自动打开对应预览标签。
7. 无可预览资源时显示聊天区或文件产物空状态。
8. 恢复期间收到更高版本事件时，在当前加载完成后再刷新一次。

恢复过程不读取消息中的 `tool_result`，不读取 Office 或 visualization 快照，不根据旧 URL 或路径重建预览。

### 8.3 并发和切换

- 每个会话拥有隔离的资源状态。
- 加载响应必须匹配当前 request token，快速切换会话时丢弃过期响应。
- 断线重连先比较资源版本，版本一致则不重复加载。
- 删除会话时级联删除资源记录，实际文件按统一清理策略处理。

不持久化用户上次选中的文件或标签页。恢复默认选中最近可预览产物，避免新增第二套 UI 状态持久化。

## 9. 异常处理

- 文件生成成功但资源事务失败：记录结构化错误，后台清理孤立文件。
- 资源事务成功但实时通知失败：目录数据仍有效，恢复或版本检查重新发现。
- 预览生成失败：主文件仍可下载，资源组展示失败状态并允许 capability 重试。
- 内容丢失：接口返回 `resource_content_missing` 并将资源标记为 `missing`。
- 不支持格式：使用通用文件详情 renderer，保留下载能力。
- 资源关系无效或越权：拒绝写入或访问，并记录可审计错误。
- 顶层产物删除采用资源组软删除，物理文件由统一清理任务处理。

## 10. 删除清单

硬切发布必须删除：

- 前端消息预览提取和 `officeDocumentRecovery`。
- `sessionDocumentResources` 中对旧字段、URL 和路径的推断。
- Store 中 Office、图表独立历史及其事件拼装逻辑。
- `office_document`、`html_document` 等驱动资源预览状态的前端分支。
- 面板中的 `pdf_id`、`html_id`、`file_path` 猜测和按格式分散下载逻辑。
- 前端对 `/api/file/{path}`、`download-word`、`download-ppt`、`download-excel` 的依赖。
- 后端从消息、metadata、旧会话列或工具私有字段推导资源的实现。
- 旧资源列表、旧预览传输契约、旧下载路径及其测试。
- `session_resource_manifests` 和旧会话资源字段。

生产版本不保留旧路由的兼容响应。

## 11. 测试策略

### 11.1 后端

- 资源组、父子关系、同组约束、版本替换和状态转换。
- 工具显式资源声明覆盖及未声明产物失败测试。
- 目录 DTO 不暴露 locator 或路径。
- 内容访问权限、MIME、inline/attachment、缓存和缺失文件。
- HTML asset 路径穿越、绝对路径和符号链接越界。
- 预览生成、失败、重试及版本绑定。
- 会话删除和资源级联。
- SSE 提交顺序和版本单调性。
- 旧消息、metadata 和旧列不会影响资源目录。

### 11.2 前端

- Store 分页、版本去重、合并、会话隔离和过期请求丢弃。
- 文件产物只显示顶层工具交付物。
- 文件点击正确进入文档、图表、画板或 fallback renderer。
- 所有 renderer 只使用资源内容接口。
- 动作成功后只通过目录刷新改变 UI。
- 页面刷新前后资源 ID、版本、文件列表和预览选择一致。
- 缺失、失败、不支持格式和无权限状态。
- 静态扫描禁止旧接口、旧 Store 字段和路径猜测。

### 11.3 端到端

对 DOCX、PDF、HTML 报告、Markdown、Excel、PPT、图片、图表和画板分别执行：

1. 新建会话并生成产物。
2. 验证文件产物标签出现顶层交付物。
3. 点击产物并验证正确预览标签和 renderer。
4. 下载并校验文件名、MIME 和内容。
5. 刷新并恢复同一会话。
6. 验证资源 ID、版本、文件列表和预览一致。
7. 断开实时通道后刷新，验证资源仍可完整恢复。

## 12. 硬切发布与验收

在一个发布窗口内完成：

1. 执行新资源关系字段、约束和旧结构删除迁移。
2. 部署全部已改造的工具生产者和后端接口。
3. 启动后端并完成 API、权限和资源内容冒烟测试。
4. 在 `/home/xckj/suyuan/frontend` 执行 `npm run build:standalone`。
5. 验证 `dist/assets` 包含统一资源接口且不包含旧资源和下载接口。
6. 执行 `docker exec suyuan-nginx nginx -s reload`。
7. 对硬切后新建会话执行完整端到端验收。
8. 静态扫描确认旧机制实现和引用为零。

发布不创建数据库或旧资源备份。代码可以回退到旧提交，但数据库结构及被删除的历史资源索引不可恢复；这属于本设计已确认的硬切约束。

## 13. 完成标准

满足以下全部条件才视为完成：

- 生产者只通过显式资源契约登记产物。
- 前端只有 `sessionResourceStore` 一套资源状态。
- 实时预览和新会话恢复读取相同资源目录。
- 文件产物、文档、图表和画板共享资源选择和版本状态。
- 所有预览和下载只使用资源内容接口。
- 前端和公开 API 不暴露服务器文件路径。
- 旧消息推断、预览快照、下载分支、旧接口和旧数据库结构已删除。
- 全部后端、前端、端到端和正式构建验收通过。
