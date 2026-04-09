# aggregate_data 工具使用指南

## 功能概述

数据聚合分析工具，支持基础统计、空气质量指数计算和质量指数计算。

## 工作流程说明

**重要**：aggregate_data 工具用于对**已查询好的数据**进行聚合分析，不直接查询数据。

完整工作流程：
1. **第一步**：使用查询工具（如 `query_gd_suncere`）并指定日期范围获取数据
2. **第二步**：使用 `aggregate_data` 对查询结果进行聚合分析

### 查询指定日期数据的方法

使用查询工具的日期过滤参数：

```python
# 示例：查询2026年1月的数据
query_gd_suncere(
    city="广州",
    start_date="2026-01-01",
    end_date="2026-01-31",
    pollutants=["PM2.5", "PM10", "O3", "NO2", "SO2", "CO"]
)
# 返回 data_id

# 然后对查询结果进行聚合
aggregate_data(
    data_id="<上一步返回的data_id>",
    aggregations=[
        {"column": "measurements.PM2_5", "function": "IAQI", "pollutant": "PM2_5"},
        {"column": "", "function": "AQI"},
        {"column": "", "function": "PRIMARY_POLLUTANT"}
    ],
    time_granularity="day"
)
```

## 聚合函数列表

### 基础统计函数
- `SUM` - 求和
- `AVG` - 平均值
- `MAX` - 最大值
- `MIN` - 最小值
- `COUNT` - 计数
- `STDDEV` - 标准差
- `VAR` - 方差
- `MEDIAN` - 中位数
- `PERCENTILE` - 百分位数（需要percentile参数）
- `O3_8H_MAX` - O3日最大8小时平均

### 空气质量指数函数（基于HJ 633-2026新标准）
- `IAQI` - 空气质量分指数
- `AQI` - 空气质量指数（取各污染物IAQI最大值）
- `PRIMARY_POLLUTANT` - 首要污染物（IAQI最大的污染物）

**⚠️ 重要限制**：IAQI/AQI/PRIMARY_POLLUTANT **仅限单日数据评价**

- 这些函数基于**日平均浓度**设计（HJ 633-2026标准）
- 如果数据跨越多日，工具会**返回错误**，提示使用 `start_date`/`end_date` 限制为单日
- **原因**：多日数据先求平均再计算IAQI，会平滑掉高值，导致评价结果不准确
- **正确用法**：使用 `start_date` 和 `end_date` 参数限制为单日（见下方示例）

### 质量指数函数
- `SINGLE_INDEX` - 单项指数（浓度/标准限值）
- `COMPREHENSIVE_INDEX` - 综合指数（新标准加权求和：PM2.5权重3，O3权重2，NO2权重2，其他权重1）

**⚠️ 重要限制**：SINGLE_INDEX/COMPREHENSIVE_INDEX **仅限多日数据评价（至少2天）**

- 这些函数用于**月/季/年等时段**的综合空气质量评价
- 如果数据只有单日，工具会**返回错误**，提示扩大时间范围
- **原因**：综合指数基于年平均标准设计，单日数据计算没有统计学意义
- **正确用法**：确保数据包含至少2天（见下方示例）

## 参数说明

### 必需参数
- `data_id` - 查询结果的数据ID
- `aggregations` - 聚合配置列表

### aggregations配置项
- `column` - 要聚合的列名
- `function` - 聚合函数
- `alias` - 结果字段别名（可选）
- `pollutant` - 污染物名称（IAQI/SINGLE_INDEX必需）
- `percentile` - 百分位数（PERCENTILE函数必需）

### 可选参数
- `group_by` - 分组字段列表
- `time_granularity` - 时间粒度（hour/day/month/year）
- `time_column` - 时间列名（默认自动检测）
- `start_date` - 起始日期（格式：YYYY-MM-DD，用于只计算指定日期范围的数据）
- `end_date` - 结束日期（格式：YYYY-MM-DD，用于只计算指定日期范围的数据）

## 使用示例

### 基础统计
```python
# 计算PM2.5日均值
aggregations=[{'column':'pm25','function':'AVG','pollutant':'PM2_5'}], time_granularity='day'

# 计算SO2的98百分位
aggregations=[{'column':'so2','function':'PERCENTILE','percentile':98,'pollutant':'SO2'}]

# 按城市统计
aggregations=[{'column':'pm25','function':'AVG'}], group_by=['city']
```

