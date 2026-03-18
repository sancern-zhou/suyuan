# 站点查询与企业查询API使用说明

## 📋 概述

本API服务提供站点查询、区县信息查询和企业查询功能，支持根据站点编码、站点名称、经纬度坐标等多种方式查询附近站点和企业，以及查询站点的详细区县信息和企业的排放信息。

**服务版本**: 3.0.0
**基础URL**: `http://180.184.91.74:9095`
**数据源**: 支持376个站点的完整地理信息 + 94,703条企业排放数据

---

## 🚀 快速开始

### 启动服务
```bash
# Windows
start_updated_api.bat

# 或直接运行
python start_nearest_stations.py
```

### 测试服务
```bash
# 健康检查
curl "http://180.184.91.74:9095/health"

# 站点查询测试
curl "http://180.184.91.74:9095/api/nearest-stations/by-coordinates?lat=23.1291&lon=113.2644&max_distance=5&max_results=5"

# 企业查询测试
curl "http://180.184.91.74:9095/api/enterprises/by-coordinates?lat=23.1291&lon=113.2644&max_distance=5&max_results=5"
```

---

## 📡 API端点总览

### 附近站点查询
- `GET /api/nearest-stations/by-station-code` - 根据站点编码查询附近站点
- `GET /api/nearest-stations/by-station-name` - 根据站点名称查询附近站点
- `GET /api/nearest-stations/by-coordinates` - 根据经纬度查询附近站点

### 区县信息查询
- `GET /api/station-district/by-station-code` - 根据站点编码查询区县信息
- `GET /api/station-district/by-station-name` - 根据站点名称查询区县信息
- `GET /api/station-district/by-district-name` - 根据区县名称查询站点列表
- `GET /api/station-district/summary` - 获取所有区县统计信息
- `GET /api/station-district/by-city` - 根据城市查询辖内所有站点（支持可选字段）

### 企业查询 🆕
- `GET /api/enterprises/by-coordinates` - 根据经纬度查询附近企业
- `GET /api/enterprises/by-station-code` - 根据站点编码查询附近企业
- `GET /api/enterprises/by-station-name` - 根据站点名称查询附近企业
- `GET /api/enterprises/industry-stats` - 获取指定范围内的行业统计
- `GET /api/enterprises/emission-summary` - 获取指定范围内的排放汇总
- `GET /api/enterprises/top-emission` - 获取排放量最高的企业
- `GET /api/enterprises/search` - 根据企业名称搜索企业

### 系统信息
- `GET /health` - 健康检查
- `GET /` - API说明文档

---

## 🔍 详细API说明

### 1. 根据站点编码查询附近站点

**端点**: `GET /api/nearest-stations/by-station-code`

**参数**:
- `station_code` (必需): 站点编码
- `max_distance` (可选): 最大距离，单位公里，默认10.0
- `max_results` (可选): 最大结果数，默认10

**请求示例**:
```bash
curl "http://180.184.91.74:9095/api/nearest-stations/by-station-code?station_code=4401000001&max_distance=5&max_results=5"
```

**响应示例**:
```json
{
  "status": "success",
  "total": 3,
  "data": [
    {
      "站点名称": "帽峰山森林公园",
      "唯一编码": "440100001",
      "所属城市": "广州",
      "所属区县": "白云区",
      "经度": 113.443,
      "纬度": 23.3035,
      "地址": "广东省广州市白云区太和镇铜锣湾水库",
      "距离": 2.5
    }
  ]
}
```

### 2. 根据站点名称查询附近站点

**端点**: `GET /api/nearest-stations/by-station-name`

**参数**:
- `station_name` (必需): 站点名称（支持模糊匹配）
- `max_distance` (可选): 最大距离，单位公里，默认10.0
- `max_results` (可选): 最大结果数，默认10

**请求示例**:
```bash
curl "http://180.184.91.74:9095/api/nearest-stations/by-station-name?station_name=广雅中学&max_distance=5&max_results=5"
```

### 3. 根据经纬度查询附近站点

**端点**: `GET /api/nearest-stations/by-coordinates`

**参数**:
- `lat` (必需): 纬度
- `lon` (必需): 经度
- `max_distance` (可选): 最大距离，单位公里，默认10.0
- `max_results` (可选): 最大结果数，默认10

**请求示例**:
```bash
curl "http://180.184.91.74:9095/api/nearest-stations/by-coordinates?lat=23.1331&lon=113.2597&max_distance=5&max_results=5"
```

### 4. 根据站点编码查询区县信息

**端点**: `GET /api/station-district/by-station-code`

**参数**:
- `station_code` (必需): 站点编码

**请求示例**:
```bash
curl "http://180.184.91.74:9095/api/station-district/by-station-code?station_code=4401000001"
```

**响应示例**:
```json
{
  "status": "success",
  "data": {
    "站点名称": "广东南岭",
    "唯一编码": "4401000001",
    "区县": "阳山县",
    "城市": "广州",
    "省份": "广东省",
    "乡镇": "秤架瑶族乡",
    "详细地址": "广东省清远市阳山县秤架瑶族乡广东屋脊",
    "行政区划代码": "441823",
    "经度": 112.8988,
    "纬度": 24.6988
  }
}
```

### 5. 根据站点名称查询区县信息

**端点**: `GET /api/station-district/by-station-name`

**参数**:
- `station_name` (必需): 站点名称（支持模糊匹配）
- `top_k` (可选): 返回前K个最相近的匹配，默认1

**请求示例**:
```bash
# 查询最匹配的1个站点
curl "http://180.184.91.74:9095/api/station-district/by-station-name?station_name=广雅"

# 查询最匹配的3个站点
curl "http://180.184.91.74:9095/api/station-district/by-station-name?station_name=广雅&top_k=3"
```

**响应示例 (top_k=1)**:
```json
{
  "status": "success",
  "data": {
    "站点名称": "广雅中学",
    "唯一编码": "440100051",
    "区县": "荔湾区",
    "城市": "广州",
    "省份": "广东省",
    "乡镇": "南源街道",
    "详细地址": "广东省广州市荔湾区南源街道水厂路",
    "行政区划代码": "440103",
    "经度": 113.2347,
    "纬度": 23.1422
  }
}
```

