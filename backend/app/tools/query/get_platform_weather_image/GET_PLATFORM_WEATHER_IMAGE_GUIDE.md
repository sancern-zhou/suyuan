# 环境大数据管理云平台气象图片工具说明

## 概述

使用 `get_platform_weather_image` 获取环境大数据管理云平台的气象图片，也可以查询已由 NMC 抓取器缓存的中国地面天气形势图。

调用工具前必须先阅读本文件。工具 schema 只保留轻量参数说明，产品清单、时间规则、中文名映射、示例和扩展方式均以本文件为准。

## 适用场景

- 用户需要全国降水量预报图、逐时降水量预报图、能见度图、全国雷达拼图、全国24小时降水量、城市预测轨迹图或城市后向轨迹图。
- 污染溯源报告需要引用中央气象台风场、降水、能见度等天气图作为气象背景。
- 报告、PPT、污染过程分析需要引用气象背景图片。
- 需要把平台图片保存为本地文件，再交给图片分析、报告生成或PPT工具使用。

## 工具参数

- `product`：图片产品类型，可用标准值或中文名。
- `date`：日期，支持 `YYYYMMDD` 或 `YYYY-MM-DD`，默认当天。
- `time`：统一时间/时效参数，按下方产品表填写。时效图使用三位字符串如 `024`，小时图使用两位字符串如 `06`，雷达拼图使用 `HH:MM` 如 `15:12`，城市预测轨迹图使用城市名或9位城市编码，城市后向轨迹图使用 `城市,轨迹日期`。
- `download`：是否下载图片，默认 `true`。

## 已支持产品

| 标准值 | 中文名 | 平台编号 | 时间规则 |
| --- | --- | --- | --- |
| `forecast_trajectory` | 城市预测轨迹图 | `1013` | 每天一张；`time` 填城市名如 `广州`、`东莞`，或9位城市编码如 `101280101` |
| `backward_trajectory` | 城市后向轨迹图 | `1014` | 每天一张；`date` 为平台目录日期，`time` 填 `城市,轨迹日期`，如 `南昌,20260608` |
| `national_precip_forecast` | 全国降水量预报图 | `1012` | 使用三位预报时效，如 `024`、`048` |
| `hourly_precip_forecast` | 逐时降水量预报图 | `1023` | 每6小时一张：`06`、`12`、`18`、`24` |
| `visibility` | 中央气象台能见度图 | `1034` | 每小时一张 |
| `radar_mosaic` | 全国雷达拼图 | `1041` | `08:00` 到 `23:36`，每6分钟一张 |
| `rainfall_24h` | 全国24小时降水量 | `1051` | 每天固定 `00`、`06`、`12` 三张 |
| `hourly_wind_field` | 全国逐小时风场实况图 | `1052` | 每天从 `00` 时到 `07` 时 |
| `radar_composite_reflectivity` | 全国雷达组合反射率图 | `2111` | 使用三位时效，从 `001` 到 `072` |
| `precipitable_water` | 整层可降水量 | `2111` | 使用三位时效；样例包含 `000`，工具兼容 `000` 到 `072` |
| `***REMOVED***` | 24H内的10m最大风速 | `2111` | 三个预报尺度：`024`、`048`、`072` |
| `***REMOVED***` | 24H降水预报 | `2111` | 从 `024` 到 `072`，每小时一张 |
| `grapes_gfs_radar_reflectivity` | GRAPES_GFS(雷达组合反射率)预报图 | `2112` | 从 `003` 到 `240`，每3小时一张 |
| `national_max_temperature_forecast` | 中央气象台全国气温预报图（最高气温） | `2114` | 从 `024` 到 `240`，每24小时一张 |
| `national_min_temperature_forecast` | 中央气象台全国气温预报图（最低气温） | `2114` | 从 `024` 到 `240`，每24小时一张 |
| `nmc_surface_weather_chart` | 中国地面天气形势图 | NMC 抓取缓存 | `time` 填 `latest`、`最新`，或页面显示时间如 `08/08 20:00` |

