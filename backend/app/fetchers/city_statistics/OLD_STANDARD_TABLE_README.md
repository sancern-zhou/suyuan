# 168城市空气质量统计表（旧标准限值版本）

## 概述

本模块提供了基于**HJ 663-2013旧标准限值**的168城市空气质量统计计算和存储功能。

## 两张表架构设计

为了避免重复计算，系统采用两张独立表分别存储新旧标准的综合指数：

### city_168_statistics_new_standard（新标准表）
- **修约规则**：statistical_data规则
  - PM2.5/PM10/SO2/NO2/O3_8h：保留1位小数
  - CO：保留2位小数
- **存储的综合指数（2套）**：
  - `comprehensive_index`：新限值+新算法（PM2.5权重3，NO2/O3权重2）
  - `comprehensive_index_new_limit_old_algo`：新限值+旧算法（所有权重均为1）
- **用途**：按新标准（HJ 663-2026）评价空气质量

### city_168_statistics_old_standard（旧标准表）
- **修约规则**：final_output规则（一般修约规范）
  - CO：保留1位小数
  - PM2.5/SO2/NO2/PM10/O3_8h：取整（保留0位小数）
- **存储的综合指数（2套）**：
  - `comprehensive_index_new_algo`：旧限值+新算法（PM2.5权重3，NO2/O3权重2）
  - `comprehensive_index_old_algo`：旧限值+旧算法（所有权重均为1）
- **用途**：按旧标准（HJ 663-2013）评价空气质量，用于历史数据对比

## 关键计算差异

### 1. 浓度修约示例

假设某城市PM2.5均值为25.67μg/m³，CO百分位数为1.234mg/m³：

| 表名 | PM2.5修约后 | CO修约后 |
|------|------------|---------|
| city_168_statistics_new_standard | 25.7（保留1位） | 1.23（保留2位） |
| city_168_statistics_old_standard | 26（取整） | 1.2（保留1位） |

假设SO2均值为12.34μg/m³：

| 表名 | SO2修约后 |
|------|----------|
| city_168_statistics_new_standard | 12.3（保留1位） |
| city_168_statistics_old_standard | 12（取整） |

### 2. 综合指数计算

使用**修约后的浓度值**计算单项指数和综合指数：

```
单项指数 = 修约后浓度 / 旧限值
综合指数 = Σ(单项指数 × 权重)
```

## 文件说明

### 1. create_old_standard_table.sql
创建`city_168_statistics_old_standard`表的SQL脚本。

**执行方式**：
```bash
# 在SQL Server Management Studio中执行
# 或使用sqlcmd命令
sqlcmd -S 180.184.30.94,1433 -U sa -P "#Ph981,6J2bOkWYT7p?5slH$I~g_0itR" -d XcAiDb -i create_old_standard_table.sql
```

### 2. city_statistics_old_standard_fetcher.py
定期抓取和计算旧标准限值数据的Python脚本。

**核心功能**：
- 从qc_history表查询日数据
- 计算统计浓度（使用final_output修约规则）
- 计算单项指数（使用旧限值）
- 计算2套综合指数（旧限值+新算法、旧限值+旧算法）
- 保存到city_168_statistics_old_standard表
- 自动更新排名

**执行方式**：
```bash
# 进入目录
cd backend/app/fetchers/city_statistics

# 计算月度统计（默认为昨天）
python city_statistics_old_standard_fetcher.py --type monthly

# 计算年度累计
python city_statistics_old_standard_fetcher.py --type annual_ytd

# 计算当月累计
python city_statistics_old_standard_fetcher.py --type current_month

# 指定日期
python city_statistics_old_standard_fetcher.py --date 2024-03-31 --type monthly
```

### 3. batch_update_old_standard_table.py
批量回填历史数据的Python脚本。

**功能**：
- 从city_168_statistics_new_standard表读取现有数据
- 使用final_output规则重新修约浓度
- 使用旧限值重新计算单项指数和综合指数
- 保存到city_168_statistics_old_standard表
- 更新所有排名

**执行方式**：
```bash
# 进入目录
cd backend/app/fetchers/city_statistics

# 执行批量回填
python batch_update_old_standard_table.py
```

**注意事项**：
- 执行前确保city_168_statistics_old_standard表已创建
- 执行时间取决于数据量（约10-30分钟）
- 执行过程中会显示进度