### 6. 根据区县名称查询站点列表

**端点**: `GET /api/station-district/by-district-name`

**参数**:
- `district_name` (必需): 区县名称（支持模糊匹配）

**请求示例**:
```bash
curl "http://180.184.91.74:9095/api/station-district/by-district-name?district_name=白云区"
```

**响应示例**:
```json
{
  "status": "success",
  "total": 15,
  "data": [
    {
      "站点名称": "帽峰山森林公园",
      "唯一编码": "440100001",
      "所属城市": "广州",
      "所属区县": "白云区",
      "经度": 113.443,
      "纬度": 23.3035,
      "地址": "广东省广州市白云区太和镇铜锣湾水库",
      "省份": "广东省",
      "城市": "广州市",
      "乡镇": "太和镇",
      "行政区划代码": "440111"
    }
  ]
}
```

### 7. 获取区县统计信息

**端点**: `GET /api/station-district/summary`

**请求示例**:
```bash
curl "http://180.184.91.74:9095/api/station-district/summary"
```

**响应示例**:
```json
{
  "status": "success",
  "total_districts": 45,
  "data": {
    "白云区": 15,
    "越秀区": 8,
    "荔湾区": 6,
    "天河区": 12,
    "海珠区": 9,
    "黄埔区": 7,
    "番禺区": 11,
    "花都区": 5,
    "南沙区": 4,
    "从化区": 3,
    "增城区": 6
  }
}
```

### 8. 根据城市查询辖内站点（支持可选字段） 🆕

**端点**: `GET /api/station-district/by-city`

**参数**:
- `city_name` (必需): 城市名称（支持模糊匹配，如“广州”匹配“广州市”）
- `fields` (可选): 逗号分隔的字段列表，取值范围：`name,code,lat,lon,district,township`
  - 默认返回：`name,code,lat,lon,district,township`

**请求示例**:
```bash
# 1) 使用默认字段
curl "http://180.184.91.74:9095/api/station-district/by-city?city_name=广州"

# 2) 自定义字段，仅返回名称与经纬度
curl "http://180.184.91.74:9095/api/station-district/by-city?city_name=广州&fields=name,lat,lon"
```

**响应示例（自定义字段：name,lat,lon）**:
```json
{
  "status": "success",
  "city_query": "广州",
  "total": 2,
  "fields": ["name", "lat", "lon"],
  "data": [
    {"站点名称": "广雅中学", "纬度": 23.1291, "经度": 113.2424},
    {"站点名称": "天河体育中心", "纬度": 23.1365, "经度": 113.3258}
  ]
}
```

### 8.1. 站点类型ID筛选[object Object]

**适用接口**: `GET /api/station-district/by-city`

**新增参数**:
- `station_type_id` (可选): 站点类型ID筛选，支持精确匹配，默认不筛选
- `fields` 参数新增 `type_id` 选项，用于返回站点类型ID字段

**站点类型ID说明**:
- `1.0`: 城市环境评价点 (134个站点)
- `2.0`: 区域环境评价点 (126个站点)
- `3.0`: 港澳台站点 (5个站点)
- `4.0`: 对照点 (2个站点)
- `5.0`: 污染监控点 (80个站点)
- `6.0`: 工业园区点 (5个站点)
- `7.0`: 组分网/特殊监测点 (7个站点)
- `8.0`: 背景点 (1个站点)
- `9.0`: 传输通道点 (3个站点)
- `15.0`: 路边交通点 (12个站点)

**筛选示例**:
```bash
# 查询广州市所有城市环境评价点
curl "http://180.184.91.74:9095/api/station-district/by-city?city_name=广州&station_type_id=1.0"

# 查询深圳市所有路边交通点，只返回名称和类型ID
curl "http://180.184.91.74:9095/api/station-district/by-city?city_name=深圳&station_type_id=15.0&fields=name,type_id"

# 查询所有污染监控点
curl "http://180.184.91.74:9095/api/station-district/by-city?city_name=广东&station_type_id=5.0"
```

**筛选响应示例**:
```json
{
  "status": "success",
  "city_query": "广州",
  "station_type_id_filter": 1.0,
  "total": 15,
  "fields": ["name", "code", "type_id"],
  "station_type_stats": {
    "1.0": 15
  },
  "data": [
    {
      "站点名称": "广雅中学",
      "唯一编码": "440100051",
      "站点类型ID": 1.0
    }
  ]
}
```

### 9. 健康检查

**端点**: `GET /health`

**请求示例**:
```bash
curl "http://180.184.91.74:9095/health"
```

**响应示例**:
```json
{
  "status": "healthy",
  "service": "nearest-stations-api",
  "stations_count": 376,
  "enterprises_count": 94703
}
```

---

## 🏭 企业查询API详细说明

### 9. 根据经纬度查询附近企业

**端点**: `GET /api/enterprises/by-coordinates`

**参数**:
- `lat` (必需): 纬度
- `lon` (必需): 经度
- `max_distance` (可选): 最大距离，单位公里，默认5.0
- `max_results` (可选): 最大结果数，默认100
- `industry_filter` (可选): 行业过滤，如"机动车燃油零售"
- `[污染物]_threshold` (可选): 排放阈值过滤，如`VOCs_threshold=1.0`

**支持的污染物类型**: SO2, NOx, PM2.5, PM10, CO, VOCs

**请求示例**:
```bash
# 基础查询
curl "http://180.184.91.74:9095/api/enterprises/by-coordinates?lat=23.1291&lon=113.2644&max_distance=5&max_results=10"

# 带行业过滤
curl "http://180.184.91.74:9095/api/enterprises/by-coordinates?lat=23.1291&lon=113.2644&max_distance=5&industry_filter=机动车燃油零售"

# 带排放阈值过滤
curl "http://180.184.91.74:9095/api/enterprises/by-coordinates?lat=23.1291&lon=113.2644&max_distance=5&VOCs_threshold=10.0&SO2_threshold=1.0"
```

