# 江西省噪声平台 API 与项目工具说明

## 1. 平台概述

江西省噪声平台提供噪声、气象和车流量数据查询能力。江西项目通过五个按数据粒度拆分的异步 LLM 工具访问平台。

平台访问要求：

- Token 端点：`GET /api/noiseproduct/AirCityBaseCommon/GetExternalApiToken`
- Token 参数：`UserName`、`SecretKey`
- 数据请求头：`Authorization: Bearer <token>`
- 必需请求头：`syscode: NOISE`
- 时间格式：`YYYY-MM-DD HH:MM:SS`
- 平台目前提供的是 HTTP 地址；部署侧必须通过网络访问控制、VPN 或安全反向代理降低 Token 明文传输风险。

代码和日志不得保存、输出或提交认证密钥、Token 或 Token 前缀。

## 2. 当前工具开放范围

当前开放五个独立分页查询工具：

| 工具 | 能力 | 端点 |
|---|---|---|
| `query_jiangxi_noise_city_hour` | 城市小时聚合值 | `/api/noiseproduct/airdata/DATCityHour/GetFunCityHourDisplayListAsync` |
| `query_jiangxi_noise_station_minute` | 站点分钟值 | `/api/noiseproduct/airdata/DATStationMinute/GetDATStationMinuteDisplayPagedListAsync` |
| `query_jiangxi_noise_station_hour` | 站点小时值 | `/api/noiseproduct/airdata/DATStationHour/GetDATStationHourDisplayPagedListAsync` |
| `query_jiangxi_noise_station_day` | 站点日均值 | `/api/noiseproduct/airdata/DATStationDay/GetDATStationDayDisplayPagedListAsync` |
| `query_jiangxi_noise_station_statistics` | 站点任意时段统计值 | `/api/noiseproduct/airdata/DATStationDay/GetNoiseStationAnyDateDisplayPagedListAsync` |

工具支持自动翻页、江西省/地市/站点名称解析、站点编码查询和大结果外部化。

## 3. 运行配置

江西部署环境必须配置：

```bash
export PROJECT="jiangxi"
export JIANGXI_NOISE_BASE_URL="http://<平台地址>:<端口>"
export JIANGXI_NOISE_USERNAME="<外部接口用户名>"
export JIANGXI_NOISE_SECRET_KEY="<外部接口密钥>"
export JIANGXI_NOISE_TIMEOUT_SECONDS="30"
```

`JIANGXI_NOISE_BASE_URL`、`JIANGXI_NOISE_USERNAME` 和 `JIANGXI_NOISE_SECRET_KEY` 没有代码内默认值。配置缺失时，工具返回 `configuration_error`，不会在服务启动阶段访问平台。

Token 在客户端内存中缓存。数据请求首次收到 HTTP 401 时，客户端重新认证并重试一次；第二次仍为 401 时终止请求。

## 4. LLM 工具参数

### 4.1 公共参数

| 参数 | 类型 | 说明 |
|---|---|---|
| `start_time` | ISO 8601 字符串 | 开始时间 |
| `end_time` | ISO 8601 字符串 | 结束时间 |
| `page_size` | 1-1000 整数 | 单页数量，默认 500 |
| `max_pages` | 1-100 整数 | 最大页数，默认 20 |
| `data_type` | 0 / 1 | 支持该参数的接口中，0 为原始数据，1 为审核数据 |

无时区时间按 `Asia/Shanghai` 解释；有时区时间转换为 `Asia/Shanghai`。`start_time` 不能晚于 `end_time`，单次查询跨度不能超过 30 天。

`query_jiangxi_noise_city_hour`、`query_jiangxi_noise_station_hour` 和
`query_jiangxi_noise_station_day` 默认使用审核数据（`data_type=1`）；分钟值和时段统计默认使用原始数据。

### 4.2 站点查询

站点查询必须提供 `station_codes`，不能同时提供 `city_names`。站点代码只接受字母、数字、下划线和短横线。

```json
{
  "station_codes": ["1737A"],
  "start_time": "2026-07-27T00:00:00+08:00",
  "end_time": "2026-07-28T00:00:00+08:00",
  "data_type": 1,
  "page_size": 500,
  "max_pages": 20
}
```

站点日均查询仅将 `granularity` 改为 `day`。

### 4.3 城市查询

城市查询必须提供 `city_names`，不能同时提供 `station_codes`，且 `granularity` 必须为 `hour`。`city_names` 接受下表中的城市名称或 6 位代码。

