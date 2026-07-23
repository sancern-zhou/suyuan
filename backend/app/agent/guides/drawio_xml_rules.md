# Draw.io XML Rules

本文件约束 `create_drawio_board` 的 XML 生成质量。

## 基本结构

`create_drawio_board` 只接收以下 XML：

1. 标准 draw.io `<mxfile>...</mxfile>`：必须包含 `<diagram><mxGraphModel><root>...</root></mxGraphModel></diagram>`
2. 完整 `<mxGraphModel>...</mxGraphModel>`
3. 一个或多个 `<mxCell>...</mxCell>` 片段

输出目标必须能被 diagrams.net/draw.io 渲染。

不要把 `<mxGraphModel>` 直接包在 `<mxfile>` 下。以下结构不是合法输入：

```xml
<mxfile>
  <mxGraphModel>
    <root>...</root>
  </mxGraphModel>
</mxfile>
```

如果不想生成完整标准 `<mxfile>`，直接传 `<mxGraphModel>` 或 `<mxCell>` 片段。

## mxCell 规则

1. 每个业务节点和连线必须有稳定、唯一的 `id`。
2. 不要使用随机且不可读的 id；优先使用有语义的 id，例如 `station_source_1`、`pollution_process_2`。
3. 顶层业务节点通常使用 `vertex="1"`、`parent="1"`。
4. 连线通常使用 `edge="1"`、`parent="1"`，并设置有效的 `source` 和 `target`。
5. 节点必须包含 `<mxGeometry ... as="geometry" />`。
6. 普通节点应设置 `x`、`y`、`width`、`height`，避免重叠或不可见。
7. 连线应包含 `<mxGeometry relative="1" as="geometry" />`。

## 布局规则

1. 默认使用从左到右或从上到下的清晰业务流。
2. 同层节点保持对齐，间距稳定。
3. 避免节点重叠、连线穿越过多、文本超出节点。
4. 节点文本应短而明确；长说明应拆成多个节点或放入注释节点。
5. 商务风格优先：清晰边框、浅色填充、克制配色，不使用花哨装饰。
6. 子节点的 `mxGeometry x/y` 是相对其 `parent` 的局部坐标，不是画布绝对坐标。例如父泳道位于 `(50, 670)`，子节点希望显示在画布 `(130, 720)`，应写 `x="80" y="50"`。
7. 泳道或容器内的子节点必须落在父节点内容区内，并避开泳道标题区；不要让 `x + width` 或 `y + height` 超出父节点尺寸。

## 连线路由规则

1. 可以省略新连线的折点，由系统先自动规划；如需显式折点，只能使用 `<Array as="points"><mxPoint x="..." y="..."/></Array>`，不要使用 `<Object>`。
2. `create_drawio_board` 会对 AI 新生成的候选画板逐条尝试自动避让；能够安全处理的连线会写入显式正交路径。
3. 无法避让的连线会保留原始路径，并通过 `routing_status`、`routing_issues` 和路由指标报告；单条或多条连线避让失败不得阻止候选画板生成。
4. `routing_status=partial` 或 `fallback` 是非阻断警告。Agent 应继续截图和验收，不要仅因路由警告重新生成整张画板。
5. 收到 `routing_issues` 后可以读取 `cause`、`blocking_node_ids`、`repair_actions` 和 `failure_fingerprint` 辅助人工诊断；只有用户明确要求整理连线，或截图显示严重不可读时，才进行局部修订。
6. 装饰背景和非交互标题应设置 `pointerEvents=0`，避免被识别为业务节点障碍物。

## 样式规则

1. 节点样式应显式包含 `rounded=1;whiteSpace=wrap;html=1;`。
2. 关键节点可以使用不同填充色，但不要形成单一高饱和配色。
3. 连线样式应包含 `edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;`。
4. 文本节点或注释节点必须保证可读。

## 禁止事项

1. 禁止生成缺少 id 的 mxCell。
2. 禁止生成 source/target 指向不存在节点的连线。
3. 禁止无原因改变所有已有 id。
4. 禁止把 Mermaid、PlantUML、SVG 或 ECharts option 当作 draw.io XML 传入。
5. 禁止在用户只要求局部修改时重排整张图。