**响应示例**:
```json
{
  "status": "success",
  "total": 5,
  "query_params": {
    "lat": 23.1291,
    "lon": 113.2644,
    "max_distance": 5.0,
    "max_results": 10,
    "industry_filter": null,
    "emission_threshold": {}
  },
  "data": [
    {
      "企业名称": "广州市荔湾区粉末静电喷涂厂",
      "企业编码": "",
      "行业": "金属表面处理及热处理加工",
      "地址": "",
      "经度": 113.2625,
      "纬度": 23.119722222222222,
      "城市": "广州市",
      "区县": "荔湾区",
      "省份": "广东省",
      "排放信息": {
        "SO2": 0.0,
        "NOx": 0.0,
        "PM2.5": 0.0,
        "PM10": 0.0,
        "CO": 0.0,
        "VOCs": 0.018853
      },
      "企业类型": "",
      "运营状态": "运营中",
      "距离": 1.061
    }
  ]
}
```

### 10. 根据站点编码查询附近企业

**端点**: `GET /api/enterprises/by-station-code`

**参数**:
- `station_code` (必需): 站点编码
- `max_distance` (可选): 最大距离，单位公里，默认5.0
- `max_results` (可选): 最大结果数，默认100
- `industry_filter` (可选): 行业过滤
- `[污染物]_threshold` (可选): 排放阈值过滤

**请求示例**:
```bash
curl "http://180.184.91.74:9095/api/enterprises/by-station-code?station_code=440104003&max_distance=3&max_results=5"
```

### 11. 根据站点名称查询附近企业

**端点**: `GET /api/enterprises/by-station-name`

**参数**:
- `station_name` (必需): 站点名称（支持模糊匹配）
- `max_distance` (可选): 最大距离，单位公里，默认5.0
- `max_results` (可选): 最大结果数，默认100
- `industry_filter` (可选): 行业过滤
- `[污染物]_threshold` (可选): 排放阈值过滤
- `simple_result` (可选): 🆕 简化结果，为`true`时只返回企业名称和经纬度坐标，默认`false`

**请求示例**:
```bash
# 基础查询
curl "http://180.184.91.74:9095/api/enterprises/by-station-name?station_name=增城新塘&max_distance=5&industry_filter=机动车燃油零售"

# 🆕 简化结果查询（只返回企业名称和经纬度）
curl "http://180.184.91.74:9095/api/enterprises/by-station-name?station_name=增城新塘&max_distance=5&simple_result=true"
```

**简化结果示例**:
```json
{
  "status": "success",
  "total": 3,
  "query_params": {
    "station_name": "增城新塘",
    "max_distance": 5.0,
    "max_results": 100,
    "simple_result": true
  },
  "data": [
    {
      "企业名称": "立高食品股份有限公司增城分公司",
      "经度": 113.79571944444444,
      "纬度": 23.190519444444444,
      "距离": 0.483
    },
    {
      "企业名称": "广州同明电子有限公司",
      "经度": 113.79555555555555,
      "纬度": 23.191111111111113,
      "距离": 0.531
    }
  ]
}
```

### 12. 获取行业统计信息

**端点**: `GET /api/enterprises/industry-stats`

**参数**:
- `lat` (必需): 纬度
- `lon` (必需): 经度
- `max_distance` (可选): 最大距离，单位公里，默认10.0

**请求示例**:
```bash
curl "http://180.184.91.74:9095/api/enterprises/industry-stats?lat=23.1291&lon=113.2644&max_distance=10"
```

**响应示例**:
```json
{
  "status": "success",
  "query_params": {
    "lat": 23.1291,
    "lon": 113.2644,
    "max_distance": 10.0
  },
  "data": {
    "机动车燃油零售": 96,
    "皮鞋制造": 230,
    "包装装潢及其他印刷": 145,
    "其他机织服装制造": 116,
    "塑料零件及其他塑料制品制造": 65,
    "糕点、面包制造": 28
  }
}
```

### 13. 获取排放汇总信息

**端点**: `GET /api/enterprises/emission-summary`

**参数**:
- `lat` (必需): 纬度
- `lon` (必需): 经度
- `max_distance` (可选): 最大距离，单位公里，默认10.0

**请求示例**:
```bash
curl "http://180.184.91.74:9095/api/enterprises/emission-summary?lat=23.1291&lon=113.2644&max_distance=5"
```

**响应示例**:
```json
{
  "status": "success",
  "query_params": {
    "lat": 23.1291,
    "lon": 113.2644,
    "max_distance": 5.0
  },
  "data": {
    "SO2": 0.197,
    "NOx": 5.868,
    "PM2.5": 0.168,
    "PM10": 0.209,
    "CO": 3.614,
    "VOCs": 224.532
  }
}
```

### 14. 获取排放量最高的企业

**端点**: `GET /api/enterprises/top-emission`

**参数**:
- `lat` (必需): 纬度
- `lon` (必需): 经度
- `max_distance` (可选): 最大距离，单位公里，默认10.0
- `pollutant` (可选): 污染物类型，默认"VOCs"
- `top_n` (可选): 返回前N个企业，默认10

**请求示例**:
```bash
curl "http://180.184.91.74:9095/api/enterprises/top-emission?lat=23.1291&lon=113.2644&max_distance=5&pollutant=VOCs&top_n=3"
```

**响应示例**:
```json
{
  "status": "success",
  "total": 3,
  "query_params": {
    "lat": 23.1291,
    "lon": 113.2644,
    "max_distance": 5.0,
    "pollutant": "VOCs",
    "top_n": 3
  },
  "data": [
    {
      "企业名称": "广州白云山天心制药股份有限公司",
      "行业": "化学药品制剂制造",
      "排放量": 43.405,
      "距离": 4.965,
      "排放信息": {
        "SO2": 0.016,
        "NOx": 2.645,
        "PM2.5": 0.038,
        "PM10": 0.038,
        "CO": 1.646,
        "VOCs": 43.406
      }
    }
  ]
}
```

### 15. 根据企业名称搜索企业

**端点**: `GET /api/enterprises/search` 或 `POST /api/enterprises/search`

