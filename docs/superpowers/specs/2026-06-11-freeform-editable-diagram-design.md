# Universal Freeform Draw.io Canvas Design

## 背景

当前图形生成主要通过 `create_diagram_artifact` 的模板化 HTML 渲染实现。该方式适合稳定预览、报告嵌入和 Word A4 静态图片输出，但对复杂图形不够灵活：Agent 需要先把内容压进 `layers/groups/items` 或 `steps/edges`，导致跨层依赖、混合部署、局部放大、旁路链路、自定义拓扑、自由流程和思维导图表达受限。同时，当前产物以 HTML/PNG 为主，用户无法像 Visio 或 diagrams.net 一样继续编辑图形。

本设计目标是增加通用自由画布能力，让 Agent 能直接生成和编辑可编辑图形。架构图、流程图、思维导图、拓扑图和业务关系图都应是同一画布能力的应用场景，而不是分别受不同模板约束的专用能力。

## 目标

- Agent 可以不受分层模板限制，按通用画布图元自由生成和编辑图形。
- 生成 `.drawio` 作为主编辑源，用户可在 diagrams.net 中打开和编辑。
- 同次生成可预览图片，至少包含 `.png`，可选生成 `.drawio.svg`。
- 现有模板化架构图能力保持兼容，不破坏已有 HTML artifact 和报告嵌入链路。
- 后续用户提出局部修改时，Agent 能基于稳定元素 ID 修改节点、连线、分组和样式。
- `freeform` 画布不限定图形类型；只要基础元素能表达，架构图、流程图、思维导图、数据流图、拓扑图都可以使用该模式。

## 非目标

- 第一阶段不直接生成 Visio `.vsdx`。用户可通过 diagrams.net 从 `.drawio` 导出 Visio 格式。
- 第一阶段不实现完整的 diagrams.net GUI 编辑器嵌入，只提供文件下载和预览。
- 不移除现有模板模式；规范分层图、流程图、决策树仍可使用模板模式。

## 推荐方案

扩展 `create_diagram_artifact`，增加 `diagram_mode`：

- `template`：现有模式，继续使用 `layers/groups/items`、`steps/edges` 和类型模板。
- `freeform`：新增通用自由画布模式，Agent 直接传入 draw.io 风格画布元素，由工具生成 `.drawio` 主文件并导出预览图片。

不新增面向 Agent 的新工具名。这样 Agent 仍只需要记住一个图表工具，工具内部根据模式选择渲染器，前端 artifact 返回结构也能复用。

## 通用自由画布输入模型

`freeform` 模式不是“自由架构图模板”，而是一个通用可编辑画布。它使用接近 draw.io 画布的结构化模型，让 Agent 通过基础图元、文本、容器和连线自由组合图形。

```json
{
  "diagram_mode": "freeform",
  "artifact_id": "smart_platform_architecture",
  "title": "智慧环保平台架构图",
  "canvas": {
    "width": 1600,
    "height": 1000,
    "grid": 20,
    "background": "#ffffff"
  },
  "shapes": [
    {
      "id": "web_portal",
      "type": "rounded_rect",
      "label": "Web 门户",
      "x": 320,
      "y": 180,
      "width": 180,
      "height": 70,
      "style": {
        "fill": "#ffffff",
        "stroke": "#5f6368",
        "font_size": 18
      }
    },
    {
      "id": "api_gateway",
      "type": "rounded_rect",
      "label": "API 网关",
      "x": 620,
      "y": 180,
      "width": 180,
      "height": 70,
      "style": {
        "fill": "#e7f0fb",
        "stroke": "#466f9f",
        "font_size": 18
      }
    }
  ],
  "connectors": [
    {
      "id": "edge_web_gateway",
      "from": "web_portal",
      "to": "api_gateway",
      "label": "HTTPS",
      "type": "orthogonal",
      "style": {
        "stroke": "#374151",
        "end_arrow": "block"
      }
    }
  ],
  "groups": [
    {
      "id": "cloud_zone",
      "label": "政务云",
      "x": 420,
      "y": 120,
      "width": 820,
      "height": 620,
      "style": {
        "fill": "#f7f8fb",
        "stroke": "#9aa9c3",
        "dashed": true
      }
    }
  ],
  "output_formats": ["drawio", "png", "drawio_svg"]
}
```

### Shape 类型

基础元素以 draw.io 的通用 shape 能力为准。第一阶段内置最常用的一组别名，同时提供原生 draw.io shape 透传能力，避免 Agent 被固定枚举限制。

