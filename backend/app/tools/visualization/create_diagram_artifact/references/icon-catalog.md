# Diagram Icon Catalog

调用 `create_diagram_artifact` 且图中模块需要图例时读取本文件。图例只辅助识别模块类型，不替代文字标签。

## 使用规则

- `icon` 是可选字段，写在 `layers[].items[]` 或 `layers[].groups[].items[]` 上。
- 只给关键模块加图例；同一组内不要每个模块都强行加不同图例。
- 图例必须与模块语义一致，不确定时省略 `icon`。
- 不使用云厂商具体产品图标；这里只使用通用架构图例。
- 图例 token 使用英文小写，展示文本仍按模板要求使用中文。
- 同一个 group 内，连续模块不要使用完全相同图标超过 2 次。
- 同一层内，核心模块优先使用不同图标，避免整层都使用 `app`、`sensor`、`device` 等兜底图标。
- 如果模块语义确实相同，可以使用相同图标，但应通过模块名、分组、层主题色或必要的 `detail` 区分。
- 不要为了去重乱选图标，语义优先；无法确定时宁可省略 `icon`。
- 分层架构图默认只在底部两层展示图标；业务应用层、平台支撑层优先不写 `icon`，除非 Agent 明确设置该层 `icon_policy="show"`。

## 常用图例

| token | 适用模块 | 示例 |
|---|---|---|
| `web` | Web 站点、浏览器入口、门户 | 统一门户、Web 管理端 |
| `mobile` | 移动端、App、小程序 | 移动巡检端、移动告警 |
| `desktop` | PC 客户端、桌面工作台 | 监控工作台 |
| `app` | 业务应用、应用模块集合 | 业务管理、报表中心 |
| `user` | 用户、角色、组织 | 运维人员、管理员 |
| `dashboard` | 驾驶舱、看板、监控大屏 | 综合驾驶舱、态势看板 |
| `workflow` | 工作流、流程编排、协同办理 | 工单流转、审批流程 |
| `report` | 报表、统计报告、分析报告 | 报表中心、统计分析 |
| `search` | 检索、查询、发现服务 | 综合查询、全文检索 |
| `sync` | 同步、交换、数据对接 | 数据同步、系统对接 |
| `notification` | 通知、提醒、消息送达 | 通知服务、消息提醒 |
| `api` | API、接口服务、开放接口 | 开放 API、接口服务 |
| `gateway` | 网关、接入层、路由入口 | API 网关、物联网网关 |
| `server` | 服务器、主机、应用服务 | 应用服务器、云服务器 |
| `compute` | 计算资源、算力、任务执行 | 弹性计算、计算节点 |
| `container` | 容器、容器平台、编排 | 容器服务、K8s 集群 |
| `database` | 关系数据库、业务库、指标库 | 业务数据库、指标库 |
| `timeseries` | 时序库、监测时间序列 | 时序数据库、分钟数据 |
| `warehouse` | 数据仓库、主题库、宽表 | 数据仓库、专题库 |
| `object-storage` | 对象存储、非结构化资源 | 图片存储、附件对象 |
| `lake` | 数据湖、原始数据池 | 数据湖、原始数据 |
| `storage` | 文件、对象存储、缓存、数据仓库 | 对象存储、缓存服务 |
| `cloud` | 云平台、云资源、云服务集合 | 云平台、云支撑能力 |
| `network` | 网络、专线、通信链路 | 4G 网络、专网 |
| `message` | 消息、事件、队列、通知 | 消息服务、事件推送 |
| `security` | 认证、权限、安全、防护 | 认证权限、Web 应用安全 |
| `rule` | 规则、策略、判断引擎 | 规则引擎、告警规则 |
| `map` | GIS、地图、空间服务 | GIS 管理、地图展示 |
| `file` | 文档、报告、附件、知识文件 | 报告文件、附件归档 |
| `video` | 视频、摄像头、视频监控 | 视频监控 |
| `camera` | 摄像机、抓拍设备、视频采集 | 监控摄像机、抓拍设备 |
| `sensor` | 传感器、采集设备、监测终端 | 监测设备、空气站 |
| `device` | 通用硬件、终端、物联设备 | 在线设备、电动闸门 |
| `terminal` | 终端设备、边缘终端、采集终端 | 采集终端、边缘终端 |
| `meter` | 仪表、计量设备、表计 | 流量计、在线仪表 |
| `switch` | 开关、闸门、控制设备 | 电动闸门、远程开关 |
| `water` | 水环境、水质、水源地 | 水质监测、水源地 |
| `air` | 空气质量、大气环境 | 空气监测、大气站 |
| `weather` | 气象综合、天气条件 | 气象监测、天气态势 |
| `wind` | 风场、风速、风向 | 风场分析、风速监测 |
| `rain` | 降雨、雨量、水文气象 | 降雨监测、雨量站 |
| `temperature` | 温度、热环境 | 温度监测、热环境 |
| `humidity` | 湿度、含水率 | 湿度监测、空气湿度 |
| `noise` | 噪声、声环境 | 噪声监测、声环境 |
| `soil` | 土壤、土壤环境 | 土壤监测、土壤调查 |
| `groundwater` | 地下水、地下水位 | 地下水监测、水位监测 |
| `emission` | 废气、废水、排放口、污染排放 | 排放监管、废气监测 |
| `outfall` | 排口、入河排污口、外排口 | 排口监管、入河排口 |
| `pipeline` | 管网、管线、输送链路 | 污水管网、雨污管线 |
| `waste` | 固废、垃圾、一般废弃物 | 固废监管、垃圾处置 |
| `hazard` | 危废、风险源、危险事件 | 危废监管、风险源 |
| `factory` | 企业、工厂、污染源单位 | 企业污染源、重点企业 |
| `river` | 河流、断面、水系 | 河流断面、流域监测 |
| `station` | 站点、自动站、监测站房 | 空气站、水质站 |
| `alarm` | 告警、预警、异常事件 | 告警中心、超标预警 |
| `sampling` | 采样、样品采集 | 手工采样、采样任务 |
| `lab` | 实验室、检测分析 | 实验室检测、样品分析 |
| `inspection` | 巡检、现场检查、执法核查 | 现场巡检、执法检查 |
| `drone` | 无人机、空中巡查 | 无人机巡检、航拍巡查 |
| `satellite` | 卫星遥感、遥感监测 | 卫星遥感、遥感反演 |
| `model` | 模型计算、模拟评估 | 扩散模型、数值模拟 |
| `forecast` | 预测预报、趋势研判 | 空气质量预报、趋势预测 |
| `trace` | 溯源、轨迹、来源解析 | 污染溯源、轨迹分析 |
| `external` | 外部系统、第三方接口 | 第三方平台、外部 API |