**GET方法参数（单个查询）**:
- `enterprise_name` (必需): 企业名称关键词
- `max_results` (可选): 最大结果数，默认50

**POST方法参数（支持批量查询）** 🆕:
- `enterprise_name` (可选): 单个企业名称关键词
- `enterprise_names` (可选): 🆕 企业名称关键词数组，支持批量查询，不限制数组大小
- `max_results` (可选): 最大结果数，默认500（批量查询时）

**请求示例**:
```bash
# GET方法：单个企业查询
curl "http://180.184.91.74:9095/api/enterprises/search?enterprise_name=石化&max_results=10"

# POST方法：单个企业查询
curl -X POST "http://180.184.91.74:9095/api/enterprises/search" \
  -H "Content-Type: application/json" \
  -d '{"enterprise_name": "石化", "max_results": 10}'

# 🆕 POST方法：批量企业查询（企业名称数组）
curl -X POST "http://180.184.91.74:9095/api/enterprises/search" \
  -H "Content-Type: application/json" \
  -d '{"enterprise_names": ["石化", "制药", "电子", "食品"], "max_results": 100}'

# 🆕 POST方法：大批量企业查询示例
curl -X POST "http://180.184.91.74:9095/api/enterprises/search" ^
  -H "Content-Type: application/json" ^
  -d '{"enterprise_names": ["中国石化", "广州石化", "中石油", "中海油", "壳牌", "埃克森美孚"], "max_results": 200}'
```

**批量查询响应示例** 🆕:
```json
{
  "status": "success",
  "total": 15,
  "query_params": {
    "enterprise_names": ["石化", "制药", "电子"],
    "enterprise_names_count": 3,
    "max_results": 100,
    "search_mode": "batch"
  },
  "data": [
    {
      "企业名称": "中国石化销售股份有限公司广东肇庆西郊加油站",
      "企业编码": "",
      "行业": "机动车燃油零售",
      "经度": 112.42388888888888,
      "纬度": 23.081944444444446,
      "排放信息": {
        "SO2": 0.0,
        "NOx": 0.0,
        "PM2.5": 0.0,
        "PM10": 0.0,
        "CO": 0.0,
        "VOCs": 1.6003129999999994
      }
    }
  ]
}
```

**特性说明**:
- 🆕 **无数组大小限制**: `enterprise_names`数组可以包含任意数量的企业名称
- 🆕 **智能匹配**: 每个企业名称都会进行模糊匹配搜索
- 🆕 **去重处理**: 自动去除重复的企业记录
- 🆕 **高效查询**: 批量查询比多次单独查询更高效
- **向后兼容**: 完全兼容原有的GET方法单个查询

---

## 🛠️ 编程语言示例

### Python示例

```python
import requests

# 基础URL
BASE_URL = "http://180.184.91.74:9095"

# 1. 查询站点区县信息
def get_station_district(station_code):
    response = requests.get(f"{BASE_URL}/api/station-district/by-station-code",
                          params={"station_code": station_code})
    return response.json()

# 2. 查询附近站点
def get_nearby_stations(station_code, max_distance=5, max_results=5):
    response = requests.get(f"{BASE_URL}/api/nearest-stations/by-station-code",
                          params={
                              "station_code": station_code,
                              "max_distance": max_distance,
                              "max_results": max_results
                          })
    return response.json()

# 3. 根据区县查询站点
def get_stations_by_district(district_name):
    response = requests.get(f"{BASE_URL}/api/station-district/by-district-name",
                          params={"district_name": district_name})
    return response.json()

# 4. 🆕 查询附近企业
def get_nearby_enterprises(lat, lon, max_distance=5, max_results=10, industry_filter=None):
    params = {
        "lat": lat,
        "lon": lon,
        "max_distance": max_distance,
        "max_results": max_results
    }
    if industry_filter:
        params["industry_filter"] = industry_filter

    response = requests.get(f"{BASE_URL}/api/enterprises/by-coordinates", params=params)
    return response.json()

# 5. 🆕 获取行业统计
def get_industry_stats(lat, lon, max_distance=10):
    response = requests.get(f"{BASE_URL}/api/enterprises/industry-stats",
                          params={
                              "lat": lat,
                              "lon": lon,
                              "max_distance": max_distance
                          })
    return response.json()

# 6. 🆕 获取排放汇总
def get_emission_summary(lat, lon, max_distance=10):
    response = requests.get(f"{BASE_URL}/api/enterprises/emission-summary",
                          params={
                              "lat": lat,
                              "lon": lon,
                              "max_distance": max_distance
                          })
    return response.json()

# 7. 🆕 获取高排放企业
def get_top_emission_enterprises(lat, lon, max_distance=10, pollutant="VOCs", top_n=5):
    response = requests.get(f"{BASE_URL}/api/enterprises/top-emission",
                          params={
                              "lat": lat,
                              "lon": lon,
                              "max_distance": max_distance,
                              "pollutant": pollutant,
                              "top_n": top_n
                          })
    return response.json()

# 8. 🆕 企业搜索（单个）
def search_enterprise_by_name(enterprise_name, max_results=50):
    response = requests.get(f"{BASE_URL}/api/enterprises/search",
                          params={
                              "enterprise_name": enterprise_name,
                              "max_results": max_results
                          })
    return response.json()

# 9. 🆕 企业批量搜索
def search_enterprises_by_names(enterprise_names, max_results=500):
    response = requests.post(f"{BASE_URL}/api/enterprises/search",
                           json={
                               "enterprise_names": enterprise_names,
                               "max_results": max_results
                           })
    return response.json()

# 10. 🆕 简化结果查询附近企业
def get_nearby_enterprises_simple(station_name, max_distance=5, max_results=10):
    response = requests.get(f"{BASE_URL}/api/enterprises/by-station-name",
                          params={
                              "station_name": station_name,
                              "max_distance": max_distance,
                              "max_results": max_results,
                              "simple_result": "true"
                          })
    return response.json()

# 使用示例
if __name__ == "__main__":
    # 坐标：广州市中心
    lat, lon = 23.1291, 113.2644

    # 查询站点区县信息
    district_info = get_station_district("4401000001")
    print("站点区县信息:", district_info)

    # 查询附近站点
    nearby_stations = get_nearby_stations("4401000001", max_distance=3)
    print("附近站点:", nearby_stations)

    # 查询附近企业
    nearby_enterprises = get_nearby_enterprises(lat, lon, max_distance=5, max_results=5)
    print("附近企业:", nearby_enterprises)

    # 查询行业统计
    industry_stats = get_industry_stats(lat, lon, max_distance=10)
    print("行业统计:", industry_stats)

    # 查询排放汇总
    emission_summary = get_emission_summary(lat, lon, max_distance=5)
    print("排放汇总:", emission_summary)

    # 查询VOCs排放量最高的企业
    top_vocs_enterprises = get_top_emission_enterprises(lat, lon, max_distance=5, pollutant="VOCs", top_n=3)
    print("VOCs排放量最高企业:", top_vocs_enterprises)

    # 🆕 单个企业搜索
    enterprise_search = search_enterprise_by_name("石化", max_results=10)
    print("企业搜索结果:", enterprise_search)

    # 🆕 批量企业搜索
    batch_search = search_enterprises_by_names(["石化", "制药", "电子"], max_results=50)
    print("批量企业搜索结果:", batch_search)

    # 🆕 简化结果查询
    simple_results = get_nearby_enterprises_simple("增城新塘", max_distance=5, max_results=10)
    print("简化结果查询:", simple_results)
```

