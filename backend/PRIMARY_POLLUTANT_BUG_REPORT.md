# 首要污染物统计差异分析报告

## 问题现象

用户查询 2026年1月广州新旧标准对比时发现：
- 新标准 `primary_pollutant_days['PM2_5']` = 3（或4）
- 但 `exceed_details` 中 PM2.5 作为首要污染物的只有 2 天
- 数据不一致，无法对应

## 根本原因

### 1. 统计口径不同

**`primary_pollutant_days` 统计规则**（代码位置：`query_new_standard_report/tool.py:1052`）：
```python
aqi_new = max(pollutants_with_iaqi_new.values())
if aqi_new > 50:  # ← 统计所有 AQI > 50 的天
    for pollutant, iaqi in pollutants_with_iaqi_new.items():
        if iaqi == aqi_new:
            primary_pollutant_days[pollutant] += 1
```

**`exceed_details` 记录规则**（代码位置：`query_new_standard_report/tool.py:1073`）：
```python
if max_single_index_new > 1:  # ← 只记录超标天
    exceed_days += 1
    # 记录超标详情...
```

**关键差异**：
- `primary_pollutant_days` 包含：AQI > 50 的所有天数（包括未超标）
- `exceed_details` 仅包含：max_single_index > 1 的超标天数

### 2. 新旧标准差异导致的首要污染物变化

根据实际数据分析：

| 日期 | 新标准首要 | 旧标准首要 | 新标准AQI | 新标准max_idx | 说明 |
|------|-----------|-----------|----------|--------------|------|
| 01-01 | PM2.5 | PM2.5 | 74.0 | 1.283 | 两种标准都是PM2.5 |
| 01-17 | **PM2.5** | NO2 | 106.7 | 2.275 | 新标准PM2.5限值降低导致PM2.5的IAQI变大 |
| 01-20 | **PM2.5** | PM10 | 62.0 | 1.050 | 新标准PM2.5的IAQI超过PM10 |
| 01-24 | PM2.5 | PM2.5 | 64.0 | 1.117 | 两种标准都是PM2.5 |

**新标准 PM2.5 首要污染物天数 = 4 天**：['01-01', '01-17', '01-20', '01-24']
**旧标准 PM2.5 首要污染物天数 = 2 天**：['01-01', '01-24']

### 3. 具体案例分析

**01-20 这天的问题**：
```
浓度数据：
- PM2.5 = 41 μg/m³
- PM10 = 69 μg/m³
- NO2 = 42 μg/m³
- O3_8h = 46 μg/m³

新标准计算：
- PM2.5_IAQI = 62.0（最大）
- PM10_IAQI = 60.0
- NO2_IAQI = 53.0
- O3_8h_IAQI = 23.0
- AQI = 62.0 > 50 → 统计 PM2.5 为首要污染物
- max_index = 41/60 = 0.683 ≤ 1 → 不超标

旧标准计算：
- PM2.5_IAQI = 57.5
- PM10_IAQI = 59.5（最大）
- NO2_IAQI = 53.0
- O3_8h_IAQI = 23.0
- AQI = 59.5 > 50 → 统计 PM10 为首要污染物
```

**问题**：新标准中 01-20 这天 PM2.5 是首要污染物（计入 primary_pollutant_days），但不超标（不计入 exceed_details）

## 数据验证

运行分析脚本 `analyze_primary_pollutant_difference.py` 的结果：

```
新标准（AQI > 50 统计）:
  PM2_5   : 4 天  ← 包含 01-20（未超标）
  PM10    : 0 天
  NO2     : 9 天
  O3_8h   : 8 天

旧标准（AQI > 50 统计）:
  PM2_5   : 2 天
  PM10    : 2 天
  NO2     : 10 天
  O3_8h   : 8 天

新标准超标天数: 17
旧标准超标天数: 17
```

## 修复建议

### 方案1：修改 primary_pollutant_days 统计逻辑（推荐）

将首要污染物统计改为只统计超标天，与 exceed_details 对应：

```python
# 修改位置：query_new_standard_report/tool.py:1052
# 修改前：
if aqi_new > 50:
    for pollutant, iaqi in pollutants_with_iaqi_new.items():
        if iaqi == aqi_new:
            primary_pollutant_days[pollutant] += 1

# 修改后：
if max_single_index_new > 1:  # 只统计超标天
    for pollutant, iaqi in pollutants_with_iaqi_new.items():
        if iaqi == aqi_new:
            primary_pollutant_days[pollutant] += 1
```

**优点**：
- 逻辑一致，primary_pollutant_days 与 exceed_details 对应
- 用户期望看到的是超标天的首要污染物统计

**缺点**：
- 与国标定义略有不同（国标定义首要污染物是 AQI > 50 时的最大 IAQI）

### 方案2：保持现状，添加说明

在返回结果中添加字段说明：
```python
"primary_pollutant_days_note": "包含所有 AQI > 50 的首要污染物（未超标天也计入）"
"exceed_details_note": "仅记录超标天（max_single_index > 1）的首要污染物"
```

**优点**：
- 不改变现有逻辑
- 符合国标定义

**缺点**：
- 两个指标仍然不一致，容易引起用户困惑

## 推荐方案

**推荐方案1**，理由：
1. 用户更关心超标情况下的首要污染物
2. primary_pollutant_days 与 exceed_details 应该保持一致
3. 避免数据不一致导致的用户困惑

## 影响范围

需要修改的文件：
- `backend/app/tools/query/query_new_standard_report/tool.py`（第1052行）
- `backend/app/tools/query/query_gd_suncere/tool.py`（第2109行，旧标准计算）

## 测试验证

修改后需要验证：
1. primary_pollutant_days 的天数等于或小于 exceed_details 中对应污染物的天数
2. 新旧标准对比时，两个指标的统计口径一致
3. 回归测试：运行历史数据验证统计结果正确性
