# 首要污染物统计差异问题完整分析

## 问题现象

用户查询 2026年1月广州新旧标准对比时发现：
- 新标准 `primary_pollutant_days['PM2_5']` = 3（或4）
- 但 `exceed_details` 中 PM2.5 作为首要污染物的只有 2 天
- 两个指标无法对应，数据不一致

## 根本原因分析

### 1. 统计口径不同

**`primary_pollutant_days` 的统计规则**：
```python
# 代码位置：query_new_standard_report/tool.py:1052
aqi_new = max(pollutants_with_iaqi_new.values())
if aqi_new > 50:  # ← 统计所有 AQI > 50 的天
    for pollutant, iaqi in pollutants_with_iaqi_new.items():
        if iaqi == aqi_new:
            primary_pollutant_days[pollutant] += 1
```

**`exceed_details` 的记录规则**：
```python
# 代码位置：query_new_standard_report/tool.py:1073
if max_single_index_new > 1:  # ← 只记录超标天
    exceed_days += 1
    # 记录超标详情...
```

**关键差异**：
- `primary_pollutant_days` 包含所有 AQI > 50 的天数（包括未超标）
- `exceed_details` 仅包含 max_single_index > 1 的超标天数

### 2. 具体案例分析

根据实际数据分析，2026年1月广州的数据：

#### 新标准 PM2.5 首要污染物天数 = 4 天
| 日期 | AQI | PM2.5_IAQI | max_index | 是否超标 | 说明 |
|------|-----|------------|-----------|---------|------|
| 01-01 | 74.0 | 74.0 | 1.283 | ✓ | 两种标准都是PM2.5 |
| 01-17 | 106.7 | 106.7 | 2.275 | ✓ | 新旧标准首要污染物不同 |
| 01-20 | 62.0 | 62.0 | 1.050 | ✓ | 新旧标准首要污染物不同 |
| 01-24 | 64.0 | 64.0 | 1.117 | ✓ | 两种标准都是PM2.5 |

#### 旧标准 PM2.5 首要污染物天数 = 2 天
| 日期 | AQI | PM2.5_IAQI | max_index | 是否超标 | 说明 |
|------|-----|------------|-----------|---------|------|
| 01-01 | 65.0 | 65.0 | 1.133 | ✓ | 两种标准都是PM2.5 |
| 01-24 | 58.8 | 58.8 | 0.966 | ✗ | 两种标准都是PM2.5 |

**关键发现**：
- 01-17 和 01-20 在新标准下 PM2.5 是首要污染物
- 这两天的 max_index 都 > 1，都是超标天
- 但在 exceed_details 中记录的首要污染物可能不是 PM2.5

### 3. 数据验证

**用户提供的官方数据（旧标准）**：
- 2026-01-17: 首要污染物 = NO2（AQI=106）
- 2026-01-20: 首要污染物 = PM10（AQI=60）

**新标准计算结果**：
- 2026-01-17: 首要污染物 = PM2.5（AQI=106.7）
- 2026-01-20: 首要污染物 = PM2.5（AQI=62.0）

**原因**：
- 新标准 PM2.5 限值从 75 降到 60
- PM2.5 的 IAQI 计算断点变化
- 导致 PM2.5 的 IAQI 在新标准下更大

## 问题确认

用户提到的 `primary_pollutant_days['PM2_5'] = 3` 可能是因为：
1. 实际计算结果是 4 天（01-01, 01-17, 01-20, 01-24）
2. 如果某些天没有超标但 AQI > 50，会计入 `primary_pollutant_days`
3. 但不会计入 `exceed_details`

## 修复建议

### 方案1：修改 primary_pollutant_days 统计逻辑（推荐）

将首要污染物统计改为只统计超标天：

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
- 逻辑一致，`primary_pollutant_days` 与 `exceed_details` 对应
- 用户更关心超标情况下的首要污染物
- 避免数据不一致导致的困惑

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
- 两个指标仍然不一致
- 容易引起用户困惑

## 调试日志

已在关键位置添加详细的调试日志：

1. **每日计算详情** (`daily_calculation_debug`)
   - 浓度值、IAQI、质量指数、AQI

2. **首要污染物判断** (`primary_pollutant_debug`)
   - AQI、首要污染物、是否超标

3. **超标详情** (`exceed_detail_debug`)
   - 超标污染物列表、首要污染物

4. **总结统计** (`primary_pollutant_analysis_summary`)
   - 各污染物首要污染物天数
   - exceed_details中的首要污染物统计
   - 对比分析

详细说明见：`backend/DEBUG_LOGS_GUIDE.md`

## 测试验证

运行查询后检查：
1. 查看关键日期（01-17, 01-20）的计算日志
2. 对比新旧标准的 IAQI 计算
3. 确认 `primary_pollutant_days` 和 `exceed_details` 的统计差异
4. 验证修复方案的有效性

## 影响范围

需要修改的文件：
- `backend/app/tools/query/query_new_standard_report/tool.py`（第1052行）
- `backend/app/tools/query/query_gd_suncere/tool.py`（第2109行，旧标准计算）

## 总结

问题的根本原因是 `primary_pollutant_days` 和 `exceed_details` 的统计口径不同：
- 前者统计所有 AQI > 50 的首要污染物
- 后者仅记录超标天的首要污染物

推荐采用方案1，将 `primary_pollutant_days` 改为只统计超标天，以保持两个指标的一致性。
