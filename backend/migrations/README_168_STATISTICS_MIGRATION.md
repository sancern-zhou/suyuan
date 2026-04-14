# 168城市统计表迁移说明

## 迁移目标

将 `city_168_statistics` 表拆分为两个独立的表：

### 迁移前（当前）
```
city_168_statistics (混合表，包含新旧标准所有字段)
├── comprehensive_index (新标准)
├── comprehensive_index_old (旧标准)
├── comprehensive_index_new_limit_old_algo (新限值+旧算法)
├── comprehensive_index_old_limit_new_algo (旧限值+新算法)
└── ... (所有字段混在一起)
```

### 迁移后（目标）
```
city_168_statistics_old_standard (旧标准表 HJ 633-2013)
├── comprehensive_index_new_algo (新算法综合指数)
├── comprehensive_index_rank_new_algo (新算法排名)
└── comprehensive_index_old_algo (旧算法综合指数)
    └── 注意：旧标准表的字段命名与代码中的不一致，需要调整

city_168_statistics_new_standard (新标准表 HJ 633-2026)
├── comprehensive_index (新标准综合指数)
├── comprehensive_index_rank (新标准排名)
└── comprehensive_index_new_limit_old_algo (新限值+旧算法，用于对比)

city_168_statistics (将被删除或重命名)
```

## 执行步骤

### 步骤1：创建新标准表
```bash
cd /home/xckj/suyuan/backend
sqlcmd -S 180.184.30.94,1433 -U sa -P "#Ph981,6J2bOkWYT7p?5slH$I~g_0itR" -d XcAiDb -i migrations/migrate_168_statistics_to_new_standard.sql
```

### 步骤2：验证数据
```sql
-- 检查新标准表数据量
SELECT COUNT(*) FROM city_168_statistics_new_standard;

-- 检查旧标准表数据量
SELECT COUNT(*) FROM city_168_statistics_old_standard;

-- 检查最新数据
SELECT TOP 5 * FROM city_168_statistics_new_standard
ORDER BY stat_date DESC;
```

### 步骤3：备份数据库（重要！）
```bash
# 备份数据库
sqlcmd -S 180.184.30.94,1433 -U sa -P "YourPassword" -Q "BACKUP DATABASE XcAiDb TO DISK='D:\backup\XcAiDb_backup_20260409.bak' WITH FORMAT;"
```

### 步骤4：删除旧标准字段
```bash
cd /home/xckj/suyuan/backend
sqlcmd -S 180.184.30.94,1433 -U sa -P "#Ph981,6J2bOkWYT7p?5slH$I~g_0itR" -d XcAiDb -i migrations/remove_old_standard_fields.sql
```

### 步骤5：清理工作
```sql
-- 选项A：删除 city_168_statistics 表（如果不需要保留）
-- DROP TABLE dbo.city_168_statistics;

-- 选项B：重命名 city_168_statistics 表（作为备份）
-- EXEC sp_rename 'city_168_statistics', 'city_168_statistics_backup_20260409';
```

## 代码更新

### 需要更新的文件

1. **backend/app/utils/sql_validator.py**
   - 更新表名白名单，添加 `city_168_statistics_new_standard`

2. **backend/app/fetchers/city_statistics/city_statistics_fetcher.py**
   - ✅ 已更新：表名从 `city_168_statistics_new_standard` 改为 `city_168_statistics`（但应该改回来）
   - ⚠️ 需要改回：保持使用 `city_168_statistics_new_standard` 表名

3. **backend/app/tools/planning/complex_query_planner/tool.py**
   - 更新工具描述，说明使用 `city_168_statistics_new_standard` 表
   - 更新查询示例，使用新标准表的字段

### 执行顺序

1. ✅ 创建 SQL 迁移脚本
2. ⏳ 执行迁移脚本
3. ⏳ 验证数据
4. ⏳ 更新代码中的表名
5. ⏳ 删除旧字段
6. ⏳ 测试查询功能

## 数据验证检查清单

- [ ] 新标准表记录数 = 旧标准表记录数（约5040条）
- [ ] 新标准表包含所有必需字段
- [ ] 旧标准表数据完整
- [ ] 查询测试：能够正确查询新标准数据
- [ ] 查询测试：能够正确查询旧标准数据
- [ ] 对比查询：能够正确查询新旧标准对比数据

## 回滚方案

如果迁移失败，执行以下回滚操作：

```sql
-- 1. 删除新标准表（如果已创建）
-- DROP TABLE IF EXISTS dbo.city_168_statistics_new_standard;

-- 2. 恢复备份
-- RESTORE DATABASE XcAiDb FROM DISK='D:\backup\XcAiDb_backup_20260409.bak' WITH REPLACE;
```

## 注意事项

1. **数据备份**：执行迁移前必须备份数据库
2. **停机时间**：建议在业务低峰期执行迁移
3. **代码更新**：迁移完成后需要同步更新代码
4. **测试验证**：迁移完成后需要测试所有查询功能

## 联系人

- 执行人：Claude Code
- 日期：2026-04-09
- 备注：请先在测试环境验证后再在生产环境执行
