# 旧标准表修约格式修复说明

## 问题描述

旧标准表（`city_168_statistics_old_standard` 和 `province_statistics_old_standard`）的污染物浓度字段返回值带有多余的小数点，例如：
- SO2: `6.0` 而不是 `6`
- NO2: `27.0` 而不是 `27`
- CO: `0.80` 正确（保留1位小数）

## 根本原因

数据库字段类型定义与修约规则不匹配：

### 原字段类型
```sql
so2_concentration  decimal(10, 1)  -- 1位小数
no2_concentration  decimal(10, 1)  -- 1位小数
pm10_concentration decimal(10, 1)  -- 1位小数
pm2_5_concentration decimal(10, 1) -- 1位小数
co_concentration   decimal(10, 2)  -- 2位小数
o3_8h_concentration decimal(10, 1) -- 1位小数
```

### 期望的修约规则（final_output）
```python
SO2/NO2/PM10/PM2.5/O3_8h: 取整（0位小数）
CO: 保留1位小数
```

### 修复后字段类型
```sql
so2_concentration  int              -- 取整
no2_concentration  int              -- 取整
pm10_concentration int              -- 取整
pm2_5_concentration int             -- 取整
co_concentration   decimal(4, 1)    -- 保留1位小数（4位精度足够，最大值<100）
o3_8h_concentration int             -- 取整
```

## 修复方案

### 1. 数据库层面修复（推荐）

**执行步骤**：

```bash
cd backend
python migrations/execute_fix_old_standard_rounding.py
```

**脚本功能**：
- 添加临时字段存储修约后的值
- 将现有数据修约并存储到临时字段
- 删除旧字段
- 重命名新字段
- 验证修复结果

**影响范围**：
- `city_168_statistics_old_standard` 表
- `province_statistics_old_standard` 表

### 2. 代码层面修复

已更新的文件：

1. **`app/fetchers/city_statistics/city_statistics_old_standard_fetcher.py`**
   - 修改 `apply_final_output_rounding()` 函数
   - 取整的污染物返回 `int` 类型而非 `float`
   - CO 返回 `float` 类型（保留1位小数）

2. **`app/fetchers/city_statistics/create_old_standard_table.sql`**
   - 修正字段类型定义
   - CO 从 `decimal(10,1)` 改为 `decimal(4,1)`

3. **`migrations/rename_province_statistics_and_create_old_standard.sql`**
   - 修正省级旧标准表字段类型定义
   - PM2.5 从 `decimal(10,1)` 改为 `int`
   - CO 从 `decimal(10,1)` 改为 `decimal(4,1)`

## 修约规则详解

### 污染物浓度修约规则（final_output）

| 污染物 | 修约规则 | 字段类型 | 示例 |
|--------|----------|----------|------|
| SO2 | 取整 | int | 6 |
| NO2 | 取整 | int | 27 |
| PM10 | 取整 | int | 40 |
| PM2.5 | 取整 | int | 22 |
| CO | 保留1位小数 | decimal(4,1) | 0.8 |
| O3_8h | 取整 | int | 153 |

### 计算逻辑

```python
def apply_final_output_rounding(value: float, pollutant: str):
    """应用最终输出修约规则"""
    precision_map = {
        'PM2_5': 0,  # 取整
        'CO': 1,     # 保留1位小数
        'SO2': 0,    # 取整
        'NO2': 0,    # 取整
        'PM10': 0,   # 取整
        'O3_8h': 0,  # 取整
    }

    precision = precision_map.get(pollutant, 0)
    rounded_value = safe_round(value, precision)

    # 如果精度为0（取整），返回整数类型
    if precision == 0:
        return int(rounded_value)
    else:
        return rounded_value
```

## 验证修复结果

### 查询字段类型

```sql
SELECT
    COLUMN_NAME,
    DATA_TYPE,
    NUMERIC_PRECISION,
    NUMERIC_SCALE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'city_168_statistics_old_standard'
  AND COLUMN_NAME IN ('so2_concentration', 'no2_concentration',
                      'pm10_concentration', 'pm2_5_concentration',
                      'co_concentration', 'o3_8h_concentration')
ORDER BY ORDINAL_POSITION;
```

### 查询示例数据

```sql
SELECT TOP 3
    city_name,
    so2_concentration,
    no2_concentration,
    pm10_concentration,
    pm2_5_concentration,
    co_concentration,
    o3_8h_concentration
FROM city_168_statistics_old_standard
WHERE stat_date LIKE '2025%'
ORDER BY stat_date DESC, city_name;
```

**预期结果**：
```
城市名    SO2  NO2  PM10  PM2.5  CO   O3_8h
广州      6    27   40    22     0.8  153
深圳      7    19   34    17     0.8  141
珠海      6    18   35    19     0.6  148
```

## 注意事项

1. **执行迁移前务必备份数据库**
2. **迁移过程中会锁定表，建议在低峰期执行**
3. **迁移后需要重启相关服务以清除缓存**
4. **新标准表（`city_168_statistics_new_standard`）不受影响**

## 相关文件

- `backend/migrations/fix_old_standard_rounding.sql` - SQL 迁移脚本
- `backend/migrations/execute_fix_old_standard_rounding.py` - Python 执行脚本
- `backend/app/fetchers/city_statistics/city_statistics_old_standard_fetcher.py` - 城市旧标准表 fetcher
- `backend/app/fetchers/city_statistics/province_statistics_old_standard_fetcher.py` - 省级旧标准表 fetcher
- `backend/app/fetchers/city_statistics/create_old_standard_table.sql` - 建表 SQL

## 更新历史

- 2026-04-10: 创建修复脚本和文档
