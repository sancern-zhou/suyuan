# stat_type 字段重命名文档

## 重命名原因

原命名对LLM不够直观，容易产生歧义：
- `cumulative_month` + `2026-02` 可能被误解为"2月的累计数据"
- 实际含义是"年初至2月的累计"（1-2月）

## 新命名规则

| 旧 stat_type | 新 stat_type | 说明 |
|--------------|--------------|------|
| `cumulative_month` | `ytd_to_month` | 年初到某月的累计（Year-To-Date to Month） |
| `current_month` | `month_current` | 当月累计（进行中） |
| `monthly` | `month_complete` | 完整月数据（已结束） |
| `annual_ytd` | `year_to_date` | 年初至今累计 |

## 命名优势

### 1. 清晰表达时间范围
```
ytd_to_month + stat_date='2026-02'  → 年初至2月累计（1-2月）
month_current + stat_date='2026-04' → 4月当月累计（4月）
month_complete + stat_date='2026-03' → 3月完整月（3月）
year_to_date + stat_date='2026'      → 年初至今（1-4月）
```

### 2. LLM更容易理解
- `ytd` 明确表达"年初至今"（Year-To-Date）
- `month_current` vs `month_complete` 明确区分"进行中"和"已完成"
- `year_to_date` 比较口语化，LLM理解更准确

### 3. 消除歧义
```
旧命名：
  cumulative_month + 2026-02  → 可能误解为"2月的累计"
新命名：
  ytd_to_month + 2026-02      → 明确表达"年初到2月的累计"
```

## 数据示例（2026年4月时）

| stat_type | stat_date | 时间范围 | 含义 |
|-----------|-----------|----------|------|
| `ytd_to_month` | `2026-01` | 1月1日-1月31日 | 年初至1月累计 |
| `ytd_to_month` | `2026-02` | 1月1日-2月28日 | 年初至2月累计 |
| `ytd_to_month` | `2026-03` | 1月1日-3月31日 | 年初至3月累计 |
| `month_current` | `2026-04` | 4月1日-至今 | 4月当月累计（进行中） |
| `year_to_date` | `2026` | 1月1日-至今 | 年初至今累计 |
| `month_complete` | `2026-03` | 3月完整月 | 3月完整月数据 |

## 修改的文件

1. `backend/app/fetchers/city_statistics/city_statistics_fetcher.py`
2. `backend/app/fetchers/city_statistics/province_statistics_fetcher.py`
3. `backend/manual_update_2026_statistics.py`
4. `backend/clear_all_statistics.py`
5. `backend/clear_all_statistics.sql`

## 数据库迁移

### 清除旧数据
```bash
python backend/clear_all_statistics.py
```

### 重新计算数据
```bash
python backend/manual_update_2026_statistics.py
```

## 兼容性说明

**破坏性更新**：此重命名不兼容旧数据，需要：
1. 清除表中所有数据
2. 重新计算所有统计数据

## LLM工具提示词更新

建议在相关工具的系统提示词中添加：

```markdown
## 省份/城市统计数据表字段说明

**stat_type（统计类型）**：
- `ytd_to_month`: 年初到某月的累计（Year-To-Date to Month）
  - stat_date='2026-01' → 2026年年初至1月累计（1月1日-1月31日）
  - stat_date='2026-02' → 2026年年初至2月累计（1月1日-2月28日）
  - stat_date='2026-03' → 2026年年初至3月累计（1月1日-3月31日）

- `month_current`: 当月累计（进行中）
  - stat_date='2026-04' → 2026年4月当月累计（4月1日-至今）

- `year_to_date`: 年初至今累计
  - stat_date='2026' → 2026年年初至今累计（1月1日-至今）

- `month_complete`: 完整月数据（已结束）
  - stat_date='2026-03' → 2026年3月完整月（3月1日-3月31日）
```

## 作者

Claude Code
日期：2026-04-18
版本：1.0.0
