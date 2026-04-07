# 168城市空气质量统计预计算缓存系统

## 概述

本系统实现了168个重点城市空气质量统计数据的预计算和缓存功能，解决了实时计算排名的性能问题。

### 核心功能

- **自动调度**：每天上午8点自动运行
- **三种统计类型**：
  - `monthly`: 月度统计（完整月数据，每月1日更新）
  - `annual_ytd`: 年度累计（1月至当前月，每天更新）
  - `current_month`: 当月累计（当月1日至当前日，每天更新）
- **HJ663标准**：严格按照HJ663标准计算综合指数和单项指数
- **自动排名**：根据综合指数自动计算城市排名

## 架构设计

### 数据库表结构

表名：`city_168_statistics`（在XcAiDb数据库中）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT | 主键 |
| stat_date | DATE | 统计日期 |
| stat_type | NVARCHAR(20) | 统计类型（monthly/annual_ytd/current_month） |
| city_name | NVARCHAR(50) | 城市名称 |
| city_code | INT | 城市代码 |
| so2_concentration | DECIMAL(10,1) | SO₂浓度 |
| no2_concentration | DECIMAL(10,1) | NO₂浓度 |
| pm10_concentration | DECIMAL(10,1) | PM₁₀浓度 |
| pm2_5_concentration | DECIMAL(10,1) | PM₂.₅浓度 |
| co_concentration | DECIMAL(10,2) | CO浓度 |
| o3_8h_concentration | DECIMAL(10,1) | O₃_8h浓度 |
| so2_index | DECIMAL(10,3) | SO₂单项指数 |
| no2_index | DECIMAL(10,3) | NO₂单项指数 |
| pm10_index | DECIMAL(10,3) | PM₁₀单项指数 |
| pm2_5_index | DECIMAL(10,3) | PM₂.₅单项指数 |
| co_index | DECIMAL(10,3) | CO单项指数 |
| o3_8h_index | DECIMAL(10,3) | O₃_8h单项指数 |
| comprehensive_index | DECIMAL(10,3) | 综合指数 |
| comprehensive_index_rank | INT | 综合指数排名 |
| data_days | INT | 数据天数 |
| sample_coverage | DECIMAL(5,2) | 样本覆盖率（%） |
| region | NVARCHAR(50) | 区域 |
| province | NVARCHAR(50) | 省份 |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

### 索引

- `idx_city_168_date`: stat_date
- `idx_city_168_type`: stat_type
- `idx_city_168_city`: city_name
- `idx_city_168_rank`: comprehensive_index_rank
- `idx_city_168_date_type`: stat_date + stat_type（复合索引）

## 文件结构

```
backend/app/fetchers/city_statistics/
├── __init__.py                      # 模块导出
├── city_statistics_fetcher.py       # 核心抓取器
├── create_table.sql                 # 数据库表创建脚本
├── backfill_2024.py                 # 2024年数据回填脚本
└── README.md                        # 本文档
```

## 安装步骤

### 1. 创建数据库表

```bash
cd backend
sqlcmd -S 180.184.30.94,1433 -U sa -P "#Ph981,6J2bOkWYT7p?5slH$I~g_0itR" -d XcAiDb -i app/fetchers/city_statistics/create_table.sql
```

或在SQL Server Management Studio中直接执行`create_table.sql`脚本。

### 2. 验证表创建

```sql
SELECT * FROM information_schema.tables WHERE table_name = 'city_168_statistics';
```

### 3. 回填历史数据（可选）

如果需要回填2024年数据：

```bash
cd backend
python app/fetchers/city_statistics/backfill_2024.py
```

## 使用方法

### 查询数据

使用`execute_sql_query`工具查询缓存数据：

#### 查询珠三角城市排名（按综合指数）

```sql
SELECT city_name, comprehensive_index, comprehensive_index_rank
FROM city_168_statistics
WHERE stat_type = 'monthly'
  AND stat_date = '2024-03-01'
  AND city_name IN ('广州', '深圳', '珠海', '佛山', '江门', '肇庆', '惠州', '东莞', '中山')
ORDER BY comprehensive_index_rank;
```

#### 查询PM2.5排名前十城市

```sql
SELECT TOP 10 city_name, pm2_5_concentration, comprehensive_index_rank
FROM city_168_statistics
WHERE stat_type = 'monthly'
  AND stat_date = '2024-03-01'
ORDER BY pm2_5_concentration ASC;
```

#### 查询深圳年度累计排名

