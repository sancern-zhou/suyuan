# 省级统计旧标准历史数据回填说明

## 概述

省级统计已改造为新旧标准两张表架构：
- `province_statistics_new_standard` - 新标准限值（PM10=60, PM2.5=30）
- `province_statistics_old_standard` - 旧标准限值（PM10=70, PM2.5=35）

## 需要回填的历史数据

### 新标准表（province_statistics_new_standard）
- **数据源**：原 `province_statistics` 表（已重命名）
- **数据范围**：2024年至今的历史数据
- **操作**：删除旧标准字段，保留新限值+新算法、新限值+旧算法两套数据

### 旧标准表（province_statistics_old_standard）
- **数据源**：需要重新计算
- **数据范围**：2024年至今
- **计算方式**：运行 `ProvinceStatisticsOldStandardFetcher`

## 回填步骤

### 1. 执行数据库迁移

```bash
cd /home/xckj/suyuan/backend/migrations
sqlcmd -S 180.184.30.94,1433 -U sa -P "#Ph981,6J2bOkWYT7p?5slH$I~g_0itR" -d XcAiDb -i rename_province_statistics_and_create_old_standard.sql
```

### 2. 回填旧标准历史数据

#### 方法1：使用Python脚本回填

创建回填脚本 `/home/xckj/suyuan/backend/app/fetchers/city_statistics/backfill_province_old_standard.py`:

```python
"""
省级统计旧标准历史数据回填脚本

回填2024年至今的旧标准数据
"""

import asyncio
from datetime import datetime, timedelta
from app.fetchers.city_statistics.province_statistics_old_standard_fetcher import (
    ProvinceStatisticsOldStandardFetcher
)

async def backfill_old_standard():
    """回填旧标准历史数据"""
    fetcher = ProvinceStatisticsOldStandardFetcher()

    # 回填2024年数据
    start_date = datetime(2024, 1, 1).date()
    end_date = datetime(2024, 12, 31).date()

    print(f"开始回填旧标准数据: {start_date} 到 {end_date}")

    current_date = start_date
    while current_date <= end_date:
        # 计算该月的月度数据
        if current_date.day == 1:  # 每月第一天
            month_start = current_date.replace(day=1)
            # 获取该月最后一天
            if current_date.month == 12:
                month_end = current_date.replace(year=current_date.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                month_end = current_date.replace(month=current_date.month + 1, day=1) - timedelta(days=1)

            stat_date = month_start.strftime('%Y-%m-%d')
            print(f"处理月度数据: {stat_date}")

            try:
                await fetcher._run_calculation(
                    month_start.strftime('%Y-%m-%d'),
                    month_end.strftime('%Y-%m-%d'),
                    stat_date,
                    'monthly'
                )
            except Exception as e:
                print(f"处理失败: {stat_date}, 错误: {e}")

        current_date += timedelta(days=1)

    print("旧标准数据回填完成")

if __name__ == '__main__':
    asyncio.run(backfill_old_standard())
```

运行回填脚本：
```bash
cd /home/xckj/suyuan/backend
python -m app.fetchers.city_statistics.backfill_province_old_standard
```

#### 方法2：手动触发单次计算

如果只需要特定月份的数据，可以在Python交互环境中执行：

```python
from app.fetchers.city_statistics.province_statistics_old_standard_fetcher import ProvinceStatisticsOldStandardFetcher
import asyncio

async def calculate_specific_month(year, month):
    fetcher = ProvinceStatisticsOldStandardFetcher()

    # 计算该月的月度数据
    from datetime import datetime
    stat_date = datetime(year, month, 1).strftime('%Y-%m-%d')

    # 获取该月的日期范围
    if month == 12:
        end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = datetime(year, month + 1, 1) - timedelta(days=1)

    start_date = datetime(year, month, 1)

    await fetcher._run_calculation(
        start_date.strftime('%Y-%m-%d'),
        end_date.strftime('%Y-%m-%d'),
        stat_date,
        'monthly'
    )

# 使用示例
asyncio.run(calculate_specific_month(2024, 1))  # 计算2024年1月
asyncio.run(calculate_specific_month(2024, 2))  # 计算2024年2月
# ... 继续其他月份
```

### 3. 验证数据

```sql
-- 检查新标准表数据
SELECT stat_date, stat_type, COUNT(*) as count
FROM province_statistics_new_standard
GROUP BY stat_date, stat_type
ORDER BY stat_date DESC;

-- 检查旧标准表数据
SELECT stat_date, stat_type, COUNT(*) as count
FROM province_statistics_old_standard
GROUP BY stat_date, stat_type
ORDER BY stat_date DESC;

-- 对比同一月份的数据
SELECT
    ns.stat_date,
    ns.province_name,
    ns.comprehensive_index as new_standard_new_algo,
    os.comprehensive_index_new_algo as old_standard_new_algo,
    ns.comprehensive_index_new_limit_old_algo as new_standard_old_algo,
    os.comprehensive_index_old_algo as old_standard_old_algo
FROM province_statistics_new_standard ns
INNER JOIN province_statistics_old_standard os
    ON ns.stat_date = os.stat_date
    AND ns.stat_type = os.stat_type
    AND ns.province_name = os.province_name
WHERE ns.stat_date = '2024-01-01'
ORDER BY ns.province_name;
```

## 注意事项

1. **修约规则差异**：
   - 新标准：浓度统一保留1位小数
   - 旧标准：PM2.5/CO保留1位小数，SO2/NO2/PM10/O3_8h取整

2. **综合指数差异**：
   - 新标准表：新限值+新算法、新限值+旧算法
   - 旧标准表：旧限值+新算法、旧限值+旧算法

3. **调度时间**：
   - 新标准：每天上午8点
   - 旧标准：每天上午8点（与城市统计一致）

4. **数据一致性**：
   - 两张表的省份分组应完全一致
   - city_count 和 city_names 应相同

## 完成后检查清单

- [ ] 数据库迁移脚本执行成功
- [ ] 旧标准表创建成功
- [ ] 新标准表旧字段删除成功
- [ ] 历史数据回填完成
- [ ] 数据验证通过
- [ ] 后端服务重启成功
- [ ] 调度器正常运行
- [ ] 前端显示4个抓取器
