# Diagram Design Reference Index

调用 `create_diagram_artifact` 前，必须先判定图表类型，再读取对应模板文档和 `checklist.md`。不要把所有图都当作普通 flowchart。

## 设计依据

- 借鉴 guizang 的工作流：先判断内容形状，再选模板；先读模板，再生成；最后用 checklist 自检。
- 借鉴 C4 模型：架构图应按受众和抽象层级分级，不要在一张图里同时塞系统上下文、容器、组件和部署细节。
- 借鉴云厂商架构图规范：图的目标是表达设计、部署、拓扑和组件关系；服务图标/产品名必须成对出现，不能变形或滥用。
- 借鉴 IBM 2x Grid：使用稳定网格、统一间距、常见比例和重复节奏，而不是随机摆放节点。
- 借鉴视觉层级原则：通过尺寸、颜色、对比、留白和分组引导阅读顺序；不要靠更多线条解决结构不清。

## 类型判定

| `diagram_type` | 适用请求 | 核心问题 | 必读模板 |
|---|---|---|---|
| `layered_architecture` | 系统架构、平台架构、感知层/网络层/IaaS/平台层/业务层等分层系统 | 各层如何自下而上支撑？ | `layered-system.md` |
| `architecture` | 兼容旧名称；新调用优先使用 `layered_architecture` | 这个系统由哪些边界清晰的能力块组成？ | `architecture.md` |
| `process` | 审批、作业、任务执行、业务流转 | 事情按什么顺序发生？ | `process.md` |
| `decision_tree` | 规则判断、诊断、风险分级、条件路径 | 根据什么条件走向哪个结论？ | `decision-tree.md` |
| `data_flow` | 数据采集、处理、存储、分析、输出 | 数据从哪里来、如何变换、到哪里去？ | `data-flow.md` |

## 渐进读取流程

1. 读取本文件，选择一个 `diagram_type`。
2. 读取对应类型模板，确定节点抽象方式、方向、分组和连线策略。
3. 如果需要模块图例，读取 `icon-catalog.md`，为关键模块选择通用 `icon` token。
4. 读取 `checklist.md`，做视觉密度和结构自检。
5. 架构图生成 `layers/groups/items`；流程、决策树和数据流生成 `steps/edges`；再调用 `create_diagram_artifact`。

## 选择优先级

- 用户说“系统架构图”且出现多层能力，优先 `layered_architecture`。
- 用户说“总体架构”“平台架构”“能力架构”，但没有清晰层级，优先 `architecture`。
- 用户描述“一步一步、先后、审批、执行”，优先 `process`。
- 用户描述“如果、是否、满足条件、否则”，优先 `decision_tree`。
- 用户描述“采集、清洗、入库、计算、输出、同步”，优先 `data_flow`。

## 输出前的最小设计稿

调用工具前，先在脑内或草稿中完成这 4 行：

- 类型：`diagram_type=...`
- 主阅读方向：`TB` / `LR`
- 分组：架构图列出每个 `layer/group` 及模块数；流程图列出关键节点数
- 主干：列出 3-8 条关键 `edges`

如果这 4 行写不清，说明还不能调用工具。

## 结构化字段约定

Schema 只保留轻量参数骨架。复杂图表必须按本节和对应模板文档补全结构化字段。

- `layers`: 分层架构图优先输入。每层至少包含 `label`，可包含 `theme`、`role`、`variant`、`icon_policy`、`groups` 或 `items`。
- `groups`: 层内语义分组。每个分组包含 `label` 和 `items`；单个分组模块过多时，Agent 先按语义拆分或合并，不依赖渲染器伪造分组。
- `items`: 模块列表。模块至少包含 `label`，可包含 `detail`、`icon`、`role`、`emphasis`、`variant`。
- `role`: 语义角色，可用 `entry`、`business`、`platform`、`data`、`infrastructure`、`external`、`support`。
- `variant`: 视觉变体，可用 `default`、`foundation`、`external`、`critical`。仅在 Agent 已明确判断层或模块语义时填写。
- `emphasis`: 模块强调，可用 `normal`、`high`、`muted`。核心模块用 `high`，辅助模块用 `muted`；不要高亮过多节点。
- `icon_policy`: 层内图标策略，可用 `auto`、`show`、`hide`。需要图例时先读取 `icon-catalog.md`。
- `edges`: 连线列表，包含 `from`、`to`，可包含短 `label`、`style`、`flow_strength`。
- `flow_strength`: 主干流向强度，可用 `normal`、`strong`；`strong` 只用于核心数据流或能力支撑链路。

`role`、`variant`、`emphasis`、`flow_strength`、`icon_policy` 必须由 Agent 显式判断后填写。渲染器不会根据 `label` 关键词自动推断视觉强调、核心模块、外部依赖或主干流向。