### JavaScript示例

```javascript
// 基础URL
const BASE_URL = "http://180.184.91.74:9095";

// 1. 查询站点区县信息
async function getStationDistrict(stationCode) {
    const response = await fetch(`${BASE_URL}/api/station-district/by-station-code?station_code=${stationCode}`);
    return await response.json();
}

// 2. 查询附近站点
async function getNearbyStations(stationCode, maxDistance = 5, maxResults = 5) {
    const response = await fetch(`${BASE_URL}/api/nearest-stations/by-station-code?station_code=${stationCode}&max_distance=${maxDistance}&max_results=${maxResults}`);
    return await response.json();
}

// 3. 根据区县查询站点
async function getStationsByDistrict(districtName) {
    const response = await fetch(`${BASE_URL}/api/station-district/by-district-name?district_name=${districtName}`);
    return await response.json();
}

// 4. 🆕 查询附近企业
async function getNearbyEnterprises(lat, lon, maxDistance = 5, maxResults = 10, industryFilter = null) {
    let url = `${BASE_URL}/api/enterprises/by-coordinates?lat=${lat}&lon=${lon}&max_distance=${maxDistance}&max_results=${maxResults}`;
    if (industryFilter) {
        url += `&industry_filter=${encodeURIComponent(industryFilter)}`;
    }

    const response = await fetch(url);
    return await response.json();
}

// 5. 🆕 获取行业统计
async function getIndustryStats(lat, lon, maxDistance = 10) {
    const response = await fetch(`${BASE_URL}/api/enterprises/industry-stats?lat=${lat}&lon=${lon}&max_distance=${maxDistance}`);
    return await response.json();
}

// 6. 🆕 获取排放汇总
async function getEmissionSummary(lat, lon, maxDistance = 10) {
    const response = await fetch(`${BASE_URL}/api/enterprises/emission-summary?lat=${lat}&lon=${lon}&max_distance=${maxDistance}`);
    return await response.json();
}

// 7. 🆕 获取高排放企业
async function getTopEmissionEnterprises(lat, lon, maxDistance = 10, pollutant = "VOCs", topN = 5) {
    const response = await fetch(`${BASE_URL}/api/enterprises/top-emission?lat=${lat}&lon=${lon}&max_distance=${maxDistance}&pollutant=${pollutant}&top_n=${topN}`);
    return await response.json();
}

// 8. 🆕 企业搜索（单个）
async function searchEnterpriseByName(enterpriseName, maxResults = 50) {
    const response = await fetch(`${BASE_URL}/api/enterprises/search?enterprise_name=${encodeURIComponent(enterpriseName)}&max_results=${maxResults}`);
    return await response.json();
}

// 9. 🆕 企业批量搜索
async function searchEnterprisesByNames(enterpriseNames, maxResults = 500) {
    const response = await fetch(`${BASE_URL}/api/enterprises/search`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            enterprise_names: enterpriseNames,
            max_results: maxResults
        })
    });
    return await response.json();
}

// 10. 🆕 简化结果查询附近企业
async function getNearbyEnterprisesSimple(stationName, maxDistance = 5, maxResults = 10) {
    const response = await fetch(`${BASE_URL}/api/enterprises/by-station-name?station_name=${encodeURIComponent(stationName)}&max_distance=${maxDistance}&max_results=${maxResults}&simple_result=true`);
    return await response.json();
}

// 使用示例
async function main() {
    try {
        // 坐标：广州市中心
        const lat = 23.1291, lon = 113.2644;

        // 查询站点区县信息
        const districtInfo = await getStationDistrict("4401000001");
        console.log("站点区县信息:", districtInfo);

        // 查询附近站点
        const nearbyStations = await getNearbyStations("4401000001", 3);
        console.log("附近站点:", nearbyStations);

        // 查询附近企业
        const nearbyEnterprises = await getNearbyEnterprises(lat, lon, 5, 5);
        console.log("附近企业:", nearbyEnterprises);

        // 查询行业统计
        const industryStats = await getIndustryStats(lat, lon, 10);
        console.log("行业统计:", industryStats);

        // 查询排放汇总
        const emissionSummary = await getEmissionSummary(lat, lon, 5);
        console.log("排放汇总:", emissionSummary);

        // 查询VOCs排放量最高的企业
        const topVocsEnterprises = await getTopEmissionEnterprises(lat, lon, 5, "VOCs", 3);
        console.log("VOCs排放量最高企业:", topVocsEnterprises);

        // 🆕 单个企业搜索
        const enterpriseSearch = await searchEnterpriseByName("石化", 10);
        console.log("企业搜索结果:", enterpriseSearch);

        // 🆕 批量企业搜索
        const batchSearch = await searchEnterprisesByNames(["石化", "制药", "电子"], 50);
        console.log("批量企业搜索结果:", batchSearch);

        // 🆕 简化结果查询
        const simpleResults = await getNearbyEnterprisesSimple("增城新塘", 5, 10);
        console.log("简化结果查询:", simpleResults);

    } catch (error) {
        console.error("请求失败:", error);
    }
}

main();
```

