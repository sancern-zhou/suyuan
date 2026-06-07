# Architecture Diagram Template

适用于系统架构、平台架构、产品能力架构、模块关系图。目标是让读者快速理解系统边界、核心能力块和关键依赖，而不是罗列全部功能清单。

## P0 硬规则

- 先确定抽象层级：系统上下文、容器/服务、组件、部署环境只能选一个主层级；不要混画。
- 每张图只服务一个受众：领导看能力边界，研发看服务依赖，运维看部署拓扑。
- 系统架构图优先使用 `diagram_type="layered_architecture"` 和 `layers/groups/items`。
- 每个 layer/group 3-7 个模块最稳；单个 group 超过 7 个时拆成二级分组或合并为能力簇。
- 单层模块明显多于其他层时，先调整信息结构；模板会自动启用紧凑布局和小尺寸图标，但不能用它替代合理分组。
- 边只画关键依赖，禁止“每个模块互相连一遍”。
- 视觉强调必须来自 Agent 显式语义字段，例如 `emphasis`、`variant`、`role`、`flow_strength`；不要指望模板根据 `label` 里的“核心、基础、监测、平台”等词自动高亮。

## 结构模型

优先从下面 5 类区域中选择 3-6 个：

- 用户与入口：Web、移动端、第三方系统、统一门户、API Gateway。
- 业务应用：业务平台、管理后台、工作台、业务域服务。
- 平台能力：认证、权限、规则引擎、消息、GIS、调度、AI 能力。
- 数据能力：数据接入、数据仓库、缓存、文件、指标库、知识库。
- 基础设施与外部依赖：计算、存储、网络、安全、云服务、外部 API。

## 推荐布局

- `direction="TB"`：上层用户/业务，下层平台/数据/基础设施，适合平台架构。
- `direction="LR"`：左侧入口，中间处理，右侧输出/外部系统，适合集成架构。
- 组之间形成 2-4 条主干路径，不要生成网状蜘蛛图。
- `edges.from/to` 必须表达真实语义方向；如果展示顺序与数据流方向相反，也要按真实流向填写，模板会尊重反向连接器。

## draw.io 视觉语言

- 架构图默认采用传统 draw.io 风格，画布保持白底，不采用网页 dashboard 或营销页风格。
- 字体与 Python 报告图表工具保持一致，优先 `FZXiaoBiaoSong-B05S`。
- 外部系统、人工服务、第三方接口放在边界或右侧独立容器，不混在内部主干层里。

## 节点文案

- 节点标题：2-8 个字，最多 12 个中文字符。
- 第二行可写技术或职责，例如 `API 服务\n鉴权 | 限流 | 路由`。
- 分层架构图不依赖页尾说明解释逻辑；主标题、层名、组名、节点和边必须能自解释。

## 推荐参数

- `diagram_type`: `layered_architecture`
- `direction`: 默认 `TB`，集成链路用 `LR`
- `layers`: 按展示顺序组织区域和模块
- `edges`: 只连接跨区域主关系或关键依赖
- `emphasis`: 模块级视觉强调，取值 `normal`、`high`、`muted`；只有确认为核心能力时才写 `high`
- `variant`: 层或模块视觉变体，取值 `default`、`foundation`、`external`、`critical`
- `role`: 层或模块语义角色，取值 `entry`、`business`、`platform`、`data`、`infrastructure`、`external`、`support`
- `shape`: 模块形状，常用 `database` 表示数据存储；未明确时保持默认矩形。
- `flow_strength`: 边的主干强度，取值 `normal`、`strong`；核心数据流或能力支撑链路可写 `strong`
- `edges.from/to`: 真实流向或依赖方向；不要为了展示顺序反写。

## 示例节点抽象

```json
{
  "diagram_type": "layered_architecture",
  "layers": [
    {"id": "entry", "label": "入口层", "role": "entry", "items": [{"label": "统一门户"}, {"label": "移动端"}, {"label": "API Gateway"}]},
    {"id": "business", "label": "业务层", "role": "business", "items": [{"label": "工单管理"}, {"label": "报表中心"}, {"label": "监控工作台", "emphasis": "high"}]},
    {"id": "platform", "label": "平台层", "role": "platform", "items": [{"label": "认证权限"}, {"label": "消息服务"}, {"label": "规则引擎"}]},
    {"id": "data", "label": "数据层", "role": "data", "items": [{"label": "指标库", "shape": "database"}, {"label": "文件存储", "shape": "database"}, {"label": "知识库", "shape": "database"}]},
    {"id": "infra", "label": "基础设施", "role": "infrastructure", "variant": "foundation", "items": [{"label": "计算"}, {"label": "存储"}, {"label": "网络"}]}
  ],
  "edges": [
    {"from": "entry", "to": "business", "label": "访问业务"},
    {"from": "business", "to": "platform", "label": "调用能力", "flow_strength": "strong"},
    {"from": "platform", "to": "data", "label": "读写数据"},
    {"from": "data", "to": "infra", "label": "资源承载"}
  ]
}
```

## 视觉要求

- 使用清晰的区域 band 或 cluster，组名比节点更醒目。
- 主路径用实线，辅助依赖用虚线。
- 颜色不超过 3 个语义：主干、支撑、外部。
- 外部系统应放边界位置，不与内部模块混排。
- 分层架构图优先压缩层高并放大节点文字，适配方案/PPT 中的缩放阅读。
- 分层架构图上层业务/支撑模块默认不展示图标；底部传输、数据存储、感知等固定类型层可保留图标。
- 数据库、存储、队列、文档、云服务等明确组件类型应使用对应 draw.io 形状或语义 `icon`，不要把所有组件都画成同一种方框。
- 模板默认保证标题、层名、模块标题、模块说明和边标签有清晰字号/字重梯度；Agent 不要用长文本弥补视觉层级。
- 需要高亮核心模块时，Agent 必须显式给该 item 写 `emphasis="high"`；需要基座感时，显式给该 layer 写 `variant="foundation"`。
- 单层最多 1-3 个高亮模块；如果高亮太多，先重新判断核心对象。

## 禁止事项

- 不要把架构图画成普通步骤流程。
- 不要把部署节点、业务功能、代码组件混在同一层级。
- 不要让节点横向无限扩展；宁可合并节点，也不要依赖横向滚动阅读。
- 不要使用网页组件语言：浮动卡片、厚阴影、渐变背景、hover 效果、胶囊编号。
- 不要通过业务词、行业词或中文关键词触发模板样式；模板只能消费显式语义字段。
- 不要依赖底部说明弥补主图方向、分组或语义不清。
