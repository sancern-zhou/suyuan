# 广东省站点查询工具 - 数据字段测试报告

## 测试时间
2026-04-08

## 测试结果

### 1. 城市小时数据查询 (`query_gd_suncere_city_hour`)

#### 原始API返回的字段（共60个）：

**基础字段：**
- `code`: 城市编码（如 "440100"）
- `name`: 城市名称（如 "广州"）
- `timePoint`: 时间点（如 "2026-04-07T14:55:22"）
- `dataType`: 数据类型（1=审核实况）

**污染物浓度字段：**
- `pM2_5`: PM2.5浓度
- `pM10`: PM10浓度
- `sO2`: SO2浓度
- `nO2`: NO2浓度
- `o3`: O3浓度
- `co`: CO浓度
- `nO`: NO浓度
- `nOx`: NOx浓度
- 各污染物的IAQI和Mark字段

**气象字段（⭐ 支持）：**
- `windSpeed`: 风速 (m/s)
- `windDirect`: 风向 (度)
- `temperature`: 温度 (°C)
- `humidity`: 相对湿度 (%)
- `pressure`: 气压 (hPa)
- `rainFall`: 降雨量 (mm)
- `precipitation`: 降水量 (mm)
- `visibility`: 能见度 (km)

**其他字段：**
- `aqi`: AQI指数
- `primaryPollutant`: 首要污染物
- `qualityType`: 空气质量等级
- `createTime`, `modifyTime`: 创建/修改时间

#### 标准化后的字段：

**顶层字段：**
- `name`: 站点/城市名称
- `station_code`: 站点代码
- `timestamp`: 时间戳
- `data_type`: 数据类型
- `created_time`, `modified_time`: 创建/修改时间
- `record_id`: 记录ID
- `measurements`: 测量数据字典

**measurements 字段（标准化后）：**
- `PM2_5`: PM2.5浓度
- `PM10`: PM10浓度
- `SO2`: SO2浓度
- `NO2`: NO2浓度
- `O3`: O3浓度
- `CO`: CO浓度
- `O3_8h`: O3_8h浓度
- `PM2_5_IAQI`, `PM10_IAQI`, `SO2_IAQI`, `NO2_IAQI`, `CO_IAQI`, `O3_8h_IAQI`: 各污染物IAQI

**气象字段（⭐ include_weather=True 时）：**
- `wind_speed_10m`: 10米风速 (m/s)
- `wind_direction_10m`: 10米风向 (度)
- `temperature_2m`: 2米气温 (°C)
- `relative_humidity_2m`: 2米相对湿度 (%)
- `surface_pressure`: 地面气压 (hPa)
- `precipitation`: 降水量 (mm)
- `visibility`: 能见度 (km)

---

### 2. 站点小时数据查询 (`query_gd_suncere_station_hour_new`)

#### 原始API返回的字段（共64个）：

站点数据相比城市数据，额外包含：
- `code`: 站点编码（如 "1001A"）
- `name`: 站点名称（如 "广雅中学"）
- `cityCode`: 城市编码
- `cityName`: 城市名称
- `districtCode`: 区县编码
- `districtName`: 区县名称
- `uniqueCode`: 唯一编码

其他字段与城市小时数据相同，包括：
- 所有污染物浓度字段
- 所有气象字段（windSpeed, windDirect, temperature, humidity, pressure等）

#### 标准化后的字段：

**顶层字段：**
- `station_code`: 站点代码
- `name`: 站点名称
- `timestamp`: 时间戳
- `city_code`: 城市代码
- `cityName`: 城市名称
- `districtName`: 区县名称
- `record_id`: 记录ID
- `measurements`: 测量数据字典

**measurements 字段（包含新标准计算的IAQI/AQI）：**
- 所有污染物浓度（PM2_5, PM10, SO2, NO2, CO, O3_8h）
- 新标准IAQI（PM2.5断点60，PM10断点120）
- `AQI`: 新标准AQI
- `primary_pollutant`: 新标准首要污染物

**气象字段（⭐ include_weather=True 时）：**
- 与城市小时数据相同的气象字段

---

## 数据质量说明

### 气象字段可能的状态

根据测试，广东省API返回的气象字段可能有以下值：
- `"—"` : 数据缺失（最常见）
- `"-99"` 或 `"-99.000"` : 无效值标记
- 具体的数值：有效数据

**注意**：某些站点的气象数据可能不完整或完全缺失，这是数据源的正常情况。

### 数据映射关系

原始字段 → 标准化字段：
- `windSpeed` → `wind_speed_10m`
- `windDirect` → `wind_direction_10m`
- `temperature` → `temperature_2m`
- `humidity` → `relative_humidity_2m`
- `pressure` → `surface_pressure`
- `precipitation` → `precipitation`
- `rainFall` → `precipitation` (备用)
- `visibility` → `visibility`

---

## 使用示例

### 不包含气象字段（默认）
```python
result = query_city_hour_data(
    cities=["广州"],
    start_time="2026-04-01 00:00:00",
    end_time="2026-04-01 23:59:59",
    context=context
    # include_weather=False (默认)
)
```

返回的 measurements 字段：
```python
{
    "PM2_5": 35,
    "PM10": 67,
    "SO2": 12,
    "NO2": 38,
    "CO": 0.8,
    "O3_8h": 89,
    "PM2_5_IAQI": 58,
    # ... 其他IAQI字段
    # 不包含气象字段
}
```

### 包含气象字段
```python
result = query_city_hour_data(
    cities=["广州"],
    start_time="2026-04-01 00:00:00",
    end_time="2026-04-01 23:59:59",
    context=context,
    include_weather=True  # ⭐ 启用气象字段
)
```

返回的 measurements 字段：
```python
{
    "PM2_5": 35,
    "PM10": 67,
    # ... 污染物字段
    "wind_speed_10m": 2.3,      # ⭐ 风速
    "wind_direction_10m": 135,   # ⭐ 风向
    "temperature_2m": 28.5,      # ⭐ 温度
    "relative_humidity_2m": 75,  # ⭐ 湿度
    "surface_pressure": 1013.2,  # ⭐ 气压
    # 可能还包含：
    # "precipitation": 0.0,
    # "visibility": 15.5
}
```

---

## 总结

1. ✅ **城市小时数据**和**站点小时数据**都支持气象字段提取
2. ✅ 默认 `include_weather=False`，不包含气象字段（保持向后兼容）
3. ✅ 设置 `include_weather=True` 时，返回数据中包含标准化后的气象字段
4. ⚠️ 气象字段的数据质量取决于广东省API，某些站点可能缺失气象数据
5. ✅ 所有气象字段都经过标准化处理，字段名与其他气象数据源保持一致