### cURL示例

```bash
# === 站点查询 ===

# 1. 查询站点区县信息
curl "http://180.184.91.74:9095/api/station-district/by-station-code?station_code=4401000001"

# 2. 查询附近站点
curl "http://180.184.91.74:9095/api/nearest-stations/by-station-code?station_code=4401000001&max_distance=5&max_results=5"

# 3. 根据区县查询站点
curl "http://180.184.91.74:9095/api/station-district/by-district-name?district_name=白云区"

# === 企业查询 🆕 ===

# 4. 根据经纬度查询附近企业
curl "http://180.184.91.74:9095/api/enterprises/by-coordinates?lat=23.1291&lon=113.2644&max_distance=5&max_results=10"

# 5. 根据站点编码查询附近企业
curl "http://180.184.91.74:9095/api/enterprises/by-station-code?station_code=440104003&max_distance=3&max_results=5"

# 6. 查询附近企业（带行业过滤）
curl "http://180.184.91.74:9095/api/enterprises/by-coordinates?lat=23.1291&lon=113.2644&max_distance=5&industry_filter=机动车燃油零售"

# 7. 查询附近企业（带排放阈值过滤）
curl "http://180.184.91.74:9095/api/enterprises/by-coordinates?lat=23.1291&lon=113.2644&max_distance=5&VOCs_threshold=10.0&SO2_threshold=1.0"

# 8. 获取行业统计信息
curl "http://180.184.91.74:9095/api/enterprises/industry-stats?lat=23.1291&lon=113.2644&max_distance=10"

# 9. 获取排放汇总信息
curl "http://180.184.91.74:9095/api/enterprises/emission-summary?lat=23.1291&lon=113.2644&max_distance=5"

# 10. 获取VOCs排放量最高的企业
curl "http://180.184.91.74:9095/api/enterprises/top-emission?lat=23.1291&lon=113.2644&max_distance=5&pollutant=VOCs&top_n=3"

# 11. 搜索企业（单个）
curl "http://180.184.91.74:9095/api/enterprises/search?enterprise_name=石化&max_results=10"

# 🆕 12. 批量搜索企业（POST方法）
curl -X POST "http://180.184.91.74:9095/api/enterprises/search" \
  -H "Content-Type: application/json" \
  -d '{"enterprise_names": ["石化", "制药", "电子", "食品"], "max_results": 100}'

# 🆕 13. 简化结果查询附近企业
curl "http://180.184.91.74:9095/api/enterprises/by-station-name?station_name=增城新塘&max_distance=5&simple_result=true&max_results=10"

# 🆕 14. 大批量企业搜索（无数量限制）
curl -X POST "http://180.184.91.74:9095/api/enterprises/search" \
  -H "Content-Type: application/json" \
  -d '{"enterprise_names": ["中国石化", "广州石化", "中石油", "中海油", "壳牌", "埃克森美孚", "BP", "道达尔", "雪佛龙", "康菲"], "max_results": 500}'

# === 系统信息 ===

# 12. 健康检查
curl "http://180.184.91.74:9095/health"

# 13. 获取API文档
curl "http://180.184.91.74:9095/"
```

---

## 📊 数据字段说明

### 站点信息字段
- `站点名称`: 监测站点名称
- `唯一编码`: 站点唯一标识码
- `所属城市`: 站点所属城市
- `所属区县`: 站点所属区县
- `经度`: 经度坐标
- `纬度`: 纬度坐标
- `地址`: 详细地址信息
- `省份`: 所属省份
- `城市`: 所属城市（详细）
- `乡镇`: 所属乡镇/街道
- `行政区划代码`: 行政区划代码
- `距离`: 距离（仅在附近站点查询中返回）

### 🆕 企业信息字段
- `企业名称`: 企业/公司名称
- `企业编码`: 企业唯一标识码（部分企业可能为空）
- `行业`: 企业所属行业分类
- `地址`: 企业详细地址
- `经度`: 企业经度坐标
- `纬度`: 企业纬度坐标
- `城市`: 所属城市
- `区县`: 所属区县
- `省份`: 所属省份
- `企业类型`: 企业类型分类
- `运营状态`: 企业运营状态（如"运营中"）
- `距离`: 距离查询点的距离（公里）
- `排放信息`: 包含六种污染物的排放数据
  - `SO2`: 二氧化硫排放量（吨/年）
  - `NOx`: 氮氧化物排放量（吨/年）
  - `PM2.5`: 细颗粒物排放量（吨/年）
  - `PM10`: 可吸入颗粒物排放量（吨/年）
  - `CO`: 一氧化碳排放量（吨/年）
  - `VOCs`: 挥发性有机物排放量（吨/年）

### 支持的污染物类型
- **SO2**: 二氧化硫
- **NOx**: 氮氧化物
- **PM2.5**: 细颗粒物
- **PM10**: 可吸入颗粒物
- **CO**: 一氧化碳
- **VOCs**: 挥发性有机物

### 支持的行业类型（部分）
- 机动车燃油零售
- 皮鞋制造
- 包装装潢及其他印刷
- 其他机织服装制造
- 塑料零件及其他塑料制品制造
- 糕点、面包制造
- 化学药品制剂制造
- 中成药生产
- 金属表面处理及热处理加工
- 光学仪器制造
- 等90多种行业分类

### 响应状态码
- `200`: 请求成功
- `400`: 请求参数错误
- `404`: 未找到指定资源
- `500`: 服务器内部错误

---

## ⚠️ 注意事项

