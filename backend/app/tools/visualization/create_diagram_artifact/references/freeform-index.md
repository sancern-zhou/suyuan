# Freeform Diagram Design Reference Index

使用 `create_diagram_artifact` 且 `diagram_mode="freeform"` 前，必须先读取本文件。freeform 是可编辑 Draw.io 画布，输入字段是 `canvas/shapes/connectors/groups`，不要套用模板模式的 `layers/groups/items` 约束。

## CRITICAL：先大纲，再绘图，再 QA，再提交

freeform 图表尤其容易因为自由摆放而失控，必须按固定流程交付：

1. **先写大纲**：明确画布方向、层/区域、节点清单、容器边界、主干连线、预览与 `.drawio` 交付格式。大纲写不清时不能调用工具。
2. **再生成图表**：按大纲生成 `canvas/shapes/connectors/groups`。不要边画边补业务逻辑，不要临时把所有模块和线条堆进画布。
3. **然后做 QA**：生成后必须按 `freeform-checklist.md` 检查重叠、层级、连线数量、普通节点级连线、文字遮挡、下载格式和可编辑性。
4. **修改后最终提交**：QA 发现问题时，必须通过 `operation="patch"` 或重新生成来修正，并复查关键问题；不能把首次生成结果直接提交给用户。

完成标准是“大纲已落实、Draw.io 主文件已生成、SVG/PNG 可预览、QA 问题已处理或明确说明为非阻断告警”。

## 何时使用 freeform

- 用户要求可继续编辑、Draw.io、Visio、自由布局、复杂拓扑、非标准结构或不受模板限制。
- 架构图需要精确摆放、跨层依赖、外部系统、设备拓扑、站房/网络/数据链路等自由组合。
- 思维导图、拓扑图、组织结构、定制关系图等内置模板无法稳定表达的图。

## 渐进读取流程

1. 读取本文件，确认使用 `diagram_mode="freeform"`。
2. 读取 `freeform-primitives.md`，掌握所有 freeform 图共用的 `shape.type`、`connector.type`、布局原语、groups 和 style 字段。
3. 判断图意图：架构/分层/拓扑类继续读取 `freeform-architecture.md`；其他自定义图至少按 `freeform-primitives.md` 的结构、密度和可编辑约束设计。
4. 架构图先选择表达方式：层级带、业务域、系统边界、左右侧输入输出、底部基础设施带、实体元素库和连接语义库。
5. 读取 `freeform-checklist.md`，做节点、连线、重叠、下载格式自检。
6. 写出调用前最小设计稿，作为本次 freeform 图的大纲。
7. 再构造 `canvas/shapes/connectors/groups` 并调用工具。
8. 工具返回后按 `freeform-checklist.md` 做 QA；需要修改时用 patch/render 复查后再交付。

## 调用前最小设计稿

- 画布：确定宽高、主阅读方向和层/区域数量。
- 节点：列出 6-40 个核心节点，明确哪些是容器、哪些是普通节点。
- 分组：用 `groups` 表示背景区域或语义边界，不用重叠普通节点伪造分组。
- 实体：为数据库、数据湖、队列、缓存、网关、外部系统、用户、模型服务、监控告警选择可识别形态。
- 连线：只保留主干依赖和必要跨区关系；区分主数据流、同步调用、异步消息、批处理、控制流、监控告警和反馈闭环。
- 交付：工具固定输出 `.drawio` 主源文件，并同时生成 SVG/PNG；SVG 是预览载体，HTML 不是图表交付物。

如果上面 5 行写不清，先重构信息结构，不要直接绘制。

## 字段约束

- `canvas`: 必须给出足够画布；架构图建议宽度 1000-1600，高度按层数扩展。
- `shapes`: 每个节点必须有稳定 `id`、短 `label`、明确 `x/y/width/height`。
- `connectors`: 每条线必须表达真实语义方向；线标签保持 2-6 个汉字，非必要不写。
- `groups`: 用于区域框、泳道、外部系统边界；不要把业务模块重复放进 group 和 shape 造成重叠。
- `style`: 使用显式 `fill`/`stroke` 或 Draw.io `fillColor`/`strokeColor`；不要依赖渲染器按中文关键词猜样式。
- 视觉风格固定为商务清爽风格；显式 `style/fillColor/strokeColor/strokeWidth/fontSize` 优先于默认视觉属性。
- `postprocess`: 默认启用确定性后处理。可用 `{"enabled": false}` 保留 Agent 原始布局；可用 `warn_only:true` 只返回质量告警。

## 后处理边界

- 后处理只做机械修正：网格对齐、容器内子模块重排、容器和画布扩展、默认样式补齐、A4 字号 1.5 倍放大、模块文字溢出时优先左右扩宽节点，达到宽度上限后再自动换行并必要增高节点，明显高扇入/长标签/过稀画布告警。
- 容器内子模块重排是硬约束：同一 group 或 `container/swimlane` shape 内的普通模块不得重叠、不得溢出容器，并应在容器内上下分布居中；内容放不下时优先扩大容器和画布，不压缩模块尺寸。
- 后处理不会新增业务节点、删除语义节点、改变连接关系，也不会把自由布局改成模板布局。
- 如果返回 `quality_warnings`，优先由 Agent 根据 warnings 重新设计语义结构；几何硬约束应由工具后处理兜底。

freeform 的核心质量来自 Agent 的结构化布局决策；工具负责导出、兜底渲染和确定性的几何硬约束，不替 Agent 自动重新设计业务结构。