## 分层架构图建议

- 上层业务应用、平台支撑、对外服务：默认不使用图标，直接强化文字。
- 底部传输、数据存储、基础设施、感知采集：可使用图标，因为类型相对稳定。
- 如用户要求全图无图标，给所有 layer 设置 `icon_policy="hide"`。
- 如某个上层确有稳定图标语义，给该 layer 设置 `icon_policy="show"`，并只给少量关键模块写 `icon`。

## 通用图例选择

- 入口层：`web`、`mobile`、`desktop`、`user`、`dashboard`。
- 接入层：`api`、`gateway`、`network`、`security`。
- 服务层：`server`、`app`、`workflow`、`rule`、`message`、`notification`、`map`、`search`、`sync`、`report`。
- 数据层：`database`、`timeseries`、`warehouse`、`object-storage`、`lake`、`storage`、`file`。
- 基础设施层：`cloud`、`compute`、`container`、`server`、`network`。
- 感知层：`water`、`air`、`weather`、`wind`、`rain`、`temperature`、`humidity`、`noise`、`soil`、`groundwater`、`emission`、`factory`、`river`、`station`、`camera`、`alarm`、`sensor`、`terminal`、`meter`、`switch`、`device`、`video`、`network`。
- 环境业务层：`sampling`、`lab`、`inspection`、`drone`、`satellite`、`model`、`forecast`、`trace`、`pipeline`、`outfall`、`waste`、`hazard`。

## 避免重复图例

- 同一 group 中如果模块超过 3 个，先按语义选择更细 token，不要全部使用 `app`、`sensor`、`device`。
- 连续模块不要使用完全相同图标超过 2 次；如果连续项确实同类，优先拆成更具体的 group。
- 同一层内的核心模块优先使用不同图标，例如“水质监测/空气监测/排放监管/河流断面”应优先使用 `water`、`air`、`emission`、`river`。
- 不要为了去重乱选图标；图标必须能被模块名称自然解释。
- 图标选择由 Agent 在工具调用前显式填写 `icon` token；模板不会根据中文模块名自动匹配图标。

## 环保场景映射

| 模块语义 | 推荐 token |
|---|---|
| 水环境、水质、水源地 | `water` |
| 大气、空气质量、空气站 | `air` 或 `station` |
| 气象综合、天气条件 | `weather` |
| 风场、风速、风向 | `wind` |
| 降雨、雨量 | `rain` |
| 温度、热环境 | `temperature` |
| 湿度、含水率 | `humidity` |
| 噪声、声环境 | `noise` |
| 土壤、土壤环境 | `soil` |
| 地下水、地下水位 | `groundwater` |
| 废气、废水、排放口 | `emission` |
| 排口、入河排污口、外排口 | `outfall` |
| 管网、管线、输送链路 | `pipeline` |
| 固废、垃圾、一般废弃物 | `waste` |
| 危废、风险源、危险事件 | `hazard` |
| 企业、污染源单位、工厂 | `factory` |
| 河流、断面、流域 | `river` |
| 自动站、监测站房 | `station` |
| 摄像机、视频采集 | `camera` 或 `video` |
| 超标、预警、异常事件 | `alarm` |
| 采样、样品采集 | `sampling` |
| 实验室、检测分析 | `lab` |
| 巡检、现场检查、执法核查 | `inspection` |
| 无人机、空中巡查 | `drone` |
| 卫星遥感、遥感监测 | `satellite` |
| 模型计算、模拟评估 | `model` |
| 预测预报、趋势研判 | `forecast` |
| 溯源、轨迹、来源解析 | `trace` |
| 采集终端、边缘终端 | `terminal` |
| 在线仪表、计量表 | `meter` |
| 闸门、开关、控制设备 | `switch` |

## 平台与数据映射

| 模块语义 | 推荐 token |
|---|---|
| 驾驶舱、态势看板 | `dashboard` |
| 工单、审批、协同流程 | `workflow` |
| 报表、统计分析 | `report` |
| 查询、检索 | `search` |
| 系统对接、数据交换 | `sync` |
| 通知、提醒、送达 | `notification` |
| 时序监测数据 | `timeseries` |
| 数据仓库、专题库 | `warehouse` |
| 附件、图片、非结构化对象 | `object-storage` |
| 原始数据湖 | `lake` |

## 示例

```json
{
  "label": "数据层",
  "items": [
    {"label": "业务数据库", "icon": "database"},
    {"label": "时序数据", "icon": "timeseries"},
    {"label": "对象存储", "icon": "object-storage"},
    {"label": "报告文件", "icon": "file"}
  ]
}
```