```json
{
  "cities": ["南昌市", "赣州市"],
  "start_time": "2026-07-27T00:00:00+08:00",
  "end_time": "2026-07-28T00:00:00+08:00",
  "data_type": 1,
  "page_size": 500,
  "max_pages": 20
}
```

## 5. 江西省城市代码

| 城市 | 代码 | 城市 | 代码 |
|---|---:|---|---:|
| 南昌市 | 360100 | 景德镇市 | 360200 |
| 萍乡市 | 360300 | 九江市 | 360400 |
| 新余市 | 360500 | 鹰潭市 | 360600 |
| 赣州市 | 360700 | 吉安市 | 360800 |
| 宜春市 | 360900 | 抚州市 | 361000 |
| 上饶市 | 361100 |  |  |

未知城市名称或代码会在本地被拒绝，不会转发到远端平台。

## 6. 平台请求参数

已开放端点使用相同的基础分页和时间参数：

```text
skipCount=0
maxResultCount=<1..1000>
dataType=<0|1>
timePoint[0]=YYYY-MM-DD HH:MM:SS
timePoint[1]=YYYY-MM-DD HH:MM:SS
```

站点接口追加：

```text
codes[0]=1737A
codes[1]=...
```

城市接口追加：

```text
CityCodes[0]=360100
CityCodes[1]=...
```

平台分页成功响应结构：

```json
{
  "success": true,
  "result": {
    "items": [],
    "totalCount": 0
  }
}
```

## 7. 工具返回结构

成功返回：

```json
{
  "status": "success",
  "success": true,
  "data": [],
  "metadata": {
    "tool_name": "query_jiangxi_noise_station_hour",
    "granularity": "hour",
    "total_records": 0,
    "pagination_truncated": false
  },
  "summary": "江西噪声站点小时数据查询完成"
}
```

工具自动翻页；结果超过对话预览上限时会保存完整数据并返回文件资源引用。达到 `max_pages` 仍未取完时，`metadata.pagination_truncated=true`。

失败返回：

```json
{
  "status": "failed",
  "success": false,
  "data": [],
  "error_code": "invalid_city",
  "error": "不支持的江西省城市：不存在市",
  "summary": "不支持的江西省城市：不存在市"
}
```

远端 HTTP 错误、认证错误和平台业务错误统一转换为稳定消息。远端 `msg`、原始响应、请求头及异常堆栈不会返回给 LLM。

## 8. 主要数据字段

站点小时值常见字段：`code`、`name`、`timePoint`、`leq`、`la`、`l5`、`l10`、`l50`、`l90`、`l95`、`lMin`、`lMax`、`vdr`、`sd`、`cityName`、`districtName`，以及气象和车流量字段。

站点日均值常见字段：`code`、`name`、`timePoint`、`ld`、`ln`、`ldn`、`lnMax`、`vdRd`、`vdRn` 和达标标识字段。

城市小时聚合值常见字段：`cityCode`、`cityName`、`timePointStr`、`leq_1`、`leq_2`、`leq_3`、`leq_4`。

平台部分数值以字符串返回，调用方在计算前应显式转换并处理空值。

## 9. Python 异步客户端示例

```python
import asyncio
from datetime import datetime

from app.external_apis.jiangxi_noise_api_client import JiangxiNoiseDataClient


async def main():
    client = JiangxiNoiseDataClient.from_env()
    result = await client.query_station_hour_data(
        station_codes=["1737A"],
        start_time=datetime.fromisoformat("2026-07-27T00:00:00+08:00"),
        end_time=datetime.fromisoformat("2026-07-28T00:00:00+08:00"),
        data_type=0,
        max_result_count=50,
    )
    print(result["total_count"], len(result["data"]))


asyncio.run(main())
```

示例依赖运行环境预先设置第三节列出的环境变量。不要在脚本中写入真实用户名或密钥。

## 10. 项目与分支隔离

- 专属分支：`project/jiangxi-noise`
- 项目清单：`projects/jiangxi/project.yaml`
- 模块清单：`modules/jiangxi-noise/module.yaml`
- 工具仅在项目启用 `jiangxi-noise` 模块并在项目清单中声明对应拆分工具时注册。
- `default` 项目不会注册该工具，其他项目无需拉取江西专属分支。

江西部署应直接检出并更新 `project/jiangxi-noise` 分支，不要把该分支拉取合并到其他项目分支。