1. **服务启动**: 确保API服务已启动（端口9092）
2. **数据格式**: 所有坐标使用WGS-84坐标系
3. **距离计算**: 使用Haversine公式计算球面距离
4. **模糊匹配**: 站点名称和区县名称支持模糊匹配
5. **结果限制**: 建议设置合理的`max_results`参数避免返回过多数据
6. **错误处理**: 请检查响应中的`status`字段判断请求是否成功
7. **🆕 企业数据**: 企业数据来源于2022年广东省点源清单，包含94,703条记录
8. **🆕 排放单位**: 所有排放量数据单位为吨/年
9. **🆕 行业过滤**: 行业过滤支持精确匹配，建议使用完整的行业名称
10. **🆕 排放阈值**: 排放阈值过滤支持多个污染物同时设置，只有同时满足所有条件的企业才会被返回
11. **🆕 地理精度**: 企业经纬度坐标精确到小数点后6位，确保查询精度

---

## 🔧 故障排除

### 常见问题

1. **服务无法启动**
   - 检查端口9092是否被占用
   - 确认Python环境已安装
   - 检查依赖文件是否存在（需要openpyxl库）

2. **数据加载失败**
   - 确认地理数据文件存在
   - 确认企业数据JSON文件存在（94,703条记录）
   - 检查文件格式是否正确
   - 查看服务日志获取详细错误信息

3. **查询结果为空**
   - 检查站点编码是否正确
   - 确认搜索参数是否合理
   - 验证数据文件中是否包含目标站点/企业
   - 🆕 检查地理范围是否过小（建议max_distance >= 1.0公里）

4. **🆕 企业查询问题**
   - 企业搜索需要使用中文关键词
   - 行业过滤需要使用完整的行业名称
   - 排放阈值设置不能过高，否则可能无结果
   - 某些企业可能缺少部分字段信息

### 调试方法

1. **查看服务日志**: 启动服务时会显示详细日志
2. **使用健康检查**: 访问`/health`端点确认服务状态
3. **测试简单查询**: 先测试基础功能再测试复杂查询
4. **🆕 验证数据加载**: 健康检查会显示加载的站点数和企业数
5. **🆕 分步调试**: 先测试经纬度查询，再测试过滤条件

### 性能优化建议

1. **合理设置参数**:
   - `max_distance`: 建议5-20公里
   - `max_results`: 建议10-100条
   - 避免设置过大的查询范围

2. **🆕 企业查询优化**:
   - 使用行业过滤减少结果集
   - 设置合理的排放阈值
   - 优先使用经纬度查询而非站点名称查询

---

## 📞 技术支持

如有问题，请检查：
1. 服务是否正常启动
2. 请求参数是否正确
3. 网络连接是否正常
4. 数据文件是否完整






# 上风向企业筛选 + 高德静态图 接口说明（已更新）

本模块提供“按小时级风数据筛选上风向企业 + 生成地图图片URL”的独立接口，并只返回可直接展示的短链接（public_url）。同时返回企业行业与排放信息。

- 路由：POST /api/external/wind/upwind-and-map
- 模块：api_upwind/
- 依赖：
  - 站点解析：src/utils/nearest_station_finder.py
  - 企业查询：src/utils/enterprise_query_engine.py
  - 高德静态图（服务端拼URL）

## 1. 如何启动本服务（Quick Start）
1) 配置环境变量（务必在“启动服务的同一终端”先设置）
- Windows PowerShell（当前会话）：
  - `$env:AMAP_WEB_KEY="<你的高德Web服务Key>"`
- Windows 永久（新会话生效）：
  - `setx AMAP_WEB_KEY "<你的高德Web服务Key>"`
- macOS/Linux：
  - `export AMAP_WEB_KEY=<你的高德Web服务Key>`

2) 启动服务
- `python start_nearest_stations.py`
- 默认监听：`http://0.0.0.0:9095`

3) 健康检查
- `GET http://localhost:9095/health`
- 预期返回：`{"status":"healthy",...}`

注意
- 请确保在“启动命令所在的终端”中已设置 AMAP_WEB_KEY 后再执行启动，否则服务读不到高德Key。
- PowerShell 不支持 `AMAP_WEB_KEY=xxx python ...` 这种 Linux 写法；应使用 `$env:AMAP_WEB_KEY="..."` 然后再运行 Python。
- 生产环境建议在“Web服务”Key上配置服务器出口IP白名单；前端/第三方请使用我们返回的短链 public_url 展示图片。

## 2. 最新更新
- 仅返回短链接：响应中只包含 public_url / public_urls，不再返回长的 image_url，避免前端/代理因长URL或转义导致失败（20003）。
- 标注策略（modes）：
  - pin（默认，最稳）：站点 S、企业合并为单个 E 组，URL最短。
  - base36（单字符编号，每页≤30）：每家一个编号（1..9,A..Z），自动分页，返回 public_urls。
  - topn_mixed（推荐折中）：Top-N 编号 + 其余企业按分档（hi/mid/low）合并为 E 并分色，URL显著缩短且可区分重点企业。
- 返回企业行业与排放：filtered[*] 新增 industry 与 emissions（如 {"SO2":0,"NOx":0,"VOCs":5.52,...}）。meta.emissions_schema 列出本次出现的污染物键名。
- 分页：base36 的分页上限固定为 30/页；topn_mixed 通常为单图（不分页）。

## 3. 请求体（JSON）
- station_name string 必填（站点名称，模糊匹配）
- winds array[min=1] 必填（小时级风）
  - 每项：{ time: ISO8601含时区, wd_deg: [0,360), ws_ms: >=0 }
- search_range_km number 可选（默认5）
- max_enterprises number 可选（默认100，用于候选上限）
- map_type string 可选（normal|satellite，默认 normal）
- mode string 可选（pin|base36|topn_mixed，默认 pin）
- top_n number 可选（仅 topn_mixed 生效，默认12，建议≤10）

注意：仅从 Body 读取 JSON；不要把参数放到 URL/Params；Content-Type 建议 application/json; charset=utf-8。

## 4. 标注策略说明
- pin（默认）
  - markers：S（站点，蓝）+ E（企业，合并，橙）
  - meta.legend: {"station":"S","enterprise":"E"}
  - 适合：稳态展示，URL最短。