NMC 天气形势图示例：

```json
{
  "product": "nmc_surface_weather_chart",
  "time": "latest"
}
```

该产品读取 `nmc_weather_chart_fetcher` 已缓存的图片，不直接套用环境大数据平台的固定 URL 模板。

## 调用示例

获取 2026-06-09 024 时效的全国降水量预报图：

```json
{
  "product": "national_precip_forecast",
  "date": "20260609",
  "time": "024"
}
```

获取 2026-06-09 15:12 的全国雷达拼图：

```json
{
  "product": "radar_mosaic",
  "date": "20260609",
  "time": "15:12"
}
```

获取 2026-06-10 广州城市预测轨迹图：

```json
{
  "product": "forecast_trajectory",
  "date": "20260610",
  "time": "广州"
}
```

该产品 URL 构成为：`{平台域名}:8313/1013/{YYYYMMDD}/{城市编码}{YYYYMMDD}.gif`。例如广州为 `101280101`，对应 `.../1013/20260610/10128010120260610.gif`。

获取 2026-06-10 平台目录下、轨迹日期为 2026-06-08 的南昌后向轨迹图：

```json
{
  "product": "backward_trajectory",
  "date": "20260610",
  "time": "南昌,20260608"
}
```

该产品 URL 构成为：`{平台域名}:8313/1014/{目录日期}/{城市编码}{轨迹日期}.gif`。例如南昌为 `101240101`，对应 `.../1014/20260610/10124010120260608.gif`。`time` 也可写为 `101240101,2026-06-08`。

## 返回结果使用

返回结果要按消费方区分使用，不能混用：

### 前端聊天框/可视化面板

- `visuals` / `data.visuals`：前端可直接消费的图片块，包含 `type=image`、`image_url`、`local_path`、`markdown_image`。
- `data.image_url`：前端聊天框可直接消费的图片 URL，格式为 `/api/image/{image_id}`；只有 `download=true` 且下载成功时返回。
- `data.image_id`：图片缓存 ID，对应 `data.image_url`，可作为前端展示标识使用。
- 最终回复中需要展示图片时，优先使用 `visuals[0].markdown_image`；如果需要手动拼 Markdown，可使用 `data.image_url`。
- 不要向用户暴露平台原始内网 URL。工具内部会访问平台地址，但结果中面向前端的是 `/api/image/{image_id}`。

### 后端图片分析/工具链调用

- 调用图片分析工具时，必须使用 `data.local_path` 或 `visuals[].local_path`。
- 不要把 `data.image_url`、`visual_ids` 或 `/api/image/{image_id}` 当成本地文件路径传给图片分析工具；这些是前端展示 URL 或缓存标识。
- 如果上下文压缩后只剩 `visual_ids`，但没有 `data.local_path`，应重新调用本工具并设置 `download=true` 获取完整返回，或按固定保存目录查找文件，不要根据 `visual_id` 猜测 `/api/image/...` 作为分析输入。

### 报告/PPT/文件资产

- 需要把图片写入报告、PPT或作为文件资产引用时，优先使用 `data.local_path` 或 `visuals[].local_path`。
- `data.local_path` 是固定保存位置的本地 PNG 文件路径，即使 `download=false` 也会返回该预期路径。
- `data.downloaded` 表示图片是否已经下载并写入 `data.local_path`。只有 `data.downloaded=true` 时，本地路径才保证可直接读取。

### 其他字段

- `data.product_name`：中文产品名。
- `data.time_key`：工具归一化后的时次或时效。
- `download=false` 时不会生成前端图片缓存 URL，`data.image_url` 和 `data.image_id` 为空，`visuals` 为空；此模式只适合查看预期路径或进行轻量校验。

## 扩展规则

新增平台图片产品时，先在 `tool.py` 的 `PRODUCTS` 配置中增加：

- `key`
- `code`
- `name`
- `filename_template`
- `required`
- 时间约束字段
- 常用中文别名

然后在 `tool_test.py` 增加至少一个真实示例 URL 的精确匹配测试。