### 空气质量指数
```python
# 计算PM2.5的IAQI
aggregations=[{'column':'pm25','function':'IAQI','pollutant':'PM2_5'}]

# 计算AQI（需要数据中包含六参数浓度）
aggregations=[{'column':'aqi','function':'AQI'}]

# 计算首要污染物（IAQI最大的污染物）
aggregations=[{'column':'','function':'PRIMARY_POLLUTANT','alias':'primary_pollutant'}]

# 同时计算AQI和首要污染物
aggregations=[
    {'column':'measurements.PM2_5','function':'IAQI','pollutant':'PM2_5','alias':'PM2_5_IAQI'},
    {'column':'measurements.O3_8h','function':'IAQI','pollutant':'O3_8h','alias':'O3_8h_IAQI'},
    {'column':'','function':'AQI','alias':'AQI'},
    {'column':'','function':'PRIMARY_POLLUTANT','alias':'primary_pollutant'}
]
```

### 日期过滤（只计算指定日期）
```python
# 只计算2026年1月17日的AQI和首要污染物
aggregate_data(
    data_id="air_quality_unified:v1:xxx",
    aggregations=[
        {'column':'measurements.PM2_5','function':'IAQI','pollutant':'PM2_5','alias':'PM2_5_IAQI'},
        {'column':'measurements.O3_8h','function':'IAQI','pollutant':'O3_8h','alias':'O3_8h_IAQI'},
        {'column':'','function':'AQI','alias':'AQI'},
        {'column':'','function':'PRIMARY_POLLUTANT','alias':'primary_pollutant'}
    ],
    start_date='2026-01-17',
    end_date='2026-01-17'
)

# 只计算2026年1月的数据
aggregate_data(
    data_id="air_quality_unified:v1:xxx",
    aggregations=[
        {'column':'measurements.PM2_5','function':'AVG','pollutant':'PM2_5'}
    ],
    start_date='2026-01-01',
    end_date='2026-01-31',
    time_granularity='day'
)
```

### 质量指数
```python
# 计算PM2.5单项指数
aggregations=[{'column':'pm25','function':'SINGLE_INDEX','pollutant':'PM2_5'}]

# 计算综合指数（需要数据中包含六参数浓度）
aggregations=[{'column':'composite','function':'COMPREHENSIVE_INDEX'}]
```

## 新标准说明（HJ 633-2026）

### IAQI断点变化
- PM2.5: IAQI=100时浓度60μg/m³（旧标准75）
- PM10: IAQI=100时浓度120μg/m³（旧标准150）

### 单项指数标准限值
- PM2_5: 30 μg/m³
- PM10: 60 μg/m³
- SO2: 60 μg/m³
- NO2: 40 μg/m³
- CO: 4 mg/m³
- O3_8h: 160 μg/m³

### 综合指数计算公式（新标准 HJ 633-2026）
```
综合指数 = Σ(单项指数 × 权重) = Σ((Ci/Si) × Wi)
```

**权重配置**：
- PM2.5权重：3
- PM10权重：1
- SO2权重：1
- NO2权重：2
- CO权重：1
- O3_8h权重：2

其中：
- Ci为污染物浓度
- Si为标准限值（年均限值）
- Wi为权重

## 污染物列名映射

工具支持多种列名格式：
- PM2_5: pm2_5, pm25, PM2_5, PM2.5, PM25
- PM10: pm10, PM10
- SO2: so2, SO2
- NO2: no2, NO2
- CO: co, CO
- O3_8h: o3_8h, o3, O3_8h, O3

## 注意事项

1. **天数限制（重要）**：
   - **IAQI/AQI/PRIMARY_POLLUTANT**：仅限单日数据，多日数据会返回错误
   - **SINGLE_INDEX/COMPREHENSIVE_INDEX**：仅限多日数据（≥2天），单日数据会返回错误
   - 这些限制基于HJ 633-2026标准，确保评价结果的科学性和准确性

2. IAQI和SINGLE_INDEX函数必须提供pollutant参数

3. AQI和COMPREHENSIVE_INDEX要求数据中包含所有六参数浓度

4. 百分位数计算时需要提供percentile参数

5. 支持分组聚合和时间粒度聚合

6. 自动应用国家标准修约规则（四舍六入五成双）

7. **日期过滤**：使用start_date和end_date参数可以只计算指定日期范围的数据，日期格式为YYYY-MM-DD

8. 日期过滤支持多种时间格式自动识别（如"2026-01-17 12:00:00"、"2026-01-17T12:00:00"等）

9. **时间列自动检测**：工具会自动检测时间列（支持timestamp、time、date、datetime、time_point等字段名）