## 修约规则对比

### statistical_data规则（现有表）
```python
ROUNDING_PRECISION = {
    'statistical_data': {
        'PM2_5': 1,      # μg/m³，保留1位
        'PM10': 1,       # μg/m³，保留1位
        'SO2': 1,        # μg/m³，保留1位
        'NO2': 1,        # μg/m³，保留1位
        'O3_8h': 1,      # μg/m³，保留1位
        'CO': 2,         # mg/m³，保留2位
    }
}
```

### final_output规则（新表）
```python
final_output_precision = {
    'PM2_5': 0,      # 取整
    'CO': 1,         # 保留1位小数
    'SO2': 0,        # 取整
    'NO2': 0,        # 取整
    'PM10': 0,       # 取整
    'O3_8h': 0,      # 取整
}
```

## 标准限值和权重

### 旧标准限值（HJ 663-2013）
```python
ANNUAL_STANDARD_LIMITS_2013 = {
    'SO2': 60,
    'NO2': 40,
    'PM10': 70,   # 旧标准
    'PM2_5': 35,  # 旧标准
    'CO': 4,
    'O3_8h': 160
}
```

### 综合指数权重

#### 新算法权重（PM2.5权重3，NO2权重2，O3权重2）
```python
WEIGHTS_NEW_ALGO = {
    'SO2': 1,
    'NO2': 2,
    'PM10': 1,
    'PM2_5': 3,
    'CO': 1,
    'O3_8h': 2
}
```

#### 旧算法权重（所有权重均为1）
```python
WEIGHTS_OLD_ALGO = {
    'SO2': 1,
    'NO2': 1,
    'PM10': 1,
    'PM2_5': 1,
    'CO': 1,
    'O3_8h': 1
}
```

## 数据查询示例

### 查询旧标准限值的综合指数
```sql
-- 查询某城市某月度的旧标准综合指数
SELECT
    stat_date,
    city_name,
    stat_type,
    pm2_5_concentration,  -- 已取整
    so2_concentration,    -- 已取整
    comprehensive_index_new_algo,   -- 旧限值+新算法
    comprehensive_index_old_algo,   -- 旧限值+旧算法
    comprehensive_index_rank_new_algo,
    comprehensive_index_rank_old_algo
FROM city_168_statistics_old_standard
WHERE city_name = N'广州'
  AND stat_type = 'monthly'
  AND stat_date >= '2024-01-01'
ORDER BY stat_date;
```

### 对比新旧表的数据
```sql
-- 对比同一城市新旧标准的综合指数差异
SELECT
    a.stat_date,
    a.city_name,
    a.pm2_5_concentration AS new_standard_pm25,  -- 保留1位小数
    b.pm2_5_concentration AS old_standard_pm25,  -- 取整
    -- 新标准表：新限值
    a.comprehensive_index AS new_limit_new_algo,
    a.comprehensive_index_new_limit_old_algo AS new_limit_old_algo,
    -- 旧标准表：旧限值
    b.comprehensive_index_new_algo AS old_limit_new_algo,
    b.comprehensive_index_old_algo AS old_limit_old_algo
FROM city_168_statistics_new_standard a
INNER JOIN city_168_statistics_old_standard b
    ON a.stat_date = b.stat_date
    AND a.city_name = b.city_name
    AND a.stat_type = b.stat_type
WHERE a.city_name = N'广州'
  AND a.stat_type = 'monthly'
  AND a.stat_date >= '2024-01-01'
ORDER BY a.stat_date;
```

## 定时任务配置

在crontab中添加定时任务（每天上午8点执行）：

```bash
# 编辑crontab
crontab -e

# 添加以下行
0 8 * * * cd /home/xckj/suyuan/backend && python -m app.fetchers.city_statistics.city_statistics_old_standard_fetcher --type monthly >> /var/log/city_old_standard_fetcher.log 2>&1
```

## 注意事项

1. **数据一致性**：确保city_168_statistics_new_standard表的数据已更新到最新日期
2. **执行顺序**：先执行batch_update_old_standard_table.py回填历史数据，再配置定时任务
3. **错误处理**：脚本包含异常处理和日志记录，错误信息会输出到控制台
4. **性能优化**：批量更新时使用事务，每100条记录提交一次

## 联系方式

如有问题，请联系开发团队。