- `rect`
- `rounded_rect`
- `text`
- `container`
- `swimlane`
- `database`
- `cloud`
- `queue`
- `document`
- `circle`
- `ellipse`
- `hexagon`
- `diamond`
- `triangle`
- `parallelogram`
- `cylinder`
- `actor`
- `note`
- `callout`
- `brace`
- `bracket`
- `line`
- `arrow`
- `image`
- `drawio_shape`

`database` 和 `cylinder` 第一阶段可以映射到同一种 draw.io 圆柱形。`container`、`swimlane` 和 `group` 用于表达区域边界、分组框和泳道。

`drawio_shape` 是扩展出口：Agent 可以传入 `drawio_shape_name` 和 `drawio_style`，直接使用 diagrams.net 支持的 shape/style，例如 `mxgraph.aws4.resourceIcon`、`process`、`manualInput` 等。工具只做安全过滤、尺寸校验和 XML 转义，不把它强行映射回内置类型。未知普通 `type` 降级为 `rounded_rect`，并在 metadata 中返回 warning；明确使用 `drawio_shape` 时不降级。

### Connector 类型

第一阶段支持：

- `straight`
- `orthogonal`
- `curved`

连线可配置 `start_arrow`、`end_arrow`、`dashed`、`stroke`、`stroke_width`、`waypoints` 和短标签。`from/to` 优先引用 shape ID；无法引用时允许使用绝对坐标端点。思维导图、流程图、数据流图和架构图都复用同一 connector 模型，只是布局和语义不同。

### 图形类型语义

`freeform` 可选传入 `diagram_intent` 作为语义提示，但它不改变底层画布模型：

- `architecture`
- `process`
- `mind_map`
- `data_flow`
- `topology`
- `org_chart`
- `custom`

`diagram_intent` 只用于默认画布尺寸、推荐连线样式、导出命名和 Agent 提示，不用于限制可用图元。Agent 可以在任意 intent 下使用所有基础元素。

## 生成流程

1. Agent 根据用户需求选择 `diagram_mode`。
2. 用户明确要规范模板、报告一致性或自动分层时，可以走 `template`。
3. 用户强调自由编辑、可编辑源文件、类似 Visio/draw.io、复杂拓扑、思维导图或非标准布局时，走 `freeform`。
4. `freeform` renderer 将 `canvas/shapes/connectors/groups` 转换为 draw.io XML。
5. 工具写出 `diagram.drawio`。
6. 工具调用导出器生成 `diagram.png` 和可选 `diagram.drawio.svg`。
7. 工具继续创建 HTML artifact，HTML 页面展示预览图片并提供元数据。
8. 返回 `artifact/artifacts/refs/visuals`，包含所有可下载文件。

## 文件输出

每个 artifact 目录包含：

- `index.html`：右侧面板预览入口。
- `diagram.drawio`：主编辑源。
- `assets/diagram.png`：默认预览图片。
- `assets/diagram.drawio.svg`：可选，兼具 SVG 预览和 draw.io 编辑元数据。
- `meta.json`：记录 `diagram_mode`、源文件、导出文件、元素数量、warnings、导出器版本。

返回给前端的 artifact 列表应包含多个文件：

- 主预览 artifact：`png` 或 `html_artifact`。
- 可编辑下载 artifact：`.drawio`。
- 可选下载 artifact：`.drawio.svg`。

## 导出器选择

第一优先级使用 diagrams.net/drawio CLI 或本地可用的 draw.io export 能力，因为它能保证 `.drawio` 到 `.png/.svg` 的一致性。

如果运行环境没有导出器：

- 仍生成 `.drawio`。
- 使用简化 SVG/PNG fallback 渲染器生成预览。
- 在 metadata 中返回 `exporter_unavailable` warning。

这种降级不能阻塞用户下载 `.drawio`，但最终实现应提供部署检查，提示生产环境安装导出器。

## Agent 编辑流程

为便于后续修改，`freeform` 模式必须要求 Agent 给每个 shape、connector、group 写稳定 `id`。后续用户说“把 API 网关移到左边”“新增一条虚线”“把这几个模块框成政务云区域”“把流程节点改成菱形判断”“给思维导图新增一个分支”时，Agent 读取已有 `.drawio` 或保存的源模型，执行局部修改：

