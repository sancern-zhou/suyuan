# Layered Architecture Diagram Template

适用于明确分层的系统架构图，例如“感知层、网络层、IaaS、平台层、业务层”。目标是让读者看到自下而上的支撑关系和每层职责。

## P0 硬规则

- 每一层必须写入 `layers`，层级顺序不能跳。
- 每层必须有 `label`，层内模块必须归入 `groups/items`。
- 旧 `steps + group` 只用于兼容已有调用，新调用必须优先使用 `layers/groups/items`。
- 层间只画主干箭头，通常每相邻两层 1 条。
- 单个 group 超过 7 个模块，Agent 必须按业务语义拆成二级分组或合并为更高层能力项；模板不自动伪造业务分组。
- 单层模块过多时，不要让某一层视觉压过全图；优先由 Agent 拆分 group、合并同类项，模板只自动启用紧凑布局和小尺寸图标作为视觉保护。
- 展示文本默认只使用中文；不要在层名、组名或模块名中加入英文括注，例如不要写 `业务层（Operation Layer）`。
- 层名优先 2-6 个中文字符，模块名优先 2-8 个中文字符，最长不超过 10 个中文字符。
- 视觉强调由 Agent 显式字段驱动，不由模板按中文标签关键词推断。核心模块写 `emphasis="high"`，基座层写 `variant="foundation"`，外部依赖写 `variant="external"` 或 `role="external"`。

## 层级顺序

常见自下而上顺序：

1. 感知层：传感器、站点、视频、设备、闸门、采样器。
2. 网络层：4G、NB-IoT、LoRaWAN、专网、VPN、边缘网关。
3. 基础设施层：计算、存储、数据库、网络、安全、容器。
4. 平台/支撑层：设备管理、连接管理、GIS、规则、消息、账号、协议。
5. 业务应用层：监测平台、应急平台、业务管理、教育中心、移动端。

如果用户给的是“端-边-云-用”，按“端侧/边缘/云平台/业务应用”组织。

## 推荐布局

- 默认 `direction="TB"`，但语义是自下而上；如果工具渲染从上到下，应把业务层放最上、感知层放最下。
- 每层像一条横向 band：左侧层名，右侧模块网格。
- 层间箭头使用 2-6 个中文字符的短标签，例如“采集上传”“网络传输”“资源承载”“能力支撑”。
- 箭头方向必须和 `edges.from/to` 语义一致。业务在上、感知在下时，支撑关系通常向下；数据上传关系通常从感知层指向业务层，工具会尊重显式反向 edge。
- `edges.label` 只写关系动作，不重复 `from/to` 层名。

## 推荐参数

- `diagram_type`: `layered_architecture`
- `layout_engine`: `auto` 或省略
- `direction`: `TB`
- `layers`: 必填，按展示顺序从上到下排列
- `edges`: 连接层 `id`，只表达相邻层主干依赖
- `icon`: 可选，写在模块 item 上；需要图例时先读取 `icon-catalog.md`
- `role`: 可选，写在 layer 或 item 上，表达 `entry`、`business`、`platform`、`data`、`infrastructure`、`external`、`support`
- `variant`: 可选，写在 layer 或 item 上，表达 `default`、`foundation`、`external`、`critical`
- `emphasis`: 可选，写在 item 上，表达 `normal`、`high`、`muted`
- `flow_strength`: 可选，写在 edge 上，表达 `normal`、`strong`
- `icon_policy`: 可选，写在 layer 上，表达 `auto`、`show`、`hide`；默认 `auto` 只在底部两层显示图标。
- 分层架构图上层业务/支撑模块优先不用图标，因为类型常不完整且容易误导；传输、数据存储、感知等底部固定层可保留图标。
- 图标语义优先，不要为了去重乱选图标；底部环保/监测类模块优先使用 `noise`、`weather`、`network`、`database`、`timeseries`、`station`、`sensor` 等细分 token。
- 单层最多 1-3 个 `emphasis="high"`；高亮过多会削弱主次。

## 内容文案规范

- 层名：只写中文职责名，例如“业务层”“平台支撑层”“基础设施层”“网络层”“感知层”。
- 组名：写能力类别，例如“业务系统”“平台能力”“云基础服务”“通信方式”“监测设备”。
- 模块名：写具体能力或对象，不写完整句子。
- 不把英文翻译、技术解释、产品介绍放进 `label`；必要说明写入 `detail` 或上游文档，不依赖页尾说明补救主图。
- 单个 group 超过 7 个模块时，优先按语义拆成 2-3 个 group，或合并成更高层能力项。

## 示例分层

```json
{
  "diagram_type": "layered_architecture",
  "layers": [
    {
      "id": "business",
      "label": "业务应用层",
      "role": "business",
      "icon_policy": "hide",
      "groups": [
        {
          "label": "业务系统",
          "items": [
            {"label": "环境监测平台", "emphasis": "high"},
            {"label": "应急指挥平台"},
            {"label": "移动巡检端"}
          ]
        }
      ]
    },
    {
      "id": "support",
      "label": "平台支撑层",
      "role": "platform",
      "icon_policy": "hide",
      "groups": [
        {
          "label": "平台能力",
          "items": [
            {"label": "设备管理"},
            {"label": "规则引擎"},
            {"label": "GIS 服务"}
          ]
        }
      ]
    },
    {
      "id": "infra",
      "label": "基础设施层",
      "role": "infrastructure",
      "variant": "foundation",
      "items": [
        {"label": "弹性计算", "icon": "compute"},
        {"label": "关系数据库", "icon": "database"},
        {"label": "时序数据", "icon": "timeseries"},
        {"label": "对象存储", "icon": "object-storage"}
      ]
    }
  ],
  "edges": [
    {"from": "infra", "to": "support", "label": "资源承载"},
    {"from": "support", "to": "business", "label": "能力支撑", "flow_strength": "strong"}
  ]
}
```

## 视觉要求

- 层标题的视觉权重高于普通模块。
- 模块卡片等宽或等高，避免同层卡片忽大忽小。
- 分层图默认采用压缩层高和放大节点文字的展示方式，优先保证放入方案/PPT 后仍能看清文字。
- 高密度层自动采用更紧凑的网格和间距；但这只是视觉保护，不能替代 Agent 的语义拆分。
- 层之间留白要大于同层模块间距，形成清晰分隔。
- 不同层使用同色系深浅或低饱和区分，不要彩虹配色。
- 上层业务和支撑模块不要为了装饰添加图标；只有底部固定类型层或 Agent 明确 `icon_policy="show"` 时才展示图标。
- 模板默认提供更强的标题、编号、箭头、文字和图标对比度；Agent 只需声明语义，不要在 label 中写“重点”“核心”来暗示样式。

## 禁止事项

- 不要只连接层标题，却让层内模块无约束横向铺开。
- 不要把上下层关系画成复杂网状依赖。
- 不要在分层图中加入过多异常流程、审批流程；这些应另画 process 图。
- 不要让模板或调用方按 `label` 关键词自动套用 `emphasis`、`variant` 或强箭头。
- 不要期待模板自动拆分、合并、改名或选择业务重点；这些不确定决策必须由 Agent 按规范完成。
- 不要依赖底部说明解释架构逻辑；分层图产物默认不渲染页尾说明。