- base36（单字符编号）
  - 每家企业用 1..9,A..Z 单字符；每页最多30个（_PAGE_SIZE=30）→ public_urls 多图返回。
  - meta.names_index_map：编号→企业名（当前页）。
  - 适合：一页内企业≤30，或接受多张图轮播。
- topn_mixed（Top-N 编号 + 其余合并分色）
  - Top-N：单字符编号；其他：合并为 E，并按 score_norm 分为 hi/mid/low 三档着色。
  - meta.legend: {"station":"S","topN":"1..9,A..Z","E_colors":{"hi":"#FF4500","mid":"#FFA500","low":"#CCCCCC"}}
  - meta.bins: {p75,p40}（分档阈值）。
  - 适合：既要在图上区分重点企业，又要稳定 URL。

## 5. 返回体（JSON）
- status: success|error
- public_url: string（短链，302到高德静态图；前端/Dify 只用该URL展示）
- public_urls: array（多页时返回所有短链）
- filtered: array（企业列表，按 score_norm 降序）
  - 元素字段：
    - id?, name, lat, lng, distance_km
    - score_sum?, score_norm?, hit_ratio?
    - symbol?（base36 或 topn_mixed TopN 编号）
    - tier?（topn_mixed：hi/mid/low）
    - industry?（行业）
    - emissions?（{SO2,NOx,VOCs,PM2.5,PM10,CO,...}）
- meta: object
  - provider: "amap"
  - station: {name,lat,lng}
  - zoom, center, markers_count, label_strategy
  - legend?（见各模式）
  - names_index_map?（base36 当前页 / topn_mixed TopN）
  - emissions_schema?（本次出现的污染物键名）
  - hours_total, hours_effective, calm_hours
  - time_range: {start,end,tz}
  - page, pages, page_size
  - bins?（topn_mixed：{p75,p40}）

## 6. 单行请求示例（便于复制，UTF-8安全）
- pin（最稳）
{"station_name":"\u5e7f\u96c5\u4e2d\u5b66","winds":[{"time":"2025-10-13T12:00:00Z","wd_deg":45,"ws_ms":2.5},{"time":"2025-10-13T13:00:00Z","wd_deg":60,"ws_ms":1.8},{"time":"2025-10-13T14:00:00Z","wd_deg":70,"ws_ms":0.2}],"search_range_km":5,"max_enterprises":80,"map_type":"normal","mode":"pin"}

- base36（每页≤30）
{"station_name":"\u5e7f\u96c5\u4e2d\u5b66","winds":[{"time":"2025-10-13T12:00:00Z","wd_deg":45,"ws_ms":2.5},{"time":"2025-10-13T13:00:00Z","wd_deg":60,"ws_ms":1.8},{"time":"2025-10-13T14:00:00Z","wd_deg":70,"ws_ms":0.2}],"search_range_km":5,"max_enterprises":50,"map_type":"normal","mode":"base36"}

- topn_mixed（推荐折中，Top-N 编号 + 其余分色合并）
{"station_name":"\u5e7f\u96c5\u4e2d\u5b66","winds":[{"time":"2025-10-13T12:00:00Z","wd_deg":45,"ws_ms":2.5},{"time":"2025-10-13T13:00:00Z","wd_deg":60,"ws_ms":1.8},{"time":"2025-10-13T14:00:00Z","wd_deg":70,"ws_ms":0.2}],"search_range_km":5,"max_enterprises":30,"map_type":"normal","mode":"topn_mixed","top_n":8}

## 7. 新增接口：按企业名称清单绘图（Top-6 编号 + 其余合并）
- 路由：POST /api/external/wind/by-names-and-map
- 功能：输入站点名称和企业名称数组（≤35），返回一张图：前6个企业用单字符编号（1..6），其余企业合并为 E（中档颜色）。仅返回短链 public_url。
- 请求体（JSON）：
  - station_name: string（必填）
  - enterprise_names: array[string]（必填，长度 1..35）
  - map_type: string（可选，normal|satellite；默认 normal）
- 响应：
  - public_url: string
  - public_urls: [string]
  - filtered: [{ id?, name, lat, lng, distance_km, symbol?, tier?, industry?, emissions? }]
  - meta: { provider, station, legend, layout:"topn_mixed", top_n:6, ... }
- 单行示例：
{"station_name":"\u5e7f\u96c5\u4e2d\u5b66","enterprise_names":["中国石化销售股份有限公司广东肇庆城中加油站","广东省花城印刷厂","广州市荔湾区西郊站前加油站","广州市荔湾区恒源鞋厂","广州市荔湾区穗龙彩印厂","广州登峰鞋厂","广州市荔湾区豪达鞋业","广州市美格尔标牌有限公司","泰隆鞋厂","万履鞋业"],"map_type":"normal"}

## 8. 前端/Dify 使用建议
- 只用 public_url / public_urls 渲染图片；不要使用长的 image_url（接口已移除）。
- 若 base36 或 topn_mixed 在个别环境仍报 20003，可：
  - 降低 top_n（如 ≤8）与 max_enterprises（如 ≤30）
  - 或切回 pin
- 列表侧展示：编号→企业名对照（names_index_map / filtered.symbol）、行业与排放（filtered[i].industry/emissions）。

## 9. 高德静态图注意
- size 推荐使用 900%2A600（星号*需URL编码为%2A）
- markers 组之间用 %7C 分隔；同组内坐标用 ; 分隔
- 所有文本标注使用单字符，避免 20003

## 10. 错误排查
- 400 Invalid request：Body 未按 JSON 传参（winds 必须是数组），或 time 非 ISO8601。
- 404 Station not found：中文编码问题或名称不在库；可用 Unicode 编码或换站点名。
- 20003（UNKNOWN_ERROR）：前端误用长URL或URL过长；改用 public_url，或切换 pin/降低点数。

## 11. 环境变量
- AMAP_WEB_KEY：高德 Web 服务 Key（在启动服务的同一终端先设置再启动）
- 其他可选：
  - AMAP_STATIC_BASE（默认 https://restapi.amap.com/v3/staticmap）
  - AMAP_DEFAULT_SIZE（默认 900*600）
  - AMAP_MAX_MARKERS（默认 50）
