# 国家气象中心天气形势图查询工具说明

## 概述

`get_platform_weather_image` 仅用于查询 `nmc_weather_chart_fetcher` 已抓取并缓存的国家气象中心中国地面天气形势图。

## 数据来源

- 来源：国家气象中心（NMC）。
- 缓存 schema：`nmc_weather_chart`。
- 产品：`nmc_surface_weather_chart`（中国地面天气形势图）。
- 工具读取 fetcher 已登记的数据和本地图片，不直接请求其他图片平台。

## 参数

- `product`：固定填写 `nmc_surface_weather_chart`。
- `time`：可省略或填写 `latest`、`最新`；也可填写 fetcher 记录的页面显示时间，如 `08/11 08:00`。
- 传入 `date` 时，即使 `time=latest` 也只返回该日期的缓存图；未命中时会返回当前缓存日期范围。
- `date`：可选，格式为 `YYYYMMDD` 或 `YYYY-MM-DD`，与 `time` 一起用于筛选缓存时次。
- `download`：是否返回前端图片展示信息，默认 `true`。

## 调用示例

查询最新天气形势图：

```json
{
  "product": "nmc_surface_weather_chart",
  "date": "20260811",
  "time": "latest"
}
```

查询指定页面显示时间的天气形势图：

```json
{
  "product": "nmc_surface_weather_chart",
  "date": "2026-08-11",
  "time": "08/11 08:00"
}
```

## 返回结果

- `data.product_name`：中国地面天气形势图。
- `data.time_key`：fetcher 记录的页面显示时间。
- `data.source`：国家气象中心（NMC）。
- `data.local_path`：fetcher 缓存的本地图片路径，供 `read_file` 或报告工具读取。
- `data.image_url`：前端可访问的图片地址；仅在 `download=true` 时返回。
- `data.data_id`：`nmc_weather_chart` 数据登记 ID。
- `visuals`：前端图片展示块。

如果没有匹配缓存，工具返回 `not_found`，应先确认 `nmc_weather_chart_fetcher` 已产生对应时次数据。