```sql
SELECT city_name, comprehensive_index, comprehensive_index_rank, data_days
FROM city_168_statistics
WHERE stat_type = 'annual_ytd'
  AND stat_date = '2024-01-01'
  AND city_name = '深圳';
```

### 自动运行

系统会在每天上午8点自动运行，无需手动干预。

查看调度状态：

```python
from app.fetchers import create_scheduler

scheduler = create_scheduler()
status = scheduler.get_status()
print(status)
```

## HJ663标准说明

### 统计方法

| 污染物 | 统计方法 | 标准限值 |
|--------|----------|----------|
| SO₂、NO₂、PM₁₀、PM₂.₅ | 算术平均值 | 60, 40, 60, 30 μg/m³ |
| CO | 日平均第95百分位数 | 4 mg/m³ |
| O₃ | 日最大8小时第90百分位数 | 160 μg/m³ |

### 综合指数计算

```
综合指数 = Σ(单项指数 × 权重)
```

权重配置：
- PM₂.₅: 3
- O₃: 2
- NO₂: 2
- 其他（SO₂、CO、PM₁₀）: 1

### 单项指数计算

```
单项指数 = 污染物浓度 / 标准限值
```

## 168城市名单

### 京津冀及周边地区（38个）
北京、天津、河北（9个）、山东（13个）、河南（14个）

### 长三角地区（31个）
上海、江苏（13个）、浙江（6个）、安徽（11个）

### 汾渭平原（13个）
山西（8个）、陕西（5个）

### 成渝地区（16个）
重庆、四川（15个）

### 长江中游城市群（21个）
湖北（10个）、江西（5个）、湖南（6个）

### 珠三角地区（9个）
广州、深圳、珠海、佛山、江门、肇庆、惠州、东莞、中山

### 其他重点城市（40个）
涉及河北、山西、内蒙古、辽宁、吉林、黑龙江、浙江、安徽、湖北、福建、广西、海南、贵州、云南、西藏、甘肃、青海、宁夏、新疆等省份

## 性能优化

### 查询性能

- 使用复合索引`(stat_date, stat_type)`优化常用查询
- 排名查询使用`comprehensive_index_rank`索引
- 预计算避免实时计算168个城市的数据

### 存储优化

- 每月约168条记录（monthly）
- 每年约2,016条记录（168城市 × 12月）
- 数据库空间占用：约1MB/年

## 维护说明

### 日志监控

查看Fetcher运行日志：

```python
import structlog
logger = structlog.get_logger()
```

日志关键字：
- `city_statistics_fetcher_started`
- `city_statistics_fetcher_completed`
- `monthly_statistics_completed`
- `annual_ytd_statistics_completed`
- `current_month_statistics_completed`

### 数据验证

验证数据完整性：

```sql
-- 检查每月记录数
SELECT stat_date, stat_type, COUNT(*) as count
FROM city_168_statistics
GROUP BY stat_date, stat_type
ORDER BY stat_date DESC;

-- 检查排名连续性
SELECT stat_date, stat_type, MIN(comprehensive_index_rank) as min_rank,
       MAX(comprehensive_index_rank) as max_rank,
       COUNT(*) as city_count
FROM city_168_statistics
WHERE comprehensive_index_rank IS NOT NULL
GROUP BY stat_date, stat_type
ORDER BY stat_date DESC;
```

### 重新计算

如需重新计算某月数据：

```sql
-- 删除旧数据
DELETE FROM city_168_statistics
WHERE stat_type = 'monthly'
  AND stat_date = '2024-03-01';

-- 运行Fetcher重新计算
from app.fetchers import create_scheduler

scheduler = create_scheduler()
fetcher = scheduler.get_fetcher('city_168_statistics_fetcher')
await fetcher.run_now()
```

## 故障排查

### 常见问题

1. **表不存在**
   - 检查表是否创建：`SELECT * FROM information_schema.tables WHERE table_name = 'city_168_statistics'`
   - 重新执行`create_table.sql`

2. **数据不更新**
   - 检查调度器是否运行：`scheduler.is_running()`
   - 查看Fetcher日志

3. **排名不连续**
   - 检查是否有城市数据缺失
   - 验证综合指数是否为NULL

4. **SQL查询失败**
   - 检查`sql_validator.py`中是否添加了`city_168_statistics`到白名单
   - 验证表名拼写

## 联系方式

如有问题，请联系开发团队。

---

**版本**: 1.0.0
**更新日期**: 2026-04-05
**作者**: Claude Code