- 移动：更新 `x/y`。
- 调整大小：更新 `width/height`。
- 改文字：更新 `label`。
- 改连线：更新 `from/to/waypoints/style`。
- 分组：新增或调整 `group/container`。
- 风格统一：批量更新 `style`。
- 图形替换：更新 `type`，例如矩形改菱形、普通节点改圆柱。
- 层级调整：更新父子关系或 group 归属，用于思维导图、泳道图和区域分组。

第一阶段可采用“源模型 JSON + `.drawio` 同步生成”的方式降低解析复杂度。工具在 `meta.json` 或旁路 `diagram.source.json` 中保存规范化模型。Agent 编辑时优先修改源模型，再重新生成 `.drawio` 和预览图。

## 与现有模板模式的边界

模板模式继续保留以下约束：

- 读类型模板和 checklist。
- 架构图优先 `layers/groups/items`。
- 适合报告、规范图、结构清晰的分层图。

自由模式放宽这些约束，并且不限定输出图类型：

- 不强制读取分层模板。
- 不要求 `layers/groups/items`。
- 允许绝对坐标、自由布局、混合形状和跨区域连线。
- 允许用同一套基础元素生成架构图、流程图、思维导图、拓扑图、组织结构图和自定义示意图。
- 仍需要基础质量检查：元素 ID 唯一、文本非空、连线端点有效、画布边界合理、预览非空。

## 前端展示

前端优先展示 `png` 或 `drawio_svg` 预览。右侧面板提供下载入口：

- “下载可编辑源文件”：`.drawio`
- “下载可编辑 SVG”：`.drawio.svg`
- “下载图片”：`.png`

如果现有右侧面板只支持单 artifact，需要扩展为同一结果下展示多个相关文件。文件关系通过 `refs.artifacts` 或 artifact metadata 表达。

## 错误处理

- 缺少 `artifact_id/title`：沿用现有失败返回。
- `freeform` 没有任何 shape：失败，提示不要空参调用。
- shape ID 重复：失败或自动重命名并返回 warning；推荐第一阶段失败，避免后续编辑混乱。
- connector 引用不存在：第一阶段直接失败，返回缺失端点 ID，迫使 Agent 修正，避免生成不可稳定编辑的图。
- 导出器不可用：不失败，返回 `.drawio` 和 fallback 预览，并给出 warning。
- 图片导出失败：不失败，保留 `.drawio`，HTML 预览展示错误说明和下载链接。

## 测试计划

- 单元测试：freeform 输入校验、ID 唯一性、connector 引用校验、基础 shape 类型映射、draw.io XML 生成。
- 快照测试：固定输入生成稳定 `.drawio` 关键结构。
- 导出测试：有导出器时生成 `.png/.drawio.svg` 且文件非空。
- 降级测试：无导出器时仍生成 `.drawio` 和 fallback 预览。
- 回归测试：template 模式现有行为不变。
- 前端测试：同一工具结果展示多个下载项。
- 场景测试：同一 freeform 模型分别覆盖架构图、流程图、思维导图和拓扑图，不依赖模板字段。

## 分阶段落地

### 阶段一：后端自由画布最小闭环

- 在 `create_diagram_artifact` 增加 `diagram_mode`、`canvas`、`shapes`、`connectors`、`groups`、`output_formats`。
- 实现通用 draw.io XML writer 和基础 shape/style 映射表。
- 保存 `.drawio` 和源模型 JSON。
- 生成基础 PNG 预览，导出器不可用时 fallback。
- 返回多 artifact metadata。

### 阶段二：预览与下载体验

- 前端右侧面板支持多个相关下载文件。
- 默认展示 PNG/SVG，明确标注 `.drawio` 可编辑源文件。
- 支持 `present_artifact` 预览 `.drawio` 相关结果。

### 阶段三：Agent 局部编辑

- 增加读取已有 freeform diagram 源模型的路径。
- Agent 根据用户修改意图定位元素 ID。
- 工具支持基于源模型更新后重新导出。

### 阶段四：高级图形能力

- 支持图片图标库、云厂商图标、自动避让连线、布局辅助、局部自动排版。
- 持续扩展 draw.io shape 映射表，逐步覆盖更多 diagrams.net 基础图形和常用图形库。
- 可选支持 `.vsdx` 导出，但不作为主编辑源。

## 开放问题

- 生产环境是否允许安装 draw.io CLI 或 diagrams.net export 依赖。
- 前端 artifact 面板当前多文件展示能力是否足够，是否需要单独的“相关文件”区域。
- 是否需要把 `.drawio` 源模型纳入会话记忆，以便跨轮稳定编辑。
